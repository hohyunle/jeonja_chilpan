from __future__ import annotations

import ast
import operator
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from .models import Diagnostic, ExecutionTrace, TraceStep, display_value, snapshot_variables
from .parser import parse_code, source_for


_MAX_CONTAINER_ITEMS = 10_000
_MAX_TEXT_LENGTH = 100_000
_MAX_INTEGER_BITS = 16_384
_MAX_TOTAL_OUTPUT_LENGTH = 1_000_000


class EducationalRuntimeError(Exception):
    def __init__(self, message: str, node: ast.AST | None = None):
        self.message = message
        self.node = node
        super().__init__(message)


class ExecutionLimitReached(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ReturnSignal(Exception):
    def __init__(self, value: Any):
        self.value = value


class InputCancelled(Exception):
    pass


class InputBroker:
    """Thread-safe bridge between the executor worker and the Qt input dialog."""

    def __init__(self, on_request: Callable[[str], None] | None = None):
        self._on_request = on_request
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._value: str | None = None
        self._cancelled = False

    def request(self, prompt: str) -> str:
        with self._lock:
            self._value = None
            self._cancelled = False
            self._event.clear()
        if self._on_request:
            self._on_request(prompt)
        self._event.wait()
        with self._lock:
            if self._cancelled:
                raise InputCancelled()
            return self._value or ""

    def submit(self, value: str) -> None:
        with self._lock:
            self._value = value
            self._cancelled = False
            self._event.set()

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            self._event.set()


@dataclass(slots=True)
class UserFunction:
    node: ast.FunctionDef


class EducationalExecutor:
    """Execute only the explicitly supported educational Python subset."""

    def __init__(
        self,
        code: str,
        *,
        input_broker: InputBroker | None = None,
        max_steps: int = 2_000,
        max_seconds: float = 2.5,
    ) -> None:
        self.code = code
        self.input_broker = input_broker
        self.max_steps = max_steps
        self.max_seconds = max_seconds
        self.trace = ExecutionTrace(code)
        self._started_at = 0.0
        self._frames: list[dict[str, Any]] = [{}]
        self._frame_names: list[str] = ["global"]
        self._functions: dict[str, UserFunction] = {}
        self._call_stack: list[str] = []
        self._output_characters = 0

    @property
    def variables(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for frame in self._frames:
            merged.update(frame)
        # Trace callers keep a "before" mapping while the real frame may be
        # mutated by append(), pop(), or list-item assignment. Return a snapshot
        # here so before/after states remain faithful to the teaching sequence.
        return snapshot_variables(merged)

    @property
    def scope_name(self) -> str:
        return self._frame_names[-1]

    def run(self) -> ExecutionTrace:
        parsed = parse_code(self.code)
        if not parsed.ok:
            self.trace.error = parsed.diagnostics[0]
            return self.trace
        assert parsed.tree is not None
        self._started_at = time.perf_counter()
        try:
            # Definitions are registered before executing statements so a function
            # may be called from a statement appearing after it.
            for statement in parsed.tree.body:
                if isinstance(statement, ast.FunctionDef):
                    self._functions[statement.name] = UserFunction(statement)
            self._exec_block(parsed.tree.body)
            self.trace.final_variables = dict(self.variables)
        except ExecutionLimitReached as exc:
            self.trace.stopped_reason = exc.reason
            self._record(
                "limit",
                "실행 제한으로 중단",
                None,
                {"reason": exc.reason},
                {"reason": exc.reason},
                check_limit=False,
            )
            self.trace.final_variables = dict(self.variables)
        except InputCancelled:
            self.trace.stopped_reason = "사용자가 입력을 취소했습니다."
            self._record(
                "cancelled",
                "입력 취소",
                None,
                {},
                {},
                {"reason": self.trace.stopped_reason},
                check_limit=False,
            )
            self.trace.final_variables = dict(self.variables)
        except EducationalRuntimeError as exc:
            line = getattr(exc.node, "lineno", None)
            column = getattr(exc.node, "col_offset", None)
            self.trace.error = Diagnostic(exc.message, line, column, "runtime")
            self._record(
                "error",
                "실행 오류",
                exc.node,
                self.variables,
                self.variables,
                {"message": exc.message},
                check_limit=False,
            )
            self.trace.final_variables = dict(self.variables)
        except Exception as exc:  # Defensive boundary for the UI.
            self.trace.error = Diagnostic(f"실행 중 예기치 않은 오류: {exc}", kind="runtime")
            self._record(
                "error",
                "실행 오류",
                None,
                self.variables,
                self.variables,
                {"message": str(exc)},
                check_limit=False,
            )
            self.trace.final_variables = dict(self.variables)
        return self.trace

    def _check_limits(self) -> None:
        if len(self.trace.steps) >= self.max_steps:
            raise ExecutionLimitReached(f"최대 실행 Step 수({self.max_steps})를 초과했습니다.")
        if time.perf_counter() - self._started_at > self.max_seconds:
            raise ExecutionLimitReached(f"최대 실행 시간({self.max_seconds:.1f}초)을 초과했습니다.")

    def _record(
        self,
        kind: str,
        title: str,
        node: ast.AST | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        details: dict[str, Any] | None = None,
        *,
        check_limit: bool = True,
    ) -> None:
        if check_limit:
            self._check_limits()
        self.trace.steps.append(
            TraceStep(
                index=len(self.trace.steps) + 1,
                kind=kind,
                title=title,
                line=getattr(node, "lineno", None) if node else None,
                source=source_for(self.code, node) if node else "",
                # ``variables`` already returns a deep snapshot. Copy only the
                # outer mapping here to avoid cloning every list twice per Step.
                variables_before=dict(before or {}),
                variables_after=dict(after or {}),
                details=details or {},
                scope=self.scope_name,
            )
        )

    def _exec_block(self, statements: list[ast.stmt]) -> None:
        for statement in statements:
            self._check_limits()
            self._exec_statement(statement)

    def _exec_statement(self, node: ast.stmt, *, branch_label: str | None = None) -> None:
        if isinstance(node, ast.FunctionDef):
            return
        if isinstance(node, ast.Assign):
            before = self.variables
            value = self._eval(node.value)
            for target in node.targets:
                self._assign(target, value)
            self._record(
                "assignment",
                "값 대입",
                node,
                before,
                self.variables,
                {"expression": source_for(self.code, node), "value": display_value(value)},
            )
            return
        if isinstance(node, ast.AugAssign):
            before = self.variables
            current = self._read_target(node.target)
            right = self._eval(node.value)
            value = self._apply_binary(node.op, current, right, node)
            self._assign(node.target, value)
            self._record(
                "assignment",
                "값 변경",
                node,
                before,
                self.variables,
                {"expression": source_for(self.code, node), "value": display_value(value)},
            )
            return
        if isinstance(node, ast.Expr):
            before = self.variables
            value = self._eval(node.value)
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                if node.value.func.id == "print":
                    self._record(
                        "output",
                        "출력",
                        node,
                        before,
                        self.variables,
                        {"output": self.trace.outputs[-1] if self.trace.outputs else ""},
                    )
                    return
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
                self._record(
                    "list",
                    "리스트 변경",
                    node,
                    before,
                    self.variables,
                    {"expression": source_for(self.code, node), "result": display_value(value)},
                )
                return
            self._record(
                "expression",
                "식 평가",
                node,
                before,
                self.variables,
                {"expression": source_for(self.code, node), "result": display_value(value)},
            )
            return
        if isinstance(node, ast.If):
            before = self.variables
            condition = self._eval(node.test)
            chosen = node.body if condition else node.orelse
            branch = branch_label or ("if" if condition else "else")
            self._record(
                "condition",
                "조건 판단",
                node,
                before,
                self.variables,
                {
                    "condition": source_for(self.code, node.test),
                    "result": bool(condition),
                    "branch": branch,
                },
            )
            if (
                not condition
                and len(node.orelse) == 1
                and isinstance(node.orelse[0], ast.If)
                and node.orelse[0].col_offset == node.col_offset
            ):
                self._exec_statement(node.orelse[0], branch_label="elif")
            else:
                self._exec_block(chosen)
            return
        if isinstance(node, ast.For):
            before = self.variables
            iterable = self._eval(node.iter)
            try:
                iterator = iter(iterable)
            except TypeError as exc:
                raise EducationalRuntimeError("for 반복 대상은 반복 가능한 값이어야 합니다.", node) from exc
            try:
                count = len(iterable)
            except TypeError:
                count = None
            self._record(
                "loop",
                "반복 시작",
                node,
                before,
                self.variables,
                {"loop_type": "for", "count": count, "iterable": display_value(iterable)},
            )
            iteration = 0
            for value in iterator:
                iteration += 1
                self._check_limits()
                before_iteration = self.variables
                self._assign(node.target, value)
                self._record(
                    "iteration",
                    f"반복 {iteration}회차",
                    node,
                    before_iteration,
                    self.variables,
                    {"loop_type": "for", "iteration": iteration, "variable": display_value(value)},
                )
                self._exec_block(node.body)
            self._exec_block(node.orelse)
            self._record(
                "loop_end",
                "반복 종료",
                node,
                self.variables,
                self.variables,
                {"loop_type": "for", "count": iteration},
            )
            return
        if isinstance(node, ast.While):
            iteration = 0
            while True:
                self._check_limits()
                before = self.variables
                condition = self._eval(node.test)
                self._record(
                    "condition",
                    "반복 조건 판단",
                    node,
                    before,
                    self.variables,
                    {
                        "condition": source_for(self.code, node.test),
                        "result": bool(condition),
                        "loop_type": "while",
                        "iteration": iteration + 1,
                    },
                )
                if not condition:
                    break
                iteration += 1
                self._exec_block(node.body)
            self._exec_block(node.orelse)
            self._record(
                "loop_end",
                "반복 종료",
                node,
                self.variables,
                self.variables,
                {"loop_type": "while", "count": iteration},
            )
            return
        if isinstance(node, ast.Return):
            value = self._eval(node.value) if node.value else None
            self._record(
                "return",
                "return 반환",
                node,
                self.variables,
                self.variables,
                {"value": display_value(value)},
            )
            raise ReturnSignal(value)
        raise EducationalRuntimeError(f"지원하지 않는 실행 문장입니다: {type(node).__name__}", node)

    def _eval(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self._lookup(node.id, node)
        if isinstance(node, ast.List):
            if len(node.elts) > _MAX_CONTAINER_ITEMS:
                raise EducationalRuntimeError("리스트가 너무 커서 실행할 수 없습니다.", node)
            values = []
            for element in node.elts:
                self._check_limits()
                values.append(self._eval(element))
            return values
        if isinstance(node, ast.Subscript):
            value = self._eval(node.value)
            index = self._eval(node.slice)
            if not isinstance(index, int):
                raise EducationalRuntimeError("리스트 인덱스는 정수여야 합니다.", node)
            if not isinstance(value, list):
                raise EducationalRuntimeError("리스트 변수에 대한 인덱싱만 지원합니다.", node)
            try:
                return value[index]
            except (IndexError, KeyError, TypeError) as exc:
                raise EducationalRuntimeError("리스트 인덱스 범위를 벗어났습니다.", node) from exc
        if isinstance(node, ast.BinOp):
            return self._apply_binary(node.op, self._eval(node.left), self._eval(node.right), node)
        if isinstance(node, ast.UnaryOp):
            value = self._eval(node.operand)
            try:
                if isinstance(node.op, ast.UAdd):
                    return +value
                if isinstance(node.op, ast.USub):
                    return -value
                if isinstance(node.op, ast.Not):
                    return not value
            except (TypeError, ValueError) as exc:
                raise EducationalRuntimeError("단항 연산을 적용할 수 없습니다.", node) from exc
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result = True
                for value_node in node.values:
                    result = self._eval(value_node)
                    if not result:
                        break
                return result
            result = False
            for value_node in node.values:
                result = self._eval(value_node)
                if result:
                    break
            return result
        if isinstance(node, ast.Compare):
            left = self._eval(node.left)
            result = True
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator)
                result = result and self._apply_compare(op, left, right, node)
                left = right
                if not result:
                    break
            return result
        if isinstance(node, ast.Call):
            return self._call(node)
        raise EducationalRuntimeError(f"지원하지 않는 표현식입니다: {type(node).__name__}", node)

    def _apply_binary(self, op: ast.operator, left: Any, right: Any, node: ast.AST) -> Any:
        operations: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }
        function = operations.get(type(op))
        if function is None:
            raise EducationalRuntimeError("지원하지 않는 산술 연산입니다.", node)
        if isinstance(op, ast.Pow) and isinstance(right, int) and right > _MAX_INTEGER_BITS:
            raise EducationalRuntimeError(
                f"거듭제곱 지수가 너무 큽니다(최대 {_MAX_INTEGER_BITS}).", node
            )
        if isinstance(op, ast.Mult):
            if isinstance(left, (str, list)) and isinstance(right, int) and right > 0:
                max_size = _MAX_CONTAINER_ITEMS if isinstance(left, list) else _MAX_TEXT_LENGTH
                if len(left) * right > max_size:
                    raise EducationalRuntimeError("반복 결과가 너무 큽니다.", node)
            if isinstance(right, (str, list)) and isinstance(left, int) and left > 0:
                max_size = _MAX_CONTAINER_ITEMS if isinstance(right, list) else _MAX_TEXT_LENGTH
                if len(right) * left > max_size:
                    raise EducationalRuntimeError("반복 결과가 너무 큽니다.", node)
        try:
            result = function(left, right)
        except (TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
            raise EducationalRuntimeError(f"연산을 수행할 수 없습니다: {exc}", node) from exc
        if isinstance(result, int) and result.bit_length() > _MAX_INTEGER_BITS:
            raise EducationalRuntimeError("정수 결과가 너무 큽니다.", node)
        if isinstance(result, str) and len(result) > _MAX_TEXT_LENGTH:
            raise EducationalRuntimeError("문자열 결과가 너무 깁니다.", node)
        if isinstance(result, list) and len(result) > _MAX_CONTAINER_ITEMS:
            raise EducationalRuntimeError("리스트 결과가 너무 큽니다.", node)
        return result

    def _apply_compare(self, op: ast.cmpop, left: Any, right: Any, node: ast.AST) -> bool:
        operations: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
            ast.Eq: operator.eq,
            ast.NotEq: operator.ne,
            ast.Lt: operator.lt,
            ast.LtE: operator.le,
            ast.Gt: operator.gt,
            ast.GtE: operator.ge,
        }
        function = operations.get(type(op))
        if function is None:
            raise EducationalRuntimeError("지원하지 않는 비교 연산입니다.", node)
        try:
            return bool(function(left, right))
        except (TypeError, ValueError) as exc:
            raise EducationalRuntimeError(f"비교할 수 없습니다: {exc}", node) from exc

    def _call(self, node: ast.Call) -> Any:
        if isinstance(node.func, ast.Attribute):
            receiver = self._eval(node.func.value)
            arguments = [self._eval(argument) for argument in node.args]
            if node.func.attr == "append":
                if not isinstance(receiver, list) or len(arguments) != 1:
                    raise EducationalRuntimeError("append()는 리스트와 인자 하나가 필요합니다.", node)
                if len(receiver) >= _MAX_CONTAINER_ITEMS:
                    raise EducationalRuntimeError("리스트가 너무 커서 append()할 수 없습니다.", node)
                receiver.append(arguments[0])
                return None
            if node.func.attr == "pop":
                if not isinstance(receiver, list) or arguments:
                    raise EducationalRuntimeError("pop()은 리스트에서 인자 없이 사용합니다.", node)
                if not receiver:
                    raise EducationalRuntimeError("빈 리스트에서는 pop()할 수 없습니다.", node)
                return receiver.pop()
            raise EducationalRuntimeError(f"지원하지 않는 메서드입니다: {node.func.attr}()", node)
        if not isinstance(node.func, ast.Name):
            raise EducationalRuntimeError("지원하지 않는 함수 호출입니다.", node)
        name = node.func.id
        arguments = [self._eval(argument) for argument in node.args]
        if name == "print":
            text = " ".join(str(argument) for argument in arguments)
            if self._output_characters + len(text) > _MAX_TOTAL_OUTPUT_LENGTH:
                raise EducationalRuntimeError("출력이 너무 많아 실행을 중단했습니다.", node)
            self._output_characters += len(text)
            self.trace.outputs.append(text)
            return None
        if name == "input":
            if len(arguments) > 1:
                raise EducationalRuntimeError("input()은 프롬프트 하나만 받을 수 있습니다.", node)
            prompt = str(arguments[0]) if arguments else ""
            if self.input_broker is None:
                raise EducationalRuntimeError("현재 실행 환경에서 input()을 사용할 수 없습니다.", node)
            value = self.input_broker.request(prompt)
            self._record(
                "input",
                "사용자 입력",
                node,
                self.variables,
                self.variables,
                {"prompt": prompt, "value": value},
            )
            return value
        if name in {"int", "float", "str"}:
            if len(arguments) != 1:
                raise EducationalRuntimeError(f"{name}()은 인자 하나가 필요합니다.", node)
            try:
                return {"int": int, "float": float, "str": str}[name](arguments[0])
            except (TypeError, ValueError, OverflowError) as exc:
                raise EducationalRuntimeError(f"{name}() 변환에 실패했습니다: {exc}", node) from exc
        if name == "range":
            if not 1 <= len(arguments) <= 3 or not all(isinstance(value, int) for value in arguments):
                raise EducationalRuntimeError("range()는 정수 인자를 1~3개 받아야 합니다.", node)
            try:
                return range(*arguments)
            except (TypeError, ValueError) as exc:
                raise EducationalRuntimeError(f"range()를 만들 수 없습니다: {exc}", node) from exc
        if name == "len":
            if len(arguments) != 1:
                raise EducationalRuntimeError("len()은 인자 하나가 필요합니다.", node)
            try:
                return len(arguments[0])
            except TypeError as exc:
                raise EducationalRuntimeError("len()은 길이가 있는 값에만 사용할 수 있습니다.", node) from exc
        if name in self._functions:
            return self._call_user_function(name, arguments, node)
        raise EducationalRuntimeError(f"지원하지 않는 함수입니다: {name}()", node)

    def _call_user_function(self, name: str, arguments: list[Any], node: ast.Call) -> Any:
        function = self._functions[name].node
        if name in self._call_stack:
            raise EducationalRuntimeError("재귀 호출은 지원하지 않습니다.", node)
        parameters = [argument.arg for argument in function.args.args]
        if len(parameters) != len(arguments):
            raise EducationalRuntimeError(
                f"{name}()은 인자 {len(parameters)}개를 받아야 합니다.", node
            )
        self._record(
            "function_call",
            f"{name}() 호출",
            node,
            self.variables,
            self.variables,
            {"function": name, "arguments": [display_value(value) for value in arguments]},
        )
        frame = dict(zip(parameters, arguments))
        self._frames.append(frame)
        self._frame_names.append(name)
        self._call_stack.append(name)
        self._record(
            "parameter",
            "매개변수 전달",
            function,
            self.variables,
            self.variables,
            {"function": name, "parameters": {key: display_value(value) for key, value in frame.items()}},
        )
        try:
            self._exec_block(function.body)
        except ReturnSignal as signal:
            return_value = signal.value
        else:
            return_value = None
        finally:
            self._call_stack.pop()
            self._frames.pop()
            self._frame_names.pop()
        self._record(
            "function_return",
            f"{name}() 반환",
            function,
            self.variables,
            self.variables,
            {"function": name, "value": display_value(return_value)},
        )
        return return_value

    def _lookup(self, name: str, node: ast.AST) -> Any:
        for frame in reversed(self._frames):
            if name in frame:
                return frame[name]
        raise EducationalRuntimeError(f"정의되지 않은 변수입니다: {name}", node)

    def _read_target(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Name):
            return self._lookup(node.id, node)
        if isinstance(node, ast.Subscript):
            return self._eval(node)
        raise EducationalRuntimeError("읽을 수 없는 대입 대상입니다.", node)

    def _assign(self, target: ast.AST, value: Any) -> None:
        if isinstance(target, ast.Name):
            self._frames[-1][target.id] = value
            return
        if isinstance(target, ast.Subscript):
            container = self._eval(target.value)
            index = self._eval(target.slice)
            if not isinstance(container, list) or not isinstance(index, int):
                raise EducationalRuntimeError("리스트와 정수 인덱스가 필요합니다.", target)
            try:
                container[index] = value
            except IndexError as exc:
                raise EducationalRuntimeError("리스트 인덱스 범위를 벗어났습니다.", target) from exc
            return
        raise EducationalRuntimeError("변수 또는 리스트 항목에만 대입할 수 있습니다.", target)
