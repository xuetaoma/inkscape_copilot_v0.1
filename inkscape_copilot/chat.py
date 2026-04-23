from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field

from .bridge import append_job
from .defaults import default_document_context
from .openai_bridge import OpenAIPlannerError, plan_with_openai, stream_chat_reply
from .planner import DocumentContext, SelectionItem


@dataclass
class ChatSession:
    model: str | None = None
    document: DocumentContext = field(default_factory=default_document_context)
    history: list[dict[str, str]] = field(default_factory=list)

    def clear(self) -> None:
        self.history.clear()


def _default_context() -> DocumentContext:
    return default_document_context()


def _load_context(path: str | None) -> DocumentContext:
    if not path:
        return _default_context()

    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    selection = [
        SelectionItem(
            object_id=str(item["object_id"]),
            tag=str(item["tag"]),
            fill=item.get("fill"),
            stroke=item.get("stroke"),
            bbox=item.get("bbox"),
        )
        for item in payload.get("selection", [])
    ]
    return DocumentContext(
        width=payload.get("width"),
        height=payload.get("height"),
        selection=selection,
    )


def _print_help() -> None:
    print("Commands:")
    print("  /help   Show this help")
    print("  /clear  Clear conversation history")
    print("  /context  Show the current document context")
    print("  /quit   Exit chat")


def run_chat(model: str | None = None, context_path: str | None = None) -> int:
    session = ChatSession(model=model, document=_load_context(context_path))

    print("Inkscape Copilot Interactive Mode")
    print("Type a prompt and watch the copilot stream its response.")
    print("The structured plan is shown after each turn.")
    print("Use /help for commands.")

    while True:
        try:
            prompt = input("\ncopilot> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        if not prompt:
            continue

        if prompt == "/quit":
            return 0
        if prompt == "/help":
            _print_help()
            continue
        if prompt == "/clear":
            session.clear()
            print("Conversation cleared.")
            continue
        if prompt == "/context":
            print(json.dumps(session.document.to_dict(), indent=2))
            continue

        session.history.append({"role": "user", "content": prompt})

        print("\nassistant> ", end="", flush=True)
        assistant_chunks: list[str] = []
        try:
            for chunk in stream_chat_reply(session.history, session.document, model=session.model):
                assistant_chunks.append(chunk)
                print(chunk, end="", flush=True)
            print()

            assistant_text = "".join(assistant_chunks).strip()
            if assistant_text:
                session.history.append({"role": "assistant", "content": assistant_text})

            plan = plan_with_openai(prompt, session.document, model=session.model)
        except OpenAIPlannerError as exc:
            print(f"\nerror> {exc}", file=sys.stderr)
            if session.history and session.history[-1]["role"] == "user":
                session.history.pop()
            continue

        print("\nplan>")
        print(json.dumps(plan.to_dict(), indent=2))

        if plan.actions:
            job = append_job(prompt, plan, source="interactive-chat")
            print(f"\nqueue> enqueued {job.job_id}")
        else:
            print("\nqueue> no executable actions enqueued")

    return 0
