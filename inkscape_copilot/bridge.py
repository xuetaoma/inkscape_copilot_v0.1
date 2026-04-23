from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .defaults import DEFAULT_PAGE_HEIGHT_PX, DEFAULT_PAGE_WIDTH_PX
from .planner import DocumentContext
from .schema import ActionPlan


def runtime_root() -> Path:
    explicit_root = os.environ.get("INKSCAPE_COPILOT_HOME")
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()

    app_support_root = (
        Path.home()
        / "Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/inkscape_copilot_runtime"
    )
    return app_support_root.resolve()


PROJECT_ROOT = runtime_root()
STATE_DIR = PROJECT_ROOT / "state"
QUEUE_FILE = STATE_DIR / "queue.jsonl"
STATUS_FILE = STATE_DIR / "status.json"
EVENTS_FILE = STATE_DIR / "events.jsonl"
DOCUMENT_CONTEXT_FILE = STATE_DIR / "document_context.json"
SESSION_FILE = STATE_DIR / "session.json"
PLANNED_STEP_FILE = STATE_DIR / "planned_step.json"
EXECUTION_RESULT_FILE = STATE_DIR / "execution_result.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BridgeJob:
    job_id: str
    created_at: str
    prompt: str
    plan: ActionPlan
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "created_at": self.created_at,
            "prompt": self.prompt,
            "plan": self.plan.to_dict(),
            "source": self.source,
        }

    @classmethod
    def create(cls, prompt: str, plan: ActionPlan, source: str = "chat") -> "BridgeJob":
        return cls(
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            created_at=utc_now(),
            prompt=prompt,
            plan=plan,
            source=source,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BridgeJob":
        return cls(
            job_id=str(payload["job_id"]),
            created_at=str(payload["created_at"]),
            prompt=str(payload["prompt"]),
            plan=ActionPlan.from_dict(payload["plan"]),
            source=str(payload.get("source", "unknown")),
        )


def ensure_state_files() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not QUEUE_FILE.exists():
        QUEUE_FILE.write_text("", encoding="utf-8")
    if not EVENTS_FILE.exists():
        EVENTS_FILE.write_text("", encoding="utf-8")
    if not STATUS_FILE.exists():
        _atomic_write(
            STATUS_FILE,
            json.dumps(
                {
                    "state": "idle",
                    "updated_at": utc_now(),
                    "applied_job_ids": [],
                    "failed_job_ids": [],
                    "last_job_id": None,
                    "last_error": None,
                },
                indent=2,
            ),
        )
    if not DOCUMENT_CONTEXT_FILE.exists():
        _atomic_write(
            DOCUMENT_CONTEXT_FILE,
            json.dumps(
                {
                    "document_name": None,
                    "document_path": None,
                    "width": DEFAULT_PAGE_WIDTH_PX,
                    "height": DEFAULT_PAGE_HEIGHT_PX,
                    "selection_count": 0,
                    "selection": [],
                    "object_count": 0,
                    "objects": [],
                    "updated_at": utc_now(),
                },
                indent=2,
            ),
        )
    if not SESSION_FILE.exists():
        _atomic_write(
            SESSION_FILE,
            json.dumps(
                {
                    "active": False,
                    "updated_at": utc_now(),
                    "started_at": None,
                    "last_heartbeat_at": None,
                    "worker_state": "idle",
                    "attached_document_name": None,
                    "last_error": None,
                },
                indent=2,
            ),
        )
    if not PLANNED_STEP_FILE.exists():
        _atomic_write(
            PLANNED_STEP_FILE,
            json.dumps(
                {
                    "prompt": None,
                    "plan": None,
                    "ready_to_apply": False,
                    "created_at": None,
                    "updated_at": utc_now(),
                },
                indent=2,
            ),
        )
    if not EXECUTION_RESULT_FILE.exists():
        _atomic_write(
            EXECUTION_RESULT_FILE,
            json.dumps(
                {
                    "state": "idle",
                    "job_id": None,
                    "summary": None,
                    "error": None,
                    "updated_at": utc_now(),
                },
                indent=2,
            ),
        )


def _atomic_write(path: Path, content: str) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def write_status(payload: dict[str, Any]) -> None:
    ensure_state_files()
    _atomic_write(STATUS_FILE, json.dumps(payload, indent=2))


def read_status() -> dict[str, Any]:
    ensure_state_files()
    raw = STATUS_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return {
            "state": "idle",
            "updated_at": utc_now(),
            "applied_job_ids": [],
            "failed_job_ids": [],
            "last_job_id": None,
            "last_error": None,
        }
    payload = json.loads(raw)
    payload.setdefault("applied_job_ids", [])
    payload.setdefault("failed_job_ids", [])
    payload.setdefault("last_job_id", None)
    payload.setdefault("last_error", None)
    payload.setdefault("state", "idle")
    payload.setdefault("updated_at", utc_now())
    return payload


def append_job(prompt: str, plan: ActionPlan, source: str = "chat") -> BridgeJob:
    ensure_state_files()
    job = BridgeJob.create(prompt=prompt, plan=plan, source=source)
    with QUEUE_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(job.to_dict()) + "\n")
    status = read_status()
    status.update(
        {
            "state": "queued",
            "updated_at": utc_now(),
            "last_job_id": job.job_id,
            "last_error": None,
        }
    )
    write_status(status)
    append_event("job_queued", {"job_id": job.job_id, "prompt": prompt, "source": source})
    return job


def read_jobs() -> list[BridgeJob]:
    ensure_state_files()
    jobs: list[BridgeJob] = []
    for line in QUEUE_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        jobs.append(BridgeJob.from_dict(json.loads(line)))
    return jobs


def pending_jobs() -> list[BridgeJob]:
    status = read_status()
    applied = set(status.get("applied_job_ids", []))
    failed = set(status.get("failed_job_ids", []))
    return [job for job in read_jobs() if job.job_id not in applied and job.job_id not in failed]


def mark_job_applied(job_id: str) -> None:
    status = read_status()
    applied = list(status.get("applied_job_ids", []))
    if job_id not in applied:
        applied.append(job_id)
    status.update(
        {
            "state": "applied",
            "updated_at": utc_now(),
            "applied_job_ids": applied,
            "last_job_id": job_id,
            "last_error": None,
        }
    )
    write_status(status)


def mark_error(job_id: str | None, error: str) -> None:
    status = read_status()
    failed = list(status.get("failed_job_ids", []))
    if job_id and job_id not in failed:
        failed.append(job_id)
    status.update(
        {
            "state": "error",
            "updated_at": utc_now(),
            "last_job_id": job_id,
            "last_error": error,
            "failed_job_ids": failed,
        }
    )
    write_status(status)


def reset_state() -> None:
    ensure_state_files()
    _atomic_write(QUEUE_FILE, "")
    _atomic_write(EVENTS_FILE, "")
    write_status(
        {
            "state": "idle",
            "updated_at": utc_now(),
            "applied_job_ids": [],
            "failed_job_ids": [],
            "last_job_id": None,
            "last_error": None,
        }
    )
    _atomic_write(
        DOCUMENT_CONTEXT_FILE,
        json.dumps(
            {
                "document_name": None,
                "document_path": None,
                "width": DEFAULT_PAGE_WIDTH_PX,
                "height": DEFAULT_PAGE_HEIGHT_PX,
                "selection_count": 0,
                "selection": [],
                "updated_at": utc_now(),
            },
            indent=2,
        ),
    )
    _atomic_write(
        SESSION_FILE,
        json.dumps(
            {
                "active": False,
                "updated_at": utc_now(),
                "started_at": None,
                "last_heartbeat_at": None,
                "worker_state": "idle",
                "attached_document_name": None,
                "last_error": None,
            },
            indent=2,
        ),
    )
    _atomic_write(
        PLANNED_STEP_FILE,
        json.dumps(
            {
                "prompt": None,
                "plan": None,
                "ready_to_apply": False,
                "created_at": None,
                "updated_at": utc_now(),
            },
            indent=2,
        ),
    )
    _atomic_write(
        EXECUTION_RESULT_FILE,
        json.dumps(
            {
                "state": "idle",
                "job_id": None,
                "summary": None,
                "error": None,
                "updated_at": utc_now(),
            },
            indent=2,
        ),
    )


def append_event(event_type: str, payload: dict[str, Any]) -> None:
    ensure_state_files()
    event = {"type": event_type, "created_at": utc_now(), **payload}
    with EVENTS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def read_events(limit: int = 100) -> list[dict[str, Any]]:
    ensure_state_files()
    lines = [line for line in EVENTS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines[-limit:]]


def write_planned_step(prompt: str | None, plan: ActionPlan | None, *, ready_to_apply: bool) -> None:
    ensure_state_files()
    payload = {
        "prompt": prompt,
        "plan": plan.to_dict() if plan is not None else None,
        "ready_to_apply": ready_to_apply,
        "created_at": utc_now() if plan is not None else None,
        "updated_at": utc_now(),
    }
    _atomic_write(PLANNED_STEP_FILE, json.dumps(payload, indent=2))


def read_planned_step() -> dict[str, Any]:
    ensure_state_files()
    raw = PLANNED_STEP_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return {
            "prompt": None,
            "plan": None,
            "ready_to_apply": False,
            "created_at": None,
            "updated_at": utc_now(),
        }
    payload = json.loads(raw)
    payload.setdefault("prompt", None)
    payload.setdefault("plan", None)
    payload.setdefault("ready_to_apply", False)
    payload.setdefault("created_at", None)
    payload.setdefault("updated_at", utc_now())
    return payload


def clear_planned_step() -> None:
    write_planned_step(None, None, ready_to_apply=False)


def write_execution_result(
    *,
    state: str,
    job_id: str | None = None,
    summary: str | None = None,
    error: str | None = None,
) -> None:
    ensure_state_files()
    payload = {
        "state": state,
        "job_id": job_id,
        "summary": summary,
        "error": error,
        "updated_at": utc_now(),
    }
    _atomic_write(EXECUTION_RESULT_FILE, json.dumps(payload, indent=2))


def read_execution_result() -> dict[str, Any]:
    ensure_state_files()
    raw = EXECUTION_RESULT_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return {
            "state": "idle",
            "job_id": None,
            "summary": None,
            "error": None,
            "updated_at": utc_now(),
        }
    payload = json.loads(raw)
    payload.setdefault("state", "idle")
    payload.setdefault("job_id", None)
    payload.setdefault("summary", None)
    payload.setdefault("error", None)
    payload.setdefault("updated_at", utc_now())
    return payload


def write_document_context(document: DocumentContext) -> None:
    ensure_state_files()
    payload = document.to_dict()
    payload["updated_at"] = utc_now()
    _atomic_write(DOCUMENT_CONTEXT_FILE, json.dumps(payload, indent=2))


def read_document_context() -> dict[str, Any]:
    ensure_state_files()
    raw = DOCUMENT_CONTEXT_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return {
            "document_name": None,
            "document_path": None,
            "width": None,
            "height": None,
            "selection_count": 0,
            "selection": [],
            "object_count": 0,
            "objects": [],
            "updated_at": utc_now(),
        }
    payload = json.loads(raw)
    payload.setdefault("document_name", None)
    payload.setdefault("document_path", None)
    payload.setdefault("width", None)
    payload.setdefault("height", None)
    payload.setdefault("selection_count", 0)
    payload.setdefault("selection", [])
    payload.setdefault("object_count", len(payload.get("objects", [])) if isinstance(payload.get("objects"), list) else 0)
    payload.setdefault("objects", [])
    payload.setdefault("updated_at", utc_now())
    return payload


def write_session_state(payload: dict[str, Any]) -> None:
    ensure_state_files()
    current = read_session_state()
    current.update(payload)
    current["updated_at"] = utc_now()
    _atomic_write(SESSION_FILE, json.dumps(current, indent=2))


def read_session_state() -> dict[str, Any]:
    ensure_state_files()
    raw = SESSION_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return {
            "active": False,
            "updated_at": utc_now(),
            "started_at": None,
            "last_heartbeat_at": None,
            "worker_state": "idle",
            "attached_document_name": None,
            "last_error": None,
        }
    payload = json.loads(raw)
    payload.setdefault("active", False)
    payload.setdefault("updated_at", utc_now())
    payload.setdefault("started_at", None)
    payload.setdefault("last_heartbeat_at", None)
    payload.setdefault("worker_state", "idle")
    payload.setdefault("attached_document_name", None)
    payload.setdefault("last_error", None)
    return payload


def mark_session_started(document_name: str | None = None) -> None:
    write_session_state(
        {
            "active": True,
            "started_at": utc_now(),
            "last_heartbeat_at": utc_now(),
            "worker_state": "watching",
            "attached_document_name": document_name,
            "last_error": None,
        }
    )
    append_event("session_started", {"document_name": document_name})


def mark_session_heartbeat(worker_state: str = "watching") -> None:
    write_session_state(
        {
            "active": True,
            "last_heartbeat_at": utc_now(),
            "worker_state": worker_state,
        }
    )


def mark_session_stopped(error: str | None = None) -> None:
    write_session_state(
        {
            "active": False,
            "worker_state": "error" if error else "stopped",
            "last_error": error,
        }
    )
    append_event("session_stopped", {"error": error})
