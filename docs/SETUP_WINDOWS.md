# Windows 11 개발 환경 및 실행 방법

## 1. 권장 폴더

가능하면 노트북에서 프로젝트를 다음처럼 ASCII 경로에 둔다.

```text
C:\CodeTrace
```

현재 소스는 한글 프로젝트 경로에서도 동작하도록 작성되어 있지만, PaddlePaddle
Windows 모델 로더가 비ASCII 모델 경로에서 문제를 일으킬 수 있어 OCR 모델은 반드시
아래와 같은 ASCII 경로에 둔다.

```text
C:\Temp\CodeTrace\models
```

## 2. 저장소 받기

```powershell
git clone https://github.com/hohyunle/jeonja_chilpan.git C:\CodeTrace
Set-Location C:\CodeTrace
```

현재 원격 저장소의 기본 브랜치는 `main`이다.

## 3. Python 환경 만들기

Python 3.12를 설치한 뒤 PowerShell에서 실행한다.

```powershell
py -3.12 -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

현재 기준 의존성은 다음과 같다.

```text
PySide6==6.10.3
Pillow==12.1.1
numpy>=2.0,<3
paddleocr==3.4.0
paddlepaddle==3.3.1
```

노트북에서 새로 설치할 때 PaddlePaddle wheel 설치가 오래 걸릴 수 있다. 설치가
끝난 뒤 다음을 확인한다.

```powershell
.\.venv\Scripts\python.exe -m pip check
```

## 4. OCR 모델 준비

Git에는 모델 바이너리를 넣지 않는다. 반드시 detection 모델과 한국어 recognition
모델을 둘 다 준비해야 화면 OCR이 활성화된다.

```text
C:\Temp\CodeTrace\models\
├─ PP-OCRv5_mobile_det\
│  ├─ inference.json
│  └─ inference.pdiparams
└─ korean_PP-OCRv5_mobile_rec\
   ├─ inference.json
   └─ inference.pdiparams
```

### 방법 A: 기존 PaddleX 캐시 복사

노트북에 이미 PaddleOCR 모델을 내려받았다면:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\prepare_ocr_models.ps1
```

기본 원본은 `%USERPROFILE%\.paddlex\official_models`다. 필요한 폴더가 없으면
스크립트가 오류를 보여준다.

### 방법 B: 개발 PC에서 모델 폴더 복사

인터넷이 느리거나 없는 노트북이라면, 모델이 준비된 PC의 다음 폴더를 통째로 복사한다.

```text
C:\Temp\CodeTrace\models\PP-OCRv5_mobile_det
C:\Temp\CodeTrace\models\korean_PP-OCRv5_mobile_rec
```

USB 등으로 옮긴 뒤에도 폴더 이름과 `inference.json`, `inference.pdiparams` 파일을
그대로 유지한다.

### 방법 C: 모델 다운로드

인터넷이 허용된 환경에서 공식 PaddleOCR 모델을 받을 수 있다. 한국어 모델 이름은
`korean_PP-OCRv5_mobile_rec`이다. 다운로드 후 압축을 풀어 위 폴더 이름으로 맞춘다.
모델은 실행 중 네트워크가 필요하지 않도록 미리 준비해야 한다.

## 5. 프로그램 실행

### 개발 실행

```powershell
Set-Location C:\CodeTrace
.\.venv\Scripts\python.exe -m app.main
```

또는:

```powershell
.\run.ps1
```

CMD에서는:

```cmd
cd /d C:\CodeTrace
run.bat
```

앱이 켜지면 OCR 모델을 백그라운드에서 예열한다. 예열이 끝나기 전에는 `화면에서
코드 선택` 버튼이 비활성화될 수 있다. `코드 직접 입력`은 바로 사용할 수 있다.

### 바탕화면 EXE 만들기

프로젝트 폴더에서 다음을 실행한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_launcher.ps1
```

바탕화면에 `CodeTrace.exe`가 생긴다. 이 EXE는 앱 전체를 독립 패키징한 파일이 아니라
현재 프로젝트 폴더의 `.venv`와 `app` 소스를 실행하는 작은 런처다. 따라서 개발 중
소스가 바뀌면 보통 다음 실행부터 반영된다.

다른 노트북으로 프로젝트를 옮기면 그 노트북에서 `.venv`를 새로 만들고 런처도 다시
생성한다. 런처는 실행 파일 옆의 `캡스톤` 폴더 또는 현재 프로젝트의 고정 경로를
찾도록 되어 있으므로, 폴더 이름/위치를 바꾸면 직접 실행 명령을 사용하거나 런처를
그 위치에서 다시 만든다.

## 6. 첫 실행 점검 순서

1. 외부 PDF/PPT 뷰어를 먼저 연다.
2. CodeTrace의 OCR 준비 상태가 완료될 때까지 기다린다.
3. `화면에서 코드 선택`을 누른다.
4. 코드가 있는 한 모니터 안에서 영역을 드래그한다.
5. 미리보기에서 음영이 섞이지 않았는지 확인한다.
6. `OCR 실행`을 누른다.
7. OCR 결과를 코드 편집창에서 확인하고, 들여쓰기·기호·한글을 수정한다.
8. `실행`을 누른다.
9. Visualizer의 `처음 / 이전 / 재생 / 다음`으로 Step을 확인한다.

## 7. 테스트 명령

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m pip check
```

기준 상태에서는 단위 테스트 22개가 통과한다. 실제 OCR 테스트는 모델과 화면 장치가
필요하므로 단위 테스트와 별도로 실행한다.

## 8. 자주 발생하는 문제

### `화면에서 코드 선택`이 비활성화됨

OCR 모델 예열 중이거나 모델 준비에 실패한 상태다. 직접 코드 입력은 가능하다.
`C:\Temp\CodeTrace\models`에 두 모델 폴더가 모두 있는지 확인하고 앱을 다시 시작한다.

### 한국어가 네모/엉뚱한 문자로 나옴

영어 전용 recognition 모델을 사용하면 안 된다. 반드시 다음 이름인지 확인한다.

```text
korean_PP-OCRv5_mobile_rec
```

### 모델을 찾지 못했다는 오류

경로에 한글이 들어간 경우 `CODETRACE_OCR_MODEL_DIR`로 ASCII 경로를 지정한다.

```powershell
$env:CODETRACE_OCR_MODEL_DIR = 'C:\Temp\CodeTrace\models'
.\.venv\Scripts\python.exe -m app.main
```

### 실행 창이 바로 닫힘

EXE 대신 PowerShell에서 직접 실행해 오류를 확인한다.

```powershell
.\.venv\Scripts\python.exe -m app.main
```

### Git 인증 오류

인증 계정에 저장소 쓰기 권한이 있는지 확인한다. 인증을 바꾼 뒤:

```powershell
git push -u origin main
```
