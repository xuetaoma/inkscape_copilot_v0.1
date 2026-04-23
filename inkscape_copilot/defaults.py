from __future__ import annotations

from .planner import DocumentContext


DEFAULT_PAGE_WIDTH_PX = 220.0
DEFAULT_PAGE_HEIGHT_PX = 290.0


def default_document_context() -> DocumentContext:
    return DocumentContext(
        width=DEFAULT_PAGE_WIDTH_PX,
        height=DEFAULT_PAGE_HEIGHT_PX,
        selection=[],
        objects=[],
    )
