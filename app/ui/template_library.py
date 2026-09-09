"""Semantic visualization template metadata.

The template library is deliberately independent from the executor.  A template
describes how a trace should be taught; it does not create execution facts.
Only templates for which the current trace contains enough semantic evidence are
enabled by the visualizer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    key: str
    number: str
    name: str
    category: str
    summary: str
    rules: tuple[str, ...]

    @property
    def display_name(self) -> str:
        return f"{self.number} · {self.name}"


TEMPLATE_SPECS: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        "values", "01", "변수 · 연산", "기초 실행",
        "변수 카드와 식의 결과를 안정된 위치에서 비교합니다.",
        ("변수 카드는 실행 중 위치를 바꾸지 않습니다.", "변경된 값은 이전 값과 나란히 비교합니다.", "미정의·None·문자열·불리언을 구분해 표시합니다."),
    ),
    TemplateSpec(
        "branch", "02", "조건 분기", "제어 흐름",
        "조건식의 결과와 실제로 선택된 한 갈래를 보여줍니다.",
        ("True/False는 오류 색상과 구분합니다.", "선택되지 않은 갈래는 실행되지 않음으로 남깁니다.", "분기 결과는 다음 Step의 상태 변화와 연결합니다."),
    ),
    TemplateSpec(
        "loop", "03", "반복문", "제어 흐름",
        "고정된 반복 본문과 회차별 상태 변화를 함께 보여줍니다.",
        ("반복 본문을 회차마다 복제하지 않습니다.", "회차·반복 변수·누적값을 표로 기록합니다.", "반복 시작과 종료를 실제 Trace Step으로 구분합니다."),
    ),
    TemplateSpec(
        "array", "04", "배열 · 인덱스", "자료구조",
        "고정 인덱스 셀과 현재 접근 위치를 보여줍니다.",
        ("셀 위치와 인덱스는 실행 중 이동하지 않습니다.", "접근 위치는 셀 밖의 포인터로 표시합니다.", "범위를 벗어난 접근에는 존재하지 않는 셀을 만들지 않습니다."),
    ),
    TemplateSpec(
        "matrix", "05", "2차원 배열", "자료구조",
        "행·열 헤더와 현재 좌표를 가진 격자를 보여줍니다.",
        ("행과 열의 좌표를 항상 함께 표시합니다.", "방문·미방문·현재 셀을 구분합니다.", "합계나 누적 결과는 격자 바깥에 둡니다."),
    ),
    TemplateSpec(
        "stack", "06", "스택", "자료구조",
        "top 위치와 push/pop의 결과를 세로로 보여줍니다.",
        ("top은 실제 현재 위치를 가리킵니다.", "push/pop은 같은 top에서 일어나는 것으로 표시합니다.", "꺼낸 값은 스택 바깥에서 별도로 보여줍니다."),
    ),
    TemplateSpec(
        "queue", "07", "큐", "자료구조",
        "front와 rear, 삽입·삭제 방향을 가로로 보여줍니다.",
        ("enqueue는 rear에서, dequeue는 front에서 일어납니다.", "실제 상태 변화가 없으면 셀을 불필요하게 재배치하지 않습니다.", "front/rear 포인터와 큐 값을 분리합니다."),
    ),
    TemplateSpec(
        "linked", "08", "연결 리스트", "자료구조",
        "노드의 값·next 참조와 참조 변경 순서를 보여줍니다.",
        ("노드 ID와 위치는 가능한 한 안정적으로 유지합니다.", "값과 next 참조를 한 노드 안에서 구분합니다.", "참조가 바뀌는 순서를 Trace 순서로 설명합니다."),
    ),
    TemplateSpec(
        "hash", "09", "해시 테이블", "자료구조",
        "키·해시·버킷·충돌을 분리해 보여줍니다.",
        ("충돌은 별도 체인 또는 슬롯으로 표시합니다.", "키 비교와 버킷 위치를 같은 의미로 취급하지 않습니다.", "Python dict 내부 구현을 추측해 표시하지 않습니다."),
    ),
    TemplateSpec(
        "tree", "10", "트리", "자료구조",
        "계층 위치가 고정된 노드와 현재 경로를 보여줍니다.",
        ("현재 노드와 탐색 경로를 강조합니다.", "일반 트리의 위치를 임의로 BST처럼 해석하지 않습니다.", "노드가 없는 자리에 가짜 노드를 만들지 않습니다."),
    ),
    TemplateSpec(
        "graph", "11", "그래프", "알고리즘",
        "고정된 노드·간선과 방문 순서를 분리해 보여줍니다.",
        ("force layout으로 실행 중 노드를 흔들지 않습니다.", "방문 경로와 대기 큐를 별도로 보여줍니다.", "방향·가중치 정보는 Trace가 제공할 때만 표시합니다."),
    ),
    TemplateSpec(
        "sort", "12", "정렬", "알고리즘",
        "배열의 비교·교환과 인덱스 상태를 분리해 보여줍니다.",
        ("비교와 교환을 서로 다른 이벤트로 구분합니다.", "요소 ID를 유지해 중복 값도 추적합니다.", "정렬 완료 여부를 색상만으로 표현하지 않습니다."),
    ),
    TemplateSpec(
        "search", "13", "이진 탐색", "알고리즘",
        "정렬 배열에서 low·mid·high와 제외 범위를 보여줍니다.",
        ("원래 인덱스를 유지합니다.", "현재 탐색 범위와 제외된 범위를 구분합니다.", "mid 계산과 비교 결과를 하나의 의미 있는 Step으로 묶습니다."),
    ),
    TemplateSpec(
        "dp", "14", "동적 계획법", "알고리즘",
        "점화식에 따른 의존 셀과 현재 기록 셀을 보여줍니다.",
        ("읽은 셀과 쓴 셀을 구분합니다.", "실제 점화식과 계산 근거를 함께 표시합니다.", "격자 크기가 커지면 가로 스크롤을 허용합니다."),
    ),
    TemplateSpec(
        "recursion", "15", "함수 · 재귀", "실행 구조",
        "호출 스택·프레임·지역 변수·반환을 보여줍니다.",
        ("호출 프레임 ID와 반환 흐름을 안정적으로 유지합니다.", "부모 호출은 자식 호출이 반환될 때까지 대기 상태입니다.", "재귀는 실행기가 명시적으로 지원할 때만 활성화합니다."),
    ),
    TemplateSpec(
        "async", "16", "비동기 · 동시성", "실행 구조",
        "작업 레인별 대기·실행·완료 흐름을 보여줍니다.",
        ("대기와 실행 상태를 구분합니다.", "시각화만으로 CPU 병렬 실행을 암시하지 않습니다.", "실제 스케줄링 정보를 Trace가 제공할 때만 사용합니다."),
    ),
)


TEMPLATE_BY_KEY = {spec.key: spec for spec in TEMPLATE_SPECS}

# These aliases preserve the small public surface used by the first prototype.
TEMPLATE_ALIASES = {
    "variables": "values",
    "loops": "loop",
    "lists": "array",
    "functions": "recursion",
    "flow": "values",
}


def canonical_template(key: str) -> str:
    return TEMPLATE_ALIASES.get(key, key)


def get_template(key: str) -> TemplateSpec:
    return TEMPLATE_BY_KEY[canonical_template(key)]

