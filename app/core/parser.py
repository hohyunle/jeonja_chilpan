from __future__ import annotations

import ast
from dataclasses import dataclass

from .models import Diagnostic


class UnsupportedSyntax(Exception):
    def __init__(self, message: str, node: ast.AST | None = None):
        self.message = message
        self.node = node
        super().__init__(message)


@dataclass(slots=True)
class ParseResult:
    tree: ast.Module | None
    diagnostics: list[Diagnostic]

    @property
    def ok(self) -> bool:
        return self.tree is not None and not self.diagnostics


_ALLOWED_NODES = {
    ast.Module,
    ast.Expr,
    ast.Assign,
    ast.AugAssign,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.List,
    ast.Subscript,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.If,
    ast.For,
    ast.While,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Return,
    ast.Call,
    ast.keyword,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
}

_ALLOWED_CONSTANT_TYPES = (int, float, str, bool, type(None))
_ALLOWED_CALL_NAMES = {"print", "input", "int", "float", "str", "range", "len"}
_ALLOWED_LIST_METHODS = {"append", "pop"}


def _node_location(node: ast.AST) -> tuple[int | None, int | None]:
    return getattr(node, "lineno", None), getattr(node, "col_offset", None)


class SupportedSyntaxValidator(ast.NodeVisitor):
    """Reject unsupported syntax before the educational executor sees it."""

    def __init__(self) -> None:
        self.function_depth = 0
        self.loop_depth = 0

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) not in _ALLOWED_NODES:
            raise UnsupportedSyntax(
                f"지원하지 않는 Python 문법입니다: {type(node).__name__}", node
            )
        super().generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, _ALLOWED_CONSTANT_TYPES):
            raise UnsupportedSyntax("정수, 실수, 문자열, 불리언만 지원합니다.", node)

    def visit_Name(self, node: ast.Name) -> None:
        if not node.id.isidentifier():
            raise UnsupportedSyntax("올바른 변수 이름이 아닙니다.", node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if not node.targets:
            raise UnsupportedSyntax("대입 대상이 없습니다.", node)
        for target in node.targets:
            self._visit_assignment_target(target)
        self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._visit_assignment_target(node.target)
        self.visit(node.value)
        if type(node.op) not in {ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod}:
            raise UnsupportedSyntax("지원하지 않는 복합 대입 연산자입니다.", node)

    def _visit_assignment_target(self, node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            return
        if isinstance(node, ast.Subscript):
            self.visit_Subscript(node)
            return
        raise UnsupportedSyntax("변수 또는 리스트 항목에만 대입할 수 있습니다.", node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self.visit(node.value)
        self.visit(node.slice)
        if not isinstance(node.value, ast.Name):
            raise UnsupportedSyntax("리스트 변수에 대한 인덱싱만 지원합니다.", node)

    def visit_Call(self, node: ast.Call) -> None:
        if node.keywords:
            raise UnsupportedSyntax("키워드 인자는 지원하지 않습니다.", node)
        if isinstance(node.func, ast.Name):
            if node.func.id not in _ALLOWED_CALL_NAMES:
                # User-defined calls are validated at runtime against definitions.
                self.visit(node.func)
            for argument in node.args:
                self.visit(argument)
            return
        if isinstance(node.func, ast.Attribute):
            if node.func.attr not in _ALLOWED_LIST_METHODS:
                raise UnsupportedSyntax(f"지원하지 않는 메서드입니다: {node.func.attr}()", node)
            if not isinstance(node.func.value, ast.Name):
                raise UnsupportedSyntax("리스트 변수의 메서드만 지원합니다.", node)
            self.visit(node.func.value)
            for argument in node.args:
                self.visit(argument)
            return
        raise UnsupportedSyntax("지원하지 않는 함수 호출 형태입니다.", node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self.function_depth > 0:
            raise UnsupportedSyntax("중첩 함수 정의는 지원하지 않습니다.", node)
        if node.col_offset != 0:
            raise UnsupportedSyntax("함수 정의는 코드의 최상위에서만 지원합니다.", node)
        if not node.name.isidentifier():
            raise UnsupportedSyntax("올바른 함수 이름이 아닙니다.", node)
        if node.decorator_list or node.returns is not None or node.type_comment:
            raise UnsupportedSyntax("데코레이터와 타입 주석은 지원하지 않습니다.", node)
        if node.args.vararg or node.args.kwarg or node.args.kwonlyargs or node.args.defaults:
            raise UnsupportedSyntax("단순한 위치 매개변수만 지원합니다.", node)
        self.function_depth += 1
        self.visit(node.args)
        for statement in node.body:
            self.visit(statement)
        self.function_depth -= 1

    def visit_Return(self, node: ast.Return) -> None:
        if self.function_depth == 0:
            raise UnsupportedSyntax("return은 함수 안에서만 사용할 수 있습니다.", node)
        if node.value is not None:
            self.visit(node.value)

    def visit_For(self, node: ast.For) -> None:
        if not isinstance(node.target, ast.Name):
            raise UnsupportedSyntax("for 반복 변수는 하나의 변수여야 합니다.", node)
        self.visit(node.target)
        self.visit(node.iter)
        self.loop_depth += 1
        for statement in node.body:
            self.visit(statement)
        if node.orelse:
            for statement in node.orelse:
                self.visit(statement)
        self.loop_depth -= 1

    def visit_While(self, node: ast.While) -> None:
        self.visit(node.test)
        self.loop_depth += 1
        for statement in node.body:
            self.visit(statement)
        if node.orelse:
            for statement in node.orelse:
                self.visit(statement)
        self.loop_depth -= 1


def parse_code(code: str) -> ParseResult:
    if not code.strip():
        return ParseResult(None, [Diagnostic("실행할 코드가 없습니다.")])
    try:
        tree = ast.parse(code, mode="exec", type_comments=False)
    except SyntaxError as exc:
        return ParseResult(
            None,
            [
                Diagnostic(
                    message=exc.msg or "문법 오류입니다.",
                    line=exc.lineno,
                    column=exc.offset - 1 if exc.offset else None,
                    kind="syntax",
                )
            ],
        )
    try:
        SupportedSyntaxValidator().visit(tree)
    except UnsupportedSyntax as exc:
        line, column = _node_location(exc.node) if exc.node else (None, None)
        return ParseResult(None, [Diagnostic(exc.message, line, column, "unsupported")])
    return ParseResult(tree, [])


def source_for(code: str, node: ast.AST) -> str:
    return ast.get_source_segment(code, node) or ""
