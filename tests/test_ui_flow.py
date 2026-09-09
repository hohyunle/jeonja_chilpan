from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.executor import EducationalExecutor
from app.main import MainWindow
from app.core.models import ExecutionTrace, WorkflowState
from app.ui.template_library import TEMPLATE_SPECS
from app.ui.visualizer import VisualizerWindow
from app.ui.code_editor import CodeEditorDialog


class SelectionFlowUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_new_start_clears_pending_regions_after_confirmation(self) -> None:
        window = MainWindow(warmup_ocr=False)
        window.session.append_ocr("x = 1")
        started = []
        window.begin_selection = lambda: started.append(True)

        original_question = QMessageBox.question
        QMessageBox.question = staticmethod(
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes
        )
        try:
            window.new_start()
            self.application.processEvents()
        finally:
            QMessageBox.question = original_question
            window.close()
            self.application.processEvents()

        self.assertFalse(window.session.code_session.has_pending)
        self.assertTrue(started)

    def test_mouse_selection_state_returns_to_idle_on_escape(self) -> None:
        window = MainWindow(warmup_ocr=False)
        try:
            window.begin_selection()
            self.assertEqual(window.workflow_state, WorkflowState.SELECTING)
            window._selection_cancelled()
            self.assertEqual(window.workflow_state, WorkflowState.IDLE)
        finally:
            window.close()
            self.application.processEvents()

    def test_list_visualization_exposes_indexes(self) -> None:
        visualizer = VisualizerWindow(
            EducationalExecutor("items = [10]\nitems.append(20)").run()
        )
        try:
            visualizer.set_template("lists")
            visualizer.next_step()
            html = visualizer.detail.toHtml()
            self.assertIn("[0]", html)
            self.assertIn("[1]", html)
        finally:
            visualizer.close()
            self.application.processEvents()

    def test_template_registry_uses_trace_semantics(self) -> None:
        visualizer = VisualizerWindow(EducationalExecutor("x = 1").run())
        try:
            self.assertEqual(len(TEMPLATE_SPECS), 16)
            self.assertIn("values", visualizer._active_template_keys)
            self.assertNotIn("graph", visualizer._active_template_keys)
        finally:
            visualizer.close()
            self.application.processEvents()

    def test_input_panel_emits_value_from_mouse_keyboard_controls(self) -> None:
        visualizer = VisualizerWindow(ExecutionTrace(""))
        submitted: list[str] = []
        visualizer.input_submitted.connect(submitted.append)
        try:
            visualizer.show_input_prompt("값:")
            visualizer.input_edit.setText("42")
            visualizer._submit_input()
            self.assertEqual(submitted, ["42"])
            self.assertFalse(visualizer.input_panel.isVisible())
        finally:
            visualizer.close()
            self.application.processEvents()

    def test_editor_shows_supported_syntax_status(self) -> None:
        dialog = CodeEditorDialog("x = 1")
        try:
            self.assertIn("지원 문법", dialog.validation_label.text())
            dialog.editor.setPlainText("import os")
            self.assertIn("지원하지 않는", dialog.validation_label.text())
        finally:
            dialog.close()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
