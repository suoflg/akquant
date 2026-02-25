import ast
from typing import Any

import polars as pl

from .ops import OPS_MAP


class ExpressionParser:
    """
    Parses string expressions into Polars Expressions.

    Example: "Rank(Ts_Mean(Close, 10))" -> pl.Expr.
    """

    def parse(self, expr_str: str) -> pl.Expr:
        """Parse a factor expression string."""
        # Clean up string
        expr_str = expr_str.strip()

        # Parse using Python's AST
        try:
            tree = ast.parse(expr_str, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid expression syntax: {expr_str}") from e

        return self._visit(tree.body)

    def _visit(self, node: Any) -> Any:
        # Handle Function Calls
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only simple function calls are supported")
            func_name = node.func.id

            if func_name not in OPS_MAP:
                raise ValueError(f"Unknown function: {func_name}")

            args = [self._visit(arg) for arg in node.args]
            return OPS_MAP[func_name](*args)

        # Handle Variables (Columns)
        elif isinstance(node, ast.Name):
            # Convention: Variable names are column names.
            # Convert "Close" -> "close" to match standard lowercase columns
            return pl.col(node.id.lower())

        # Handle Constants
        elif isinstance(node, ast.Constant):  # Python 3.8+
            return node.value
        # Python < 3.8 compat (Num, Str, etc.) - probably not needed for modern envs
        elif isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Str):
            return node.s

        # Handle Binary Operators (+, -, *, /)
        elif isinstance(node, ast.BinOp):
            left = self._visit(node.left)
            right = self._visit(node.right)

            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                return left * right
            elif isinstance(node.op, ast.Div):
                return left / right
            elif isinstance(node.op, ast.Pow):
                return left**right
            elif isinstance(node.op, ast.Mod):
                return left % right
            else:
                raise ValueError(f"Unsupported binary operator: {type(node.op)}")

        # Handle Unary Operators (-, ~)
        elif isinstance(node, ast.UnaryOp):
            operand = self._visit(node.operand)

            if isinstance(node.op, ast.USub):
                return -operand
            elif isinstance(node.op, ast.Not):
                return ~operand  # Logical NOT
            else:
                raise ValueError(f"Unsupported unary operator: {type(node.op)}")

        # Handle Comparisons (<, >, ==)
        elif isinstance(node, ast.Compare):
            if len(node.ops) != 1:
                raise ValueError("Chained comparisons not supported")

            left = self._visit(node.left)
            right = self._visit(node.comparators[0])
            op = node.ops[0]

            if isinstance(op, ast.Lt):
                return left < right
            elif isinstance(op, ast.LtE):
                return left <= right
            elif isinstance(op, ast.Gt):
                return left > right
            elif isinstance(op, ast.GtE):
                return left >= right
            elif isinstance(op, ast.Eq):
                return left == right
            elif isinstance(op, ast.NotEq):
                return left != right
            else:
                raise ValueError(f"Unsupported comparison operator: {type(op)}")

        # Handle Conditional Expression (IfExp): x if cond else y
        # Mapped to pl.when(cond).then(x).otherwise(y)
        elif isinstance(node, ast.IfExp):
            test = self._visit(node.test)
            body = self._visit(node.body)
            orelse = self._visit(node.orelse)
            return pl.when(test).then(body).otherwise(orelse)

        raise ValueError(f"Unsupported expression node type: {type(node)}")
