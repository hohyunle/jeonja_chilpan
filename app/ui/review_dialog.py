from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.ui.theme import ui_font


class SelectionReviewDialog(QDialog):
    """Confirm how the just-captured screen region should be processed."""

    def __init__(self, pixmap: QPixmap, parent=None) -> None:
        super().__init__(parent)
        self.setFont(ui_font(10))
        self.setWindowTitle("선택 영역 확인")
        self.setModal(True)
        self.setMinimumSize(680, 480)
        self.resize(760, 560)
        self.action: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        eyebrow = QLabel("SCREEN CAPTURE")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("선택한 영역을 확인하세요")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        message = QLabel(
            "코드가 잘 보이면 OCR을 실행하세요. 판서나 주변 내용이 섞였다면 취소하고 영역을 다시 선택할 수 있습니다."
        )
        message.setObjectName("muted")
        message.setWordWrap(True)
        layout.addWidget(message)

        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumHeight(245)
        preview.setStyleSheet("background: #ffffff; color: #697c87; border-radius: 8px;")
        if not pixmap.isNull():
            preview.setPixmap(
                pixmap.scaled(
                    700,
                    300,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            preview.setText("캡처된 영역을 불러오지 못했습니다.")
        preview_layout.addWidget(preview, 1)
        layout.addWidget(preview_frame, 1)

        hint = QLabel("확인: 한 번 OCR 후 편집 화면으로 이동  ·  연속 선택: 현재 결과를 임시 보관")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox()
        confirm = buttons.addButton("OCR 실행", QDialogButtonBox.ButtonRole.AcceptRole)
        confirm.setObjectName("primary")
        continuous = buttons.addButton("연속 선택", QDialogButtonBox.ButtonRole.ActionRole)
        continuous.setObjectName("secondary")
        cancel = buttons.addButton("다시 선택", QDialogButtonBox.ButtonRole.RejectRole)
        cancel.setObjectName("quiet")
        confirm.clicked.connect(lambda: self._finish("confirm"))
        continuous.clicked.connect(lambda: self._finish("continue"))
        cancel.clicked.connect(lambda: self._finish("cancel"))
        layout.addWidget(buttons)

        self.setStyleSheet(
            "QDialog { background: #f5f7f8; color: #172c36; }"
            "QFrame#previewFrame { background: #e9eff2; border: 1px solid #d5e0e5; border-radius: 11px; }"
            "QLabel#eyebrow { color: #697c87; font-size: 10px; font-weight: 700; letter-spacing: 1px; }"
            "QLabel#dialogTitle { color: #172c36; font-size: 22px; font-weight: 800; }"
            "QLabel#muted { color: #697c87; font-size: 11px; }"
            "QDialogButtonBox QPushButton { min-width: 90px; padding: 9px 14px; border-radius: 8px; "
            "background: #ffffff; color: #172c36; border: 1px solid #cddbe1; font-weight: 600; }"
            "QDialogButtonBox QPushButton:hover { background: #edf4ff; border-color: #8eb2ee; }"
            "QDialogButtonBox QPushButton#primary { background: #2766cc; color: #ffffff; border-color: #2766cc; }"
            "QDialogButtonBox QPushButton#primary:hover { background: #1f57b1; }"
            "QDialogButtonBox QPushButton#quiet { color: #697c87; border-color: transparent; background: transparent; }"
        )

    def _finish(self, action: str) -> None:
        self.action = action
        self.done(QDialog.DialogCode.Accepted if action != "cancel" else QDialog.DialogCode.Rejected)
