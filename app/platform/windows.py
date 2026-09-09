from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import math
import os
from typing import Iterable

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPixmap, QScreen


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SW_RESTORE = 9
GA_ROOT = 2


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


@dataclass(slots=True)
class WindowInfo:
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]
    pid: int

    @property
    def area(self) -> int:
        return max(0, self.rect[2] - self.rect[0]) * max(0, self.rect[3] - self.rect[1])


def hwnd_for_qt_window(window: object) -> int:
    return int(window.winId())


def get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    rect = RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(wintypes.HWND(hwnd), buffer, length + 1)
    return buffer.value


def get_window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


def enumerate_visible_windows(exclude_hwnds: Iterable[int] = ()) -> list[WindowInfo]:
    excluded = {int(hwnd) for hwnd in exclude_hwnds}
    current_pid = os.getpid()
    windows: list[WindowInfo] = []

    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @enum_proc_type
    def callback(hwnd: int, _lparam: int) -> bool:
        hwnd_int = int(hwnd)
        if hwnd_int in excluded:
            return True
        if not user32.IsWindowVisible(wintypes.HWND(hwnd)):
            return True
        if user32.IsIconic(wintypes.HWND(hwnd)):
            return True
        title = get_window_title(hwnd_int).strip()
        rect = get_window_rect(hwnd_int)
        pid = get_window_pid(hwnd_int)
        if title and rect and pid != current_pid and rect[2] > rect[0] and rect[3] > rect[1]:
            windows.append(WindowInfo(hwnd_int, title, rect, pid))
        return True

    user32.EnumWindows(callback, 0)
    return windows


def likely_document_window(exclude_hwnds: Iterable[int] = ()) -> WindowInfo | None:
    """Choose a visible, non-owned window as a best-effort document window.

    The application intentionally does not depend on a PDF/PPT API. This helper
    only uses generic Windows window geometry and titles; users can still keep any
    viewer in front during normal use.
    """

    windows = enumerate_visible_windows(exclude_hwnds)
    if not windows:
        return None
    # A large visible window is a better default than a small utility window.
    return max(windows, key=lambda item: item.area)


def move_resize_window(hwnd: int, left: int, top: int, width: int, height: int) -> bool:
    if not hwnd or width <= 0 or height <= 0:
        return False
    user32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
    result = user32.SetWindowPos(
        wintypes.HWND(hwnd),
        HWND_TOP,
        int(left),
        int(top),
        int(width),
        int(height),
        SWP_NOACTIVATE | SWP_SHOWWINDOW,
    )
    return bool(result)


def capture_screen_rect(rect: QRect) -> QPixmap:
    """Capture a global desktop rectangle across the correct monitor(s).

    Qt exposes Windows monitor geometry in device-independent global
    coordinates, while each ``QScreen.grabWindow`` call expects coordinates
    local to that screen.  Capture each intersection separately and compose
    the result so negative secondary-monitor origins and mixed DPI settings do
    not shift or clip the selected code.
    """

    requested = QRect(rect).normalized()
    if requested.width() <= 0 or requested.height() <= 0:
        return QPixmap()
    screens = QGuiApplication.screens()
    if not screens:
        return QPixmap()

    intersections: list[tuple[QScreen, QRect]] = []
    for screen in screens:
        intersection = requested.intersected(screen.geometry())
        if not intersection.isEmpty():
            intersections.append((screen, intersection))
    if not intersections:
        return QPixmap()

    device_scale = max(
        1.0,
        max(float(screen.devicePixelRatio()) for screen, _ in intersections),
    )
    canvas_width = max(1, math.ceil(requested.width() * device_scale))
    canvas_height = max(1, math.ceil(requested.height() * device_scale))
    canvas = QImage(canvas_width, canvas_height, QImage.Format.Format_RGB32)
    canvas.fill(0)

    captured_any = False
    painter = QPainter(canvas)
    try:
        for screen, intersection in intersections:
            screen_geometry = screen.geometry()
            pixmap = screen.grabWindow(
                0,
                intersection.x() - screen_geometry.x(),
                intersection.y() - screen_geometry.y(),
                intersection.width(),
                intersection.height(),
            )
            if pixmap.isNull():
                continue
            target = QRect(
                round((intersection.x() - requested.x()) * device_scale),
                round((intersection.y() - requested.y()) * device_scale),
                max(1, round(intersection.width() * device_scale)),
                max(1, round(intersection.height() * device_scale)),
            )
            painter.drawPixmap(target, pixmap)
            captured_any = True
    finally:
        painter.end()

    return QPixmap.fromImage(canvas) if captured_any else QPixmap()


@dataclass(slots=True)
class SplitLayoutSnapshot:
    external_hwnd: int | None
    external_rect: tuple[int, int, int, int] | None
    visualizer_rect: tuple[int, int, int, int] | None


def arrange_split(
    external_hwnd: int | None,
    visualizer_hwnd: int,
    screen_rect: QRect,
) -> SplitLayoutSnapshot:
    snapshot = SplitLayoutSnapshot(
        external_hwnd=external_hwnd,
        external_rect=get_window_rect(external_hwnd) if external_hwnd else None,
        visualizer_rect=get_window_rect(visualizer_hwnd),
    )
    half = screen_rect.width() // 2
    if external_hwnd:
        move_resize_window(external_hwnd, screen_rect.x(), screen_rect.y(), half, screen_rect.height())
    move_resize_window(
        visualizer_hwnd,
        screen_rect.x() + half,
        screen_rect.y(),
        screen_rect.width() - half,
        screen_rect.height(),
    )
    return snapshot


def restore_layout(snapshot: SplitLayoutSnapshot, visualizer_hwnd: int) -> None:
    if snapshot.external_hwnd and snapshot.external_rect:
        left, top, right, bottom = snapshot.external_rect
        move_resize_window(snapshot.external_hwnd, left, top, right - left, bottom - top)
    if snapshot.visualizer_rect:
        left, top, right, bottom = snapshot.visualizer_rect
        move_resize_window(visualizer_hwnd, left, top, right - left, bottom - top)
