from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SUPPORTED_ACTION_KINDS = {
    "create_arrow",
    "create_bracket",
    "create_circle",
    "create_ellipse",
    "create_layer_bar",
    "create_line",
    "create_polygon",
    "create_rectangle",
    "create_repeated_circles",
    "create_rounded_rectangle",
    "create_star",
    "create_text",
    "duplicate_selection",
    "rotate_selection",
    "set_fill_none",
    "set_fill_color",
    "set_font_size",
    "set_corner_radius",
    "set_dash_pattern",
    "set_stroke_none",
    "set_z_order",
    "set_opacity",
    "set_stroke_color",
    "set_stroke_width",
    "move_selection",
    "resize_selection",
    "scale_selection",
    "rename_selection",
    "delete_object",
    "move_object",
    "replace_text",
    "select_object",
    "set_object_fill_color",
    "set_object_fill_none",
    "set_object_font_size",
    "set_object_dash_pattern",
    "set_object_stroke_color",
    "set_object_stroke_none",
    "set_object_stroke_width",
    "set_document_size",
}


def _numeric_or_default(params: dict[str, Any], key: str, default: float) -> None:
    if not isinstance(params.get(key), (int, float)):
        params[key] = default


def _string_or_default(params: dict[str, Any], key: str, default: str) -> None:
    if not isinstance(params.get(key), str):
        params[key] = default


@dataclass(frozen=True)
class Action:
    kind: str
    params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "params": self.params}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Action":
        kind = payload.get("kind")
        params = payload.get("params")
        if not isinstance(kind, str) or kind not in SUPPORTED_ACTION_KINDS:
            raise ValueError(f"Unsupported action kind: {kind}")
        if not isinstance(params, dict):
            raise ValueError("Action params must be an object.")
        if kind in {"set_fill_color", "set_stroke_color"}:
            if not isinstance(params.get("hex"), str):
                raise ValueError(f"{kind} requires params.hex")
        elif kind in {"set_fill_none", "set_stroke_none"}:
            pass
        elif kind == "set_font_size":
            if not isinstance(params.get("font_size_px"), (int, float)):
                raise ValueError("set_font_size requires numeric font_size_px")
        elif kind == "set_corner_radius":
            _numeric_or_default(params, "corner_radius", 4.0)
        elif kind == "set_dash_pattern":
            _string_or_default(params, "dash_pattern", "2,2")
        elif kind == "set_z_order":
            if str(params.get("text")) not in {"front", "back", "raise", "lower"}:
                raise ValueError("set_z_order requires params.text to be front, back, raise, or lower")
        elif kind == "set_document_size":
            if not all(isinstance(params.get(key), (int, float)) for key in ("width", "height")):
                raise ValueError("set_document_size requires numeric width and height")
        elif kind == "set_opacity":
            if not isinstance(params.get("opacity_percent"), (int, float)):
                raise ValueError("set_opacity requires numeric opacity_percent")
        elif kind == "set_stroke_width":
            if not isinstance(params.get("stroke_width_px"), (int, float)):
                raise ValueError("set_stroke_width requires numeric stroke_width_px")
        elif kind == "move_selection":
            if not isinstance(params.get("delta_x_px"), (int, float)) or not isinstance(
                params.get("delta_y_px"), (int, float)
            ):
                raise ValueError("move_selection requires numeric delta_x_px and delta_y_px")
        elif kind == "duplicate_selection":
            if not isinstance(params.get("count"), (int, float)):
                raise ValueError("duplicate_selection requires numeric count")
            if not isinstance(params.get("delta_x_px"), (int, float)) or not isinstance(
                params.get("delta_y_px"), (int, float)
            ):
                raise ValueError("duplicate_selection requires numeric delta_x_px and delta_y_px")
        elif kind == "scale_selection":
            if not isinstance(params.get("percent"), (int, float)):
                raise ValueError("scale_selection requires numeric percent")
        elif kind == "resize_selection":
            width = params.get("width")
            height = params.get("height")
            if not isinstance(width, (int, float)) and not isinstance(height, (int, float)):
                raise ValueError("resize_selection requires numeric width and/or height")
        elif kind == "rotate_selection":
            if not isinstance(params.get("degrees"), (int, float)):
                raise ValueError("rotate_selection requires numeric degrees")
        elif kind == "rename_selection":
            if not isinstance(params.get("prefix"), str):
                raise ValueError("rename_selection requires params.prefix")
        elif kind == "select_object":
            if not isinstance(params.get("object_id"), str) and not isinstance(params.get("text"), str):
                raise ValueError("select_object requires params.object_id or params.text")
        elif kind == "delete_object":
            if not isinstance(params.get("object_id"), str) and not isinstance(params.get("text"), str):
                raise ValueError("delete_object requires params.object_id or params.text")
        elif kind == "move_object":
            if not isinstance(params.get("object_id"), str) and not isinstance(params.get("text"), str):
                raise ValueError("move_object requires params.object_id or params.text")
            if not isinstance(params.get("delta_x_px"), (int, float)) or not isinstance(
                params.get("delta_y_px"), (int, float)
            ):
                raise ValueError("move_object requires numeric delta_x_px and delta_y_px")
        elif kind in {"set_object_fill_color", "set_object_stroke_color"}:
            if not isinstance(params.get("object_id"), str) and not isinstance(params.get("text"), str):
                raise ValueError(f"{kind} requires params.object_id or params.text")
            if not isinstance(params.get("hex"), str):
                raise ValueError(f"{kind} requires params.hex")
        elif kind in {"set_object_fill_none", "set_object_stroke_none"}:
            if not isinstance(params.get("object_id"), str) and not isinstance(params.get("text"), str):
                raise ValueError(f"{kind} requires params.object_id or params.text")
        elif kind == "set_object_dash_pattern":
            if not isinstance(params.get("object_id"), str) and not isinstance(params.get("text"), str):
                raise ValueError("set_object_dash_pattern requires params.object_id or params.text")
            _string_or_default(params, "dash_pattern", "2,2")
        elif kind == "set_object_stroke_width":
            if not isinstance(params.get("object_id"), str) and not isinstance(params.get("text"), str):
                raise ValueError("set_object_stroke_width requires params.object_id or params.text")
            if not isinstance(params.get("stroke_width_px"), (int, float)):
                raise ValueError("set_object_stroke_width requires numeric stroke_width_px")
        elif kind == "set_object_font_size":
            if not isinstance(params.get("object_id"), str) and not isinstance(params.get("text"), str):
                raise ValueError("set_object_font_size requires params.object_id or params.text")
            if not isinstance(params.get("font_size_px"), (int, float)):
                raise ValueError("set_object_font_size requires numeric font_size_px")
        elif kind == "replace_text":
            if not isinstance(params.get("object_id"), str) and not isinstance(params.get("text"), str):
                raise ValueError("replace_text requires params.object_id or existing params.text")
            if not isinstance(params.get("new_text"), str) or not params.get("new_text").strip():
                raise ValueError("replace_text requires params.new_text")
        elif kind == "create_rectangle":
            if not all(isinstance(params.get(key), (int, float)) for key in ("x", "y", "width", "height")):
                raise ValueError("create_rectangle requires numeric x, y, width, and height")
        elif kind == "create_rounded_rectangle":
            if not all(isinstance(params.get(key), (int, float)) for key in ("x", "y", "width", "height")):
                raise ValueError("create_rounded_rectangle requires numeric x, y, width, and height")
            _numeric_or_default(params, "corner_radius", 4.0)
        elif kind == "create_circle":
            if not all(isinstance(params.get(key), (int, float)) for key in ("cx", "cy", "radius")):
                raise ValueError("create_circle requires numeric cx, cy, and radius")
        elif kind == "create_ellipse":
            if not all(isinstance(params.get(key), (int, float)) for key in ("cx", "cy", "width", "height")):
                raise ValueError("create_ellipse requires numeric cx, cy, width, and height")
        elif kind == "create_repeated_circles":
            if not all(isinstance(params.get(key), (int, float)) for key in ("x", "y", "radius", "count", "spacing_x")):
                raise ValueError("create_repeated_circles requires numeric x, y, radius, count, and spacing_x")
            _numeric_or_default(params, "spacing_y", 0.0)
        elif kind == "create_polygon":
            if not all(isinstance(params.get(key), (int, float)) for key in ("cx", "cy", "radius", "count")):
                raise ValueError("create_polygon requires numeric cx, cy, radius, and count")
            _numeric_or_default(params, "degrees", 0.0)
        elif kind == "create_star":
            if not all(isinstance(params.get(key), (int, float)) for key in ("cx", "cy", "radius", "inner_radius", "count")):
                raise ValueError("create_star requires numeric cx, cy, radius, inner_radius, and count")
            _numeric_or_default(params, "degrees", 0.0)
        elif kind == "create_line":
            if not all(isinstance(params.get(key), (int, float)) for key in ("x1", "y1", "x2", "y2")):
                raise ValueError("create_line requires numeric x1, y1, x2, and y2")
        elif kind == "create_arrow":
            if not all(isinstance(params.get(key), (int, float)) for key in ("x1", "y1", "x2", "y2")):
                raise ValueError("create_arrow requires numeric x1, y1, x2, and y2")
        elif kind == "create_bracket":
            if not all(isinstance(params.get(key), (int, float)) for key in ("x", "y1", "y2", "width")):
                raise ValueError("create_bracket requires numeric x, y1, y2, and width")
        elif kind == "create_text":
            if not isinstance(params.get("text"), str) or not params.get("text").strip():
                raise ValueError("create_text requires params.text")
            if not all(isinstance(params.get(key), (int, float)) for key in ("x", "y", "font_size_px")):
                raise ValueError("create_text requires numeric x, y, and font_size_px")
        elif kind == "create_layer_bar":
            if not isinstance(params.get("text"), str) or not params.get("text").strip():
                params["text"] = "layer"
            if not all(
                isinstance(params.get(key), (int, float))
                for key in ("x", "y", "width", "height", "font_size_px")
            ):
                raise ValueError("create_layer_bar requires numeric x, y, width, height, and font_size_px")
            _numeric_or_default(params, "corner_radius", 3.0)
        return cls(kind=kind, params=params)


@dataclass(frozen=True)
class ActionPlan:
    summary: str
    actions: list[Action]
    needs_confirmation: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "actions": [action.to_dict() for action in self.actions],
            "needs_confirmation": self.needs_confirmation,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ActionPlan":
        summary = payload.get("summary")
        actions = payload.get("actions")
        needs_confirmation = payload.get("needs_confirmation")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Plan summary must be a non-empty string.")
        if not isinstance(actions, list):
            raise ValueError("Plan actions must be an array.")
        if not isinstance(needs_confirmation, bool):
            raise ValueError("Plan needs_confirmation must be a boolean.")
        return cls(
            summary=summary.strip(),
            actions=[Action.from_dict(item) for item in actions],
            needs_confirmation=needs_confirmation,
        )


def action_plan_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "needs_confirmation": {"type": "boolean"},
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": sorted(SUPPORTED_ACTION_KINDS),
                        },
                        "params": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "count": {"type": ["integer", "null"]},
                                "corner_radius": {"type": ["number", "null"]},
                                "cx": {"type": ["number", "null"]},
                                "cy": {"type": ["number", "null"]},
                                "dash_pattern": {"type": ["string", "null"]},
                                "degrees": {"type": ["number", "null"]},
                                "hex": {"type": ["string", "null"]},
                                "delta_x_px": {"type": ["number", "null"]},
                                "delta_y_px": {"type": ["number", "null"]},
                                "fill_hex": {"type": ["string", "null"]},
                                "font_size_px": {"type": ["number", "null"]},
                                "height": {"type": ["number", "null"]},
                                "inner_radius": {"type": ["number", "null"]},
                                "opacity_percent": {"type": ["number", "null"]},
                                "object_id": {"type": ["string", "null"]},
                                "percent": {"type": ["number", "null"]},
                                "prefix": {"type": ["string", "null"]},
                                "radius": {"type": ["number", "null"]},
                                "new_text": {"type": ["string", "null"]},
                                "stroke_hex": {"type": ["string", "null"]},
                                "stroke_width_px": {"type": ["number", "null"]},
                                "text": {"type": ["string", "null"]},
                                "text_hex": {"type": ["string", "null"]},
                                "width": {"type": ["number", "null"]},
                                "x": {"type": ["number", "null"]},
                                "x1": {"type": ["number", "null"]},
                                "x2": {"type": ["number", "null"]},
                                "y": {"type": ["number", "null"]},
                                "y1": {"type": ["number", "null"]},
                                "y2": {"type": ["number", "null"]},
                                "spacing_x": {"type": ["number", "null"]},
                                "spacing_y": {"type": ["number", "null"]},
                            },
                            "required": [
                                "count",
                                "corner_radius",
                                "cx",
                                "cy",
                                "dash_pattern",
                                "degrees",
                                "hex",
                                "delta_x_px",
                                "delta_y_px",
                                "fill_hex",
                                "font_size_px",
                                "height",
                                "inner_radius",
                                "opacity_percent",
                                "object_id",
                                "percent",
                                "prefix",
                                "radius",
                                "new_text",
                                "stroke_hex",
                                "stroke_width_px",
                                "text",
                                "text_hex",
                                "width",
                                "x",
                                "x1",
                                "x2",
                                "y",
                                "y1",
                                "y2",
                                "spacing_x",
                                "spacing_y",
                            ],
                        },
                    },
                    "required": ["kind", "params"],
                },
            },
        },
        "required": ["summary", "needs_confirmation", "actions"],
    }
