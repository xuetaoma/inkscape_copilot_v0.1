from __future__ import annotations

import json
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue
from typing import Any
from urllib.parse import urlparse

from .bridge import (
    append_job,
    pending_jobs,
    read_document_context,
    read_events,
    read_execution_result,
    read_planned_step,
    read_session_state,
    read_status,
    reset_state,
    write_execution_result,
    write_planned_step,
)
from .defaults import DEFAULT_PAGE_HEIGHT_PX, DEFAULT_PAGE_WIDTH_PX, default_document_context
from .inkscape_control import trigger_apply_pending_jobs
from .interpreter import PromptError
from .openai_bridge import OpenAIPlannerError, plan_with_openai, stream_chat_reply
from .planner import DocumentContext, DocumentObject, SelectionItem, build_fallback_plan
from .schema import ActionPlan


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Inkscape Copilot</title>
  <style>
    :root {
      --bg: #f3efe5;
      --panel: #fffaf2;
      --ink: #1e2a2f;
      --muted: #65737a;
      --line: #d8ccb8;
      --accent: #0f766e;
      --accent-2: #f59e0b;
      --user: #e2f3f1;
      --assistant: #fff4dd;
      --system: #f3ecff;
    }
    * { box-sizing: border-box; }
    html {
      height: 100%;
      overflow: hidden;
    }
    body {
      margin: 0;
      font-family: ui-rounded, "SF Pro Rounded", "Avenir Next", "Helvetica Neue", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(245,158,11,.16), transparent 28%),
        radial-gradient(circle at top right, rgba(15,118,110,.16), transparent 24%),
        linear-gradient(180deg, #f6f2e9, #efe7d8);
      color: var(--ink);
      height: 100vh;
      height: 100dvh;
      overflow: hidden;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
    }
    header {
      padding: 20px 24px 10px;
      border-bottom: 1px solid rgba(30,42,47,.08);
    }
    h1 {
      margin: 0;
      font-size: 24px;
      letter-spacing: .01em;
    }
    .sub {
      margin-top: 6px;
      color: var(--muted);
      font-size: 14px;
    }
    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 320px;
      gap: 18px;
      padding: 18px 24px;
      height: 100%;
      min-height: 0;
      overflow: hidden;
    }
    .chat, .side {
      background: rgba(255,250,242,.88);
      backdrop-filter: blur(8px);
      border: 1px solid rgba(30,42,47,.08);
      border-radius: 20px;
      box-shadow: 0 16px 50px rgba(30,42,47,.08);
      min-height: 0;
    }
    .chat {
      display: grid;
      grid-template-rows: minmax(0, 1fr);
      height: 100%;
      max-height: 100%;
      overflow: hidden;
    }
    #messages {
      overflow: auto;
      height: 100%;
      max-height: calc(100dvh - 215px);
      min-height: 0;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .msg {
      border-radius: 16px;
      padding: 12px 14px;
      white-space: pre-wrap;
      line-height: 1.45;
      border: 1px solid rgba(30,42,47,.06);
    }
    .msg.user { background: var(--user); align-self: flex-end; max-width: 82%; }
    .msg.assistant { background: var(--assistant); align-self: flex-start; max-width: 82%; }
    .msg.system { background: var(--system); align-self: center; max-width: 92%; color: #3f3a5b; }
    .msg .meta {
      display: block;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .08em;
      color: var(--muted);
      margin-bottom: 6px;
    }
    .side {
      padding: 16px;
      overflow: auto;
      max-height: calc(100dvh - 148px);
    }
    .panel-title {
      margin: 0 0 10px;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: .08em;
      color: var(--muted);
    }
    .stat {
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      border-bottom: 1px dashed rgba(30,42,47,.12);
      font-size: 14px;
    }
    .queue-item {
      border: 1px solid rgba(30,42,47,.08);
      border-radius: 14px;
      padding: 10px;
      margin-top: 10px;
      background: rgba(255,255,255,.55);
    }
    footer {
      padding: 12px 24px 22px;
      min-height: 0;
    }
    form {
      display: grid;
      grid-template-columns: 1fr auto auto auto;
      gap: 12px;
      align-items: end;
    }
    textarea {
      width: 100%;
      height: 92px;
      min-height: 92px;
      max-height: 220px;
      resize: none;
      overflow: auto;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,250,242,.92);
      padding: 14px 16px;
      font: inherit;
      color: inherit;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.7);
    }
    button {
      border: 0;
      border-radius: 16px;
      padding: 13px 18px;
      font: inherit;
      cursor: pointer;
    }
    .send {
      background: var(--accent);
      color: white;
      font-weight: 700;
    }
    .clear {
      background: #eadfcf;
      color: var(--ink);
    }
    .busy {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      margin-top: 10px;
    }
    .dot {
      width: 8px; height: 8px; border-radius: 999px; background: var(--accent-2);
      animation: pulse 1.1s infinite ease-in-out;
    }
    .attachments {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 10px;
    }
    .attachment {
      position: relative;
      width: 72px;
      height: 72px;
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid rgba(30,42,47,.12);
      background: rgba(255,250,242,.9);
      box-shadow: 0 8px 24px rgba(30,42,47,.08);
    }
    .attachment img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .attachment button {
      position: absolute;
      top: 4px;
      right: 4px;
      width: 22px;
      height: 22px;
      padding: 0;
      border-radius: 999px;
      background: rgba(30,42,47,.78);
      color: white;
      font-size: 14px;
      line-height: 1;
    }
    .attach {
      background: #eadfcf;
      color: var(--ink);
      min-width: 48px;
    }
    #image-input { display: none; }
    @keyframes pulse { 0%,100%{transform:scale(.8);opacity:.5} 50%{transform:scale(1.2);opacity:1} }
    @media (max-width: 980px) {
      html {
        height: auto;
        overflow: auto;
      }
      body {
        height: auto;
        min-height: 100vh;
        overflow: auto;
      }
      main {
        grid-template-columns: 1fr;
        overflow: visible;
      }
      .chat { min-height: 45vh; }
      .msg.user, .msg.assistant, .msg.system { max-width: 100%; }
      form { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Inkscape Copilot</h1>
    <div class="sub">A conversational sidecar for the current Inkscape document. Ask for changes, keep chatting while it works, and let it stay in sync with your active drawing.</div>
  </header>
  <main>
    <section class="chat">
      <div id="messages"></div>
    </section>
    <aside class="side">
      <h2 class="panel-title">Session</h2>
      <div id="status"></div>
      <h2 class="panel-title" style="margin-top:18px;">Current Step</h2>
      <div id="queue"></div>
    </aside>
  </main>
  <footer>
    <form id="composer">
      <textarea id="prompt" placeholder="Ask the copilot to change the drawing..."></textarea>
      <button class="attach" type="button" id="attach" title="Attach images">Image</button>
      <button class="send" type="submit">Send</button>
      <button class="clear" type="button" id="clear">Clear Chat</button>
    </form>
    <input id="image-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple>
    <div class="attachments" id="attachments"></div>
    <div class="busy" id="busy" hidden><span class="dot"></span><span>Copilot is working in the background. You can keep typing.</span></div>
  </footer>
  <script>
    const messagesEl = document.getElementById('messages');
    const statusEl = document.getElementById('status');
    const queueEl = document.getElementById('queue');
    const busyEl = document.getElementById('busy');
    const promptEl = document.getElementById('prompt');
    const formEl = document.getElementById('composer');
    const attachEl = document.getElementById('attach');
    const imageInputEl = document.getElementById('image-input');
    const attachmentsEl = document.getElementById('attachments');
    const clearEl = document.getElementById('clear');
    let lastMessageCount = 0;
    let attachedImages = [];

    function autoGrowComposer() {
      promptEl.style.height = '92px';
      promptEl.style.height = Math.min(promptEl.scrollHeight, 220) + 'px';
      promptEl.style.overflowY = promptEl.scrollHeight > 220 ? 'auto' : 'hidden';
    }

    function renderMessages(messages) {
      messagesEl.innerHTML = '';
      for (const msg of messages) {
        const div = document.createElement('div');
        div.className = `msg ${msg.role}`;
        const meta = document.createElement('span');
        meta.className = 'meta';
        meta.textContent = msg.role + (msg.pending ? ' • streaming' : '');
        div.appendChild(meta);
        div.appendChild(document.createTextNode(msg.content || ''));
        messagesEl.appendChild(div);
      }
      if (messages.length !== lastMessageCount) {
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
      lastMessageCount = messages.length;
    }

    function renderStatus(status) {
      const documentName = status.document_context?.document_name
        || status.session_state?.attached_document_name
        || 'No document attached';
      const pageWidth = status.document_context?.width ?? '—';
      const pageHeight = status.document_context?.height ?? '—';
      const stats = [
        ['Document', documentName],
        ['Page size', `${pageWidth} × ${pageHeight} px`],
        ['Copilot', status.processing ? 'Working' : 'Idle'],
        ['Pending prompts', String(status.pending_prompt_count ?? 0)],
        ['Bridge', status.bridge_status?.state ?? 'unknown'],
        ['Session', status.session_state?.active ? (status.session_state?.worker_state ?? 'active') : 'inactive'],
        ['Selection count', String(status.document_context?.selection_count ?? 0)],
        ['Planned step', status.planned_step?.ready_to_apply ? 'Ready' : 'None'],
        ['Execution', status.execution_result?.state ?? 'idle'],
        ['Brief', status.working_brief ? 'Active' : 'None'],
        ['Context', status.sync_warning ?? 'Fresh or last-synced'],
        ['Last error', status.execution_result?.error ?? status.bridge_status?.last_error ?? '—'],
      ];
      statusEl.innerHTML = '';
      for (const [label, value] of stats) {
        const row = document.createElement('div');
        row.className = 'stat';
        row.innerHTML = `<strong>${label}</strong><span>${value}</span>`;
        statusEl.appendChild(row);
      }
      busyEl.hidden = !status.processing;
    }

    function renderQueue(data) {
      const plannedStep = data.planned_step;
      const executionState = data.execution_result?.state || 'idle';
      queueEl.innerHTML = '';
      if (!plannedStep?.plan) {
        queueEl.textContent = 'No planned step yet.';
        return;
      }
      const card = document.createElement('div');
      card.className = 'queue-item';
      const summary = plannedStep.plan.summary || 'No summary';
      const actionCount = plannedStep.plan.actions?.length ?? 0;
      const execution = data.execution_result?.summary || data.execution_result?.error || 'Not applied yet.';
      card.innerHTML = `<strong>Prompt</strong><div>${plannedStep.prompt || ''}</div><div style="margin-top:6px;color:#65737a;">${summary}</div><div style="margin-top:6px;">Actions: ${actionCount}</div><div style="margin-top:6px;color:#65737a;">Execution: ${execution}</div>`;
      queueEl.appendChild(card);
    }

    function renderAttachments() {
      attachmentsEl.innerHTML = '';
      for (const [index, image] of attachedImages.entries()) {
        const wrapper = document.createElement('div');
        wrapper.className = 'attachment';
        const img = document.createElement('img');
        img.src = image.data_url;
        img.alt = image.name || 'Attached image';
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = '×';
        remove.title = 'Remove image';
        remove.addEventListener('click', () => {
          attachedImages.splice(index, 1);
          renderAttachments();
          promptEl.focus();
        });
        wrapper.appendChild(img);
        wrapper.appendChild(remove);
        attachmentsEl.appendChild(wrapper);
      }
    }

    function readFileAsDataURL(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error || new Error('Could not read image'));
        reader.readAsDataURL(file);
      });
    }

    async function refresh() {
      const res = await fetch('/api/state');
      const data = await res.json();
      renderMessages(data.messages);
      renderStatus(data);
      renderQueue(data);
    }

    formEl.addEventListener('submit', async (event) => {
      event.preventDefault();
      const prompt = promptEl.value.trim();
      if (!prompt && attachedImages.length === 0) return;
      const images = attachedImages.map((image) => image.data_url);
      promptEl.value = '';
      attachedImages = [];
      renderAttachments();
      autoGrowComposer();
      await fetch('/api/message', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt, images}),
      });
      await refresh();
      promptEl.focus();
    });

    promptEl.addEventListener('input', autoGrowComposer);
    promptEl.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        formEl.requestSubmit();
      }
    });

    clearEl.addEventListener('click', async () => {
      attachedImages = [];
      renderAttachments();
      await fetch('/api/reset', {method: 'POST'});
      await refresh();
      promptEl.focus();
    });

    attachEl.addEventListener('click', () => {
      imageInputEl.click();
    });

    imageInputEl.addEventListener('change', async () => {
      const files = Array.from(imageInputEl.files || []);
      imageInputEl.value = '';
      for (const file of files) {
        if (!file.type.startsWith('image/')) continue;
        if (file.size > 10 * 1024 * 1024) {
          console.warn(`Skipping ${file.name}: image is larger than 10 MB.`);
          continue;
        }
        if (attachedImages.length >= 6) {
          console.warn('Skipping extra image: maximum 6 images per message.');
          break;
        }
        const dataUrl = await readFileAsDataURL(file);
        attachedImages.push({name: file.name, data_url: dataUrl});
      }
      renderAttachments();
      promptEl.focus();
    });

    autoGrowComposer();
    refresh();
    setInterval(refresh, 700);
  </script>
</body>
</html>
"""


@dataclass
class WebMessage:
    role: str
    content: str
    pending: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content, "pending": self.pending}


@dataclass
class WebChatState:
    model: str | None = None
    document: DocumentContext = field(default_factory=default_document_context)
    history: list[dict[str, str]] = field(default_factory=list)
    messages: list[WebMessage] = field(default_factory=list)
    pending_prompt_count: int = 0
    processing: bool = False
    last_execution_update_at: str | None = None
    apply_in_flight: bool = False
    last_sync_warning: str | None = None
    working_brief: str | None = None


def _default_context() -> DocumentContext:
    return default_document_context()


class CopilotApp:
    def __init__(self, model: str | None = None) -> None:
        self.state = WebChatState(model=model, document=_default_context())
        self.lock = threading.Lock()
        self.prompts: Queue[tuple[str, list[str], int]] = Queue()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def enqueue_prompt(self, prompt: str, images: list[str] | None = None) -> None:
        image_urls = [image for image in images or [] if isinstance(image, str) and image.startswith("data:image/")]
        prompt_text = prompt or "Please inspect the attached image and help me use it for this Inkscape document."
        display_text = prompt_text
        if image_urls:
            display_text = f"{prompt_text}\n\nAttached image(s): {len(image_urls)}"
        with self.lock:
            self.state.pending_prompt_count += 1
            self.state.messages.append(WebMessage(role="user", content=display_text))
            self.state.messages.append(WebMessage(role="assistant", content="", pending=True))
            assistant_index = len(self.state.messages) - 1
        self.prompts.put((prompt_text, image_urls, assistant_index))

    def reset(self) -> None:
        with self.lock:
            self.state.history.clear()
            self.state.messages.clear()
            self.state.pending_prompt_count = 0
            self.state.processing = False
            self.state.last_execution_update_at = None
            self.state.apply_in_flight = False
            self.state.last_sync_warning = None
            self.state.working_brief = None
        reset_state()

    def _document_context_from_payload(self, live_context: dict[str, Any]) -> DocumentContext:
        selection = [
            SelectionItem(
                object_id=str(item["object_id"]),
                tag=str(item["tag"]),
                fill=item.get("fill"),
                stroke=item.get("stroke"),
                bbox=item.get("bbox"),
            )
            for item in live_context.get("selection", [])
        ]
        return DocumentContext(
            document_name=live_context.get("document_name"),
            document_path=live_context.get("document_path"),
            width=live_context.get("width", DEFAULT_PAGE_WIDTH_PX),
            height=live_context.get("height", DEFAULT_PAGE_HEIGHT_PX),
            selection=selection,
            objects=[
                DocumentObject(
                    object_id=str(item["object_id"]),
                    tag=str(item["tag"]),
                    text=item.get("text"),
                    fill=item.get("fill"),
                    stroke=item.get("stroke"),
                    bbox=item.get("bbox"),
                )
                for item in live_context.get("objects", [])
                if isinstance(item, dict) and item.get("object_id") and item.get("tag")
            ],
        )

    def _sync_document_context(self) -> tuple[DocumentContext, str | None]:
        live_context = read_document_context()
        if live_context.get("updated_at"):
            document = self._document_context_from_payload(live_context)
            if document.width is None:
                document = DocumentContext(
                    document_name=document.document_name,
                    document_path=document.document_path,
                    width=DEFAULT_PAGE_WIDTH_PX,
                    height=DEFAULT_PAGE_HEIGHT_PX,
                    selection=document.selection,
                    objects=document.objects,
                )
            return document, None

        warning = f"No synced document snapshot was available, so planning used the default {int(DEFAULT_PAGE_WIDTH_PX)}×{int(DEFAULT_PAGE_HEIGHT_PX)} px sheet."
        return default_document_context(), warning

    def _sync_execution_messages_locked(self) -> dict[str, Any]:
        execution_result = read_execution_result()
        updated_at = execution_result.get("updated_at")
        if updated_at and updated_at != self.state.last_execution_update_at:
            state = execution_result.get("state")
            summary = execution_result.get("summary")
            error = execution_result.get("error")
            job_id = execution_result.get("job_id")

            message: str | None = None
            if state == "dispatched" and summary:
                message = f"Apply started: {summary}"
            elif state == "applied":
                detail = summary or "Applied the current step."
                message = f"Applied step: {detail}"
            elif state == "error":
                detail = error or "The current step failed during execution."
                message = f"Apply failed: {detail}"

            if message:
                last_message = self.state.messages[-1].content if self.state.messages else None
                if last_message != message:
                    self.state.messages.append(WebMessage(role="system", content=message))

            self.state.last_execution_update_at = updated_at

        return execution_result

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            execution_result = self._sync_execution_messages_locked()
            return {
                "messages": [message.to_dict() for message in self.state.messages],
                "pending_prompt_count": self.state.pending_prompt_count,
                "processing": self.state.processing,
                "bridge_status": read_status(),
                "session_state": read_session_state(),
                "document_context": read_document_context(),
                "planned_step": read_planned_step(),
                "execution_result": execution_result,
                "sync_warning": self.state.last_sync_warning,
                "working_brief": self.state.working_brief,
                "recent_events": read_events(limit=20),
                "pending_jobs": [job.to_dict() for job in pending_jobs()],
            }

    def _update_working_brief(self, prompt: str, assistant_text: str, image_urls: list[str]) -> None:
        brief_parts: list[str] = []
        existing = self.state.working_brief
        if existing:
            brief_parts.append(existing)
        if image_urls:
            brief_parts.append(f"User provided {len(image_urls)} reference image(s).")
        if prompt:
            brief_parts.append(f"Latest user intent: {prompt}")
        if assistant_text:
            brief_parts.append(f"Assistant interpretation: {assistant_text[:1800]}")

        compact = "\n".join(part.strip() for part in brief_parts if part and part.strip())
        if compact:
            self.state.working_brief = compact[-3000:]

    def _dispatch_plan_to_inkscape(self, prompt: str, plan: ActionPlan) -> tuple[bool, str]:
        with self.lock:
            if self.state.apply_in_flight:
                return False, "The current step is already being dispatched to Inkscape."
            self.state.apply_in_flight = True

        try:
            execution_result = read_execution_result()
            if execution_result.get("state") == "dispatched":
                return False, "The current step has already been dispatched and is still waiting on Inkscape."

            queued = pending_jobs()
            if queued:
                return False, "There is already a pending step waiting for Inkscape to apply."

            job = append_job(prompt, plan, source="web-send")
            write_execution_result(
                state="dispatched",
                job_id=job.job_id,
                summary=f"Dispatched {job.job_id} to Inkscape for execution.",
            )
            with self.lock:
                self._sync_execution_messages_locked()

            apply_ok, apply_error = trigger_apply_pending_jobs()
            if apply_ok:
                return True, f"Dispatched {job.job_id} to Inkscape."

            write_execution_result(
                state="error",
                job_id=job.job_id,
                error=apply_error or "Could not dispatch planned step to Inkscape.",
            )
            with self.lock:
                self._sync_execution_messages_locked()
            return False, apply_error or "Could not dispatch planned step to Inkscape."
        finally:
            with self.lock:
                self.state.apply_in_flight = False

    def _worker_loop(self) -> None:
        while True:
            try:
                prompt, image_urls, assistant_index = self.prompts.get(timeout=0.2)
            except Empty:
                continue

            with self.lock:
                self.state.pending_prompt_count = max(0, self.state.pending_prompt_count - 1)
                self.state.processing = True
                assistant_message = self.state.messages[assistant_index]

            history_snapshot = list(self.state.history)
            if image_urls:
                history_snapshot.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            *[
                                {"type": "input_image", "image_url": image_url, "detail": "auto"}
                                for image_url in image_urls
                            ],
                        ],
                    }
                )
            else:
                history_snapshot.append({"role": "user", "content": prompt})

            assistant_chunks: list[str] = []
            error_message: str | None = None
            step_message: str | None = None
            sync_warning: str | None = None
            dispatch_message: str | None = None

            try:
                self.state.document, sync_warning = self._sync_document_context()
                current_document = self.state.document

                for chunk in stream_chat_reply(history_snapshot, current_document, model=self.state.model):
                    assistant_chunks.append(chunk)
                    with self.lock:
                        assistant_message.content = "".join(assistant_chunks)

                assistant_text = "".join(assistant_chunks).strip()

                with self.lock:
                    self._update_working_brief(prompt, assistant_text, image_urls)
                    working_brief = self.state.working_brief

                plan = plan_with_openai(
                    prompt,
                    current_document,
                    image_urls=None,
                    working_brief=working_brief,
                    model=self.state.model,
                )
                if not plan.actions and plan.needs_confirmation:
                    try:
                        fallback_plan = build_fallback_plan(prompt)
                    except PromptError:
                        fallback_plan = None
                    if fallback_plan and fallback_plan.actions:
                        plan = fallback_plan
                write_planned_step(prompt, plan, ready_to_apply=bool(plan.actions))
                write_execution_result(
                    state="planned",
                    summary="Current step has been planned and is ready for apply."
                    if plan.actions
                    else "Current step produced no executable actions.",
                )

                with self.lock:
                    self.state.history.append({"role": "user", "content": prompt})
                    if assistant_text:
                        self.state.history.append({"role": "assistant", "content": assistant_text})

                if plan.actions:
                    dispatch_ok, dispatch_result = self._dispatch_plan_to_inkscape(prompt, plan)
                    if dispatch_ok:
                        step_message = "Planned and sent to Inkscape."
                    else:
                        dispatch_message = dispatch_result
                        step_message = "Planned, but not sent to Inkscape."
                else:
                    step_message = "No executable actions."
            except OpenAIPlannerError as exc:
                error_message = str(exc)

            with self.lock:
                assistant_message.pending = False
                self.state.last_sync_warning = sync_warning
                if error_message:
                    assistant_message.content = f"{assistant_message.content}\n\nError: {error_message}".strip()
                    self.state.messages.append(WebMessage(role="system", content=f"Planner error: {error_message}"))
                else:
                    if sync_warning:
                        self.state.messages.append(WebMessage(role="system", content=f"Context note: {sync_warning}"))
                    if dispatch_message:
                        self.state.messages.append(WebMessage(role="system", content=f"Dispatch note: {dispatch_message}"))
                    if step_message:
                        self.state.messages.append(WebMessage(role="system", content=step_message))
                self.state.processing = False


def make_handler(app: CopilotApp):
    class CopilotHandler(BaseHTTPRequestHandler):
        def _json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, body: str, status: int = 200) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self._html(INDEX_HTML)
                return
            if path == "/api/state":
                self._json(app.snapshot())
                return
            self._json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._json({"error": "invalid json"}, status=400)
                return

            if path == "/api/message":
                prompt = str(payload.get("prompt", "")).strip()
                images_payload = payload.get("images", [])
                images = images_payload if isinstance(images_payload, list) else []
                images = [
                    image
                    for image in images[:6]
                    if isinstance(image, str) and image.startswith("data:image/") and len(image) <= 14_000_000
                ]
                if not prompt and not images:
                    self._json({"error": "prompt or image is required"}, status=400)
                    return
                app.enqueue_prompt(prompt, images)
                self._json({"ok": True})
                return

            if path == "/api/reset":
                app.reset()
                self._json({"ok": True})
                return

            if path == "/api/apply":
                self._json(
                    {
                        "ok": False,
                        "message": "Apply is now invoked only after clicking Send in the web chat.",
                    },
                    status=400,
                )
                return

            self._json({"error": "not found"}, status=404)

        def log_message(self, format: str, *args) -> None:
            return

    return CopilotHandler


def run_web_app(host: str = "127.0.0.1", port: int = 8765, model: str | None = None, open_browser: bool = False) -> int:
    app = CopilotApp(model=model)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    url = f"http://{host}:{port}"
    print(f"Inkscape Copilot web UI running at {url}")
    if open_browser:
        threading.Thread(target=lambda: (time.sleep(0.3), webbrowser.open(url)), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down web UI.")
    finally:
        server.server_close()
    return 0
