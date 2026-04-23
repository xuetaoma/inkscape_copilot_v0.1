from __future__ import annotations

import argparse
import json
import sys

from .bridge import pending_jobs, read_status, reset_state
from .chat import run_chat
from .defaults import default_document_context
from .openai_bridge import OpenAIPlannerError, plan_with_openai
from .schema import ActionPlan
from .interpreter import PromptError, interpret_prompt
from .webapp import run_web_app


def _local_plan(prompt: str) -> ActionPlan:
    return ActionPlan(
        summary=f"Local interpreter plan for: {prompt}",
        actions=interpret_prompt(prompt),
        needs_confirmation=False,
    )


def cmd_send(args: argparse.Namespace) -> int:
    try:
        if args.mode == "openai":
            plan = plan_with_openai(
                args.prompt,
                default_document_context(),
                model=args.model,
            )
        else:
            plan = _local_plan(args.prompt)
    except (PromptError, OpenAIPlannerError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps({"prompt": args.prompt, "mode": args.mode, "plan": plan.to_dict()}, indent=2))
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    print(json.dumps(read_status(), indent=2))
    return 0


def cmd_queue(_: argparse.Namespace) -> int:
    print(json.dumps([job.to_dict() for job in pending_jobs()], indent=2))
    return 0


def cmd_reset(_: argparse.Namespace) -> int:
    reset_state()
    print(json.dumps({"state": "idle", "queue_cleared": True}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inkscape copilot local preview tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    send_parser = subparsers.add_parser("send", help="Interpret a prompt into explicit actions")
    send_parser.add_argument("prompt", help="Prompt to translate into Inkscape actions")
    send_parser.add_argument(
        "--mode",
        choices=("local", "openai"),
        default="local",
        help="Use the local fallback planner or the configured API-backed planner",
    )
    send_parser.add_argument(
        "--model",
        help="Optional model override when using an API-backed planner",
    )
    send_parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Accepted for compatibility with future queue-based flows",
    )
    send_parser.set_defaults(func=cmd_send)

    chat_parser = subparsers.add_parser("chat", help="Start an interactive streaming copilot session")
    chat_parser.add_argument(
        "--model",
        help="Optional model override for chat mode",
    )
    chat_parser.add_argument(
        "--context-file",
        help="Optional JSON file containing document context to use during chat mode",
    )
    chat_parser.set_defaults(func=lambda args: run_chat(model=args.model, context_path=args.context_file))

    serve_parser = subparsers.add_parser("serve", help="Start the non-blocking local web copilot UI")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind the local web UI to")
    serve_parser.add_argument("--port", type=int, default=8765, help="Port to bind the local web UI to")
    serve_parser.add_argument("--model", help="Optional model override for web UI mode")
    serve_parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the web UI in a browser after the server starts",
    )
    serve_parser.set_defaults(
        func=lambda args: run_web_app(
            host=args.host,
            port=args.port,
            model=args.model,
            open_browser=args.open_browser,
        )
    )

    status_parser = subparsers.add_parser("status", help="Show the current bridge status")
    status_parser.set_defaults(func=cmd_status)

    queue_parser = subparsers.add_parser("queue", help="Show pending queued jobs")
    queue_parser.set_defaults(func=cmd_queue)

    reset_parser = subparsers.add_parser("reset", help="Clear queued jobs and reset bridge status")
    reset_parser.set_defaults(func=cmd_reset)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
