# Code Visualizer Tool

Windows 11 화면 위에서 실행되는 프로그래밍 교육용 시각화 데스크톱 프로그램입니다.
외부 PDF/PPT 뷰어를 직접 열거나 파싱하지 않고, 사용자가 드래그한 화면 영역을 캡처해 OCR 입력으로 사용합니다.

다음 개발자가 채팅 없이 이어갈 수 있도록 상세 인수인계 문서는 [`docs/README.md`](docs/README.md)에서 시작합니다.

## 현재 구현 범위

- Floating Tool과 마우스·터치-마우스 기반 화면 영역 선택
- 전자칠판 없이도 마우스 드래그/클릭/키보드로 전체 흐름 테스트 가능
- `확인`, `연속 선택`, `취소`, `새로 시작` 흐름
- 여러 선택 영역의 순서 보존 및 메모리 내 임시 결합
- 로컬 PaddleOCR 연동 어댑터
- 제한된 Python 문법 검증
- 실제 Python 인터프리터를 호출하지 않는 Educational Executor
- 변수·조건·반복·리스트·함수·입출력 Trace
- Trace 기반 변수/흐름/반복/리스트/함수 시각화
- Step 이동, 재생, 속도 조절
- 외부 문서 창과 Visualizer의 Windows Split View

### 템플릿 기반 시각화 구조

시각화 창은 `code_execution_templates_overview.png`에서 참고한 **실행 장면의
표시 원칙만** 데스크톱 UI에 적용합니다. 템플릿 라이브러리나 왼쪽 탐색 토글은
사용자 화면에 노출하지 않으며, Trace의 의미 정보에 따라 장면을 자동 선택합니다.

- 중앙에는 현재 템플릿의 전용 실행 장면, 핵심 관찰값, 학습 설명을 둡니다.
- 오른쪽에는 현재 줄이 표시된 코드, 이전→이후 상태 변화, 출력 결과를 둡니다.
- 아래에는 `처음 / 이전 / 재생 / 다음`, Step 위치, 0.5×~2× 재생 속도를 둡니다.
- `모션 줄이기`로 장면 전환 효과를 끌 수 있고, `PDF/PPT 함께 보기`로 외부 자료
  창과 시각화 창을 나란히 배치할 수 있습니다.

현재 Educational Executor가 의미 정보를 생성하는 템플릿은 `01 변수·연산`,
`02 조건 분기`, `03 반복문`, `04 배열·인덱스`, `15 함수·재귀`입니다.
나머지 템플릿은 16개 라이브러리의 설계 자리를 먼저 확보하되, 해당 자료구조의
실제 Trace 계약이 추가되기 전에는 비활성화합니다. HTML 설계 예시의 fixture 값을
실행 결과처럼 표시하지 않으며, 시각화는 항상 실제 `ExecutionTrace`만 소비합니다.

현재 버전의 입력은 Windows 마우스 이벤트를 기준으로 합니다. 따라서 전자칠판이
없어도 동일한 선택·편집·실행 흐름을 검증할 수 있습니다. 손글씨를 문자로 바꾸는
전자펜 필기 인식은 별도 기능이며 이 버전의 OCR 경로에 포함하지 않습니다.

OCR 모델은 앱 시작 직후 백그라운드에서 한 번만 준비합니다. 준비가 끝나기 전에는
화면 선택 버튼이 잠시 비활성화되고 직접 코드 입력은 사용할 수 있습니다. 모델
준비 후 개발 PC에서 측정한 OCR 시간은 일반 코드 영역 약 1.1초, 3840×2160 입력을
1536px 기준으로 줄인 경우 약 2.6~2.7초였습니다. 큰 원본 전체를 그대로 추론하지
않도록 입력 상한을 두어 선택 후 지연을 줄였습니다.

Windows PaddleOCR 안정성을 위해 모델 예열과 이후 인식을 하나의 전용 작업 스레드가
계속 소유합니다. Qt 화면 스레드는 요청과 결과 신호만 처리하므로, 예열 직후 OCR을
클릭해도 모델을 다른 스레드로 옮겨 재사용하지 않습니다.

## 실행 환경

현재 개발 머신에서 확인된 환경은 Python 3.12.4와 Python 3.13.5이며, PaddleOCR가 설치된 3.12 환경을 사용합니다.

```powershell
py -3.12 -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main
```

바탕화면에서 바로 실행하려면 런처 EXE를 한 번 생성합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_launcher.ps1
```

그러면 바탕화면에 `CodeTrace.exe`가 생성됩니다. 이 파일은 프로그램 전체를
내장하는 방식이 아니라 현재 `캡스톤` 폴더의 `.venv`와 최신 `app` 소스를
실행하는 런처입니다. 따라서 개발 중 소스 파일이 변경되어도 바탕화면 EXE를
다시 만들지 않고 다음 실행부터 최신 코드가 반영됩니다. 런처 자체를 변경하거나
프로젝트 폴더를 다른 PC로 옮길 때만 위 명령으로 다시 생성하면 됩니다.

첫 OCR 실행 전 PaddleOCR 모델이 로컬에 준비되어 있어야 합니다. 모델이 준비되지 않은 상태에서는 UI와 직접 코드 실행은 사용할 수 있지만, 화면 OCR은 오류 안내를 표시합니다.

오프라인 실행용 모델 폴더는 아래처럼 구성합니다.

```text
models/
├─ PP-OCRv5_mobile_det/
└─ korean_PP-OCRv5_mobile_rec/
```

현재 코드는 프로젝트 `models` 폴더, `C:\ProgramData\CodeTrace\models`,
`C:\Temp\CodeTrace\models` 순서로 찾습니다. 다른 위치를 사용하면
`CODETRACE_OCR_MODEL_DIR` 환경변수로 모델 루트를 지정할 수 있습니다.
모델 경로에는 한글 등 비ASCII 문자가 포함되지 않도록 배포 위치를 정하는 것이 안전합니다.

이미 PaddleOCR 모델을 내려받은 개발 PC라면 다음 명령으로 ASCII 경로에 복사할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\prepare_ocr_models.ps1
```

앱도 OCR을 처음 요청할 때 기존 PaddleX 캐시에 두 모델이 모두 있으면
`C:\Temp\CodeTrace\models`로 자동 복사합니다. 실행 중에는 네트워크를 사용하지 않습니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 구조 원칙

```text
Code → Parser/AST → Educational Executor → ExecutionTrace → Visualization
```

시각화 모듈은 실행기를 직접 호출하지 않고 `ExecutionTrace`만 소비합니다. 세션 코드와 Trace는 영구 저장하지 않습니다.

화면 흐름은 다음 상태를 명시적으로 사용합니다.

```text
IDLE → SELECTING → REVIEWING → OCR → EDITING → RUNNING → VISUALIZING
```

`연속 선택`은 OCR 결과를 메모리에만 보관한 뒤 `IDLE`로 돌아가고, `새로 시작`은
확인 후 보관 중인 영역과 OCR 결과를 모두 비웁니다.
