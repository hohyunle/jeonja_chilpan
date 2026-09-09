# CodeTrace 아키텍처

## 1. 전체 데이터 흐름

```text
외부 PDF/PPT 화면
       │ 사용자가 드래그
       ▼
SelectionOverlay
       │ global QRect
       ▼
capture_screen_rect
       │ QPixmap / PNG bytes
       ▼
SelectionReviewDialog
       │ OCR 실행 또는 연속 선택
       ▼
OcrWorker ── OcrService ── PaddleOCR
       │ OCR text
       ▼
CodeSession (메모리 임시 보관)
       ▼
CodeEditorDialog (사용자 확인·수정)
       ▼
parse_code
       │ ParseResult / Python AST
       ▼
EducationalExecutor
       │
       ▼
ExecutionTrace
       ├─ VisualizerWindow: 실행 장면
       ├─ 현재 코드 줄 강조
       ├─ 상태 변화 비교
       └─ 출력/Step 재생
```

`VisualizerWindow`는 `ExecutionTrace`를 소비하는 프레젠테이션 계층이다. 시각화에서
실행기를 다시 호출하거나 코드 문자열을 재실행하면 안 된다.

## 2. 모듈 지도

### `app/main.py`

화면 흐름을 조정하는 애플리케이션 컨트롤러다.

- `MainWindow`: Floating Tool, 세션 상태, 버튼, OCR/실행 시작
- `SelectionOverlay`: 화면 드래그 시작/취소 신호 수신
- `SelectionReviewDialog`: 캡처 미리보기와 다음 동작 선택
- `CodeEditorDialog`: OCR 결과 편집 및 실행 승인
- `VisualizerWindow`: 실행 결과 창 연결
- `QThread`: 교육용 실행기를 UI와 분리

여기에는 핵심 실행 규칙을 넣지 않는다. UI는 각 계층에 요청을 보내고 결과를 화면에
반영하는 역할만 한다.

### `app/core/parser.py`

Python 표준 라이브러리 `ast.parse`를 사용해 코드를 AST로 바꾼다.

- `ParseResult`: `tree`와 `diagnostics`
- `SupportedSyntaxValidator`: 허용 AST 노드와 호출만 통과
- `source_for`: AST 노드와 원본 코드의 의미 있는 소스 연결

현재 허용된 주요 문법은 다음과 같다.

- 변수 대입/복합 대입
- 정수, 실수, 문자열, 불리언, `None`
- 리스트와 리스트 인덱싱
- `+ - * / // % **`, 비교, `and/or/not`
- `if/elif/else`
- `for`, `while`
- 함수 정의, 위치 매개변수, `return`
- `print`, `input`, `int`, `float`, `str`, `range`, `len`
- 리스트의 `append`, `pop`

지원하지 않는 문법이 들어오면 실행하지 않고 진단 정보를 편집창에 보여준다. import,
class, 파일 I/O, 임의 라이브러리 호출, 복잡한 키워드 인자, 중첩 함수 등은 현재
지원하지 않는다.

### `app/core/executor.py`

AST만 받아 교육용 상태를 직접 계산한다. 일반 Python 인터프리터를 흉내 내는 것이
아니라 학습에 필요한 사건을 명시적으로 기록한다.

- 실행 환경은 자체 변수 맵과 함수 프레임으로 구성
- `print`는 `ExecutionTrace.outputs`에 기록
- `input`은 `InputBroker`를 통해 UI에 입력을 요청
- 매 의미 단위 실행마다 `_record`로 Step 생성
- 기본 제한: 최대 2,000 Step, 최대 2.5초
- 예외와 제한 초과는 `trace.error` 또는 `trace.stopped_reason`으로 보존

사용자 코드 실행에 `exec`, `eval`, `compile` 실행 경로를 추가하지 않는다.

### `app/core/models.py`

계층 사이의 데이터 구조가 정의된 곳이다.

#### `TraceStep`

```python
TraceStep(
    index: int,
    kind: str,
    title: str,
    line: int | None,
    source: str,
    variables_before: dict,
    variables_after: dict,
    details: dict,
    scope: str,
)
```

`variables_before`와 `variables_after`는 실행 전후의 복사본이다. 리스트처럼 mutable한
값도 이전 상태를 잃지 않도록 snapshot을 사용한다.

현재 Executor가 만드는 대표 `kind`는 다음과 같다.

| kind | 의미 | 핵심 details |
|---|---|---|
| `assignment` | 대입 또는 값 변경 | `expression`, `value` |
| `expression` | 식 평가 | `expression`, `result` |
| `output` | `print` 출력 | `output` |
| `condition` | 조건 판단 | `condition`, `result`, `branch` |
| `loop` | 반복 시작 | `loop_type`, `count`, `iterable` |
| `iteration` | 반복 한 회차 | `loop_type`, `iteration`, `variable` |
| `loop_end` | 반복 종료 | `loop_type`, `count` |
| `list` | 리스트 메서드 변경 | `expression`, `result` |
| `function_call` | 함수 호출 | 함수/인자 정보 |
| `parameter` | 매개변수 바인딩 | 함수 프레임 정보 |
| `return`/`function_return` | 반환 흐름 | 반환값 |

새 `kind`를 만들 때는 Executor만 고치지 말고 이 표, Visualizer 렌더러, 테스트를
함께 갱신한다.

### `app/core/session.py`

`CodeSession`은 연속 선택 결과를 메모리에 보관한다.

- `append_ocr`: 정규화된 코드 조각을 순서대로 추가
- `combined_code`: 조각을 줄바꿈으로 결합
- `reset`: 모든 임시 조각 삭제

파일 저장이나 DB 저장은 하지 않는다.

### `app/core/ocr.py`

로컬 PaddleOCR를 감싼 어댑터다.

- detection: `PP-OCRv5_mobile_det`
- recognition: `korean_PP-OCRv5_mobile_rec`
- CPU, oneDNN 비활성화
- 입력 긴 변을 1,536px 이하로 줄여 큰 화면에서 추론 시간을 제한
- OCR 결과를 `OcrLine`으로 정규화
- 같은 시각적 줄에 잘린 조각을 병합
- 박스 위치로 Python 들여쓰기 추정

모델 경로는 ASCII 경로를 우선한다.

```text
CODETRACE_OCR_MODEL_DIR
프로젝트 models/
C:\ProgramData\CodeTrace\models
C:\Temp\CodeTrace\models
PaddleX 공식 캐시에서 C:\Temp\CodeTrace\models로 staging
```

### `app/ui/workers.py`

두 종류의 백그라운드 작업이 있다.

#### OCR

`OcrWorker`는 Qt `QThread`로 모델을 옮기지 않는다. 장수명 Python
`threading.Thread` 하나가 `OcrService`를 생성하고 예열부터 모든 `predict` 호출까지
계속 소유한다. 이는 Windows PaddlePaddle에서 서로 다른 스레드의 모델 재사용으로
프로세스가 종료되던 문제를 피하기 위한 구조다.

#### 실행

`ExecutionWorker`는 Qt `QThread`에서 `EducationalExecutor.run()`을 실행한다. UI는
Trace가 완성될 때까지 멈추지 않고, input 요청은 Visualizer의 입력 패널로 전달한다.

### `app/platform/windows.py`

Windows API와 Qt 화면 캡처를 모아둔 플랫폼 계층이다.

- 외부 창 열거/크기 조회
- PDF/PPT로 추정되는 큰 창 찾기
- 외부 자료와 Visualizer Split View
- `QScreen.grabWindow` 기반 화면 캡처
- 듀얼모니터마다 화면 교차 영역을 계산하고 합성

Windows에서 `QScreen.grabWindow`의 부분 캡처 좌표는 해당 화면의 로컬 좌표이므로,
전역 선택 사각형에서 모니터 원점을 빼서 전달한다. 반환 픽셀은 모니터 DPI를 고려해
합성한다.

### `app/ui/selection_overlay.py`

전체 가상 데스크톱을 덮는 선택창이다.

- 연결된 모든 `QScreen.geometry()`를 합쳐 가상 영역 생성
- 드래그 시작점의 모니터를 기억
- 선택은 시작한 모니터 안으로 제한
- 선택 영역 외 음영은 낮은 불투명도
- 선택 영역은 투명하게 비워 원본 화면을 확인 가능

코드 선택은 한 모니터에서 완료된다는 제품 가정이 있으므로, 의도하지 않은 모니터
경계 교차를 허용하지 않는다.

### `app/ui/visualizer.py`

Trace의 종류를 보고 활성 장면을 자동 선택한다.

- `values`: 변수 카드와 계산 결과
- `branch`: 조건식과 선택된 경로
- `loop`: 반복 본문, 회차, 누적 기록
- `array`: 고정 인덱스와 현재 접근 위치
- `recursion`: 호출 스택과 프레임

오른쪽 증거 열은 현재 Step의 실제 `source`, 상태 변화, 출력만 표시한다. HTML 렌더러가
임의 데이터를 만들지 않도록 `trace.details`와 before/after 상태만 사용한다.

### `app/ui/theme.py`

현재 컴퓨터에 설치된 글꼴을 조회해 UI와 코드 글꼴을 선택한다.

- UI 우선순위: `Malgun Gothic`, `맑은 고딕`, CJK 계열, `Segoe UI` 등
- 코드 우선순위: `Cascadia Code`, `Consolas`, `D2Coding`, `Courier New` 등

특정 글꼴을 강제하지 않는 이유는 노트북/전자칠판 PC마다 설치 글꼴이 다를 수 있기
때문이다.

## 3. 변경 시 의존성 방향

```text
UI controller → core service/model
Visualizer     → ExecutionTrace/model
Executor       → parser result/model
OCR adapter    → OcrLine/model
Platform       → Qt/Windows only
```

다음 의존은 만들지 않는다.

- Visualizer → EducationalExecutor 직접 호출
- Parser → UI 위젯 조작
- OCR → PDF/PPT 파일 내부 API
- Core Executor → 네트워크/Windows UI
- Session → DB/파일 저장
