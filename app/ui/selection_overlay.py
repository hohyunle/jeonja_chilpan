from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QScreen
from PySide6.QtWidgets import QWidget

from app.ui.theme import ui_font


class SelectionOverlay(QWidget):
    """Mouse-driven rectangular selection overlay for the desktop screen."""

    selection_made = Signal(QRect)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._origin_global: QPoint | None = None
        self._current_global: QPoint | None = None
        self._selection = QRect()
        self._selection_screen: QScreen | None = None

    @staticmethod
    def _virtual_geometry() -> QRect:
        """Build the virtual desktop from every connected monitor."""

        geometry = QRect()
        for screen in QGuiApplication.screens():
            screen_geometry = screen.geometry()
            geometry = (
                QRect(screen_geometry)
                if geometry.isNull()
                else geometry.united(screen_geometry)
            )
        return geometry

    def _point_on_selection_screen(self, point: QPoint) -> QPoint:
        """Keep one capture inside the monitor where the drag began.

        A code region belongs to one display.  Constraining the drag prevents
        a cross-monitor QRect from being interpreted with the wrong screen's
        local origin, especially when the monitors use different scaling.
        """

        screen = self._selection_screen
        if screen is None:
            return point
        geometry = screen.geometry()
        return QPoint(
            max(geometry.left(), min(point.x(), geometry.right())),
            max(geometry.top(), min(point.y(), geometry.bottom())),
        )

    def begin(self) -> None:
        geometry = self._virtual_geometry()
        if geometry.isNull():
            return
        self.setGeometry(geometry)
        self._origin_global = None
        self._current_global = None
        self._selection = QRect()
        self._selection_screen = None
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._origin_global = event.globalPosition().toPoint()
        self._selection_screen = QGuiApplication.screenAt(self._origin_global)
        if self._selection_screen is None:
            self._selection_screen = QGuiApplication.primaryScreen()
        self._current_global = self._origin_global
        self._selection = QRect(self._origin_global, self._origin_global)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._origin_global is None:
            return
        self._current_global = self._point_on_selection_screen(
            event.globalPosition().toPoint()
        )
        self._selection = QRect(self._origin_global, self._current_global).normalized()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._origin_global is None:
            return
        self._current_global = self._point_on_selection_screen(
            event.globalPosition().toPoint()
        )
        self._selection = QRect(self._origin_global, self._current_global).normalized()
        if self._selection.width() >= 12 and self._selection.height() >= 12:
            selection = QRect(self._selection)
            self._origin_global = None
            self._selection_screen = None
            self.hide()
            self.selection_made.emit(selection)
        else:
            self._origin_global = None
            self._current_global = None
            self._selection = QRect()
            self._selection_screen = None
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(ui_font(11))
        # Keep the source PDF/PPT readable while the user is dragging. The
        # selected rectangle is cleared below, so the border remains obvious.
        painter.setBrush(QColor(15, 35, 47, 52))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())
        painter.setOpacity(1.0)
        if not self._selection.isNull():
            local_rect = self._selection.translated(-self.geometry().topLeft())
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(local_rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#65a8ff"), 3))
            painter.drawRect(local_rect)
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.drawText(
                local_rect.adjusted(8, 8, -8, -8),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                f"{self._selection.width()} × {self._selection.height()}",
            )
        instruction = self.rect().adjusted(self.width() // 2 - 190, 24, self.width() // 2 + 190, 60)
        painter.setBrush(QColor(23, 44, 54, 235))
        painter.setPen(QPen(QColor("#5d7a89"), 1))
        painter.drawRoundedRect(instruction, 9, 9)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            instruction,
            Qt.AlignmentFlag.AlignCenter,
            "코드 영역을 드래그하세요  ·  Esc 취소",
        )
