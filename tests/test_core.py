from __future__ import annotations

import unittest

from app.core.executor import EducationalExecutor
from app.core.models import CodeSession
from app.core.ocr import OcrLine, OcrService
from app.core.parser import parse_code


class CoreExecutionTests(unittest.TestCase):
    def test_assignment_and_expression_trace(self) -> None:
        trace = EducationalExecutor("a = 2\nb = 4\nx = a + b").run()
        self.assertIsNone(trace.error)
        self.assertEqual(trace.final_variables["x"], 6)
        self.assertEqual(len(trace.steps), 3)
        self.assertEqual(trace.steps[-1].details["value"], "6")

    def test_if_records_branch(self) -> None:
        trace = EducationalExecutor("x = 10\nif x > 5:\n    y = 20\nelse:\n    y = 30").run()
        self.assertIsNone(trace.error)
        condition = next(step for step in trace.steps if step.kind == "condition")
        self.assertTrue(condition.details["result"])
        self.assertEqual(trace.final_variables["y"], 20)

    def test_elif_branch_executes_in_order(self) -> None:
        trace = EducationalExecutor(
            "x = 5\nif x > 5:\n    y = 1\nelif x == 5:\n    y = 2\nelse:\n    y = 3"
        ).run()
        self.assertIsNone(trace.error)
        self.assertEqual(trace.final_variables["y"], 2)
        self.assertEqual(
            [step.details.get("branch") for step in trace.steps if step.kind == "condition"],
            ["else", "elif"],
        )

    def test_for_and_while(self) -> None:
        code = "x = 0\nfor i in range(3):\n    x = x + i\nwhile x < 4:\n    x = x + 1"
        trace = EducationalExecutor(code).run()
        self.assertIsNone(trace.error)
        self.assertEqual(trace.final_variables["x"], 4)
        self.assertIn("loop", trace.kinds)
        self.assertIn("loop_end", trace.kinds)

    def test_list_and_function(self) -> None:
        code = (
            "def add(a, b):\n"
            "    return a + b\n\n"
            "numbers = [1, 2]\n"
            "numbers.append(3)\n"
            "x = add(numbers[1], 4)\n"
            "numbers.pop()"
        )
        trace = EducationalExecutor(code).run()
        self.assertIsNone(trace.error)
        self.assertEqual(trace.final_variables["x"], 6)
        self.assertEqual(trace.final_variables["numbers"], [1, 2])
        self.assertIn("function_call", trace.kinds)
        self.assertIn("list", trace.kinds)

    def test_trace_keeps_mutable_list_before_state(self) -> None:
        trace = EducationalExecutor("items = [1]\nitems.append(2)").run()
        append_step = next(step for step in trace.steps if step.kind == "list")
        self.assertEqual(append_step.variables_before["items"], [1])
        self.assertEqual(append_step.variables_after["items"], [1, 2])

    def test_unsupported_syntax_is_rejected(self) -> None:
        result = parse_code("import os\nprint('x')")
        self.assertFalse(result.ok)
        self.assertEqual(result.diagnostics[0].kind, "unsupported")

    def test_nested_control_flow_function_is_rejected(self) -> None:
        result = parse_code("if True:\n    def helper():\n        return 1")
        self.assertFalse(result.ok)
        self.assertIn("최상위", result.diagnostics[0].message)

    def test_recursion_is_rejected_by_educational_executor(self) -> None:
        trace = EducationalExecutor("def loop():\n    loop()\nloop()").run()
        self.assertIsNotNone(trace.error)
        self.assertIn("재귀", trace.error.message)

    def test_chained_comparison_short_circuits(self) -> None:
        trace = EducationalExecutor("x = 3\ny = 1 < x < 2").run()
        self.assertIsNone(trace.error)
        self.assertFalse(trace.final_variables["y"])

    def test_execution_limit_keeps_trace(self) -> None:
        trace = EducationalExecutor("x = 0\nwhile True:\n    x = x + 1", max_steps=10, max_seconds=10).run()
        self.assertIsNone(trace.error)
        self.assertIsNotNone(trace.stopped_reason)
        self.assertTrue(trace.steps)

    def test_pathological_single_expression_is_rejected_safely(self) -> None:
        trace = EducationalExecutor("value = 2 ** 20000").run()
        self.assertIsNotNone(trace.error)
        self.assertIn("거듭제곱", trace.error.message)


class SessionTests(unittest.TestCase):
    def test_session_preserves_order_and_can_restart(self) -> None:
        session = CodeSession()
        session.append("a = 1")
        session.append("b = a + 1")
        self.assertEqual(session.combined_code(), "a = 1\nb = a + 1")
        session.clear()
        self.assertFalse(session.has_pending)


class OcrUtilityTests(unittest.TestCase):
    def test_normalize_rect_and_recover_indentation(self) -> None:
        first_box = OcrService._normalize_box([10, 10, 90, 30])
        second_box = OcrService._normalize_box([74, 40, 202, 60])
        self.assertEqual(first_box, [[10, 10], [90, 10], [90, 30], [10, 30]])
        code = OcrService.lines_to_code(
            [OcrLine("if x:", 0.99, first_box), OcrLine("print(x)", 0.99, second_box)]
        )
        self.assertEqual(code, "if x:\n    print(x)")

    def test_merge_ocr_fragments_on_the_same_source_line(self) -> None:
        left = [[10, 10], [80, 10], [80, 30], [10, 30]]
        right = [[92, 10], [130, 10], [130, 30], [92, 30]]
        next_line = [[40, 40], [110, 40], [110, 60], [40, 60]]
        code = OcrService.lines_to_code(
            [
                OcrLine("if x >=", 0.9, left),
                OcrLine("10:", 0.95, right),
                OcrLine("print(x)", 0.99, next_line),
            ]
        )
        self.assertEqual(code, "if x >= 10:\n    print(x)")

    def test_large_ocr_input_is_downscaled_to_detector_limit(self) -> None:
        import numpy as np

        small = np.zeros((200, 400, 3), dtype=np.uint8)
        self.assertIs(OcrService._prepare_image(small), small)
        large = np.zeros((2160, 3840, 3), dtype=np.uint8)
        prepared = OcrService._prepare_image(large)
        self.assertLessEqual(max(prepared.shape[:2]), 1536)


if __name__ == "__main__":
    unittest.main()
