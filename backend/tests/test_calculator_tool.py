import pytest

from app.agent.tools import calculate


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("2 + 2", 4),
        ("(10000 - 2500) / 400", 18.75),
        ("1000 * (1 + 0.05/12) ** (12*5)", 1000 * (1 + 0.05 / 12) ** 60),
        ("round(1234.5678, 2)", 1234.57),
        ("abs(-42)", 42),
        ("max(1, 2, 3)", 3),
        ("-5 + 3", -2),
    ],
)
def test_calculate_evaluates_arithmetic(expression, expected):
    result = calculate(expression)
    assert result["expression"] == expression
    assert result["result"] == pytest.approx(expected)
    assert "error" not in result


def test_calculate_rejects_division_by_zero():
    result = calculate("1 / 0")
    assert "error" in result
    assert "division by zero" in result["error"]


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "open('/etc/passwd').read()",
        "().__class__.__bases__",
        "some_variable + 1",
        "[1, 2, 3]",
        "9 ** 9 ** 9",  # blocked by the exponent cap, not just slow
    ],
)
def test_calculate_rejects_anything_outside_the_arithmetic_grammar(expression):
    result = calculate(expression)
    assert "error" in result
    assert "result" not in result


def test_calculate_rejects_malformed_expressions():
    result = calculate("2 +* 2")
    assert "error" in result
