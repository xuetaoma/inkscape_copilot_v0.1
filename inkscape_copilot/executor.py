from __future__ import annotations

import re
from math import atan2, cos, pi, sin

import inkex
from inkex import Circle, PathElement, Rectangle, Transform

from .schema import ActionPlan


def _set_style_value(node: inkex.BaseElement, key: str, value: str) -> None:
    style = dict(node.style)
    style[key] = value
    node.style = style


def _clean_text(value: str) -> str:
    cleaned = "".join(char if char >= " " or char in "\n\t" else "" for char in value)
    return cleaned.replace("SiO/Si", "SiO2/Si")


def _tag_name(node: inkex.BaseElement) -> str:
    return str(node.tag).split("}")[-1].lower()


def _node_text(node: inkex.BaseElement) -> str:
    parts: list[str] = []
    try:
        if node.text:
            parts.append(str(node.text))
        for descendant in node.iterdescendants():
            if descendant.text:
                parts.append(str(descendant.text))
    except Exception:
        return ""
    return " ".join(" ".join(parts).split())


def _find_node_by_id(svg: inkex.SvgDocumentElement, object_id: str) -> inkex.BaseElement | None:
    try:
        matches = svg.xpath(f'//*[@id="{object_id}"]')
        if matches:
            return matches[0]
    except Exception:
        pass
    try:
        for node in svg.iterdescendants():
            if node.get("id") == object_id:
                return node
    except Exception:
        return None
    return None


def _find_node_by_text(svg: inkex.SvgDocumentElement, text: str) -> inkex.BaseElement | None:
    needle = " ".join(text.lower().split())
    if not needle:
        return None
    matches: list[inkex.BaseElement] = []
    try:
        for node in svg.iterdescendants():
            if _tag_name(node) not in {"text", "tspan", "g"}:
                continue
            haystack = _node_text(node).lower()
            if needle and needle in haystack:
                matches.append(node)
    except Exception:
        return None
    return matches[-1] if matches else None


def _target_nodes(svg: inkex.SvgDocumentElement, params: dict) -> list[inkex.BaseElement]:
    node = None
    object_id = params.get("object_id")
    if isinstance(object_id, str) and object_id.strip():
        node = _find_node_by_id(svg, object_id.strip())
    if node is None:
        text = params.get("text")
        if isinstance(text, str) and text.strip():
            node = _find_node_by_text(svg, text.strip())
    if node is None:
        raise inkex.AbortExtension("Could not find the requested existing object.")
    return [node]


def _replace_text(nodes: list[inkex.BaseElement], new_text: str) -> None:
    for node in nodes:
        if _tag_name(node) == "text":
            node.text = _clean_text(new_text)
            for descendant in node.iterdescendants():
                descendant.text = None
            continue
        for descendant in node.iterdescendants():
            if _tag_name(descendant) in {"text", "tspan"}:
                descendant.text = _clean_text(new_text)
                return
        raise inkex.AbortExtension("Target object does not contain editable text.")


def _delete_nodes(nodes: list[inkex.BaseElement]) -> None:
    for node in nodes:
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)


def _set_document_size(svg: inkex.SvgDocumentElement, width: float, height: float) -> None:
    if width <= 0 or height <= 0:
        raise inkex.AbortExtension("Document size must be greater than zero.")
    svg.set("width", f"{width}px")
    svg.set("height", f"{height}px")
    svg.set("viewBox", f"0 0 {width} {height}")


def _apply_stroke_style(
    node: inkex.BaseElement,
    *,
    stroke_hex: str | None,
    stroke_width_px: float | None,
    dash_pattern: str | None = None,
) -> None:
    node.style["stroke"] = stroke_hex or "none"
    if stroke_width_px is not None:
        node.style["stroke-width"] = str(max(0.0, stroke_width_px))
    if dash_pattern:
        node.style["stroke-dasharray"] = dash_pattern


def _rename_selected(nodes: list[inkex.BaseElement], prefix: str) -> None:
    for index, node in enumerate(nodes, start=1):
        node.set("id", f"{prefix}-{index}")


def _move_selected(nodes: list[inkex.BaseElement], delta_x: float, delta_y: float) -> None:
    for node in nodes:
        node.transform = Transform(f"translate({delta_x}, {delta_y})") @ node.transform


def _scale_selected(nodes: list[inkex.BaseElement], percent: float) -> None:
    factor = percent / 100.0
    for node in nodes:
        bbox = node.bounding_box()
        center_x = bbox.left + (bbox.width / 2.0)
        center_y = bbox.top + (bbox.height / 2.0)
        transform = Transform(
            f"translate({center_x}, {center_y}) scale({factor}) translate({-center_x}, {-center_y})"
        )
        node.transform = transform @ node.transform


def _resize_selected(nodes: list[inkex.BaseElement], width: float | None, height: float | None) -> None:
    for node in nodes:
        bbox = node.bounding_box()
        current_width = float(bbox.width)
        current_height = float(bbox.height)
        if current_width <= 0 or current_height <= 0:
            raise inkex.AbortExtension("Cannot resize an object with zero width or height.")

        target_width = float(width) if width is not None else None
        target_height = float(height) if height is not None else None

        if target_width is None and target_height is None:
            raise inkex.AbortExtension("Resize requires a target width or height.")
        if target_width is not None and target_width <= 0:
            raise inkex.AbortExtension("Resize width must be greater than zero.")
        if target_height is not None and target_height <= 0:
            raise inkex.AbortExtension("Resize height must be greater than zero.")

        scale_x = (target_width / current_width) if target_width is not None else None
        scale_y = (target_height / current_height) if target_height is not None else None

        if scale_x is None:
            scale_x = scale_y
        if scale_y is None:
            scale_y = scale_x

        center_x = bbox.left + (bbox.width / 2.0)
        center_y = bbox.top + (bbox.height / 2.0)
        transform = Transform(
            f"translate({center_x}, {center_y}) scale({scale_x}, {scale_y}) translate({-center_x}, {-center_y})"
        )
        node.transform = transform @ node.transform


def _rotate_selected(nodes: list[inkex.BaseElement], degrees: float) -> None:
    for node in nodes:
        bbox = node.bounding_box()
        center_x = bbox.left + (bbox.width / 2.0)
        center_y = bbox.top + (bbox.height / 2.0)
        transform = Transform().add_rotate(degrees, center_x, center_y)
        node.transform = transform @ node.transform


def _set_opacity(nodes: list[inkex.BaseElement], opacity_percent: float) -> None:
    clamped = max(0.0, min(100.0, opacity_percent)) / 100.0
    for node in nodes:
        _set_style_value(node, "opacity", str(clamped))


def _set_stroke_width(nodes: list[inkex.BaseElement], stroke_width_px: float) -> None:
    for node in nodes:
        _set_style_value(node, "stroke-width", str(max(0.0, stroke_width_px)))


def _set_font_size(nodes: list[inkex.BaseElement], font_size_px: float) -> None:
    if font_size_px <= 0:
        raise inkex.AbortExtension("Font size must be greater than zero.")
    for node in nodes:
        _set_style_value(node, "font-size", f"{font_size_px}px")


def _set_corner_radius(nodes: list[inkex.BaseElement], corner_radius: float) -> None:
    radius = max(0.0, corner_radius)
    for node in nodes:
        node.set("rx", str(radius))
        node.set("ry", str(radius))


def _set_dash_pattern(nodes: list[inkex.BaseElement], dash_pattern: str) -> None:
    for node in nodes:
        _set_style_value(node, "stroke-dasharray", dash_pattern)


def _set_z_order(nodes: list[inkex.BaseElement], order: str) -> list[inkex.BaseElement]:
    for node in nodes:
        parent = node.getparent()
        if parent is None:
            continue
        if order == "front":
            parent.remove(node)
            parent.append(node)
        elif order == "back":
            parent.remove(node)
            parent.insert(0, node)
        elif order == "raise":
            next_node = node.getnext()
            if next_node is not None:
                next_node.addnext(node)
        elif order == "lower":
            previous_node = node.getprevious()
            if previous_node is not None:
                previous_node.addprevious(node)
    return nodes


def _duplicate_selected(
    nodes: list[inkex.BaseElement],
    count: int,
    delta_x: float,
    delta_y: float,
) -> list[inkex.BaseElement]:
    duplicates: list[inkex.BaseElement] = []
    for copy_index in range(max(1, count)):
        multiplier = copy_index + 1
        for node in nodes:
            duplicate = node.copy()
            node.addnext(duplicate)
            duplicate.transform = Transform(
                f"translate({delta_x * multiplier}, {delta_y * multiplier})"
            ) @ duplicate.transform
            duplicates.append(duplicate)
    return duplicates


def _create_rectangle(
    layer: inkex.BaseElement,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    fill_hex: str | None,
    stroke_hex: str | None,
    stroke_width_px: float | None,
    dash_pattern: str | None = None,
) -> inkex.BaseElement:
    rect = layer.add(Rectangle.new(x, y, width, height))
    rect.style["fill"] = fill_hex or "#2563eb"
    _apply_stroke_style(rect, stroke_hex=stroke_hex, stroke_width_px=stroke_width_px, dash_pattern=dash_pattern)
    return rect


def _create_rounded_rectangle(
    layer: inkex.BaseElement,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    corner_radius: float,
    fill_hex: str | None,
    stroke_hex: str | None,
    stroke_width_px: float | None,
    dash_pattern: str | None,
) -> inkex.BaseElement:
    rect = _create_rectangle(
        layer,
        x=x,
        y=y,
        width=width,
        height=height,
        fill_hex=fill_hex,
        stroke_hex=stroke_hex,
        stroke_width_px=stroke_width_px,
        dash_pattern=dash_pattern,
    )
    rect.set("rx", str(max(0.0, corner_radius)))
    rect.set("ry", str(max(0.0, corner_radius)))
    return rect


def _create_circle(
    layer: inkex.BaseElement,
    *,
    cx: float,
    cy: float,
    radius: float,
    fill_hex: str | None,
    stroke_hex: str | None,
    stroke_width_px: float | None,
) -> inkex.BaseElement:
    circle = layer.add(Circle.new((cx, cy), radius))
    circle.style["fill"] = fill_hex or "#2563eb"
    circle.style["stroke"] = stroke_hex or "none"
    if stroke_width_px is not None:
        circle.style["stroke-width"] = str(max(0.0, stroke_width_px))
    return circle


def _create_ellipse(
    layer: inkex.BaseElement,
    *,
    cx: float,
    cy: float,
    width: float,
    height: float,
    fill_hex: str | None,
    stroke_hex: str | None,
    stroke_width_px: float | None,
) -> inkex.BaseElement:
    rx = width / 2.0
    ry = height / 2.0
    ellipse = layer.add(PathElement())
    ellipse.set("d", f"M {cx - rx},{cy} A {rx},{ry} 0 1 0 {cx + rx},{cy} A {rx},{ry} 0 1 0 {cx - rx},{cy} Z")
    ellipse.style["fill"] = fill_hex or "#2563eb"
    ellipse.style["stroke"] = stroke_hex or "none"
    if stroke_width_px is not None:
        ellipse.style["stroke-width"] = str(max(0.0, stroke_width_px))
    return ellipse


def _create_repeated_circles(
    layer: inkex.BaseElement,
    *,
    x: float,
    y: float,
    radius: float,
    count: int,
    spacing_x: float,
    spacing_y: float | None,
    fill_hex: str | None,
    stroke_hex: str | None,
    stroke_width_px: float | None,
) -> list[inkex.BaseElement]:
    circles: list[inkex.BaseElement] = []
    for index in range(max(0, count)):
        circle = _create_circle(
            layer,
            cx=x + (index * spacing_x),
            cy=y + (index * (spacing_y or 0.0)),
            radius=radius,
            fill_hex=fill_hex,
            stroke_hex=stroke_hex,
            stroke_width_px=stroke_width_px,
        )
        circles.append(circle)
    return circles


def _regular_polygon_points(cx: float, cy: float, radius: float, count: int, degrees: float) -> list[tuple[float, float]]:
    start = (degrees * pi) / 180.0 - (pi / 2.0)
    step = (2.0 * pi) / count
    return [
        (cx + cos(start + (step * index)) * radius, cy + sin(start + (step * index)) * radius)
        for index in range(count)
    ]


def _create_polygon(
    layer: inkex.BaseElement,
    *,
    cx: float,
    cy: float,
    radius: float,
    count: int,
    degrees: float,
    fill_hex: str | None,
    stroke_hex: str | None,
    stroke_width_px: float | None,
) -> inkex.BaseElement:
    if count < 3:
        raise inkex.AbortExtension("Polygon requires at least 3 sides.")
    points = _regular_polygon_points(cx, cy, radius, count, degrees)
    polygon = layer.add(PathElement())
    polygon.set("d", "M " + " L ".join(f"{x},{y}" for x, y in points) + " Z")
    polygon.style["fill"] = fill_hex or "#2563eb"
    polygon.style["stroke"] = stroke_hex or "none"
    if stroke_width_px is not None:
        polygon.style["stroke-width"] = str(max(0.0, stroke_width_px))
    return polygon


def _create_star(
    layer: inkex.BaseElement,
    *,
    cx: float,
    cy: float,
    radius: float,
    inner_radius: float,
    count: int,
    degrees: float,
    fill_hex: str | None,
    stroke_hex: str | None,
    stroke_width_px: float | None,
) -> inkex.BaseElement:
    if count < 3:
        raise inkex.AbortExtension("Star requires at least 3 points.")
    if inner_radius <= 0 or inner_radius >= radius:
        raise inkex.AbortExtension("Star inner_radius must be greater than zero and smaller than radius.")
    start = (degrees * pi) / 180.0 - (pi / 2.0)
    step = pi / count
    points: list[tuple[float, float]] = []
    for index in range(count * 2):
        current_radius = radius if index % 2 == 0 else inner_radius
        angle = start + (step * index)
        points.append((cx + cos(angle) * current_radius, cy + sin(angle) * current_radius))
    star = layer.add(PathElement())
    star.set("d", "M " + " L ".join(f"{x},{y}" for x, y in points) + " Z")
    star.style["fill"] = fill_hex or "#2563eb"
    star.style["stroke"] = stroke_hex or "none"
    if stroke_width_px is not None:
        star.style["stroke-width"] = str(max(0.0, stroke_width_px))
    return star


def _create_line(
    layer: inkex.BaseElement,
    *,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    stroke_hex: str | None,
    stroke_width_px: float | None,
    dash_pattern: str | None = None,
) -> inkex.BaseElement:
    line = layer.add(inkex.Line.new((x1, y1), (x2, y2)))
    line.style["fill"] = "none"
    _apply_stroke_style(
        line,
        stroke_hex=stroke_hex or "#111827",
        stroke_width_px=stroke_width_px if stroke_width_px is not None else 2.0,
        dash_pattern=dash_pattern,
    )
    return line


def _create_arrow(
    layer: inkex.BaseElement,
    *,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    stroke_hex: str | None,
    stroke_width_px: float | None,
) -> list[inkex.BaseElement]:
    stroke = stroke_hex or "#111827"
    width = stroke_width_px if stroke_width_px is not None else 2.0
    line = _create_line(layer, x1=x1, y1=y1, x2=x2, y2=y2, stroke_hex=stroke, stroke_width_px=width)

    angle = atan2(y2 - y1, x2 - x1)
    head_length = max(6.0, width * 4.0)
    spread = pi / 7.0
    left_x = x2 - head_length * cos(angle - spread)
    left_y = y2 - head_length * sin(angle - spread)
    right_x = x2 - head_length * cos(angle + spread)
    right_y = y2 - head_length * sin(angle + spread)

    left = _create_line(layer, x1=x2, y1=y2, x2=left_x, y2=left_y, stroke_hex=stroke, stroke_width_px=width)
    right = _create_line(layer, x1=x2, y1=y2, x2=right_x, y2=right_y, stroke_hex=stroke, stroke_width_px=width)
    return [line, left, right]


def _create_bracket(
    layer: inkex.BaseElement,
    *,
    x: float,
    y1: float,
    y2: float,
    width: float,
    stroke_hex: str | None,
    stroke_width_px: float | None,
) -> list[inkex.BaseElement]:
    stroke = stroke_hex or "#111827"
    line_width = stroke_width_px if stroke_width_px is not None else 1.5
    return [
        _create_line(layer, x1=x, y1=y1, x2=x, y2=y2, stroke_hex=stroke, stroke_width_px=line_width),
        _create_line(layer, x1=x, y1=y1, x2=x + width, y2=y1, stroke_hex=stroke, stroke_width_px=line_width),
        _create_line(layer, x1=x, y1=y2, x2=x + width, y2=y2, stroke_hex=stroke, stroke_width_px=line_width),
    ]


def _create_text(
    layer: inkex.BaseElement,
    *,
    x: float,
    y: float,
    text: str,
    font_size_px: float,
    fill_hex: str | None,
) -> inkex.BaseElement:
    if font_size_px <= 0:
        raise inkex.AbortExtension("Text font size must be greater than zero.")

    text_node = layer.add(inkex.TextElement())
    text_node.set("x", str(x))
    text_node.set("y", str(y))
    text_node.text = _clean_text(text)
    text_node.style["fill"] = fill_hex or "#111827"
    text_node.style["stroke"] = "none"
    text_node.style["font-size"] = f"{font_size_px}px"
    return text_node


def _create_layer_bar(
    layer: inkex.BaseElement,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    corner_radius: float,
    text: str,
    font_size_px: float,
    fill_hex: str | None,
    stroke_hex: str | None,
    stroke_width_px: float | None,
    text_hex: str | None,
) -> list[inkex.BaseElement]:
    bar = _create_rounded_rectangle(
        layer,
        x=x,
        y=y,
        width=width,
        height=height,
        corner_radius=corner_radius,
        fill_hex=fill_hex or "#9ca3af",
        stroke_hex=stroke_hex,
        stroke_width_px=stroke_width_px,
        dash_pattern=None,
    )
    label = _create_text(
        layer,
        x=x + width / 2.0,
        y=y + height / 2.0 + font_size_px / 3.0,
        text=text,
        font_size_px=font_size_px,
        fill_hex=text_hex or "#111827",
    )
    label.style["text-anchor"] = "middle"
    return [bar, label]


SELECTION_REQUIRED_ACTIONS = {
    "set_fill_none",
    "set_fill_color",
    "set_font_size",
    "set_corner_radius",
    "set_dash_pattern",
    "set_z_order",
    "set_stroke_none",
    "set_stroke_color",
    "set_stroke_width",
    "set_opacity",
    "move_selection",
    "duplicate_selection",
    "resize_selection",
    "scale_selection",
    "rotate_selection",
    "rename_selection",
}


def apply_action_plan(
    svg: inkex.SvgDocumentElement,
    selected: list[inkex.BaseElement],
    plan: ActionPlan,
) -> tuple[list[inkex.BaseElement], str]:
    layer = svg.get_current_layer()

    for action in plan.actions:
        if action.kind == "set_document_size":
            _set_document_size(svg, float(action.params["width"]), float(action.params["height"]))
            continue

        if action.kind in SELECTION_REQUIRED_ACTIONS and not selected:
            raise inkex.AbortExtension(f"Action '{action.kind}' requires at least one selected object.")

        if action.kind == "set_fill_color":
            for node in selected:
                _set_style_value(node, "fill", str(action.params["hex"]))
            continue

        if action.kind == "set_fill_none":
            for node in selected:
                _set_style_value(node, "fill", "none")
            continue

        if action.kind == "set_font_size":
            _set_font_size(selected, float(action.params["font_size_px"]))
            continue

        if action.kind == "set_corner_radius":
            _set_corner_radius(selected, float(action.params["corner_radius"]))
            continue

        if action.kind == "set_dash_pattern":
            _set_dash_pattern(selected, str(action.params["dash_pattern"]))
            continue

        if action.kind == "set_z_order":
            selected = _set_z_order(selected, str(action.params["text"]))
            continue

        if action.kind == "set_stroke_color":
            for node in selected:
                _set_style_value(node, "stroke", str(action.params["hex"]))
            continue

        if action.kind == "set_stroke_none":
            for node in selected:
                _set_style_value(node, "stroke", "none")
            continue

        if action.kind == "set_stroke_width":
            _set_stroke_width(selected, float(action.params["stroke_width_px"]))
            continue

        if action.kind == "set_opacity":
            _set_opacity(selected, float(action.params["opacity_percent"]))
            continue

        if action.kind == "move_selection":
            _move_selected(
                selected,
                float(action.params["delta_x_px"]),
                float(action.params["delta_y_px"]),
            )
            continue

        if action.kind == "duplicate_selection":
            selected = _duplicate_selected(
                selected,
                int(action.params["count"]),
                float(action.params["delta_x_px"]),
                float(action.params["delta_y_px"]),
            )
            continue

        if action.kind == "resize_selection":
            width = action.params.get("width")
            height = action.params.get("height")
            _resize_selected(
                selected,
                float(width) if width is not None else None,
                float(height) if height is not None else None,
            )
            continue

        if action.kind == "scale_selection":
            _scale_selected(selected, float(action.params["percent"]))
            continue

        if action.kind == "rotate_selection":
            _rotate_selected(selected, float(action.params["degrees"]))
            continue

        if action.kind == "rename_selection":
            prefix = str(action.params["prefix"])
            if not re.fullmatch(r"[a-z0-9_-]+", prefix):
                raise inkex.AbortExtension("Rename prefix may only contain lowercase letters, digits, _ or -.")
            _rename_selected(selected, prefix)
            continue

        if action.kind == "select_object":
            selected = _target_nodes(svg, action.params)
            continue

        if action.kind == "delete_object":
            targets = _target_nodes(svg, action.params)
            _delete_nodes(targets)
            selected = []
            continue

        if action.kind == "move_object":
            selected = _target_nodes(svg, action.params)
            _move_selected(
                selected,
                float(action.params["delta_x_px"]),
                float(action.params["delta_y_px"]),
            )
            continue

        if action.kind == "set_object_fill_color":
            selected = _target_nodes(svg, action.params)
            for node in selected:
                _set_style_value(node, "fill", str(action.params["hex"]))
            continue

        if action.kind == "set_object_fill_none":
            selected = _target_nodes(svg, action.params)
            for node in selected:
                _set_style_value(node, "fill", "none")
            continue

        if action.kind == "set_object_stroke_color":
            selected = _target_nodes(svg, action.params)
            for node in selected:
                _set_style_value(node, "stroke", str(action.params["hex"]))
            continue

        if action.kind == "set_object_stroke_none":
            selected = _target_nodes(svg, action.params)
            for node in selected:
                _set_style_value(node, "stroke", "none")
            continue

        if action.kind == "set_object_stroke_width":
            selected = _target_nodes(svg, action.params)
            _set_stroke_width(selected, float(action.params["stroke_width_px"]))
            continue

        if action.kind == "set_object_dash_pattern":
            selected = _target_nodes(svg, action.params)
            _set_dash_pattern(selected, str(action.params["dash_pattern"]))
            continue

        if action.kind == "set_object_font_size":
            selected = _target_nodes(svg, action.params)
            _set_font_size(selected, float(action.params["font_size_px"]))
            continue

        if action.kind == "replace_text":
            selected = _target_nodes(svg, action.params)
            _replace_text(selected, str(action.params["new_text"]))
            continue

        if action.kind == "create_rectangle":
            selected = [
                _create_rectangle(
                    layer,
                    x=float(action.params["x"]),
                    y=float(action.params["y"]),
                    width=float(action.params["width"]),
                    height=float(action.params["height"]),
                    fill_hex=action.params.get("fill_hex"),
                    stroke_hex=action.params.get("stroke_hex"),
                    stroke_width_px=action.params.get("stroke_width_px"),
                    dash_pattern=action.params.get("dash_pattern"),
                )
            ]
            continue

        if action.kind == "create_rounded_rectangle":
            selected = [
                _create_rounded_rectangle(
                    layer,
                    x=float(action.params["x"]),
                    y=float(action.params["y"]),
                    width=float(action.params["width"]),
                    height=float(action.params["height"]),
                    corner_radius=float(action.params.get("corner_radius") or 4.0),
                    fill_hex=action.params.get("fill_hex"),
                    stroke_hex=action.params.get("stroke_hex"),
                    stroke_width_px=action.params.get("stroke_width_px"),
                    dash_pattern=action.params.get("dash_pattern"),
                )
            ]
            continue

        if action.kind == "create_circle":
            selected = [
                _create_circle(
                    layer,
                    cx=float(action.params["cx"]),
                    cy=float(action.params["cy"]),
                    radius=float(action.params["radius"]),
                    fill_hex=action.params.get("fill_hex"),
                    stroke_hex=action.params.get("stroke_hex"),
                    stroke_width_px=action.params.get("stroke_width_px"),
                )
            ]
            continue

        if action.kind == "create_ellipse":
            selected = [
                _create_ellipse(
                    layer,
                    cx=float(action.params["cx"]),
                    cy=float(action.params["cy"]),
                    width=float(action.params["width"]),
                    height=float(action.params["height"]),
                    fill_hex=action.params.get("fill_hex"),
                    stroke_hex=action.params.get("stroke_hex"),
                    stroke_width_px=action.params.get("stroke_width_px"),
                )
            ]
            continue

        if action.kind == "create_repeated_circles":
            selected = _create_repeated_circles(
                layer,
                x=float(action.params["x"]),
                y=float(action.params["y"]),
                radius=float(action.params["radius"]),
                count=int(action.params["count"]),
                spacing_x=float(action.params["spacing_x"]),
                spacing_y=float(action.params["spacing_y"]) if action.params.get("spacing_y") is not None else None,
                fill_hex=action.params.get("fill_hex"),
                stroke_hex=action.params.get("stroke_hex"),
                stroke_width_px=action.params.get("stroke_width_px"),
            )
            continue

        if action.kind == "create_polygon":
            selected = [
                _create_polygon(
                    layer,
                    cx=float(action.params["cx"]),
                    cy=float(action.params["cy"]),
                    radius=float(action.params["radius"]),
                    count=int(action.params["count"]),
                    degrees=float(action.params.get("degrees") or 0.0),
                    fill_hex=action.params.get("fill_hex"),
                    stroke_hex=action.params.get("stroke_hex"),
                    stroke_width_px=action.params.get("stroke_width_px"),
                )
            ]
            continue

        if action.kind == "create_star":
            selected = [
                _create_star(
                    layer,
                    cx=float(action.params["cx"]),
                    cy=float(action.params["cy"]),
                    radius=float(action.params["radius"]),
                    inner_radius=float(action.params["inner_radius"]),
                    count=int(action.params["count"]),
                    degrees=float(action.params.get("degrees") or 0.0),
                    fill_hex=action.params.get("fill_hex"),
                    stroke_hex=action.params.get("stroke_hex"),
                    stroke_width_px=action.params.get("stroke_width_px"),
                )
            ]
            continue

        if action.kind == "create_line":
            selected = [
                _create_line(
                    layer,
                    x1=float(action.params["x1"]),
                    y1=float(action.params["y1"]),
                    x2=float(action.params["x2"]),
                    y2=float(action.params["y2"]),
                    stroke_hex=action.params.get("stroke_hex"),
                    stroke_width_px=action.params.get("stroke_width_px"),
                    dash_pattern=action.params.get("dash_pattern"),
                )
            ]
            continue

        if action.kind == "create_arrow":
            selected = _create_arrow(
                layer,
                x1=float(action.params["x1"]),
                y1=float(action.params["y1"]),
                x2=float(action.params["x2"]),
                y2=float(action.params["y2"]),
                stroke_hex=action.params.get("stroke_hex"),
                stroke_width_px=action.params.get("stroke_width_px"),
            )
            continue

        if action.kind == "create_bracket":
            selected = _create_bracket(
                layer,
                x=float(action.params["x"]),
                y1=float(action.params["y1"]),
                y2=float(action.params["y2"]),
                width=float(action.params["width"]),
                stroke_hex=action.params.get("stroke_hex"),
                stroke_width_px=action.params.get("stroke_width_px"),
            )
            continue

        if action.kind == "create_text":
            selected = [
                _create_text(
                    layer,
                    x=float(action.params["x"]),
                    y=float(action.params["y"]),
                    text=str(action.params["text"]),
                    font_size_px=float(action.params["font_size_px"]),
                    fill_hex=action.params.get("fill_hex"),
                )
            ]
            continue

        if action.kind == "create_layer_bar":
            selected = _create_layer_bar(
                layer,
                x=float(action.params["x"]),
                y=float(action.params["y"]),
                width=float(action.params["width"]),
                height=float(action.params["height"]),
                corner_radius=float(action.params.get("corner_radius") or 3.0),
                text=str(action.params["text"]),
                font_size_px=float(action.params["font_size_px"]),
                fill_hex=action.params.get("fill_hex"),
                stroke_hex=action.params.get("stroke_hex"),
                stroke_width_px=action.params.get("stroke_width_px"),
                text_hex=action.params.get("text_hex"),
            )
            continue

        raise inkex.AbortExtension(f"Unsupported action: {action.kind}")

    return selected, plan.summary
