from __future__ import annotations

import sys

from PySide6.QtCore import QBuffer, QIODevice, QThread, QTimer, Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.models import ExecutionTrace, WorkflowState
from app.core.session import SessionController
from app.platform.windows import capture_screen_rect
from app.ui.code_editor import CodeEditorDialog
from app.ui.review_dialog import SelectionReviewDialog
from app.ui.selection_overlay import SelectionOverlay
from app.ui.theme import ui_font
from app.ui.visualizer import VisualizerWindow
from app.ui.workers import ExecutionWorker, OcrWorker


class MainWindow(QMainWindow):
    """Small always-on-top controller for the screen-based workflow."""

    def __init__(self, *, warmup_ocr: bool = True) -> None:
        super().__init__()
        self.setFont(ui_font(10))
        self.setWindowTitle("CodeTrace")
        self.resize(620, 330)
        self.setMinimumSize(540, 285)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self.session = SessionController()
        self._state = WorkflowState.IDLE
        self._ocr_ready = False
        self._ocr_error: str | None = None
        self.overlay = SelectionOverlay()
        self.overlay.selection_made.connect(self._selection_made)
        self.overlay.cancelled.connect(self._selection_cancelled)
        self._pending_action: str | None = None
        self._ocr_progress: QProgressDialog | None = None
        self._visualizer: VisualizerWindow | None = None
        self._execution_thread: QThread | None = None
        self._execution_worker: ExecutionWorker | None = None

        self._ocr_worker = OcrWorker()
        self._ocr_worker.finished.connect(self._ocr_finished)
        self._ocr_worker.failed.connect(self._ocr_failed)
        self._ocr_worker.ready.connect(self._ocr_warmup_finished)
        self._ocr_worker.warmup_failed.connect(self._ocr_warmup_failed)

        self._build_ui()
        if warmup_ocr:
            self._set_ocr_controls_ready(False)
        else:
            # Keep UI tests and direct-code tooling independent of optional
            # model files; the production entry point uses the default True.
            self._ocr_ready = True
            self._set_ocr_controls_ready(True)
        self._refresh_session_status()
        if warmup_ocr:
            # Load the model before the first capture so user-visible OCR latency
            # contains inference only, not PaddleOCR initialization.
            self._ocr_worker.start()
            self._ocr_worker.warmup()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("CodeTrace")
        title.setObjectName("title")
        header.addWidget(title)
        title_hint = QLabel("Python 실행 과정 학습 도우미")
        title_hint.setObjectName("titleHint")
        header.addWidget(title_hint)
        header.addStretch()
        self.status = QLabel()
        self.status.setObjectName("status")
        header.addWidget(self.status)
        layout.addLayout(header)

        description = QLabel(
            "수업 자료에서 코드 영역을 드래그하거나 직접 입력해 실행 과정을 확인하세요."
        )
        description.setObjectName("description")
        description.setWordWrap(True)
        layout.addWidget(description)

        action_card = QWidget()
        action_card.setObjectName("actionCard")
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(14, 13, 14, 14)
        action_layout.setSpacing(9)
        action_title = QLabel("새 코드 시작")
        action_title.setObjectName("sectionTitle")
        action_layout.addWidget(action_title)
        buttons = QHBoxLayout()
        buttons.setSpacing(9)
        self.select_button = QPushButton("화면에서 코드 선택")
        self.select_button.setObjectName("primary")
        self.select_button.setMinimumHeight(52)
        self.select_button.clicked.connect(self.begin_selection)
        self.direct_button = QPushButton("코드 직접 입력")
        self.direct_button.setObjectName("secondary")
        self.direct_button.setMinimumHeight(52)
        self.direct_button.clicked.connect(self.open_direct_editor)
        buttons.addWidget(self.select_button, 1)
        buttons.addWidget(self.direct_button, 1)
        action_layout.addLayout(buttons)
        layout.addWidget(action_card)

        session_card = QWidget()
        session_card.setObjectName("sessionCard")
        session_layout = QHBoxLayout(session_card)
        session_layout.setContentsMargins(14, 10, 10, 10)
        session_layout.setSpacing(10)
        session_text = QVBoxLayout()
        session_text.setSpacing(2)
        session_title = QLabel("임시 코드 세션")
        session_title.setObjectName("sectionTitle")
        session_text.addWidget(session_title)
        self.session_hint = QLabel("아직 선택한 코드가 없습니다.")
        self.session_hint.setObjectName("muted")
        session_text.addWidget(self.session_hint)
        session_layout.addLayout(session_text, 1)

        self.new_start_button = QPushButton("새로 시작")
        self.new_start_button.setObjectName("newStart")
        self.new_start_button.setMinimumHeight(36)
        self.new_start_button.setToolTip("임시 선택 영역을 모두 삭제하고 새 코드 선택을 시작합니다.")
        self.new_start_button.clicked.connect(self.new_start)
        session_layout.addWidget(self.new_start_button)
        layout.addWidget(session_card)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer_hint = QLabel("화면 선택은 드래그 · Esc로 취소")
        footer_hint.setObjectName("muted")
        footer.addWidget(footer_hint)
        footer.addStretch()
        exit_button = QPushButton("종료")
        exit_button.setObjectName("quiet")
        exit_button.clicked.connect(self.close)
        footer.addWidget(exit_button)
        layout.addLayout(footer)

        self.setStyleSheet(
            "QMainWindow, #root { background: #f5f7f8; color: #172c36; }"
            "QWidget#actionCard, QWidget#sessionCard { background: #ffffff; border: 1px solid #dfe6ea; border-radius: 12px; }"
            "QLabel#title { color: #172c36; font-size: 24px; font-weight: 800; }"
            "QLabel#titleHint { color: #697c87; font-size: 12px; padding-left: 6px; }"
            "QLabel#description { color: #526873; font-size: 12px; }"
            "QLabel#sectionTitle { color: #172c36; font-size: 13px; font-weight: 700; }"
            "QLabel#muted { color: #697c87; font-size: 11px; }"
            "QLabel#status { color: #176c60; background: #e9f6f0; border: 1px solid #b8dfd2; "
            "border-radius: 12px; padding: 5px 11px; font-size: 11px; font-weight: 700; }"
            "QLabel#status[state='busy'] { color: #a6600b; background: #fff4da; border-color: #e4bf79; }"
            "QLabel#status[state='error'] { color: #b23d47; background: #fff0f1; border-color: #e5b4b8; }"
            "QPushButton { background: #ffffff; color: #172c36; border: 1px solid #cddbe1; "
            "border-radius: 8px; padding: 8px 13px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #edf4ff; border-color: #8eb2ee; }"
            "QPushButton:disabled { background: #eef2f3; color: #9aabb2; border-color: #dfe6ea; }"
            "QPushButton#primary { background: #2766cc; color: #ffffff; border-color: #2766cc; }"
            "QPushButton#primary:hover { background: #1f57b1; }"
            "QPushButton#secondary:hover { background: #f1f6f8; }"
            "QPushButton#newStart { color: #a6600b; background: #fff8e9; border-color: #e4bf79; }"
            "QPushButton#newStart:hover { background: #fff0c9; }"
            "QPushButton#quiet { color: #697c87; border-color: transparent; background: transparent; }"
            "QPushButton#quiet:hover { color: #2766cc; background: #edf4ff; }"
        )

    def _refresh_session_status(self) -> None:
        if not self._ocr_ready and self._ocr_error:
            status_text = "OCR 모델 확인 필요"
            status_state = "error"
        elif not self._ocr_ready:
            status_text = "OCR 준비 중…"
            status_state = "busy"
        elif self.session.code_session.has_pending:
            status_text = f"연속 선택 · {self.session.code_session.segment_count}개"
            status_state = "busy"
        else:
            status_text = "대기 중"
            status_state = "ready"
        self.status.setText(status_text)
        self.status.setProperty("state", status_state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        if hasattr(self, "session_hint"):
            if self.session.code_session.has_pending:
                self.session_hint.setText(
                    f"{self.session.code_session.segment_count}개 영역이 임시 보관되어 있습니다."
                )
            else:
                self.session_hint.setText("아직 선택한 코드가 없습니다.")

    def _set_ocr_controls_ready(self, ready: bool) -> None:
        self.select_button.setEnabled(ready)
        if ready:
            self.select_button.setText("화면에서 코드 선택")
            self.select_button.setToolTip("외부 PDF/PPT 화면에서 코드 영역을 드래그합니다.")
        elif self._ocr_error:
            self.select_button.setText("OCR 모델 확인 필요")
            self.select_button.setToolTip(self._ocr_error)
        else:
            self.select_button.setText("OCR 준비 중…")
            self.select_button.setToolTip("로컬 OCR 모델을 준비하는 동안 잠시 기다려 주세요.")

    @Slot()
    def _ocr_warmup_finished(self) -> None:
        self._ocr_ready = True
        self._ocr_error = None
        self._set_ocr_controls_ready(True)
        self._refresh_session_status()

    @Slot(str)
    def _ocr_warmup_failed(self, message: str) -> None:
        self._ocr_ready = False
        self._ocr_error = message
        self._set_ocr_controls_ready(False)
        self._refresh_session_status()

    @property
    def workflow_state(self) -> WorkflowState:
        return self._state

    def begin_selection(self) -> None:
        if self._state not in {
            WorkflowState.IDLE,
            WorkflowState.VISUALIZING,
        }:
            return
        if not self._ocr_ready:
            return
        self._state = WorkflowState.SELECTING
        self.hide()
        self.overlay.begin()

    def _selection_made(self, rect) -> None:
        self._state = WorkflowState.REVIEWING
        # The overlay must be absent from the source image. Give Windows a short
        # event-loop turn to repaint the underlying PDF/PPT window before capture.
        QTimer.singleShot(120, lambda selected_rect=rect: self._capture_and_review(selected_rect))

    def _selection_cancelled(self) -> None:
        self._state = WorkflowState.IDLE
        self.show()
        self.raise_()
        self.status.setText("선택 취소")
        self._refresh_session_status()

    def _capture_and_review(self, rect) -> None:
        self._state = WorkflowState.REVIEWING
        pixmap = capture_screen_rect(rect)
        if pixmap.isNull():
            self._state = WorkflowState.IDLE
            self.show()
            QMessageBox.warning(self, "캡처 실패", "선택한 화면 영역을 캡처하지 못했습니다.")
            return
        dialog = SelectionReviewDialog(pixmap)
        dialog.exec()
        action = dialog.action
        if action == "cancel" or action is None:
            self._state = WorkflowState.IDLE
            self.show()
            self._refresh_session_status()
            return
        self._start_ocr(pixmap, action)

    def _start_ocr(self, pixmap, action: str) -> None:
        if self._state == WorkflowState.OCR:
            return
        image_bytes = self._pixmap_to_png_bytes(pixmap)
        if not image_bytes:
            self._state = WorkflowState.IDLE
            self.show()
            QMessageBox.warning(self, "캡처 실패", "이미지를 OCR 입력으로 변환하지 못했습니다.")
            return
        self._state = WorkflowState.OCR
        self._pending_action = action
        self.show()
        self.raise_()
        self.status.setText("OCR 처리 중…")
        self._ocr_progress = QProgressDialog("화면 영역을 OCR하는 중입니다…", None, 0, 0, self)
        self._ocr_progress.setWindowTitle("OCR 처리 중")
        self._ocr_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._ocr_progress.setMinimumDuration(0)
        self._ocr_progress.setStyleSheet(
            "QProgressDialog { background: #ffffff; color: #172c36; border: 1px solid #dfe6ea; }"
            "QLabel { color: #526873; padding: 8px; }"
            "QProgressBar { min-height: 7px; border: 0; background: #e5edf1; border-radius: 3px; }"
            "QProgressBar::chunk { background: #2766cc; border-radius: 3px; }"
        )
        self._ocr_progress.show()
        # The worker and its OCR model stay alive across requests, so model load
        # time is paid once rather than once per selected region.
        self._ocr_worker.process_requested.emit(image_bytes)

    @staticmethod
    def _pixmap_to_png_bytes(pixmap) -> bytes:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not pixmap.save(buffer, "PNG"):
            return b""
        return bytes(buffer.data())

    def _finish_ocr_ui(self) -> None:
        if self._ocr_progress is not None:
            self._ocr_progress.close()
            self._ocr_progress.deleteLater()
            self._ocr_progress = None

    @Slot(str)
    def _ocr_finished(self, text: str) -> None:
        action = self._pending_action
        self._pending_action = None
        self._finish_ocr_ui()
        if not text.strip():
            self._state = WorkflowState.IDLE
            self.status.setText("OCR 결과 없음")
            QMessageBox.warning(
                self,
                "인식 결과 없음",
                "선택 영역에서 코드를 인식하지 못했습니다. 영역을 넓히거나 더 선명한 화면에서 다시 시도하세요.",
            )
            self._refresh_session_status()
            return
        self.session.append_ocr(text)
        if action == "continue":
            self._state = WorkflowState.IDLE
            self._refresh_session_status()
            self.status.setText(f"연속 선택 · {self.session.code_session.segment_count}개 · 다음 영역을 선택하세요")
            return
        code = self.session.combined_code()
        # Keep the temporary session until the editor is accepted. If the user
        # cancels editing, the recognized regions should still be recoverable.
        self.open_code_editor(code)

    @Slot(str)
    def _ocr_failed(self, message: str) -> None:
        self._state = WorkflowState.IDLE
        self._pending_action = None
        self._finish_ocr_ui()
        self.status.setText("OCR 준비 실패")
        QMessageBox.critical(
            self,
            "OCR 오류",
            "로컬 OCR을 실행하지 못했습니다.\n\n"
            f"{message}\n\n"
            "PaddleOCR 모델이 한 번 이상 로컬에 준비되어 있어야 오프라인으로 실행할 수 있습니다.",
        )
        self._refresh_session_status()

    def new_start(self) -> None:
        if self._state not in {
            WorkflowState.IDLE,
            WorkflowState.VISUALIZING,
        }:
            return
        if self.session.code_session.has_pending:
            answer = QMessageBox.question(
                self,
                "새로 시작",
                "지금까지 연속 선택한 영역과 OCR 결과를 모두 삭제하고 새로 시작할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.session.reset()
        self._refresh_session_status()
        QTimer.singleShot(0, self.begin_selection)

    def open_direct_editor(self) -> None:
        initial = self.session.combined_code() if self.session.code_session.has_pending else ""
        self.open_code_editor(initial)

    def open_code_editor(self, code: str) -> None:
        previous_state = self._state
        self._state = WorkflowState.EDITING
        dialog = CodeEditorDialog(code, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._state = (
                previous_state
                if previous_state not in {
                    WorkflowState.OCR,
                    WorkflowState.REVIEWING,
                    WorkflowState.EDITING,
                }
                else WorkflowState.IDLE
            )
            return
        self.session.reset()
        self._refresh_session_status()
        self.run_code(dialog.code())

    def run_code(self, code: str) -> None:
        if self._execution_thread is not None and self._execution_thread.isRunning():
            QMessageBox.information(self, "실행 중", "현재 실행이 끝난 뒤 다시 실행하세요.")
            return
        self._state = WorkflowState.RUNNING
        placeholder = ExecutionTrace(code)
        self._visualizer = VisualizerWindow(placeholder)
        self._visualizer.input_submitted.connect(self._provide_input)
        self._visualizer.input_cancelled.connect(self._cancel_input)
        self._visualizer.show()
        self._visualizer.raise_()
        self._visualizer.activateWindow()

        thread = QThread(self)
        worker = ExecutionWorker(code)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.input_requested.connect(self._show_input_panel)
        worker.finished.connect(self._execution_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._execution_thread_finished)
        self._execution_thread = thread
        self._execution_worker = worker
        self.status.setText("실행 중…")
        thread.start()

    @Slot(str)
    def _show_input_panel(self, prompt: str) -> None:
        if self._execution_worker is None:
            return
        if self._visualizer is None:
            self._execution_worker.cancel_input()
            return
        self._visualizer.show_input_prompt(prompt)

    def _provide_input(self, value: str) -> None:
        if self._execution_worker is not None:
            self._execution_worker.provide_input(value)

    def _cancel_input(self) -> None:
        if self._execution_worker is not None:
            self._execution_worker.cancel_input()

    @Slot(object)
    def _execution_finished(self, trace: ExecutionTrace) -> None:
        self._state = WorkflowState.VISUALIZING
        if self._visualizer is not None:
            self._visualizer.hide_input_prompt()
            self._visualizer.set_trace(trace)
            self._visualizer.raise_()
            self._visualizer.activateWindow()
        if trace.error:
            self.status.setText("실행 오류")
        elif trace.stopped_reason:
            self.status.setText("실행 제한으로 중단")
        else:
            self.status.setText(f"실행 완료 · {len(trace.steps)} Steps")

    @Slot()
    def _execution_thread_finished(self) -> None:
        self._execution_thread = None
        self._execution_worker = None

    def closeEvent(self, event) -> None:
        if self._execution_worker is not None:
            self._execution_worker.cancel_input()
        if self._execution_thread is not None:
            self._execution_thread.quit()
            self._execution_thread.wait(4_000)
        self._ocr_worker.stop()
        self.overlay.close()
        if self._visualizer is not None:
            self._visualizer.close()
            self._visualizer = None
        super().closeEvent(event)


def build_application() -> QApplication:
    app = QApplication(sys.argv)
    app.setApplicationName("Code Visualizer Tool")
    app.setOrganizationName("Capstone")
    app.setFont(ui_font(10))
    return app


def main() -> int:
    app = build_application()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
