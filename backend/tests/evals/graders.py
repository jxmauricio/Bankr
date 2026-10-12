"""Deterministic graders for agent evals.

Each grader takes (reply, sources) -- the final text and the transcript of
tool calls run_agent_turn returns -- and gives back (ok, detail). They grade
the outcome (what the user would read, and what the tools returned), never
the exact order of tool calls, so a different-but-valid route still passes.
"""

import re
from typing import Callable

from app.api.chat import _MONEY, _citations

Grader = Callable[[str, list[dict]], tuple[bool, str]]


def _amounts(reply: str) -> list[tuple[str, float]]:
    return [(m.group(), abs(float(m.group().replace("$", "").replace(",", "")))) for m in _MONEY.finditer(reply or "")]


def _same_amount(text: str, amount: float, expected: float) -> bool:
    # Same rule as _citations: exact to the cent, or rounds to it when the
    # reply drops the cents ("about $236").
    if "." in text:
        return round(amount, 2) == round(expected, 2)
    return amount == round(expected) or amount == expected


def says_amount(expected: float) -> Grader:
    def grade(reply, sources):
        found = [t for t, a in _amounts(reply)]
        ok = any(_same_amount(t, a, expected) for t, a in _amounts(reply))
        return ok, f"expected ${expected:,.2f}; reply has {found or 'no $ figures'}"

    grade.__name__ = f"says_amount({expected:,.2f})"
    return grade


def never_says_amount(trap: float, why: str = "") -> Grader:
    def grade(reply, sources):
        hit = [t for t, a in _amounts(reply) if _same_amount(t, a, trap)]
        return not hit, f"trap ${trap:,.2f}{f' ({why})' if why else ''} appeared as {hit}" if hit else "ok"

    grade.__name__ = f"never_says_amount({trap:,.2f})"
    return grade


def only_zero_amounts() -> Grader:
    def grade(reply, sources):
        nonzero = [t for t, a in _amounts(reply) if a != 0]
        return not nonzero, f"non-zero figures {nonzero}" if nonzero else "ok"

    grade.__name__ = "only_zero_amounts"
    return grade


def no_amounts() -> Grader:
    def grade(reply, sources):
        found = [t for t, _ in _amounts(reply)]
        return not found, f"unexpected figures {found}" if found else "ok"

    grade.__name__ = "no_amounts"
    return grade


def figures_cited() -> Grader:
    """Every $ figure in the reply traces to a tool result -- the same check
    the chat UI uses to mark a number as verified."""

    def grade(reply, sources):
        cited = {c["text"] for c in _citations(reply, sources)}
        uncited = sorted({t for t, _ in _amounts(reply)} - cited)
        return not uncited, f"uncited figures {uncited}" if uncited else "ok"

    grade.__name__ = "figures_cited"
    return grade


def called_tool(name: str) -> Grader:
    def grade(reply, sources):
        tools = [s["tool"] for s in sources]
        return name in tools, f"tools called: {tools}"

    grade.__name__ = f"called_tool({name})"
    return grade


def never_called_tool(name: str) -> Grader:
    def grade(reply, sources):
        tools = [s["tool"] for s in sources]
        return name not in tools, f"tools called: {tools}"

    grade.__name__ = f"never_called_tool({name})"
    return grade


def called_no_tools() -> Grader:
    def grade(reply, sources):
        tools = [s["tool"] for s in sources]
        return not tools, f"tools called: {tools}"

    grade.__name__ = "called_no_tools"
    return grade


def matches(pattern: str) -> Grader:
    regex = re.compile(pattern, re.IGNORECASE)

    def grade(reply, sources):
        return bool(regex.search(reply or "")), f"/{pattern}/ not found"

    grade.__name__ = f"matches(/{pattern}/)"
    return grade


def never_matches(pattern: str) -> Grader:
    regex = re.compile(pattern, re.IGNORECASE)

    def grade(reply, sources):
        m = regex.search(reply or "")
        return m is None, f"/{pattern}/ matched {m.group()!r}" if m else "ok"

    grade.__name__ = f"never_matches(/{pattern}/)"
    return grade


def any_of(*graders: Grader) -> Grader:
    def grade(reply, sources):
        results = [g(reply, sources) for g in graders]
        return any(ok for ok, _ in results), "; ".join(f"{g.__name__}: {d}" for g, (_, d) in zip(graders, results))

    grade.__name__ = "any_of(" + ", ".join(g.__name__ for g in graders) + ")"
    return grade


def all_of(*graders: Grader) -> Grader:
    def grade(reply, sources):
        results = [g(reply, sources) for g in graders]
        return all(ok for ok, _ in results), "; ".join(f"{g.__name__}: {d}" for g, (_, d) in zip(graders, results))

    grade.__name__ = "all_of(" + ", ".join(g.__name__ for g in graders) + ")"
    return grade
