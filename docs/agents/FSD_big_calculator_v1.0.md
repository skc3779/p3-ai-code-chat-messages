# 기능 명세서 (Functional Specification Document, FSD)

## 프로젝트명: Big Calculator (대용량/공학용 계산기)
- **문서 ID:** FSD-BIG-CALC-v1.0
- **문서 버전:** v1.0
- **대상 환경:** Python 3.10 이상
- **작성일:** 2026-09-06
- **상태:** Final (승인 완료)

---

## 1. 개요 (Overview)

### 1.1 프로젝트 목적
본 문서는 Python 3 기반의 고성능 멀티패러다임 데스크톱 애플리케이션인 **Big Calculator(대용량/공학용 계산기)**의 최종 기능 명세서(FSD)입니다.  
학생, 연구원, 엔지니어 등 고난도 수식 연산과 데이터 분석이 필요한 사용자를 대상으로 하며, **대용량 무제한 정밀도(BigInt/Arbitrary Precision)**, **광범위한 공학용 함수**, **선형대수학(행렬·벡터) 엔진**, **2D 함수 그래프 플로팅**, **인터랙티브 매쓰 노트(Math Scratchpad)**, 그리고 **AI 기반 수학 풀이 어시스턴트**를 아우르는 통합 연산 환경을 구축하는 것을 목적으로 합니다.

### 1.2 핵심 범위
1. **기본 및 대용량 정밀 연산**: 사칙연산(`+`, `-`, `×`, `÷`, `%`), 무제한 자릿수 정수 및 고정밀 소수점 연산
2. **공학용 함수 라이브러리**:
   - 삼각함수 및 역삼각함수: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`
   - 지수 및 로그: `log10`, `ln`, `10^x`, `e^x`, `x^y`, `sqrt`, `n!`
   - 수학 상수: `π`, `e`, 부호 반전(`+/-`), 중첩 괄호 연산자 우선순위
   - 각도 단위 모드: DEG(디그리) / RAD(라디안) 실시간 토글
3. **선형대수학 연산 엔진**:
   - 최대 $10 \times 10$ 행렬 입력, 행렬곱, 역행렬($A^{-1}$), 행렬식($\det(A)$), 특이행렬 방어
   - 2D/3D 벡터 연산: 내적(Dot Product), 외적(Cross Product), 크기(Magnitude)
4. **인터랙티브 매쓰 노트 (Math Scratchpad)**:
   - 텍스트 에디터 기반 인라인 실시간 수식 평가 (`=` 입력 시 자동 계산)
   - 동적 변수 바인딩 ($x = 10, y = 20 \rightarrow x + y$ 변경 시 실시간 재계산)
5. **AI 기반 수학 어시스턴트 (AI Math Assistant)**:
   - 자연어 서술형 수학 문제(Word Problem) 수식 변환 및 풀이
   - 단계별 풀이 과정(Step-by-Step Solution) 스트리밍 출력
6. **시각화 및 도구**:
   - $y = f(x)$ 2D 그래프 플로팅 뷰
   - 단위 변환기 (길이, 무게, 넓이, 온도)
   - 메모리 레지스터 (`MC`, `MR`, `M+`, `M-`, `MS`)
   - 계산 내역 관리: 최근 50개 이상 보관, 선택 수식 복원, CSV/JSON 내보내기, 클립보드 복사
   - 다단계 Undo/Redo 지원
7. **현대적 UI/UX**:
   - 다크 모드 / 라이트 모드 전환
   - 최소 200px 높이의 고해상도 디지털 화면 및 반응형 레이아웃
   - 수식 실시간 문법 검사 및 괄호 매칭 색상 하이라이팅

---

## 2. 공통 준수 사항 및 아키텍처 설계 원칙

### 2.1 공통 준수 규격 5대 원칙
1. **README.md 작성**: 프로젝트 개요, 기능 소개, 아키텍처 다이어그램, 가상환경 및 설치법, 모드별 상세 조작법, 단위 테스트 실행법을 상세히 기재한다.
2. **requirements.txt 라이브러리 관리**: 공학 연산, 그래프 시각화, AI 연동에 필요한 라이브러리를 체계적으로 명시하고 호환 버전을 관리한다.
3. **src 소스 코드 디렉터리 분리**: 모든 소스코드는 `src/` 폴더 하위에 패키지 구조로 배치한다.
4. **코드 분할(Code Splitting) 및 관심사의 분리(SoC)**:
   - 수식 파서, 수학 엔진, UI 뷰, 상태 관리, AI 연동 레이어를 완전히 격리한다.
   - 단일 파일 비대화를 방지하고 함수 및 클래스 단위의 책임을 단일화한다.
5. **tests 테스트 코드 디렉터리 분리**: 모든 테스트는 `tests/` 폴더에 배치하며, 엔진별/기능별 단위 테스트와 통합 테스트로 세분화한다.

### 2.2 디렉터리 구조 명세

```
big-calculator/
├── README.md                     # 프로젝트 개요, 모드별 가이드, 설치/실행 매뉴얼
├── requirements.txt              # 외부 의존성 패키지 명세
├── docs/                         # 설계 및 요구사항 문서
│   └── reqs/
│       └── FSD_big_calculator_v1.0.md
├── src/                          # 메인 애플리케이션 소스 코드
│   ├── __init__.py
│   ├── main.py                   # 애플리케이션 엔트리포인트
│   ├── config.py                 # 전역 설정 (폰트, 테마, 정밀도, API 키 등)
│   ├── core/                     # 수식 파싱 및 구문 분석 코어
│   │   ├── __init__.py
│   │   ├── tokenizer.py          # 수식 토큰화 및 어휘 분석
│   │   ├── parser.py             # AST 생성 및 연산자 우선순위 처리
│   │   ├── validator.py          # 괄호 매칭 및 실시간 문법 검사
│   │   └── evaluator.py          # 정밀도 제어 및 수식 최종 평가
│   ├── engines/                  # 전문 도메인 연산 엔진 (SoC)
│   │   ├── __init__.py
│   │   ├── scientific_engine.py  # 삼각/로그/지수/상수/각도모드 연산
│   │   ├── linear_algebra.py     # 행렬식, 역행렬, 행렬곱, 벡터 연산
│   │   ├── scratchpad_engine.py  # 매쓰 노트 변수 바인딩 및 인라인 연산
│   │   └── unit_converter.py     # 길이/무게/넓이/온도 단위 변환 엔진
│   ├── ai/                       # AI 어시스턴트 모듈
│   │   ├── __init__.py
│   │   ├── client.py             # LLM API 통신 및 비동기 스트리밍 핸들러
│   │   └── prompt_templates.py   # 단계별 풀이 및 수식 변환 프롬프트 정의
│   ├── state/                    # 애플리케이션 상태 및 저장소
│   │   ├── __init__.py
│   │   ├── memory_register.py    # MC, MR, M+, M-, MS 메모리 레지스터
│   │   ├── history_manager.py    # 히스토리 리스트, CSV/JSON Export
│   │   └── undo_redo_manager.py  # Memento 패턴 기반 Undo/Redo 관리
│   ├── views/                    # UI 컴포넌트 계층 (View)
│   │   ├── __init__.py
│   │   ├── main_window.py        # 메인 윈도우 프레임 및 모드 전환 탭
│   │   ├── display_panel.py      # 대형 200px 디지털 화면 및 수식 하이라이터
│   │   ├── standard_keypad.py    # 표준 사칙연산 키패드 컴포넌트
│   │   ├── scientific_panel.py   # 공학용 함수 버튼 패널 (DEG/RAD 포함)
│   │   ├── matrix_dialog.py      # 행렬/벡터 입력 그리드 팝업
│   │   ├── scratchpad_view.py    # 매쓰 노트 분할 텍스트 에디터 뷰
│   │   ├── graph_view.py         # 2D 함수 그래프 플로팅 캔버스 뷰
│   │   ├── history_panel.py      # 우측/하단 슬라이드 히스토리 패널
│   │   └── theme_manager.py      # 다크/라이트 테마 스타일시트 관리
│   ├── controllers/              # 제어 계층 (Controller)
│   │   ├── __init__.py
│   │   ├── app_controller.py     # 계산기 메인 제어기
│   │   └── scratchpad_controller.py # 매쓰 노트 이벤트 제어기
│   └── resources/                # 다국어 리소스 및 에셋
│       ├── strings_ko.json       # 한국어 리소스
│       ├── strings_en.json       # 영어 리소스
│       └── themes/               # 테마별 색상 팔레트 JSON
└── tests/                        # 테스트 스위트 디렉터리
    ├── __init__.py
    ├── test_basic_arithmetic.py  # 기본 사칙연산 및 BigInt 정밀도 테스트
    ├── test_scientific_engine.py # 삼각함수, 로그, 지수, 각도모드 테스트
    ├── test_linear_algebra.py    # 행렬식, 역행렬, 벡터 연산 단위 테스트
    ├── test_scratchpad_engine.py # 매쓰 노트 변수 바인딩 및 인라인 평가 테스트
    ├── test_unit_converter.py    # 단위 변환 정확도 테스트
    ├── test_history_memory.py    # 히스토리 내보내기 및 메모리 레지스터 테스트
    └── test_parser_validator.py  # 수식 문법 오류 검출 및 괄호 검사 테스트
```

---

## 3. 상세 기능 요구사항 (Functional Requirements)

### 3.1 기본 및 공학 연산 모듈

| ID | 기능 요구사항 | 세부 명세 | 우선순위 |
|---|---|---|---|
| **FR-BIG-001** | 대용량 수치 연산 | 정수 무제한 자릿수(BigInt) 연산 및 소수점 50자리 이상의 고정밀 연산을 지원한다. | 필수 (High) |
| **FR-BIG-002** | 삼각함수 및 각도 모드 | `sin`, `cos`, `tan`, `asin`, `acos`, `atan` 지원. DEG(도)/RAD(라디안) 모드를 즉시 전환하며, 전환 즉시 이후 삼각함수 연산에 반영한다. | 필수 (High) |
| **FR-BIG-003** | 지수, 로그, 팩토리얼 | 상용로그(`log10`), 자연로그(`ln`), 제곱근(`sqrt`), 거듭제곱(`x^y`), $10^x$, $e^x$, 팩토리얼($n!$)을 지원한다. | 필수 (High) |
| **FR-BIG-004** | 수학 상수 및 부호 | $\pi$(3.141592...), $e$(2.718281...) 단일 버튼 입력 및 부호 반전(`+/-`) 기능을 지원한다. | 필수 (High) |
| **FR-BIG-005** | 중첩 괄호 및 우선순위 | 사칙연산 곱셈/나눗셈 우선순위 및 다중 중첩 괄호(`((2+3)*4)^2`)를 완벽히 해석하여 계산한다. | 필수 (High) |

### 3.2 선형대수학 엔진 (Linear Algebra)

| ID | 기능 요구사항 | 세부 명세 | 우선순위 |
|---|---|---|---|
| **FR-BIG-006** | 행렬 연산 (Matrix) | 동적 그리드 인터페이스를 통해 최대 $10 \times 10$ 행렬 입력을 지원하며, 행렬식($\det(A)$), 역행렬($A^{-1}$), 행렬 덧셈/곱셈을 수행한다. | 필수 (High) |
| **FR-BIG-007** | 특이행렬 방어 | 역행렬 연산 시 행렬식 값이 0인 경우("특이행렬"), 강제 종료 없이 `"행렬식이 0이므로 역행렬을 구할 수 없습니다."` 안내를 표시한다. | 필수 (High) |
| **FR-BIG-008** | 벡터 연산 (Vector) | 2차원 및 3차원 벡터에 대해 내적(Dot Product), 외적(Cross Product), 크기(Magnitude) 연산을 지원한다. | 보통 (Medium) |

### 3.3 인터랙티브 매쓰 노트 (Math Scratchpad)

| ID | 기능 요구사항 | 세부 명세 | 우선순위 |
|---|---|---|---|
| **FR-BIG-009** | 인라인 실시간 연산 | 분할 에디터 뷰에서 사용자가 텍스트로 수식을 입력하고 `=` 입력 또는 엔터 시, 해당 라인 우측에 인라인으로 결과를 즉시 출력한다. | 필수 (High) |
| **FR-BIG-010** | 동적 변수 바인딩 | 문서 내 `x = 10`, `rate = 0.15`와 같이 변수를 선언하면, 이후 라인의 모든 수식에서 해당 변수를 참조하며, 변수 값 수정 시 의존된 연산 결과가 실시간 재평가된다. | 필수 (High) |

### 3.4 AI 수학 어시스턴트 (AI Math Assistant)

| ID | 기능 요구사항 | 세부 명세 | 우선순위 |
|---|---|---|---|
| **FR-BIG-011** | 서술형 문제 수식화 | 자연어 문장(예: "반지름이 5인 구의 부피를 구해줘")을 입력하면 AI가 수학 수식($V = \frac{4}{3}\pi r^3$)으로 변환하여 답을 산출한다. | 보통 (Medium) |
| **FR-BIG-012** | 단계별 풀이 (Step-by-Step) | 복잡한 수식이나 미적분/방정식 연산 시, 단순 수치뿐 아니라 풀이 원리와 중간 단계를 텍스트와 수식으로 단계별 해설한다. | 보통 (Medium) |
| **FR-BIG-013** | 오프라인 보호 모드 | 네트워크 단절이나 API 키 미설정 시에도 에러로 멈추지 않고 로컬 수식 연산 엔진으로 즉시 폴백(Fallback)한다. | 필수 (High) |

### 3.5 시각화, 변환 및 데이터 관리

| ID | 기능 요구사항 | 세부 명세 | 우선순위 |
|---|---|---|---|
| **FR-BIG-014** | 2D 함수 그래프 플로팅 | $y = f(x)$ 수식을 입력받아 2D 좌표계에 연속적인 함수 곡선을 시각화하는 팝업/패널 창을 제공한다. | 보통 (Medium) |
| **FR-BIG-015** | 단위 변환기 | 길이(m, cm, inch, ft), 무게(kg, g, lb, oz), 넓이($m^2$, $ft^2$), 온도(℃, ℉, K) 상호 변환을 지원한다. | 보통 (Medium) |
| **FR-BIG-016** | 메모리 레지스터 | `MS`(저장), `MR`(호출), `M+`(더하기), `M-`(빼기), `MC`(초기화) 동작을 지원하며 UI에 현재 메모리 상태를 표시한다. | 필수 (High) |
| **FR-BIG-017** | 히스토리 및 데이터 내보내기 | 최근 계산 내역(최소 50건)을 기록하고, 클릭 시 수식을 복원한다. 또한 내역 전체를 CSV 또는 JSON 파일로 저장하거나 클립보드에 복사할 수 있다. | 필수 (High) |
| **FR-BIG-018** | 다단계 Undo / Redo | 입력 및 편집 히스토리를 스택 기반으로 추적하여 `Ctrl+Z`(실행 취소) 및 `Ctrl+Y`(재적용)를 다단계로 지원한다. | 필수 (High) |

---

## 4. 상세 비기능 요구사항 (Non-Functional Requirements)

| 요구사항 ID | 항목 | 상세 기준 |
|---|---|---|
| **NFR-BIG-001** | 응답 속도 | 일반 수식 및 공학 함수 연산: 100ms 이내 화면 반영.<br>행렬/벡터 로컬 연산: 50ms 이내 완료.<br>AI 질의 응답: 비동기 스트리밍 방식으로 첫 응답 토큰 1.5초 이내 렌더링. |
| **NFR-BIG-002** | 연산 정확도 | IEEE 754 부동소수점 한계를 보완하기 위해 Python `decimal` 또는 고정밀 연산 라이브러리를 결합하여 50자리 정밀도 보장. 삼각/로그 함수는 Python 표준 `math` 오차 범위 준수. |
| **NFR-BIG-003** | 크로스 플랫폼 | Windows 10 이상, macOS 12 이상, Linux(Ubuntu 20.04+)에서 별도의 네이티브 의존성 문제 없이 실행 가능. |
| **NFR-BIG-004** | UI 접근성 & 테마 | 다크 테마(기본값: Slate/Navy Dark) 및 고대비 라이트 테마 지원. 주요 버튼 최소 56×56px, 대형 디스플레이 높이 최소 200px. |
| **NFR-BIG-005** | 다국어 지원 (i18n) | 모든 정적 UI 텍스트, 툴팁, 오류 메시지는 `src/resources/strings_ko.json` 및 `strings_en.json`으로 분리하여 언어 전환 지원. |
| **NFR-BIG-006** | 모듈성 (SoC) | 각 엔진(`scientific_engine`, `linear_algebra`, `scratchpad_engine`, `unit_converter`)은 독립적인 인터페이스를 유지하여 UI와 무관하게 CLI 또는 테스트 러너에서 단독 구동 가능. |

---

## 5. 시스템 아키텍처 및 데이터 모델

### 5.1 계층별 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           UI 계층 (Views)                               │
│  Main Window ── Display Panel (200px) ── Standard & Scientific Keypad    │
│  Scratchpad Split View ── Matrix Dialog ── Graph Canvas ── History View │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (이벤트 중계)
┌────────────────────────────────────▼────────────────────────────────────┐
│                        제어 계층 (Controllers)                          │
│         AppController              │        ScratchpadController        │
└──────────────────┬─────────────────┴──────────────────┬─────────────────┘
                   │                                    │
┌──────────────────▼────────────────────────────────────▼─────────────────┐
│                    코어 및 도메인 엔진 계층 (Engines)                    │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌─────────────┐  │
│  │   Tokenizer & Parser  │  │   Scientific Engine   │  │ Unit        │  │
│  │   (AST & Validator)   │  │   (Trig, Log, DEG/RAD)│  │ Converter   │  │
│  └───────────────────────┘  └───────────────────────┘  └─────────────┘  │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌─────────────┐  │
│  │ Linear Algebra Engine │  │   Scratchpad Engine   │  │ AI Assistant│  │
│  │ (Matrix & Vector)     │  │ (Dynamic Var Binding) │  │ (LLM Async) │  │
│  └───────────────────────┘  └───────────────────────┘  └─────────────┘  │
└──────────────────┬────────────────────────────────────┬─────────────────┘
                   │                                    │
┌──────────────────▼────────────────────────────────────▼─────────────────┐
│                       상태 관리 계층 (State Store)                      │
│      HistoryManager (CSV/JSON)   │   MemoryRegister   │   Undo/Redo     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 핵심 데이터 모델 인터페이스

```python
# [데이터 모델 명세 요약]

class CalculationHistoryItem:
    expression: str
    result: str
    mode: str          # "STANDARD", "SCIENTIFIC", "MATRIX", "SCRATCHPAD"
    timestamp: str     # ISO-8601 포맷

class AngleMode(Enum):
    DEG = "DEGREE"
    RAD = "RADIAN"

class MatrixData:
    rows: int
    cols: int
    data: List[List[float]]

class VectorData:
    dimension: int
    components: List[float]

class ScratchpadContext:
    variables: Dict[str, float]
    line_expressions: List[str]
    line_results: List[Optional[float]]
```

---

## 6. 예외 처리 및 방어 로직 명세

| 예외 유형 | 발생 조건 | 사용자 노출 메시지 | 복구 및 시스템 동작 |
|---|---|---|---|
| **ZeroDivisionError** | 분모가 0인 수식 계산 | `"0으로 나눌 수 없습니다."` | 계산 중단, 현재 입력식 유지, 에러 하이라이트 |
| **DomainError** | 음수의 제곱근, $x \le 0$인 로그 등 | `"정의역 오류: 올바른 입력 범위를 지정하세요."` | 복소수 미지원 알림, 입력 수정 대기 |
| **SingularMatrixError** | 역행렬 계산 시 $\det(A) = 0$ | `"행렬식이 0이므로 역행렬을 계산할 수 없습니다."` | 행렬식 값(0) 표시 및 역행렬 연산 취소 |
| **MatrixDimensionMismatch** | 곱셈 시 앞 행렬 열 != 뒤 행렬 행 | `"행렬 차원이 일치하지 않아 곱셈할 수 없습니다."` | 차원 일치 가이드 다이얼로그 노출 |
| **SyntaxError** | 괄호 짝 불일치, 연산자 연속 입력 | `"수식 문법 오류: 수식을 확인해주세요."` | 일치하지 않는 괄호 위치에 붉은색 테두리 표시 |
| **AIOfflineError** | 네트워크 단절, API 키 누락 | `"AI 서비스에 연결할 수 없습니다. 로컬 연산으로 동작합니다."` | 로컬 파서 모드로 자동 즉시 전환 |

---

## 7. 테스트 명세 및 검증 계획 (`tests/`)

### 7.1 단위 테스트 스위트 구성

1. **`tests/test_basic_arithmetic.py`**
   - 사칙연산 우선순위 검증 (`TC-BIG-001`)
   - 10,000자리 정수 덧셈/곱셈 연산 정밀도 및 속도 검증 (`TC-BIG-002`)
2. **`tests/test_scientific_engine.py`**
   - DEG 모드에서 $\sin(30^\circ) = 0.5$ 검증 (`TC-BIG-003`)
   - RAD 모드에서 $\sin(\pi / 2) = 1.0$ 검증 (`TC-BIG-004`)
   - $\ln(e) = 1$, $\log_{10}(1000) = 3$, $5! = 120$ 검증 (`TC-BIG-005`)
3. **`tests/test_linear_algebra.py`**
   - 2×2, 3×3 행렬식(Determinant) 계산 검증 (`TC-BIG-006`)
   - 가역 행렬의 역행렬 곱 $A \times A^{-1} = I$ 검증 (`TC-BIG-007`)
   - 특이행렬(Singular Matrix) 예외 포착 및 방어 검증 (`TC-BIG-008`)
   - 3D 벡터 외적(Cross Product) 및 내적(Dot Product) 검증 (`TC-BIG-009`)
4. **`tests/test_scratchpad_engine.py`**
   - 변수 바인딩 $x=15, y=5 \rightarrow x \times y + 25 = 100$ 검증 (`TC-BIG-010`)
   - 상단 변수 수정 시 하단 수식 재평가 일관성 검증 (`TC-BIG-011`)
5. **`tests/test_unit_converter.py`**
   - $100^\circ\text{C} = 212^\circ\text{F}$ 변환 정밀도 검증 (`TC-BIG-012`)
   - $1\text{m} = 39.3701\text{inch}$ 변환 검증 (`TC-BIG-013`)
6. **`tests/test_history_memory.py`**
   - `MS`, `M+`, `MR` 메모리 누적 연산 검증 (`TC-BIG-014`)
   - 50건 히스토리의 CSV 파일 정상 직렬화 검증 (`TC-BIG-015`)

### 7.2 종합 수용 테스트(Acceptance Test) 매트릭스

| 테스트 ID | 대상 기능 | 테스트 시나리오 | 합격 기준 |
|---|---|---|---|
| **TC-ACC-01** | 공학 수식 복합 계산 | `sin(30) + log10(100) * sqrt(16)` (DEG 모드) | 결과 `8.5` 정확히 출력 |
| **TC-ACC-02** | 행렬 역행렬 연산 | $\begin{pmatrix} 4 & 7 \\ 2 & 6 \end{pmatrix}$ 역행렬 계산 | $\det(A) = 10$, 올바른 역행렬 요소 출력 |
| **TC-ACC-03** | 특이행렬 방어 | $\begin{pmatrix} 1 & 2 \\ 2 & 4 \end{pmatrix}$ 역행렬 시도 | 비정상 종료 없이 "특이행렬" 경고 다이얼로그 표시 |
| **TC-ACC-04** | 매쓰 노트 반응성 | 10줄의 수식과 3개 변수 연동 문서 수정 | 50ms 이내 전 라인 재평가 완료 |
| **TC-ACC-05** | 다크 모드 전환 | 단축키(`Ctrl+T`)로 테마 전환 | 모든 위젯이 다크 색상 팔레트로 깜빡임 없이 즉시 전환 |
| **TC-ACC-06** | 히스토리 내보내기 | 히스토리 10건 적재 후 CSV 내보내기 클릭 | 파일 생성 및 수식/결과/시간 정상 저장 확인 |

---

## 8. 산출물 및 빌드/실행 가이드 규격

### 8.1 README.md 작성 필수 요구사항
프로젝트 루트의 `README.md`는 다음 항목을 체계적으로 서술해야 합니다.
1. **프로젝트 타이틀 및 소개**: Big Calculator의 비전과 6대 핵심 기능
2. **신규 고도화 기능 하이라이트**: 선형대수학 엔진, 매쓰 노트, AI 수학 어시스턴트, 2D 플로팅
3. **아키텍처 및 모듈 분할 구조**: SoC 및 Code Splitting 설명, 패키지별 역할 소개
4. **설치 및 환경 설정**:
   ```bash
   # 가상환경 생성 및 활성화
   python -m venv venv
   # Windows PowerShell
   .\venv\Scripts\Activate.ps1
   # Linux/macOS
   source venv/bin/activate
   ```
5. **의존성 라이브러리 설치**: `pip install -r requirements.txt`
6. **실행 방법**: `python src/main.py`
7. **테스트 스위트 실행**: `python -m unittest discover -s tests`
8. **상세 조작 가이드**:
   - 표준/공학 계산기 모드 전환
   - DEG/RAD 각도 설정법
   - 매쓰 노트 문법 및 변수 정의법
   - 행렬 입력 인터페이스 활용법
   - 키보드 단축키 전체 일람표

### 8.2 requirements.txt 패키지 규격
공학 계산, 데이터 처리, 시각화 및 AI 연동을 위해 다음 패키지를 명시합니다.
```
# [수학 및 과학 연산]
numpy>=1.24.0
sympy>=1.12

# [2D 그래프 시각화]
matplotlib>=3.7.0

# [테스트 및 코드 품질]
pytest>=7.4.0
flake8>=6.0.0

# [AI 어시스턴트 연동 - 선택 사항]
requests>=2.31.0
```
