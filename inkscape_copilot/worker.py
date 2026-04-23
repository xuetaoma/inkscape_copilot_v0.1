from __future__ import annotations

import sys
from pathlib import Path

import inkex

PACKAGE_ROOT = Path(__file__).resolve().parent
PACKAGE_PARENT = str(PACKAGE_ROOT.parent)
if PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, PACKAGE_PARENT)

from inkscape_copilot.bridge import (
    append_event,
    clear_planned_step,
    mark_error,
    mark_job_applied,
    pending_jobs,
    read_document_context,
    write_execution_result,
    write_document_context,
)
from inkscape_copilot.executor import apply_action_plan
from inkscape_copilot.planner import DocumentContext, DocumentObject, SelectionItem

SODIPODI_DOCNAME = "{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}docname"
WORKER_DEBUG_LOG = Path(PACKAGE_PARENT) / "inkscape_copilot_runtime" / "state" / "worker_debug.log"


def _debug_log(message: str) -> None:
    try:
        WORKER_DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with WORKER_DEBUG_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.time():.3f} {message}\n")
    except Exception:
        pass


def _style_value(node: inkex.BaseElement, key: str) -> str | None:
    value = dict(node.style).get(key)
    return str(value) if value is not None else None


def _bbox_dict(node: inkex.BaseElement) -> dict[str, float] | None:
    try:
        bbox = node.bounding_box()
    except Exception:
        return None
    return {
        "left": float(bbox.left),
        "top": float(bbox.top),
        "width": float(bbox.width),
        "height": float(bbox.height),
    }


def _document_name(svg: inkex.SvgDocumentElement) -> str | None:
    for key in (SODIPODI_DOCNAME, "sodipodi:docname", "docname"):
        value = svg.get(key)
        if value:
            return str(value)
    return None


def _tag_name(node: inkex.BaseElement) -> str:
    return str(node.tag).split("}")[-1].lower()


def _node_text(node: inkex.BaseElement) -> str | None:
    parts: list[str] = []
    try:
        if node.text:
            parts.append(str(node.text))
        for descendant in node.iterdescendants():
            if descendant.text:
                parts.append(str(descendant.text))
    except Exception:
        return None
    text = " ".join(" ".join(parts).split())
    return text or None


def _document_objects(svg: inkex.SvgDocumentElement, limit: int = 120) -> list[DocumentObject]:
    objects: list[DocumentObject] = []
    try:
        nodes = list(svg.iterdescendants())
    except Exception:
        return objects

    for node in nodes:
        object_id = node.get("id")
        if not object_id:
            continue
        tag = _tag_name(node)
        if tag in {"defs", "metadata", "namedview", "style", "script"}:
            continue
        bbox = _bbox_dict(node)
        text = _node_text(node)
        if bbox is None and not text:
            continue
        objects.append(
            DocumentObject(
                object_id=str(object_id),
                tag=tag,
                text=text,
                fill=_style_value(node, "fill"),
                stroke=_style_value(node, "stroke"),
                bbox=bbox,
            )
        )
        if len(objects) >= limit:
            break
    return objects


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


def _nodes_from_snapshot_selection(svg: inkex.SvgDocumentElement) -> list[inkex.BaseElement]:
    payload = read_document_context()
    object_ids = [
        str(item["object_id"])
        for item in payload.get("selection", [])
        if isinstance(item, dict) and item.get("object_id")
    ]
    resolved: list[inkex.BaseElement] = []
    seen_ids: set[str] = set()
    for object_id in object_ids:
        node = _find_node_by_id(svg, object_id)
        if node is None:
            continue
        node_id = node.get("id")
        if node_id and node_id in seen_ids:
            continue
        if node_id:
            seen_ids.add(node_id)
        resolved.append(node)
    return resolved


def _infer_selection_from_prompt(svg: inkex.SvgDocumentElement, prompt: str) -> list[inkex.BaseElement]:
    prompt_lower = prompt.lower()
    desired_tags: tuple[str, ...] = ()
    if "text" in prompt_lower or "label" in prompt_lower or "word" in prompt_lower:
        desired_tags = ("text", "tspan")
    elif "square" in prompt_lower or "rectangle" in prompt_lower or "rect" in prompt_lower:
        desired_tags = ("rect",)
    elif "circle" in prompt_lower:
        desired_tags = ("circle", "ellipse")

    if not desired_tags:
        return []

    candidates: list[inkex.BaseElement] = []
    try:
        for node in svg.iterdescendants():
            if _tag_name(node) in desired_tags and node.get("id"):
                candidates.append(node)
    except Exception:
        return []

    if not candidates:
        return []
    return [candidates[-1]]


def resolve_effective_selection(
    svg: inkex.SvgDocumentElement,
    selected: list[inkex.BaseElement],
    prompt: str,
) -> list[inkex.BaseElement]:
    if selected:
        return selected

    snapshot_selection = _nodes_from_snapshot_selection(svg)
    if snapshot_selection:
        _debug_log(f"resolve_effective_selection using snapshot selection count={len(snapshot_selection)}")
        return snapshot_selection

    inferred_selection = _infer_selection_from_prompt(svg, prompt)
    if inferred_selection:
        _debug_log(
            "resolve_effective_selection inferred target "
            f"count={len(inferred_selection)} prompt={prompt!r}"
        )
        return inferred_selection

    return selected


def document_context_from_svg(svg: inkex.SvgDocumentElement, selected: list[inkex.BaseElement]) -> DocumentContext:
    width = None
    height = None
    try:
        width = float(svg.viewport_width)
        height = float(svg.viewport_height)
    except Exception:
        pass

    return DocumentContext(
        document_name=_document_name(svg),
        document_path=None,
        width=width,
        height=height,
        selection=[
            SelectionItem(
                object_id=node.get("id") or f"selected-{index}",
                tag=str(node.tag),
                fill=_style_value(node, "fill"),
                stroke=_style_value(node, "stroke"),
                bbox=_bbox_dict(node),
            )
            for index, node in enumerate(selected, start=1)
        ],
        objects=_document_objects(svg),
    )


def sync_document_context(svg: inkex.SvgDocumentElement, selected: list[inkex.BaseElement]) -> None:
    _debug_log(f"sync_document_context selection_count={len(selected)}")
    write_document_context(document_context_from_svg(svg, selected))


def apply_pending_jobs(svg: inkex.SvgDocumentElement, selected: list[inkex.BaseElement]) -> tuple[list[inkex.BaseElement], str]:
    _debug_log(f"apply_pending_jobs entered selection_count={len(selected)}")
    jobs = pending_jobs()
    _debug_log(f"apply_pending_jobs pending_count={len(jobs)}")
    if not jobs:
        sync_document_context(svg, selected)
        write_execution_result(state="idle", summary="No pending copilot changes to apply.")
        _debug_log("apply_pending_jobs no jobs found")
        return selected, "No pending copilot jobs found."

    current_selection = selected
    applied_count = 0
    failed_count = 0
    last_summary = ""

    for job in jobs:
        _debug_log(f"apply_pending_jobs starting job_id={job.job_id}")
        append_event("job_started", {"job_id": job.job_id, "prompt": job.prompt})
        try:
            effective_selection = resolve_effective_selection(svg, current_selection, job.prompt)
            current_selection, last_summary = apply_action_plan(svg, effective_selection, job.plan)
            mark_job_applied(job.job_id)
            write_execution_result(state="applied", job_id=job.job_id, summary=last_summary)
            clear_planned_step()
            append_event("job_applied", {"job_id": job.job_id, "summary": last_summary})
            applied_count += 1
            _debug_log(f"apply_pending_jobs applied job_id={job.job_id} summary={last_summary}")
        except Exception as exc:
            mark_error(job.job_id, str(exc))
            write_execution_result(state="error", job_id=job.job_id, error=str(exc))
            append_event("job_failed", {"job_id": job.job_id, "error": str(exc)})
            failed_count += 1
            _debug_log(f"apply_pending_jobs failed job_id={job.job_id} error={exc}")

    sync_document_context(svg, current_selection)
    if applied_count or failed_count:
        return current_selection, (
            f"Applied {applied_count} queued copilot job(s), failed {failed_count}. "
            f"Last summary: {last_summary or 'No successful jobs.'}"
        )
    return current_selection, "No queued copilot jobs were applied."


class ApplyPendingJobsWorker(inkex.EffectExtension):
    def effect(self) -> None:
        _debug_log("ApplyPendingJobsWorker.effect entered")
        append_event("worker_invoked", {"worker": "apply_pending_jobs"})
        selected = list(self.svg.selection.values())
        _selected, summary = apply_pending_jobs(self.svg, selected)
        _debug_log(f"ApplyPendingJobsWorker.effect completed summary={summary}")
        inkex.utils.debug(f"Inkscape Copilot: {summary}")


if __name__ == "__main__":
    _debug_log("worker.py __main__ executing ApplyPendingJobsWorker.run()")
    ApplyPendingJobsWorker().run()
