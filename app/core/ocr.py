from __future__ import annotations

import os
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_DETECTION_MODEL_NAME = "PP-OCRv5_mobile_det"
# The English-only model silently drops Korean glyphs.  The Korean PP-OCRv5
# mobile recognizer also supports English and digits, which keeps it suitable
# for Python source while allowing Korean comments and labels.
_RECOGNITION_MODEL_NAME = "korean_PP-OCRv5_mobile_rec"
_MODEL_ROOT_ENV = "CODETRACE_OCR_MODEL_DIR"
_MAX_INPUT_SIDE = 1536


@dataclass(slots=True)
class OcrLine:
    text: str
    confidence: float | None = None
    box: list[list[int]] | None = None


class OcrService:
    """Lazy, local-only OCR adapter.

    PaddleOCR is imported and initialized only when the first OCR request is made.
    This keeps the editor and trace workflow fast and usable even before local OCR
    models have been staged for offline use.
    """

    def __init__(self) -> None:
        self._engine: Any = None
        self._load_error: str | None = None
        self._model_root: Path | None = None

    @property
    def available(self) -> bool:
        return self._load_error is None

    @property
    def is_ready(self) -> bool:
        """Whether the local model has already been loaded in this process."""

        return self._engine is not None

    def warm_up(self) -> None:
        """Load the local OCR model before the user starts a capture."""

        self._ensure_engine()

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def _ensure_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        if self._load_error:
            raise RuntimeError(self._load_error)
        # Do not spend time on a remote connectivity probe at application startup.
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import PaddleOCR

            model_root, detection_dir, recognition_dir = self._find_local_models()

            self._engine = PaddleOCR(
                text_detection_model_name=_DETECTION_MODEL_NAME,
                text_detection_model_dir=str(detection_dir),
                text_recognition_model_name=_RECOGNITION_MODEL_NAME,
                text_recognition_model_dir=str(recognition_dir),
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device="cpu",
                # Keep more pixels from a wide slide/code capture. The default
                # 960px cap can make small source-code glyphs too tiny before
                # recognition.
                text_det_limit_side_len=1536,
                text_det_limit_type="max",
                # The bundled PIR models currently fail in PaddlePaddle's Windows
                # oneDNN path. Plain CPU inference is stable and fast enough for a
                # single code screenshot; keep this explicit for reproducibility.
                enable_mkldnn=False,
                cpu_threads=max(2, min(8, os.cpu_count() or 4)),
            )
            self._model_root = model_root
            return self._engine
        except Exception as exc:
            self._load_error = (
            "한국어 OCR 엔진을 준비하지 못했습니다. "
                "PaddleOCR 모델이 로컬에 준비되어 있는지 확인하세요. "
                f"모델 경로 환경변수: {_MODEL_ROOT_ENV}. "
                f"({exc})"
            )
            raise RuntimeError(self._load_error) from exc

    @classmethod
    def _find_local_models(cls) -> tuple[Path, Path, Path]:
        """Find the offline OCR models without triggering a network download.

        Paddle's native Windows loader is sensitive to non-ASCII model paths on
        some installations. The search prefers an explicit path and shared ASCII
        locations so the application remains usable when the Windows account or
        installation directory contains non-ASCII characters.
        """

        roots: list[Path] = []
        configured_root = os.environ.get(_MODEL_ROOT_ENV)
        if configured_root:
            roots.append(Path(configured_root))

        roots.append(Path(__file__).resolve().parents[2] / "models")
        roots.append(Path(r"C:\ProgramData\CodeTrace\models"))
        roots.append(Path(r"C:\Temp\CodeTrace\models"))

        public_root = os.environ.get("PUBLIC")
        if public_root:
            roots.append(Path(public_root) / "CodeTrace" / "models")

        seen: set[str] = set()
        for root in roots:
            try:
                root = root.expanduser().resolve()
            except OSError:
                continue
            key = str(root).casefold()
            if key in seen:
                continue
            seen.add(key)
            if not cls._is_ascii_path(root):
                continue
            detection_dir = root / _DETECTION_MODEL_NAME
            recognition_dir = root / _RECOGNITION_MODEL_NAME
            if cls._is_model_dir(detection_dir) and cls._is_model_dir(recognition_dir):
                return root, detection_dir, recognition_dir

        staged_root = cls._stage_cached_models()
        if staged_root is not None:
            return (
                staged_root,
                staged_root / _DETECTION_MODEL_NAME,
                staged_root / _RECOGNITION_MODEL_NAME,
            )

        searched = ", ".join(str(root) for root in roots)
        raise FileNotFoundError(
            "오프라인 한국어 OCR 모델을 찾지 못했습니다. "
            f"{_DETECTION_MODEL_NAME} 및 {_RECOGNITION_MODEL_NAME} 모델을 준비하세요. "
            f"검색 경로: {searched}"
        )

    @classmethod
    def _stage_cached_models(cls) -> Path | None:
        """Copy an existing PaddleX cache to the ASCII runtime location once."""

        try:
            cached_root = Path.home() / ".paddlex" / "official_models"
            destination_root = Path(r"C:\Temp\CodeTrace\models")
            if not cls._is_ascii_path(destination_root):
                return None
            source_dirs = [
                cached_root / _DETECTION_MODEL_NAME,
                cached_root / _RECOGNITION_MODEL_NAME,
            ]
            if not all(cls._is_model_dir(path) for path in source_dirs):
                return None
            destination_root.mkdir(parents=True, exist_ok=True)
            for source_dir in source_dirs:
                shutil.copytree(
                    source_dir,
                    destination_root / source_dir.name,
                    dirs_exist_ok=True,
                )
            if all(
                cls._is_model_dir(destination_root / model_name)
                for model_name in (_DETECTION_MODEL_NAME, _RECOGNITION_MODEL_NAME)
            ):
                return destination_root
        except (OSError, shutil.Error):
            return None
        return None

    @staticmethod
    def _is_model_dir(path: Path) -> bool:
        if not path.is_dir():
            return False
        # PaddleOCR 3.x uses inference.json; accepting pdmodel keeps the adapter
        # usable with a legacy offline model bundle as well.
        has_model = (path / "inference.json").is_file() or (path / "inference.pdmodel").is_file()
        return has_model and (path / "inference.pdiparams").is_file()

    @staticmethod
    def _is_ascii_path(path: Path) -> bool:
        try:
            str(path).encode("ascii")
        except UnicodeEncodeError:
            return False
        return True

    def recognize(self, image: Any) -> list[OcrLine]:
        engine = self._ensure_engine()
        results = engine.predict(self._prepare_image(image))
        lines: list[OcrLine] = []
        for result in results:
            payload = self._result_payload(result)
            texts = payload.get("rec_texts")
            scores = payload.get("rec_scores")
            boxes = payload.get("rec_boxes")
            if boxes is None:
                boxes = payload.get("rec_polys")
            texts = [] if texts is None else texts
            scores = [] if scores is None else scores
            boxes = [] if boxes is None else boxes
            for index, text in enumerate(texts):
                text = str(text).strip()
                if not text:
                    continue
                score = None
                if index < len(scores):
                    try:
                        score = float(scores[index])
                    except (TypeError, ValueError):
                        score = None
                box = None
                if index < len(boxes):
                    box = self._normalize_box(boxes[index])
                lines.append(OcrLine(text, score, box))
        # PaddleOCR returns reading order for normal code screenshots. Sorting by
        # vertical center then left edge is a safe fallback for multi-line snippets.
        lines.sort(key=lambda line: self._line_sort_key(line))
        return self._merge_same_line_fragments(lines)

    @classmethod
    def _merge_same_line_fragments(cls, lines: list[OcrLine]) -> list[OcrLine]:
        """Join OCR boxes that belong to one source-code line.

        A code screenshot can make a detector return ``if x >=`` and ``10:`` as
        two neighboring boxes. Treating those boxes as separate source lines
        would corrupt indentation and parsing. Only boxes with clear vertical
        overlap are merged; boxes without coordinates remain untouched.
        """

        if len(lines) < 2:
            return lines

        groups: list[list[OcrLine]] = []
        for line in lines:
            if not line.box:
                groups.append([line])
                continue
            target: list[OcrLine] | None = None
            for candidate in reversed(groups):
                if not candidate[-1].box:
                    break
                if cls._same_visual_line(candidate[-1], line):
                    target = candidate
                    break
                # Reading-order sorting means an older group cannot become a
                # match after a clearly separated line has already appeared.
                if cls._box_bounds(candidate[-1].box)[1] < cls._box_bounds(line.box)[1]:
                    break
            if target is None:
                groups.append([line])
            else:
                target.append(line)

        merged: list[OcrLine] = []
        for group in groups:
            if len(group) == 1:
                merged.append(group[0])
                continue
            group.sort(key=lambda item: cls._box_bounds(item.box)[0] if item.box else 0)
            text = group[0].text.strip()
            confidence_sum = 0.0
            confidence_weight = 0
            all_points: list[list[int]] = []
            for item in group:
                if item.confidence is not None:
                    weight = max(1, len(item.text.strip()))
                    confidence_sum += item.confidence * weight
                    confidence_weight += weight
                if item.box:
                    all_points.extend(item.box)
            previous = group[0]
            for item in group[1:]:
                separator = " " if cls._needs_separator(previous, item) else ""
                text += separator + item.text.strip()
                previous = item
            left = min(point[0] for point in all_points)
            top = min(point[1] for point in all_points)
            right = max(point[0] for point in all_points)
            bottom = max(point[1] for point in all_points)
            merged.append(
                OcrLine(
                    text=text,
                    confidence=(confidence_sum / confidence_weight if confidence_weight else None),
                    box=[[left, top], [right, top], [right, bottom], [left, bottom]],
                )
            )
        merged.sort(key=lambda line: cls._line_sort_key(line))
        return merged

    @staticmethod
    def _prepare_image(image: Any) -> Any:
        """Avoid spending inference time on pixels the detector will discard."""

        try:
            shape = getattr(image, "shape", None)
            if shape is None or len(shape) < 2:
                return image
            height, width = int(shape[0]), int(shape[1])
        except (TypeError, ValueError, IndexError):
            return image
        longest_side = max(height, width)
        if longest_side <= _MAX_INPUT_SIDE:
            return image
        scale = _MAX_INPUT_SIDE / longest_side
        new_size = (
            max(1, round(width * scale)),
            max(1, round(height * scale)),
        )
        try:
            from PIL import Image
            import numpy as np

            source = np.asarray(image)
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            return np.asarray(Image.fromarray(source).resize(new_size, resampling))
        except (ImportError, TypeError, ValueError):
            # Let PaddleOCR handle uncommon image containers as before.
            return image

    @staticmethod
    def _box_bounds(box: list[list[int]]) -> tuple[int, int, int, int]:
        x_values = [point[0] for point in box]
        y_values = [point[1] for point in box]
        return min(x_values), min(y_values), max(x_values), max(y_values)

    @classmethod
    def _same_visual_line(cls, first: OcrLine, second: OcrLine) -> bool:
        if not first.box or not second.box:
            return False
        _, first_top, _, first_bottom = cls._box_bounds(first.box)
        _, second_top, _, second_bottom = cls._box_bounds(second.box)
        overlap = max(0, min(first_bottom, second_bottom) - max(first_top, second_top))
        first_height = max(1, first_bottom - first_top)
        second_height = max(1, second_bottom - second_top)
        return overlap / min(first_height, second_height) >= 0.45

    @classmethod
    def _needs_separator(cls, first: OcrLine, second: OcrLine) -> bool:
        if not first.box or not second.box:
            return True
        _, _, first_right, _ = cls._box_bounds(first.box)
        second_left, _, _, _ = cls._box_bounds(second.box)
        first_left, _, _, first_bottom = cls._box_bounds(first.box)
        first_top = cls._box_bounds(first.box)[1]
        first_width = max(1, first_right - first_left)
        first_height = max(1, first_bottom - first_top)
        estimated_char_width = max(1.0, first_width / max(1, len(first.text.strip())))
        gap = second_left - first_right
        # A tiny gap is normally a detector split inside one token; a larger
        # gap is the source-code space between operators, names, or literals.
        return gap > max(2.0, min(estimated_char_width * 0.28, first_height * 0.7))

    @staticmethod
    def _normalize_box(box: Any) -> list[list[int]] | None:
        """Normalize Paddle's rectangle or polygon output to corner points."""

        try:
            values = box.tolist() if hasattr(box, "tolist") else box
            if not isinstance(values, (list, tuple)):
                return None
            if len(values) == 4 and all(
                isinstance(value, (int, float)) for value in values
            ):
                x1, y1, x2, y2 = (int(round(value)) for value in values)
                return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            points: list[list[int]] = []
            for point in values:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    return None
                points.append([int(round(point[0])), int(round(point[1]))])
            return points or None
        except (TypeError, ValueError, IndexError):
            return None

    @staticmethod
    def _line_sort_key(line: OcrLine) -> tuple[float, float]:
        if not line.box:
            return (0.0, 0.0)
        y_values = [point[1] for point in line.box]
        x_values = [point[0] for point in line.box]
        return (sum(y_values) / len(y_values), sum(x_values) / len(x_values))

    @staticmethod
    def _result_payload(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            return result.get("res", result)
        # PaddleOCR 3.x result objects expose json-like data through to_dict/json
        # depending on the installed pipeline version.
        for name in ("to_dict", "json"):
            attribute = getattr(result, name, None)
            try:
                value = attribute() if callable(attribute) else attribute
            except Exception:
                continue
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    continue
            if isinstance(value, dict):
                return value.get("res", value)
        for name in ("rec_texts", "rec_scores", "rec_boxes", "rec_polys"):
            if hasattr(result, name):
                return {
                    key: getattr(result, key, [])
                    for key in ("rec_texts", "rec_scores", "rec_boxes", "rec_polys")
                }
        return {}

    @staticmethod
    def lines_to_code(lines: list[OcrLine]) -> str:
        """Turn detected lines into editable code while recovering indentation.

        OCR engines commonly return the text content without leading whitespace.
        When boxes are available, estimate a character width from each line and
        reconstruct only the leading indentation. The editor remains the source of
        truth when the screenshot is ambiguous.
        """

        if not lines:
            return ""
        lines = OcrService._merge_same_line_fragments(lines)
        usable = [line for line in lines if line.box]
        left_edges = []
        char_widths = []
        for line in usable:
            assert line.box is not None
            left = min(point[0] for point in line.box)
            right = max(point[0] for point in line.box)
            left_edges.append(left)
            if line.text:
                char_widths.append(max(1.0, (right - left) / len(line.text)))
        base_left = min(left_edges) if left_edges else 0
        char_width = sorted(char_widths)[len(char_widths) // 2] if char_widths else 8.0

        output: list[str] = []
        for line in lines:
            text = line.text.strip()
            if not text:
                output.append("")
                continue
            indent = 0
            if line.box:
                left = min(point[0] for point in line.box)
                raw_indent = max(0.0, (left - base_left) / char_width)
                if raw_indent < 0.75:
                    indent = 0
                elif raw_indent < 2.5:
                    indent = max(1, round(raw_indent))
                else:
                    # Small detector drift often turns a real four-space indent
                    # into 3~3.5 estimated character widths. Quantize ordinary
                    # Python indentation to four-space levels once the offset is
                    # clearly intentional, while retaining unusual one/two-space
                    # indentation for short offsets.
                    indent = max(4, round(raw_indent / 4) * 4)
                # Avoid turning ordinary anti-aliasing drift into one-space noise.
                indent = min(indent, 80)
            output.append(" " * indent + text)
        return "\n".join(output)
