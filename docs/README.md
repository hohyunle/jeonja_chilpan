# CodeTrace 문서 안내

이 폴더는 채팅 기록이 없어져도 다음 노트북에서 개발을 바로 이어갈 수 있도록 만든
프로젝트 기준 문서다. 새로운 노트북에서 작업을 시작할 때는 이 문서부터 열고 아래
순서로 읽는다.

1. [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) — 프로젝트 목적, 확정 결정, 현재 상태
2. [SETUP_WINDOWS.md](SETUP_WINDOWS.md) — Windows 11 개발 환경과 오프라인 실행 준비
3. [ARCHITECTURE.md](ARCHITECTURE.md) — 모듈 구조와 데이터 계약
4. [OCR_AND_CAPTURE.md](OCR_AND_CAPTURE.md) — 한국어 OCR, 화면 캡처, 듀얼모니터 동작
5. [DEVELOPMENT.md](DEVELOPMENT.md) — 개발 규칙, 테스트, 다음 작업 순서

## 가장 중요한 한 문장

CodeTrace는 Python을 실행하는 프로그램이 아니라, 지원 문법으로 작성된 Python 코드의
실행 과정을 `Trace`로 기록하고 학습자가 이해할 수 있는 장면으로 시각화하는 Windows
11용 오프라인 교육 프로그램이다.

## 문서 관리 규칙

- 새로운 큰 의사결정은 구현 전에 `PROJECT_HANDOFF.md`의 결정 로그와 현재 상태를 먼저 갱신한다.
- 코드 동작이 문서와 달라지면 코드를 기준으로 문서를 바로 수정한다.
- 지원 문법, Trace 필드, OCR 모델, 실행 방법이 바뀌면 관련 문서와 테스트를 함께 갱신한다.
- 채팅에서만 결정하고 문서에 남기지 않는다.
