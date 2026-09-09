from __future__ import annotations

from bisect import bisect_right
from html import escape
import re

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.models import ExecutionTrace, TraceStep, display_value
from app.platform.windows import (
    SplitLayoutSnapshot,
    arrange_split,
    likely_document_window,
    restore_layout,
)
from app.ui.template_library import (
    TEMPLATE_SPECS,
    canonical_template,
    get_template,
)
from app.ui.theme import code_font, ui_font


_UNDEFINED = object()


class VisualizerWindow(QMainWindow):
    """Trace-driven educational visualizer.

    The screen follows the template prototype's common shell: a template
    library, a large semantic scene, code/diff evidence, and a replay player.
    The scene is rendered only from ``ExecutionTrace`` facts; the renderer does
    not execute code and does not invent values for templates that the current
    executor cannot support.
    """

    input_submitted = Signal(str)
    input_cancelled = Signal()

    def __init__(self, trace: ExecutionTrace, parent=None) -> None:
        super().__init__(parent)
        self.setFont(ui_font(10))
        self.setWindowTitle("CodeTrace · 실행 시각화")
        self.setMinimumSize(980, 680)
        self.resize(1240, 820)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.trace = trace
        self.step_index = 0
        self.template = "values"
        self._playing = False
        self._split_snapshot: SplitLayoutSnapshot | None = None
        self._html_cache: dict[tuple[str, int], str] = {}
        self._output_step_indexes: list[int] = []
        self._output_texts: list[str] = []
        self._active_template_keys: set[str] = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.next_step)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(16)

        root_layout.addWidget(self._build_workspace(), 1)

        self.setStyleSheet(
            "QMainWindow, #root { background: #f5f7f8; color: #172c36; }"
            "QFrame#sidebar { background: #ffffff; border: 1px solid #dfe6ea; border-radius: 14px; }"
            "QFrame#panel, QFrame#player, QFrame#sceneCard, QFrame#inputPanel { "
            "background: #ffffff; border: 1px solid #dfe6ea; border-radius: 12px; }"
            "QFrame#note { background: #f7fafb; border: 1px solid #e4ecef; border-radius: 9px; }"
            "QFrame#watchCard { background: #ffffff; border: 1px solid #dfe6ea; border-radius: 9px; }"
            "QFrame#watchCard[changed='true'] { background: #fff4da; border: 1px solid #dca54e; }"
            "QLabel#brand { color: #172c36; font-size: 22px; font-weight: 800; letter-spacing: 1px; }"
            "QLabel#eyebrow { color: #697c87; font-size: 10px; font-weight: 700; letter-spacing: 1px; }"
            "QLabel#pageTitle { color: #172c36; font-size: 25px; font-weight: 800; }"
            "QLabel#pageSubtitle { color: #697c87; font-size: 12px; }"
            "QLabel#sceneTitle { color: #172c36; font-size: 15px; font-weight: 800; }"
            "QLabel#muted { color: #697c87; font-size: 11px; }"
            "QLabel#step { color: #2766cc; font-size: 12px; font-weight: 700; }"
            "QLabel#watchName { color: #697c87; font-size: 10px; }"
            "QLabel#watchValue { color: #172c36; font-size: 16px; font-weight: 800; }"
            "QLabel#explanation { color: #526873; font-size: 11px; }"
            "QLabel#outputLabel { color: #172c36; font-size: 12px; }"
            "QLineEdit { background: #f7fafb; color: #172c36; border: 1px solid #dfe6ea; "
            "border-radius: 7px; padding: 8px 10px; }"
            "QLineEdit:focus { border: 1px solid #2766cc; }"
            "QPushButton { background: #ffffff; color: #172c36; border: 1px solid #d3dfe4; "
            "border-radius: 7px; padding: 7px 11px; }"
            "QPushButton:hover { background: #edf4ff; border-color: #8eb2ee; }"
            "QPushButton:checked { background: #edf4ff; color: #2766cc; border-color: #2766cc; }"
            "QPushButton#primary { background: #2766cc; color: #ffffff; border-color: #2766cc; }"
            "QPushButton#primary:hover { background: #1f57b1; }"
            "QCheckBox { color: #526873; font-size: 11px; spacing: 5px; }"
            "QListWidget#templateList { background: transparent; border: 0; outline: 0; "
            "font-size: 12px; }"
            "QListWidget#templateList::item { color: #405762; padding: 8px 9px; border-radius: 7px; }"
            "QListWidget#templateList::item:hover { background: #f0f5f8; }"
            "QListWidget#templateList::item:selected { background: #edf4ff; color: #2766cc; font-weight: 700; }"
            "QListWidget#templateList::item:disabled { color: #aab8be; }"
            "QSlider::groove:horizontal { height: 5px; background: #dfe6ea; border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: #2766cc; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #2766cc; border-radius: 7px; }"
            "QSplitter::handle { background: #e6edf0; width: 6px; }"
        )
        self._rebuild_output_index()
        self._configure_trace()

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        topbar = QHBoxLayout()
        breadcrumb = QLabel("CodeTrace  /  실행 시각화")
        breadcrumb.setObjectName("muted")
        topbar.addWidget(breadcrumb)
        topbar.addStretch()
        self.reduce_motion = QCheckBox("모션 줄이기")
        self.reduce_motion.toggled.connect(self._motion_setting_changed)
        topbar.addWidget(self.reduce_motion)
        self.layout_button = QPushButton("PDF/PPT 함께 보기")
        self.layout_button.setToolTip("외부 PDF/PPT 창과 나란히 배치")
        self.layout_button.clicked.connect(self.toggle_split)
        close_button = QPushButton("닫기")
        close_button.clicked.connect(self.close)
        topbar.addWidget(self.layout_button)
        topbar.addWidget(close_button)
        layout.addLayout(topbar)

        self.eyebrow = QLabel("EDUCATIONAL EXECUTION")
        self.eyebrow.setObjectName("eyebrow")
        layout.addWidget(self.eyebrow)
        self.page_title = QLabel()
        self.page_title.setObjectName("pageTitle")
        layout.addWidget(self.page_title)
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("pageSubtitle")
        self.page_subtitle.setWordWrap(True)
        layout.addWidget(self.page_subtitle)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        body.addWidget(self._build_scene_panel())
        body.addWidget(self._build_evidence_column())
        body.setSizes([730, 390])
        layout.addWidget(body, 1)

        self.input_panel = QWidget()
        self.input_panel.setObjectName("inputPanel")
        input_layout = QHBoxLayout(self.input_panel)
        input_layout.setContentsMargins(10, 7, 10, 7)
        self.input_prompt = QLabel()
        self.input_prompt.setWordWrap(True)
        input_layout.addWidget(self.input_prompt, 1)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("입력값")
        self.input_edit.returnPressed.connect(self._submit_input)
        input_layout.addWidget(self.input_edit, 1)
        submit_input = QPushButton("입력")
        submit_input.setObjectName("primary")
        submit_input.clicked.connect(self._submit_input)
        cancel_input = QPushButton("취소")
        cancel_input.clicked.connect(self._cancel_input)
        input_layout.addWidget(submit_input)
        input_layout.addWidget(cancel_input)
        self.input_panel.hide()
        layout.addWidget(self.input_panel)
        layout.addWidget(self._build_player())
        return workspace

    def _build_scene_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(9)

        scene_header = QHBoxLayout()
        scene_title = QLabel("실행 장면")
        scene_title.setObjectName("sceneTitle")
        scene_header.addWidget(scene_title)
        scene_header.addStretch()
        self.scene_badge = QLabel()
        self.scene_badge.setObjectName("muted")
        scene_header.addWidget(self.scene_badge)
        layout.addLayout(scene_header)

        self.scene_legend = QLabel("파랑 현재  ·  초록 완료  ·  주황 변경  ·  보라 반환")
        self.scene_legend.setObjectName("muted")
        layout.addWidget(self.scene_legend)

        self.card = QFrame()
        self.card.setObjectName("sceneCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 10, 12, 11)
        card_layout.setSpacing(5)
        self.card_title = QLabel()
        self.card_title.setObjectName("sceneTitle")
        card_layout.addWidget(self.card_title)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        self.detail.setReadOnly(True)
        self.detail.setFont(ui_font(11))
        self.detail.setStyleSheet(
            "QTextBrowser { background: #ffffff; border: 0; color: #172c36; "
            "font-size: 12px; padding: 2px; }"
        )
        card_layout.addWidget(self.detail, 1)
        self.card_opacity = QGraphicsOpacityEffect(self.card)
        self.card_opacity.setOpacity(1.0)
        self.card.setGraphicsEffect(self.card_opacity)
        self._card_animation = QPropertyAnimation(self.card_opacity, b"opacity", self)
        self._card_animation.setDuration(170)
        self._card_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        layout.addWidget(self.card, 1)

        self.watch_host = QWidget()
        self.watch_layout = QHBoxLayout(self.watch_host)
        self.watch_layout.setContentsMargins(0, 0, 0, 0)
        self.watch_layout.setSpacing(8)
        layout.addWidget(self.watch_host)

        self.explanation_frame = QFrame()
        self.explanation_frame.setObjectName("note")
        explanation_layout = QVBoxLayout(self.explanation_frame)
        explanation_layout.setContentsMargins(10, 8, 10, 8)
        self.explanation = QLabel()
        self.explanation.setObjectName("explanation")
        self.explanation.setWordWrap(True)
        explanation_layout.addWidget(self.explanation)
        layout.addWidget(self.explanation_frame)
        return panel

    def _build_evidence_column(self) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        code_panel = QFrame()
        code_panel.setObjectName("panel")
        code_layout = QVBoxLayout(code_panel)
        code_layout.setContentsMargins(12, 10, 12, 10)
        code_header = QHBoxLayout()
        code_label = QLabel("실행 코드")
        code_label.setObjectName("sceneTitle")
        code_header.addWidget(code_label)
        code_header.addStretch()
        code_hint = QLabel("현재 Step")
        code_hint.setObjectName("muted")
        code_header.addWidget(code_hint)
        code_layout.addLayout(code_header)
        self.code_view = QTextBrowser()
        self.code_view.setReadOnly(True)
        self.code_view.setFont(code_font(10))
        self.code_view.setStyleSheet(
            "QTextBrowser { background: #fbfcfd; border: 1px solid #e7edf0; "
            "border-radius: 7px; padding: 4px; }"
        )
        code_layout.addWidget(self.code_view, 1)
        layout.addWidget(code_panel, 4)

        diff_panel = QFrame()
        diff_panel.setObjectName("panel")
        diff_layout = QVBoxLayout(diff_panel)
        diff_layout.setContentsMargins(12, 10, 12, 8)
        diff_header = QLabel("상태 변화 기록")
        diff_header.setObjectName("sceneTitle")
        diff_layout.addWidget(diff_header)
        self.diff_view = QTextBrowser()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(code_font(9))
        self.diff_view.setStyleSheet(
            "QTextBrowser { background: #ffffff; border: 0; color: #526873; }"
        )
        diff_layout.addWidget(self.diff_view, 1)
        layout.addWidget(diff_panel, 2)

        output_panel = QFrame()
        output_panel.setObjectName("panel")
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(12, 9, 12, 9)
        output_header = QLabel("출력")
        output_header.setObjectName("muted")
        output_layout.addWidget(output_header)
        self.output_label = QLabel("없음")
        self.output_label.setObjectName("outputLabel")
        self.output_label.setWordWrap(True)
        self.output_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        output_layout.addWidget(self.output_label, 1)
        layout.addWidget(output_panel, 1)
        return column

    def _build_player(self) -> QFrame:
        player = QFrame()
        player.setObjectName("player")
        layout = QVBoxLayout(player)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(5)

        timeline = QHBoxLayout()
        self.progress = QSlider(Qt.Orientation.Horizontal)
        self.progress.setMinimum(1)
        self.progress.setMaximum(1)
        self.progress.valueChanged.connect(self._on_progress_changed)
        timeline.addWidget(self.progress, 1)
        self.step_label = QLabel()
        self.step_label.setObjectName("step")
        timeline.addWidget(self.step_label)
        layout.addLayout(timeline)

        controls = QHBoxLayout()
        previous = QPushButton("처음")
        previous.setToolTip("첫 Step")
        previous.clicked.connect(self._first_step)
        back = QPushButton("이전")
        back.setToolTip("이전 Step")
        back.clicked.connect(self.previous_step)
        self.play_button = QPushButton("재생")
        self.play_button.setObjectName("primary")
        self.play_button.setToolTip("재생/일시정지")
        self.play_button.clicked.connect(self.toggle_play)
        following = QPushButton("다음")
        following.setToolTip("다음 Step")
        following.clicked.connect(self.next_step)
        controls.addWidget(previous)
        controls.addWidget(back)
        controls.addWidget(self.play_button)
        controls.addWidget(following)
        controls.addStretch()
        controls.addWidget(QLabel("속도"))
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(1, 4)
        self.speed.setValue(2)
        self.speed.setFixedWidth(110)
        self.speed.valueChanged.connect(self._update_timer)
        controls.addWidget(self.speed)
        self.speed_value = QLabel("1×")
        self.speed_value.setObjectName("muted")
        self.speed_value.setFixedWidth(28)
        controls.addWidget(self.speed_value)
        layout.addLayout(controls)
        return player

    @staticmethod
    def _mono_font(size: int) -> QFont:
        """Compatibility helper for the code/value typography."""

        return code_font(size)

    def set_trace(self, trace: ExecutionTrace) -> None:
        """Replace the placeholder trace after background execution ends."""

        self.trace = trace
        self.step_index = 0
        self.progress.blockSignals(True)
        self.progress.setRange(1, max(1, len(trace.steps)))
        self.progress.setValue(1)
        self.progress.blockSignals(False)
        self._html_cache.clear()
        self._rebuild_output_index()
        self._configure_trace()

    def _configure_trace(self) -> None:
        self._active_template_keys = self._available_template_keys()
        preferred = [spec.key for spec in TEMPLATE_SPECS if spec.key in self._active_template_keys]
        self.template = preferred[0] if preferred else "values"
        self.progress.blockSignals(True)
        self.progress.setRange(1, max(1, len(self.trace.steps)))
        self.progress.setValue(min(self.step_index + 1, max(1, len(self.trace.steps))))
        self.progress.blockSignals(False)
        self._render_step(animate=False)

    def _rebuild_output_index(self) -> None:
        self._output_step_indexes = []
        self._output_texts = []
        for index, step in enumerate(self.trace.steps):
            if step.kind == "output" and "output" in step.details:
                self._output_step_indexes.append(index)
                self._output_texts.append(str(step.details["output"]))

    def _available_template_keys(self) -> set[str]:
        kinds = self.trace.kinds
        active: set[str] = set()
        if kinds & {"assignment", "input", "output", "expression"}:
            active.add("values")
        if "condition" in kinds:
            active.add("branch")
        if kinds & {"loop", "iteration", "loop_end"}:
            active.add("loop")
        if "list" in kinds or any(isinstance(v, list) for v in self.trace.final_variables.values()):
            active.add("array")
        if kinds & {"function_call", "parameter", "function_return", "return"}:
            active.add("recursion")
        return active or {"values"}

    def _available_templates(self) -> list[tuple[str, str]]:
        """Compatibility helper returning only templates supported by this trace."""

        return [
            (spec.key, spec.display_name)
            for spec in TEMPLATE_SPECS
            if spec.key in self._active_template_keys
        ]

    def set_template(self, template: str) -> None:
        template = canonical_template(template)
        if template not in self._active_template_keys:
            return
        self.template = template
        self._render_step(animate=True)

    def _on_progress_changed(self, value: int) -> None:
        self.step_index = max(0, value - 1)
        self._render_step(animate=True)

    def _current_step(self) -> TraceStep | None:
        if not self.trace.steps:
            return None
        return self.trace.steps[min(self.step_index, len(self.trace.steps) - 1)]

    def _render_step(self, *, animate: bool) -> None:
        step = self._current_step()
        if step is None:
            self.step_label.setText("Step 없음")
            self.scene_badge.setText("상태 확인")
            if self.trace.error is not None:
                self.page_title.setText("실행 오류")
                self.page_subtitle.setText("코드 분석 또는 실행 결과를 확인하세요.")
                self.card_title.setText("코드 확인 필요")
                self.detail.setHtml(
                    "<div style='padding:12px; color:#b23d47;'><b>오류</b><br>"
                    f"{escape(self.trace.error.format())}</div>"
                )
                self._highlight_line(self.trace.error.line)
            elif self.trace.stopped_reason:
                self.page_title.setText("실행 중단")
                self.page_subtitle.setText("실행 제한 또는 입력 취소로 Trace가 멈췄습니다.")
                self.card_title.setText("실행이 중단되었습니다")
                self.detail.setHtml(
                    f"<div style='padding:12px;'>{escape(self.trace.stopped_reason)}</div>"
                )
                self._highlight_line(None)
            else:
                self.page_title.setText("실행 결과")
                self.page_subtitle.setText("표시할 교육용 Step이 없습니다.")
                self.card_title.setText("표시할 Step 없음")
                self.detail.setHtml("<div style='padding:12px;'>Trace가 비어 있습니다.</div>")
                self._highlight_line(None)
            self.diff_view.setHtml("<span style='color:#697c87;'>비교할 상태가 없습니다.</span>")
            self.output_label.setText("없음")
            self._set_watch_cards([])
            self.explanation.setText("코드가 실행되면 학습자가 이해할 수 있는 의미 단위로 Step이 표시됩니다.")
            return

        spec = get_template(self.template)
        self.page_title.setText(spec.display_name)
        self.page_subtitle.setText(spec.summary)
        self.scene_badge.setText(f"{spec.category}  ·  {spec.number}")
        self.step_label.setText(f"Step {step.index} / {len(self.trace.steps)}  ·  {step.title}")
        self.card_title.setText(f"{spec.display_name}  ·  {step.title}")
        cache_key = (self.template, self.step_index)
        html = self._html_cache.get(cache_key)
        if html is None:
            html = self._template_html(step)
            self._html_cache[cache_key] = html
        self.detail.setHtml(html)
        self._highlight_line(step.line)
        self._render_diff(step)
        self._render_watch_cards(step)
        self._render_explanation(step, spec.summary)
        output = "\n".join(self._outputs_until_current_step())
        self.output_label.setText(output if output else "없음")
        if animate:
            self._animate_card()

    def _outputs_until_current_step(self) -> list[str]:
        count = bisect_right(self._output_step_indexes, self.step_index)
        return self._output_texts[:count]

    def show_input_prompt(self, prompt: str) -> None:
        self.input_prompt.setText(prompt or "값을 입력하세요:")
        self.input_edit.clear()
        self.input_panel.show()
        self.raise_()
        self.activateWindow()
        self.input_edit.setFocus()

    def _submit_input(self) -> None:
        value = self.input_edit.text()
        self.input_panel.hide()
        self.input_submitted.emit(value)

    def _cancel_input(self) -> None:
        self.input_panel.hide()
        self.input_cancelled.emit()

    def hide_input_prompt(self) -> None:
        self.input_panel.hide()

    def _template_html(self, step: TraceStep) -> str:
        template = canonical_template(self.template)
        if template == "branch":
            return self._branch_html(step)
        if template == "loop":
            return self._loop_html(step)
        if template == "array":
            return self._array_html(step)
        if template == "recursion":
            return self._recursion_html(step)
        return self._values_html(step)

    def _values_html(self, step: TraceStep) -> str:
        before = step.variables_before
        after = step.variables_after
        expression = step.details.get("expression", step.source or step.title)
        value = step.details.get("value", step.details.get("result", ""))
        cards = self._variable_cards(before, after)
        result = ""
        if value != "":
            result = (
                "<tr><td colspan='3' style='padding:10px 4px 2px; color:#526873;'>"
                "계산 결과</td></tr>"
                f"<tr><td colspan='3' style='font-size:18px; font-weight:700; color:#172c36;'>"
                f"{escape(str(value))}</td></tr>"
            )
        return (
            "<table width='100%' cellspacing='0' cellpadding='0'>"
            f"<tr><td colspan='3' style='padding:3px 4px 12px; color:#2766cc; font-family:Consolas;'>"
            f"{escape(str(expression))}</td></tr>"
            f"{cards}{result}</table>"
        )

    def _branch_html(self, step: TraceStep) -> str:
        details = step.details
        condition = details.get("condition", step.source or "조건식")
        result = bool(details.get("result", False))
        branch = str(details.get("branch", "if"))
        selected = "True" if result else "False"
        true_background = "#edf4ff" if result else "#f7fafb"
        true_color = "#2766cc" if result else "#aab8be"
        false_background = "#edf4ff" if not result else "#f7fafb"
        false_color = "#2766cc" if not result else "#aab8be"
        return (
            "<table width='100%' cellspacing='0' cellpadding='0'>"
            "<tr><td align='center' style='padding:8px;'>"
            "<div style='border:1px solid #dfe6ea; border-radius:9px; padding:10px; background:#ffffff;'>"
            f"<span style='color:#697c87;'>조건식</span><br><b style='font-size:18px;'>"
            f"{escape(str(condition))}</b><br>"
            f"<span style='color:#2766cc; font-weight:700;'>{selected}</span></div></td></tr>"
            "<tr><td align='center' style='color:#8b9aa1; padding:0 0 4px;'>↓ 선택된 실행 경로</td></tr>"
            "<tr><td><table width='100%' cellspacing='8' cellpadding='0'><tr>"
            f"<td width='50%' valign='top' style='border:1px solid {'#2766cc' if result else '#dfe6ea'}; "
            f'border-radius:8px; padding:11px; background:{true_background}; color:{true_color};">'
            "<b>True 경로</b><br><span style='font-size:11px;'>"
            f"{'실행됨' if result else '실행되지 않음'}</span></td>"
            f"<td width='50%' valign='top' style='border:1px solid {'#2766cc' if not result else '#dfe6ea'}; "
            f'border-radius:8px; padding:11px; background:{false_background}; color:{false_color};">'
            "<b>False / else 경로</b><br><span style='font-size:11px;'>"
            f"{'실행됨' if not result else '실행되지 않음'}</span></td>"
            "</tr></table></td></tr>"
            f"<tr><td align='center' style='padding:7px; color:#697c87;'>실제 선택: "
            f"<b style='color:#2766cc;'>{escape(branch)}</b></td></tr></table>"
        )

    def _loop_html(self, step: TraceStep) -> str:
        details = step.details
        loop_type = str(details.get("loop_type", "loop"))
        iterable = str(details.get("iterable", ""))
        iteration = details.get("iteration", details.get("count", "—"))
        body_title = "for 반복 본문" if loop_type == "for" else "while 반복 본문"
        history = [
            item
            for item in self.trace.steps[: self.step_index + 1]
            if item.kind == "iteration" and item.details.get("loop_type") == loop_type
        ]
        rows = []
        for item in history[-6:]:
            changed = self._changed_variables(item.variables_before, item.variables_after)
            rows.append(
                "<tr>"
                f"<td style='padding:7px 8px; border-bottom:1px solid #edf1f3;'>{item.details.get('iteration', '—')}</td>"
                f"<td style='padding:7px 8px; border-bottom:1px solid #edf1f3; font-family:Consolas;'>"
                f"{escape(str(item.details.get('variable', '—')))}</td>"
                f"<td style='padding:7px 8px; border-bottom:1px solid #edf1f3; font-family:Consolas;'>"
                f"{escape(changed or '상태 유지')}</td></tr>"
            )
        table = (
            "<table width='100%' cellspacing='0' cellpadding='0' style='border:1px solid #dfe6ea;'>"
            "<tr style='background:#f7fafb; color:#697c87;'><th align='left' style='padding:7px 8px;'>회차</th>"
            "<th align='left' style='padding:7px 8px;'>반복 변수</th><th align='left' style='padding:7px 8px;'>상태 변화</th></tr>"
            + ("".join(rows) or "<tr><td colspan='3' style='padding:10px; color:#697c87;'>첫 회차를 기다리는 중</td></tr>")
            + "</table>"
        )
        return (
            "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
            "<td width='39%' valign='top' style='padding:8px 13px 8px 3px;'>"
            f"<div style='color:#697c87; font-size:11px;'>{body_title}</div>"
            f"<div style='margin-top:8px; border:1px solid #dca54e; border-radius:9px; background:#fff4da; padding:14px;'>"
            f"<b style='font-family:Consolas; font-size:15px;'>{escape(loop_type)} loop</b><br>"
            f"<span style='color:#526873; font-family:Consolas;'>{escape(iterable or step.source or '조건 확인')}</span>"
            f"<br><br><span style='color:#a6600b;'>현재 회차</span><br><b style='font-size:20px;'>{escape(str(iteration))}</b></div>"
            "</td><td valign='top' style='padding:8px 3px;'>"
            f"<div style='color:#697c87; font-size:11px; padding-bottom:7px;'>회차별 누적 기록</div>{table}"
            "</td></tr></table>"
        )

    def _array_html(self, step: TraceStep) -> str:
        before = step.variables_before
        after = step.variables_after
        arrays = [(name, value) for name, value in after.items() if isinstance(value, list)]
        if not arrays:
            arrays = [(name, value) for name, value in before.items() if isinstance(value, list)]
        if not arrays:
            return "<div style='padding:12px; color:#697c87;'>표시할 배열이 없습니다.</div>"
        chunks = []
        for name, values in arrays:
            old = before.get(name)
            active_index = self._active_list_index(step, old, values)
            cells = []
            for index, value in enumerate(values):
                active = index == active_index
                border = "#2766cc" if active else "#dfe6ea"
                background = "#edf4ff" if active else "#ffffff"
                cells.append(
                    f"<td align='center' style='min-width:52px; border:1px solid {border}; border-radius:7px; "
                    f"background:{background}; padding:11px 7px; font-size:17px; font-weight:700;'>"
                    f"{escape(display_value(value))}<br><span style='font-size:10px; font-family:Consolas; "
                    f"color:{'#2766cc' if active else '#697c87'};'>[{index}]</span></td>"
                )
            pointer = "현재 접근 위치" if active_index is not None else "인덱스 정보 없음"
            empty_cell = "<td style='padding:10px;'>빈 배열</td>"
            chunks.append(
                f"<tr><td colspan='{max(1, len(values))}' style='padding:3px 0 7px; color:#526873;'>"
                f"<b>{escape(name)}</b>  <span style='color:#697c87;'>({len(values)}개) · {pointer}</span></td></tr>"
                f"<tr>{''.join(cells) or empty_cell}</tr>"
            )
        return (
            "<table width='100%' cellspacing='7' cellpadding='0'>"
            + "".join(chunks)
            + "</table>"
            "<div style='padding-top:8px; color:#697c87;'>셀은 고정되고, 현재 위치만 포인터로 강조됩니다.</div>"
        )

    def _recursion_html(self, step: TraceStep) -> str:
        stack = self._call_stack_at(self.step_index)
        details = step.details
        stack_cells = []
        for index, frame in enumerate(stack):
            active = index == len(stack) - 1
            border = "#7657ad" if active else "#dfe6ea"
            background = "#f3effb" if active else "#ffffff"
            stack_cells.append(
                f"<tr><td style='border:1px solid {border}; border-radius:7px; background:{background}; padding:9px;'>"
                f"<span style='color:#697c87;'>frame #{index}</span><br><b>{escape(frame)}</b>"
                f"<span style='float:right; color:#7657ad;'>{'실행 중' if active else '대기'}</span></td></tr>"
            )
        function_name = str(details.get("function", step.scope))
        argument_value = details.get("arguments", details.get("value", "—"))
        return (
            "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
            "<td width='45%' valign='top' style='padding:7px 14px 7px 3px;'>"
            "<div style='color:#697c87; font-size:11px;'>CALL STACK</div>"
            f"<table width='100%' cellspacing='6' cellpadding='0' style='margin-top:5px;'>"
            f"{''.join(stack_cells)}</table></td>"
            "<td valign='top' style='padding:7px 3px;'>"
            f"<div style='border:1px solid #dfe6ea; border-radius:8px; padding:12px;'>"
            f"<span style='color:#697c87;'>현재 이벤트</span><br><b style='font-size:16px; color:#7657ad;'>"
            f"{escape(function_name)}</b><br><br>"
            f"<span style='color:#697c87;'>스코프</span>  <b>{escape(step.scope)}</b><br>"
            f"<span style='color:#697c87;'>인자/반환</span>  <b>{escape(display_value(argument_value))}</b>"
            "</div></td></tr></table>"
        )

    def _variable_cards(self, before: dict, after: dict) -> str:
        values = list(after.items())
        if not values:
            return "<tr><td colspan='3' style='padding:13px 4px; color:#697c87;'>현재 표시할 변수가 없습니다.</td></tr>"
        cells = []
        for name, value in values:
            old = before.get(name, _UNDEFINED)
            changed = old is _UNDEFINED or old != value
            border = "#dca54e" if changed else "#dfe6ea"
            background = "#fff4da" if changed else "#ffffff"
            marker = " <span style='color:#a6600b; font-size:10px;'>변경</span>" if changed else ""
            cells.append(
                f"<td width='33%' valign='top' style='border:1px solid {border}; border-radius:8px; background:{background}; padding:10px;'>"
                f"<span style='color:#697c87; font-family:Consolas;'>{escape(name)}</span>{marker}<br>"
                f"<b style='font-size:18px; font-family:Consolas;'>{escape(display_value(value))}</b></td>"
            )
        rows = []
        for start in range(0, len(cells), 3):
            row = cells[start : start + 3]
            while len(row) < 3:
                row.append("<td width='33%'></td>")
            rows.append(f"<tr>{''.join(row)}</tr>")
        return "<tr><td colspan='3'><table width='100%' cellspacing='7' cellpadding='0'>" + "".join(rows) + "</table></td></tr>"

    def _changed_variables(self, before: dict, after: dict) -> str:
        changes = []
        for name in list(after) + [key for key in before if key not in after]:
            old = before.get(name, _UNDEFINED)
            new = after.get(name, _UNDEFINED)
            if old != new:
                old_text = "—" if old is _UNDEFINED else display_value(old)
                new_text = "—" if new is _UNDEFINED else display_value(new)
                changes.append(f"{name}: {old_text} → {new_text}")
        return ", ".join(changes)

    def _render_diff(self, step: TraceStep) -> None:
        names = list(step.variables_before)
        names.extend(name for name in step.variables_after if name not in names)
        rows = []
        for name in names:
            old = step.variables_before.get(name, _UNDEFINED)
            new = step.variables_after.get(name, _UNDEFINED)
            if old == new:
                continue
            old_text = "—" if old is _UNDEFINED else display_value(old)
            new_text = "—" if new is _UNDEFINED else display_value(new)
            rows.append(
                "<tr>"
                f"<td style='padding:4px 6px; color:#172c36;'><b>{escape(name)}</b></td>"
                f"<td style='padding:4px 6px; color:#697c87; font-family:Consolas;'>{escape(old_text)}</td>"
                "<td style='padding:4px; color:#aab8be;'>→</td>"
                f"<td style='padding:4px 6px; color:#a6600b; font-family:Consolas;'><b>{escape(new_text)}</b></td></tr>"
            )
        if not rows:
            rows.append("<tr><td style='padding:4px 6px; color:#697c87;'>상태 변화 없음</td></tr>")
        self.diff_view.setHtml(
            "<table width='100%' cellspacing='0' cellpadding='0'>"
            + "".join(rows)
            + "</table>"
            + f"<div style='padding:6px; color:#697c87; font-family:Consolas;'>"
            + f"{escape(step.source or step.title)}</div>"
        )

    def _render_watch_cards(self, step: TraceStep) -> None:
        details = step.details
        template = canonical_template(self.template)
        items: list[tuple[str, str, bool]] = []
        if template == "branch":
            items = [
                ("조건 결과", "True" if details.get("result") else "False", True),
                ("선택 경로", str(details.get("branch", "—")), True),
                ("현재 줄", str(step.line or "—"), False),
            ]
        elif template == "loop":
            items = [
                ("반복 유형", str(details.get("loop_type", "—")), False),
                ("현재 회차", str(details.get("iteration", details.get("count", "—"))), True),
                ("반복 변수", str(details.get("variable", "—")), False),
            ]
        elif template == "array":
            name, values = next(((n, v) for n, v in step.variables_after.items() if isinstance(v, list)), ("배열", []))
            active_index = self._active_list_index(step, step.variables_before.get(name), values)
            items = [
                ("배열", name, False),
                ("길이", str(len(values)), False),
                ("현재 인덱스", str(active_index if active_index is not None else "—"), True),
            ]
        elif template == "recursion":
            items = [
                ("현재 함수", str(details.get("function", step.scope)), True),
                ("스코프", step.scope, False),
                ("호출 깊이", str(len(self._call_stack_at(self.step_index))), True),
            ]
        else:
            changed = self._changed_variables(step.variables_before, step.variables_after)
            items = [
                ("실행 줄", str(step.line or "—"), False),
                ("변수 수", str(len(step.variables_after)), False),
                ("상태", "변경 있음" if changed else "상태 유지", bool(changed)),
            ]
        self._set_watch_cards(items)

    def _set_watch_cards(self, items: list[tuple[str, str, bool]]) -> None:
        while self.watch_layout.count():
            item = self.watch_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for name, value, changed in items:
            card = QFrame()
            card.setObjectName("watchCard")
            card.setProperty("changed", changed)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(9, 7, 9, 7)
            card_layout.setSpacing(2)
            name_label = QLabel(name)
            name_label.setObjectName("watchName")
            value_label = QLabel(value)
            value_label.setObjectName("watchValue")
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            card_layout.addWidget(name_label)
            card_layout.addWidget(value_label)
            self.watch_layout.addWidget(card, 1)
        self.watch_layout.addStretch(1)

    def _render_explanation(self, step: TraceStep, summary: str) -> None:
        changed = self._changed_variables(step.variables_before, step.variables_after)
        message = summary
        if changed:
            message += f"  이번 Step에서 {changed} 상태로 바뀌었습니다."
        elif step.kind in {"condition", "iteration", "loop", "loop_end"}:
            message += "  제어 흐름의 변화는 색상과 표의 회차 기록으로 확인할 수 있습니다."
        else:
            message += "  상태 변화가 없으면 같은 위치에서 유지되며, 실행 흐름만 기록됩니다."
        self.explanation.setText(message)

    def _active_list_index(self, step: TraceStep, old, values: list) -> int | None:
        source = step.source or str(step.details.get("expression", ""))
        match = re.search(r"\[(\d+)\]", source)
        if match:
            index = int(match.group(1))
            return index if index < len(values) else None
        if isinstance(old, list):
            for index, (left, right) in enumerate(zip(old, values)):
                if left != right:
                    return index
            if len(values) > len(old):
                return len(old)
            if len(values) < len(old) and values:
                return len(values) - 1
        return 0 if values else None

    def _call_stack_at(self, step_index: int) -> list[str]:
        stack = ["global"]
        for step in self.trace.steps[: step_index + 1]:
            if step.kind == "function_call":
                function = step.details.get("function")
                if function:
                    stack.append(str(function))
            elif step.kind == "function_return" and len(stack) > 1:
                stack.pop()
        return stack

    def _highlight_line(self, line: int | None) -> None:
        lines = self.trace.code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not lines:
            lines = [""]
        rows = []
        for index, source in enumerate(lines, start=1):
            current = bool(line and index == line)
            background = "#edf4ff" if current else "#fbfcfd"
            number_color = "#2766cc" if current else "#9aaab2"
            marker = "▶" if current else ""
            code = escape(source) if source else "&nbsp;"
            rows.append(
                f"<tr style='background:{background};'><td width='30' align='right' style='padding:3px 5px; color:{number_color};'>"
                f"{marker} {index}</td><td style='padding:3px 7px; color:#172c36; font-family:Consolas; white-space:pre;'>"
                f"{code}</td></tr>"
            )
        self.code_view.setHtml(
            "<table width='100%' cellspacing='0' cellpadding='0' style='font-size:11px;'>"
            + "".join(rows)
            + "</table>"
        )

    def _animate_card(self) -> None:
        if self.reduce_motion.isChecked():
            self.card_opacity.setOpacity(1.0)
            return
        self._card_animation.stop()
        self._card_animation.setStartValue(0.35)
        self._card_animation.setEndValue(1.0)
        self._card_animation.start()

    def _motion_setting_changed(self, enabled: bool) -> None:
        if enabled:
            self._card_animation.stop()
            self.card_opacity.setOpacity(1.0)

    def _first_step(self) -> None:
        if self.trace.steps:
            self.progress.setValue(1)

    def previous_step(self) -> None:
        self.step_index = max(0, self.step_index - 1)
        self.progress.setValue(self.step_index + 1)

    def next_step(self) -> None:
        if not self.trace.steps:
            return
        if self.step_index >= len(self.trace.steps) - 1:
            self._playing = False
            self._update_play_button()
            self._timer.stop()
            return
        self.step_index += 1
        self.progress.setValue(self.step_index + 1)

    def toggle_play(self) -> None:
        self._playing = not self._playing
        if self._playing:
            self._update_timer()
            self._timer.start()
        else:
            self._timer.stop()
        self._update_play_button()

    def _update_play_button(self) -> None:
        self.play_button.setText("일시정지" if self._playing else "재생")

    def _update_timer(self) -> None:
        intervals = {1: 2400, 2: 1300, 3: 850, 4: 550}
        self._timer.setInterval(intervals.get(self.speed.value(), 1300))
        self.speed_value.setText({1: "0.5×", 2: "1×", 3: "1.5×", 4: "2×"}.get(self.speed.value(), "1×"))

    def toggle_split(self) -> None:
        if self._split_snapshot is None:
            screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
            if screen is None:
                return
            external = likely_document_window(exclude_hwnds=[int(self.winId())])
            self._split_snapshot = arrange_split(
                external.hwnd if external else None,
                int(self.winId()),
                screen.geometry(),
            )
            self.layout_button.setText("분할 해제")
            self.layout_button.setToolTip("Floating View로 돌아가기")
        else:
            restore_layout(self._split_snapshot, int(self.winId()))
            self._split_snapshot = None
            self.layout_button.setText("PDF/PPT 함께 보기")
            self.layout_button.setToolTip("외부 PDF/PPT 창과 나란히 배치")

    def closeEvent(self, event) -> None:
        if self.input_panel.isVisible():
            self.input_panel.hide()
            self.input_cancelled.emit()
        if self._split_snapshot is not None:
            restore_layout(self._split_snapshot, int(self.winId()))
            self._split_snapshot = None
        self._timer.stop()
        super().closeEvent(event)
