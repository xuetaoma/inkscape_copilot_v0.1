from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .interpreter import interpret_prompt
from .schema import ActionPlan


@dataclass(frozen=True)
class SelectionItem:
    object_id: str
    tag: str
    fill: str | None
    stroke: str | None
    bbox: dict[str, float] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "tag": self.tag,
            "fill": self.fill,
            "stroke": self.stroke,
            "bbox": self.bbox,
        }


@dataclass(frozen=True)
class DocumentObject:
    object_id: str
    tag: str
    text: str | None
    fill: str | None
    stroke: str | None
    bbox: dict[str, float] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "tag": self.tag,
            "text": self.text,
            "fill": self.fill,
            "stroke": self.stroke,
            "bbox": self.bbox,
        }


@dataclass(frozen=True)
class DocumentContext:
    width: float | None
    height: float | None
    selection: list[SelectionItem]
    document_name: str | None = None
    document_path: str | None = None
    objects: list[DocumentObject] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_name": self.document_name,
            "document_path": self.document_path,
            "width": self.width,
            "height": self.height,
            "selection_count": len(self.selection),
            "selection": [item.to_dict() for item in self.selection],
            "object_count": len(self.objects or []),
            "objects": [item.to_dict() for item in self.objects or []],
        }


def build_fallback_plan(prompt: str) -> ActionPlan:
    actions = interpret_prompt(prompt)
    return ActionPlan(
        summary=f"Fallback interpreter plan for: {prompt}",
        actions=actions,
        needs_confirmation=False,
    )
