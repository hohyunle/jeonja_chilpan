"""Launch the current project source from a small desktop EXE."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import sys


PROJECT_FOLDER_NAME = "캡스톤"


def _show_error(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "CodeTrace 실행 오류", 0x10)
    except AttributeError:
        print(message, file=sys.stderr)


def _find_project_root() -> Path | None:
    executable_dir = Path(sys.executable).resolve().parent
    candidates = [
        executable_dir / PROJECT_FOLDER_NAME,
        Path(r"C:\Users\홍길동\Desktop\캡스톤"),
    ]
    for candidate in candidates:
        if (candidate / "app" / "main.py").is_file():
            return candidate
    return None


def main() -> int:
    project_root = _find_project_root()
    if project_root is None:
        _show_error(
            "캡스톤 프로젝트 폴더를 찾지 못했습니다.\n\n"
            "CodeTrace.exe를 캡스톤 폴더와 같은 바탕화면 위치에서 실행하세요."
        )
        return 1

    python_candidates = [
        project_root / ".venv" / "Scripts" / "pythonw.exe",
        project_root / ".venv" / "Scripts" / "python.exe",
    ]
    python_path = next((path for path in python_candidates if path.is_file()), None)
    if python_path is None:
        _show_error(
            "Python 실행 환경을 찾지 못했습니다.\n\n"
            f"다음 경로를 확인하세요:\n{project_root / '.venv' / 'Scripts'}"
        )
        return 1

    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    project_path = str(project_root)
    existing_python_path = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        project_path
        if not existing_python_path
        else project_path + os.pathsep + existing_python_path
    )
    try:
        subprocess.Popen(
            [str(python_path), "-m", "app.main"],
            cwd=project_root,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        _show_error(f"CodeTrace를 시작하지 못했습니다.\n\n{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
