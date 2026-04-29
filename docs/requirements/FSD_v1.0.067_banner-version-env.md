# FSD v1.0.067 - 배너 버전 정보 환경변수(.env) 연동

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.067 |
| 제목 | 배너 버전 정보 환경변수(.env) 연동 |
| 작성일 | 2026-03-04 |
| 상태 | 설계 완료 |
| 대상 소스 | `gemini-ai-chat-code.py`, `claude-ai-chat-code.py`, `gen-ai-chat-code.py`, `.env.example` |

---

## 1. 개요 (Overview)

현재 3개의 주요 AI 챗봇 스크립트(`gen-ai`, `claude`, `gemini`)를 실행할 때 표출되는 터미널 시작 배너 텍스트에는 v1.0.065와 같이 하드코딩된 버전 정보가 포함되어 있습니다.
버전이 업데이트될 때마다 각 스크립트를 개별적으로 수정하는 번거로움을 해결하기 위해, 배너에 표시되는 버전 정보를 `.env` 파일의 `AI_VERSION` 환경변수를 통해 동적으로 읽어오도록 개선합니다.

### 1.1 개선 목표

| # | 목표 | 설명 |
|---|------|------|
| 1 | 하드코딩 제거 | 소스코드 내 하드코딩된 `v1.0.xx` 버전 정보를 제거 |
| 2 | 환경변수 연동 | `os.getenv("AI_VERSION")` 을 통해 버전을 읽어와 동적으로 배너 출력 |
| 3 | 공통 적용 | 3개의 메인 스크립트 배너 모두 동일한 변수를 통해 버전 렌더링 |

---

## 2. 설계 (Design)

### 2.1 환경 변수 정의 (`.env` / `.env.example`)
`.env` 파일에 다음과 같은 버전 변수를 추가합니다.
```env
# AI Code Assistant 버전 정보
AI_VERSION=v1.0.067
```

### 2.2 소스코드 연동 (`print_banner` 함수)
`gemini-ai-chat-code.py`, `claude-ai-chat-code.py`, `gen-ai-chat-code.py` 내의 `print_banner()` 함수를 수정합니다.
- `os.getenv("AI_VERSION", "v1.0.067")` 방식으로 값을 읽어옴 (환경변수 미존재 시 폴백 제공)
- ASCII Art 배너의 세로줄 너비(정렬)가 깨지지 않도록 파이썬 f-string 포매팅을 활용하여 문자열 길이를 고정하거나 동적으로 계산하여 우측 패딩 공백을 제공합니다.

#### 변경 예시 (Concept)
기존:
```python
banner = f"""
...
{C}║{R}         {G}🤖  AI-Powered Code Assistant  ·  v1.0.065{R}                           {C}║{R}
...
"""
```

변경 후:
```python
version = os.getenv("AI_VERSION", "v1.0.067")
# 우측 여백을 일정하게 맞추기 위한 포매팅 (버전 문자열 길이에 따라 공백 조정)
version_str = f"v{version}" if not str(version).startswith("v") else version
padding_len = 35 - len(version_str) # 기존 디자인 규격에 맞게 계산
padding = " " * max(0, padding_len)

banner = f"""
...
{C}║{R}         {G}🤖  AI-Powered Code Assistant  ·  {version_str}{R}{padding}{C}║{R}
...
"""
```

---

## 3. 요구사항 (Requirements)

| ID | 요구사항 | 우선순위 |
|----|----------|--------:|
| REQ-067-001 | `.env.example` 파일에 `AI_VERSION` 키를 추가한다. | 필수 |
| REQ-067-002 | `claude-ai-chat-code.py`의 `print_banner()` 함수가 `AI_VERSION` 환경변수를 읽어 배너에 표시하도록 수정한다. | 필수 |
| REQ-067-003 | `gemini-ai-chat-code.py`의 `print_banner()` 함수가 `AI_VERSION` 환경변수를 읽어 배너에 표시하도록 수정한다. | 필수 |
| REQ-067-004 | `gen-ai-chat-code.py`의 `print_banner()` 함수가 `AI_VERSION` 환경변수를 읽어 배너에 표시하도록 수정한다. | 필수 |
| REQ-067-005 | 버전을 환경변수에서 읽을 수 없을 시 하드코딩된 기본값(예: `v1.0.067`)을 폴백(Fallback)으로 적용한다. | 구조안정성 |
| REQ-067-006 | 버전 문자열 길이에 상관없이 배너 양쪽 테두리 간격(레이아웃)이 깨지지 않아야 한다. | UI 최적화 |

---

## 4. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.067 | 2026-03-04 | - | 최초 작성: 배너 버전 정보 `.env` 연동 상세 |
