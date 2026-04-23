from inkscape_copilot.interpreter import PromptError, interpret_prompt
from inkscape_copilot.planner import build_fallback_plan
from inkscape_copilot.schema import ActionPlan


def test_fill_prompt() -> None:
    actions = interpret_prompt("make the selection blue")
    assert actions[0].to_dict() == {"kind": "set_fill_color", "params": {"hex": "#2563eb"}}


def test_stroke_prompt() -> None:
    actions = interpret_prompt("set stroke to #111827")
    assert actions[0].to_dict() == {"kind": "set_stroke_color", "params": {"hex": "#111827"}}


def test_move_prompt() -> None:
    actions = interpret_prompt("move the selection 24 px right")
    assert actions[0].to_dict() == {
        "kind": "move_selection",
        "params": {"delta_x_px": 24.0, "delta_y_px": 0.0},
    }


def test_scale_requires_positive_percent() -> None:
    try:
        interpret_prompt("scale the selection to 0 percent")
    except PromptError as exc:
        assert "greater than zero" in str(exc)
    else:
        raise AssertionError("Expected PromptError")


def test_fallback_plan_wraps_actions() -> None:
    plan = build_fallback_plan("make the selection blue")
    assert isinstance(plan, ActionPlan)
    assert plan.actions[0].to_dict() == {"kind": "set_fill_color", "params": {"hex": "#2563eb"}}
