from __future__ import annotations

from io import BytesIO
from queue import Queue
import threading

from PySide6.QtCore import QObject, Signal, Slot

from app.core.executor import EducationalExecutor, InputBroker
from app.core.models import ExecutionTrace
from app.core.ocr import OcrService


class OcrWorker(QObject):
    """Own PaddleOCR from warm-up through recognition on one native thread.

    PaddlePaddle's Windows runtime can terminate the process when an engine is
    initialized in one Qt callback and reused from a later Qt callback. A
    dedicated Python worker keeps the model and every predict call on the same
    thread while Qt remains responsible only for queued UI signals.
    """

    finished = Signal(str)
    failed = Signal(str)
    ready = Signal()
    warmup_failed = Signal(str)
    process_requested = Signal(bytes)

    def __init__(self) -> None:
        super().__init__()
        self._service: OcrService | None = None
        self._requests: Queue[tuple[str, bytes | None]] = Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.process_requested.connect(self.process)

    def start(self) -> None:
        """Start the long-lived OCR owner thread if it is not running."""

        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="CodeTrace-OCR",
            daemon=True,
        )
        self._thread.start()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @Slot()
    def warmup(self) -> None:
        """Queue model loading without blocking the Qt UI thread."""

        self.start()
        self._requests.put(("warmup", None))

    def _run(self) -> None:
        service = OcrService()
        self._service = service
        while not self._stop.is_set():
            operation, payload = self._requests.get()
            if operation == "stop":
                break
            if operation == "warmup":
                try:
                    service.warm_up()
                    self.ready.emit()
                except Exception as exc:
                    # A missing offline model should not prevent direct-code
                    # execution. The main window displays a setup hint.
                    self.warmup_failed.emit(str(exc))
                continue
            if operation != "process" or payload is None:
                continue
            self._process_in_worker(service, payload)

    def _process_in_worker(self, service: OcrService, image_bytes: bytes) -> None:
        try:
            from PIL import Image
            import numpy as np

            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            lines = service.recognize(np.asarray(image))
            self.finished.emit(service.lines_to_code(lines))
        except Exception as exc:
            self.failed.emit(str(exc))

    @Slot(bytes)
    def process(self, image_bytes: bytes) -> None:
        """Queue a capture; the same worker thread performs model inference."""

        self.start()
        self._requests.put(("process", image_bytes))

    def stop(self) -> None:
        """Stop the OCR owner thread during application shutdown."""

        thread = self._thread
        if thread is None:
            return
        self._stop.set()
        self._requests.put(("stop", None))
        if thread is not threading.current_thread():
            thread.join(timeout=5.0)
        self._thread = None
        self._service = None


class ExecutionWorker(QObject):
    finished = Signal(object)
    input_requested = Signal(str)

    def __init__(self, code: str) -> None:
        super().__init__()
        self.code = code
        self._broker = InputBroker(self._request_input)

    def _request_input(self, prompt: str) -> None:
        self.input_requested.emit(prompt)

    @Slot()
    def run(self) -> None:
        trace = EducationalExecutor(
            self.code,
            input_broker=self._broker,
            max_steps=2_000,
            max_seconds=2.5,
        ).run()
        self.finished.emit(trace)

    def provide_input(self, value: str) -> None:
        self._broker.submit(value)

    def cancel_input(self) -> None:
        self._broker.cancel()
