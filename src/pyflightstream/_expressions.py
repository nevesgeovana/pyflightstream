"""The arithmetic a pproc ``[equations]`` entry may write, parsed and never executed.

An expression is user text out of an input artifact, so it is never handed to
``eval``. It is parsed with :mod:`ast` and walked: a node outside the small
grammar below is refused by name, when the artifact is READ, and the same walk
evaluates it at post. One grammar, so the loader and the evaluator cannot
disagree about what an expression is.

THE GRAMMAR: numbers, names, ``+ - * / **``, unary minus and plus, parentheses,
and a call of one of :data:`ALLOWED_FUNCTIONS` with positional arguments.
Nothing else: no attribute, no subscript, no comparison, no string, no lambda.

A floor module: it imports the package's errors and the standard library only,
so both the ``cases`` layer (which validates) and the ``post`` layer (which
evaluates) may use it.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable

from pyflightstream._errors import InputArtifactError

__all__ = [
    "ALLOWED_FUNCTIONS",
    "evaluate_expression",
    "expression_symbols",
    "parse_expression",
]

#: The functions an expression may call, and what each one is. Angles are in
#: radians for the three trigonometric ones; ``radians`` and ``degrees`` convert.
ALLOWED_FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "radians": math.radians,
    "degrees": math.degrees,
    "min": min,
    "max": max,
}

_BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.Pow: lambda left, right: left**right,
}
_UNARY: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.USub: lambda value: -value,
    ast.UAdd: lambda value: +value,
}

_GRAMMAR = "numbers, names, + - * / **, unary minus, parentheses and the functions " + ", ".join(
    ALLOWED_FUNCTIONS
)


def _refuse(expression: str, what: str) -> InputArtifactError:
    return InputArtifactError(
        f"the expression {expression!r} {what}. An [equations] expression is arithmetic "
        f"and nothing else: {_GRAMMAR}. Rewrite it with those."
    )


def _check(node: ast.AST, expression: str) -> None:
    """Refuse the first node of ``node`` that is outside the grammar."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise _refuse(expression, f"holds {node.value!r}, which is not a number")
        return
    if isinstance(node, ast.Name):
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINARY:
            raise _refuse(expression, f"uses the operator {type(node.op).__name__}")
        _check(node.left, expression)
        _check(node.right, expression)
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARY:
            raise _refuse(expression, f"uses the operator {type(node.op).__name__}")
        _check(node.operand, expression)
        return
    if isinstance(node, ast.Call):
        called = node.func.id if isinstance(node.func, ast.Name) else None
        if called not in ALLOWED_FUNCTIONS:
            shown = called if called is not None else ast.unparse(node.func)
            raise _refuse(expression, f"calls {shown!r}, which is not one of its functions")
        if node.keywords or not node.args:
            raise _refuse(expression, f"calls {called}() without plain positional arguments")
        for argument in node.args:
            if isinstance(argument, ast.Starred):
                raise _refuse(expression, f"unpacks an argument of {called}()")
            _check(argument, expression)
        return
    raise _refuse(expression, f"holds a {type(node).__name__}, which is not arithmetic")


def parse_expression(expression: str) -> ast.expr:
    """Return the parsed body of ``expression``, every node inside the grammar.

    Raises
    ------
    InputArtifactError
        If the text is not one Python expression, or holds a construct outside
        the grammar. The message names the construct and lists the grammar.

    Examples
    --------
    >>> type(parse_expression("2 * (CT + 1)")).__name__
    'BinOp'
    """
    try:
        tree = ast.parse(str(expression).strip(), mode="eval")
    except SyntaxError as error:
        raise _refuse(expression, f"is not one arithmetic expression ({error.msg})") from error
    _check(tree.body, expression)
    return tree.body


def expression_symbols(expression: str) -> list[str]:
    """Return the names ``expression`` READS, once each, in order of appearance.

    A called function is not a symbol: ``sqrt(CT)`` reads ``CT`` alone.

    Examples
    --------
    >>> expression_symbols("sqrt(FX**2 + FY**2) / FX")
    ['FX', 'FY']
    """
    body = parse_expression(expression)
    called = {id(node.func) for node in ast.walk(body) if isinstance(node, ast.Call)}
    read = [
        node for node in ast.walk(body) if isinstance(node, ast.Name) and id(node) not in called
    ]
    # `ast.walk` is breadth-first; the order a reader expects is the text's own.
    read.sort(key=lambda node: (node.lineno, node.col_offset))
    return list(dict.fromkeys(node.id for node in read))


def evaluate_expression(expression: str, resolve: Callable[[str], float]) -> float:
    """Evaluate ``expression``, asking ``resolve`` for the value of each name.

    ``resolve`` raises whatever refusal the caller wants for a name it cannot
    answer; this function adds nothing to it. A division by zero, a root of a
    negative or an overflow is an :class:`ArithmeticError` or a
    :class:`ValueError` of the standard library and is left to the caller, who
    knows which equation and which row it happened on.

    Examples
    --------
    >>> evaluate_expression("-CT * 2 + max(1, 3)", {"CT": 0.5}.__getitem__)
    2.0
    """

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Constant):
            return float(node.value)  # type: ignore[arg-type]
        if isinstance(node, ast.Name):
            return float(resolve(node.id))
        if isinstance(node, ast.BinOp):
            return float(_BINARY[type(node.op)](walk(node.left), walk(node.right)))
        if isinstance(node, ast.UnaryOp):
            return float(_UNARY[type(node.op)](walk(node.operand)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = ALLOWED_FUNCTIONS[node.func.id]
            return float(function(*(walk(argument) for argument in node.args)))
        raise _refuse(expression, f"holds a {type(node).__name__}, which is not arithmetic")

    return walk(parse_expression(expression))
