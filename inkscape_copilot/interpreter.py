from __future__ import annotations

import re

from .schema import Action


class PromptError(ValueError):
    """Raised when a prompt cannot be translated safely."""


NAMED_COLORS = {
    "red": "#ef4444",
    "orange": "#f97316",
    "yellow": "#eab308",
    "green": "#22c55e",
    "blue": "#2563eb",
    "navy": "#1e3a8a",
    "purple": "#7c3aed",
    "pink": "#ec4899",
    "black": "#111827",
    "white": "#ffffff",
    "gray": "#6b7280",
    "grey": "#6b7280",
}


def _normalize(prompt: str) -> str:
    return " ".join(prompt.strip().lower().split())


def _extract_fill_color(prompt: str) -> str | None:
    hex_match = re.search(r"(?:fill|color|colour|recolor|recolour|make).*?(#[0-9a-f]{6})", prompt)
    if hex_match:
        return hex_match.group(1)

    named_match = re.search(
        r"(?:make|set|change|recolor|recolour)\s+(?:the\s+)?selection(?:\s+fill)?\s+(?:to\s+)?([a-z]+)",
        prompt,
    )
    if named_match:
        return NAMED_COLORS.get(named_match.group(1))

    fill_named_match = re.search(r"set\s+(?:the\s+)?fill\s+to\s+([a-z]+)", prompt)
    if fill_named_match:
        return NAMED_COLORS.get(fill_named_match.group(1))

    return None


def _extract_stroke_color(prompt: str) -> str | None:
    hex_match = re.search(r"(?:stroke|outline).*?(#[0-9a-f]{6})", prompt)
    if hex_match:
        return hex_match.group(1)

    named_match = re.search(r"set\s+(?:the\s+)?(?:stroke|outline)\s+to\s+([a-z]+)", prompt)
    if named_match:
        return NAMED_COLORS.get(named_match.group(1))

    return None


def _extract_move(prompt: str) -> tuple[float, float] | None:
    match = re.search(
        r"move\s+(?:the\s+)?selection\s+(\d+(?:\.\d+)?)\s*(?:px|pixels?)?\s*(left|right|up|down)",
        prompt,
    )
    if not match:
        return None

    distance = float(match.group(1))
    direction = match.group(2)
    if direction == "left":
        return -distance, 0.0
    if direction == "right":
        return distance, 0.0
    if direction == "up":
        return 0.0, -distance
    return 0.0, distance


def _extract_scale(prompt: str) -> float | None:
    match = re.search(
        r"scale\s+(?:the\s+)?selection\s+(?:to\s+)?(\d+(?:\.\d+)?)\s*(?:%|percent)?",
        prompt,
    )
    if not match:
        return None
    return float(match.group(1))


def _extract_relative_scale(prompt: str) -> float | None:
    smaller_match = re.search(r"make\s+(?:the\s+)?(?:selection|text|it)\s+smaller", prompt)
    if smaller_match:
        return 80.0

    larger_match = re.search(r"make\s+(?:the\s+)?(?:selection|text|it)\s+(?:larger|bigger)", prompt)
    if larger_match:
        return 125.0

    return None


def _extract_rotate(prompt: str) -> float | None:
    match = re.search(
        r"rotate\s+(?:the\s+)?selection\s+(-?\d+(?:\.\d+)?)\s*(?:deg|degree|degrees)?",
        prompt,
    )
    if not match:
        return None
    return float(match.group(1))


def _extract_opacity(prompt: str) -> float | None:
    match = re.search(
        r"(?:set\s+)?(?:the\s+)?(?:selection\s+)?opacity\s+(?:to\s+)?(\d+(?:\.\d+)?)\s*(?:%|percent)?",
        prompt,
    )
    if not match:
        return None
    return float(match.group(1))


def _extract_stroke_width(prompt: str) -> float | None:
    match = re.search(
        r"set\s+(?:the\s+)?stroke\s+width\s+to\s+(\d+(?:\.\d+)?)\s*(?:px|pixels?)?",
        prompt,
    )
    if not match:
        return None
    return float(match.group(1))


def _extract_font_size(prompt: str) -> float | None:
    match = re.search(
        r"(?:set|change|make)\s+(?:the\s+)?(?:text\s+)?font\s+size\s+(?:to\s+)?(\d+(?:\.\d+)?)\s*(?:px|pixels?)?",
        prompt,
    )
    if not match:
        return None
    return float(match.group(1))


def _extract_resize(prompt: str) -> tuple[float | None, float | None] | None:
    match = re.search(
        r"(?:resize|set\s+(?:the\s+)??size\s+of)\s+(?:the\s+)?selection\s+(?:to\s+)?(\d+(?:\.\d+)?)\s*(?:x|by)\s*(\d+(?:\.\d+)?)",
        prompt,
    )
    if match:
        return float(match.group(1)), float(match.group(2))

    width_match = re.search(
        r"set\s+(?:the\s+)?selection\s+width\s+(?:to\s+)?(\d+(?:\.\d+)?)\s*(?:px|pixels?)?",
        prompt,
    )
    height_match = re.search(
        r"set\s+(?:the\s+)?selection\s+height\s+(?:to\s+)?(\d+(?:\.\d+)?)\s*(?:px|pixels?)?",
        prompt,
    )
    if width_match or height_match:
        width = float(width_match.group(1)) if width_match else None
        height = float(height_match.group(1)) if height_match else None
        return width, height

    return None


def _extract_create_text(prompt: str) -> dict[str, float | str] | None:
    quoted = re.search(
        r"(?:write|add|create|insert)\s+text\s+[\"“](.+?)[\"”](?:.*?\bat\s+(\d+(?:\.\d+)?)\s*(?:,|x)\s*(\d+(?:\.\d+)?))?(?:.*?\bsize\s+(\d+(?:\.\d+)?))?",
        prompt,
    )
    if quoted:
        text = quoted.group(1).strip()
        x = float(quoted.group(2)) if quoted.group(2) else 20.0
        y = float(quoted.group(3)) if quoted.group(3) else 32.0
        font_size_px = float(quoted.group(4)) if quoted.group(4) else 24.0
        return {"text": text, "x": x, "y": y, "font_size_px": font_size_px}

    unquoted = re.search(
        r"(?:write|add|create|insert)\s+text\s+(.+?)(?:\s+at\s+(\d+(?:\.\d+)?)\s*(?:,|x)\s*(\d+(?:\.\d+)?))?(?:\s+size\s+(\d+(?:\.\d+)?))?$",
        prompt,
    )
    if not unquoted:
        return None

    text = unquoted.group(1).strip().strip("\"' ")
    if not text:
        return None
    x = float(unquoted.group(2)) if unquoted.group(2) else 20.0
    y = float(unquoted.group(3)) if unquoted.group(3) else 32.0
    font_size_px = float(unquoted.group(4)) if unquoted.group(4) else 24.0
    return {"text": text, "x": x, "y": y, "font_size_px": font_size_px}


def _extract_duplicate(prompt: str) -> tuple[int, float, float] | None:
    if "duplicate" not in prompt and "copy" not in prompt:
        return None

    direction_match = re.search(
        r"(?:duplicate|copy)\s+(?:the\s+)?selection(?:\s+(\d+)\s+times?)?(?:.*?(\d+(?:\.\d+)?)\s*(?:px|pixels?)?\s*(left|right|up|down))?",
        prompt,
    )
    if not direction_match:
        return None

    count = int(direction_match.group(1)) if direction_match.group(1) else 1
    distance = float(direction_match.group(2)) if direction_match.group(2) else 24.0
    direction = direction_match.group(3) or "right"
    if direction == "left":
        return count, -distance, 0.0
    if direction == "right":
        return count, distance, 0.0
    if direction == "up":
        return count, 0.0, -distance
    return count, 0.0, distance


def _extract_rename(prompt: str) -> str | None:
    match = re.search(
        r"rename\s+(?:the\s+)?selection\s+(?:with\s+prefix|to\s+prefix)\s+([a-z0-9_-]+)",
        prompt,
    )
    if not match:
        return None
    return match.group(1)


def _extract_cleanup(prompt: str) -> bool:
    return bool(
        re.search(
            r"\b(clean\s*up|cleanup|polish|make\s+it\s+nice|make\s+it\s+better|make\s+it\s+clean|action\s+is\s+okay|looks?\s+okay|go\s+ahead)\b",
            prompt,
        )
    )


def interpret_prompt(prompt: str) -> list[Action]:
    normalized = _normalize(prompt)
    if not normalized:
        raise PromptError("Prompt is empty.")

    stroke_color = _extract_stroke_color(normalized)
    if stroke_color:
        return [Action(kind="set_stroke_color", params={"hex": stroke_color})]

    fill_color = _extract_fill_color(normalized)
    if fill_color:
        return [Action(kind="set_fill_color", params={"hex": fill_color})]

    move = _extract_move(normalized)
    if move:
        delta_x, delta_y = move
        return [Action(kind="move_selection", params={"delta_x_px": delta_x, "delta_y_px": delta_y})]

    duplicate = _extract_duplicate(normalized)
    if duplicate:
        count, delta_x, delta_y = duplicate
        return [Action(kind="duplicate_selection", params={"count": count, "delta_x_px": delta_x, "delta_y_px": delta_y})]

    scale = _extract_scale(normalized)
    if scale is not None:
        if scale <= 0:
            raise PromptError("Scale percent must be greater than zero.")
        return [Action(kind="scale_selection", params={"percent": scale})]

    relative_scale = _extract_relative_scale(normalized)
    if relative_scale is not None:
        return [Action(kind="scale_selection", params={"percent": relative_scale})]

    rotate = _extract_rotate(normalized)
    if rotate is not None:
        return [Action(kind="rotate_selection", params={"degrees": rotate})]

    opacity = _extract_opacity(normalized)
    if opacity is not None:
        return [Action(kind="set_opacity", params={"opacity_percent": opacity})]

    stroke_width = _extract_stroke_width(normalized)
    if stroke_width is not None:
        return [Action(kind="set_stroke_width", params={"stroke_width_px": stroke_width})]

    font_size = _extract_font_size(normalized)
    if font_size is not None:
        if font_size <= 0:
            raise PromptError("Font size must be greater than zero.")
        return [Action(kind="set_font_size", params={"font_size_px": font_size})]

    resize = _extract_resize(normalized)
    if resize is not None:
        width, height = resize
        if width is not None and width <= 0:
            raise PromptError("Resize width must be greater than zero.")
        if height is not None and height <= 0:
            raise PromptError("Resize height must be greater than zero.")
        return [Action(kind="resize_selection", params={"width": width, "height": height})]

    rename_prefix = _extract_rename(normalized)
    if rename_prefix:
        return [Action(kind="rename_selection", params={"prefix": rename_prefix})]

    if _extract_cleanup(normalized):
        return [
            Action(kind="set_fill_color", params={"hex": "#374151"}),
            Action(kind="set_stroke_width", params={"stroke_width_px": 0.0}),
        ]

    create_text = _extract_create_text(prompt.strip())
    if create_text:
        fill_hex = _extract_fill_color(normalized)
        return [
            Action(
                kind="create_text",
                params={
                    "text": create_text["text"],
                    "x": create_text["x"],
                    "y": create_text["y"],
                    "font_size_px": create_text["font_size_px"],
                    "fill_hex": fill_hex or "#111827",
                },
            )
        ]

    raise PromptError(
        "I could not translate that prompt safely. Try fill color, stroke color, move, duplicate, scale, resize, rotate, opacity, stroke width, font size, rename, or create text."
    )
