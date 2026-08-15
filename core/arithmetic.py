"""
M.O.N.D.A.Y. — arithmetic, evaluated rather than executed.

The legacy calculator branch in `core/planner.py` ran::

    res_val = eval(expr, {"__builtins__": {}}, {})

on whatever a `[\\d\\.\\s\\+\\-\\*\\/\\(\\)\\^]+` regex had captured. Two things
were wrong with that, and only one of them is the obvious one.

**`^` is not exponentiation in Python.** It is bitwise XOR. `calculate 2^3`
answered **1**, and `calculate 5^2` answered **7** — wrong, confidently, with a
tick mark in front. Nobody typing `2^3` into an assistant means XOR.

**`eval` was reachable with more than the regex suggests.** Emptying
`__builtins__` blocks `__import__`, but the expression still ran through the
CPython evaluator, so `9**9**9` hangs the process on an integer the machine
cannot hold, and any widening of that character class — the kind of change that
looks harmless in review — hands the evaluator real syntax.

Parsing to an AST and walking it removes both problems: `^` can mean what the
user meant, and there is no expression this module can be given that reaches
anything but the operators listed in `_BINARY`. What it cannot evaluate, it
declines to evaluate.
"""

from __future__ import annotations

import ast
import operator
from typing import Union

Number = Union[int, float]

#: The only operations that exist here. Anything else raises.
_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

#: Refused before evaluation. 2**4000 is instant; 9**9**9 is not, and the
#: process has no way back once it starts. Bounding the exponent is cheaper and
#: more predictable than trying to interrupt it.
MAX_EXPONENT = 1000


class ArithmeticRefused(ValueError):
    """The expression was not something this module will evaluate."""


def _eval(node: ast.AST) -> Number:
    if isinstance(node, ast.Expression):
        return _eval(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ArithmeticRefused("only numbers are allowed")
        return node.value

    if isinstance(node, ast.UnaryOp):
        op = _UNARY.get(type(node.op))
        if op is None:
            raise ArithmeticRefused(f"unsupported unary operator {type(node.op).__name__}")
        return op(_eval(node.operand))

    if isinstance(node, ast.BinOp):
        op = _BINARY.get(type(node.op))
        if op is None:
            raise ArithmeticRefused(f"unsupported operator {type(node.op).__name__}")
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ArithmeticRefused(
                f"exponent {right} is above the {MAX_EXPONENT} limit"
            )
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ArithmeticRefused("division by zero")
        return op(left, right)

    raise ArithmeticRefused(f"unsupported expression {type(node).__name__}")


def evaluate(expression: str) -> Number:
    """Evaluates an arithmetic expression, or raises `ArithmeticRefused`.

    `^` is read as exponentiation, because that is what someone typing it into an
    assistant means. Python's XOR is not reachable from here at all.
    """
    text = (expression or "").strip()
    if not text:
        raise ArithmeticRefused("nothing to calculate")

    text = text.replace("^", "**").replace("×", "*").replace("÷", "/")

    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ArithmeticRefused(f"that isn't an expression I can read: {exc.msg}") from exc

    result = _eval(tree)
    # 12 / 4 is 3, not 3.0 — the user asked a question about numbers, not about
    # floating point.
    if isinstance(result, float) and result.is_integer():
        return int(result)
    return result


def format_result(value: Number) -> str:
    """Renders a result without trailing float noise."""
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)
