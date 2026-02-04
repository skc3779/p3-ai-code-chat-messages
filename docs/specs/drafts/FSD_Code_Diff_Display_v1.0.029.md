# FSD: 코드 Diff 표시 기능 (P3-03)

> **문서 버전**: v1.0.028  
> **작성일**: 2026-01-25  
> **상태**: Draft  
> **관련 SRS**: SRS_Claude_Code_Assistant_Improvements_v1.0.016.md

---

## 1. 개요

### 1.1 목적
AI가 생성한 전체 코드를 단순히 출력하는 대신, 기존 코드와의 차이점(Diff)을 시각적으로 보여주어 사용자가 변경 사항을 쉽게 파악하도록 합니다.

### 1.2 현재 문제
* AI가 파일 전체를 새로 작성하여 줌.
* 긴 파일의 경우 어떤 부분이 바뀌었는지 한눈에 알기 어려움.

---

## 2. 기능 요구사항

### 2.1 Diff 뷰어
* AI 응답에 파일 수정 제안이 포함된 경우, 원본 파일과 비교하여 Diff를 생성.
* `/diff` 명령어로 가장 최근 제안에 대한 Diff 출력.
* 터미널 색상 코드를 사용하여 추가된 라인(초록색), 삭제된 라인(빨간색) 표시.

### 2.2 자동 적용
* `/apply` 명령어로 Diff 내용을 실제 파일에 적용(Patch).

---

## 3. 기술 설계

### 3.1 라이브러리
* Python 내장 `difflib` 모듈 사용.

### 3.2 구현 로직
* **공통 모듈**: `src/diff_viewer.py` (신규)
    * `DiffViewer` 클래스: 두 문자열(코드) 간의 차이를 분석하고 색상 정보가 포함된 Diff 텍스트 생성.
    * `generate_colored_diff(original: str, new: str) -> str`

### 3.3 통합 포인트
* **GenAICodeAssistant 및 ClaudeCodeAssistant**:
    * AI 응답 처리 후 `CodeExecutor` 또는 `FileManager`와 연계하여 `/diff` 명령어 지원.
    * 두 어시스턴트 모두 동일한 `DiffViewer` 유틸리티를 사용하여 일관된 출력 제공.

---

## 4. 검증 계획
* `ClaudeCodeAssistant`로 코드 수정 요청 후 `/diff` 확인.
* `GenAICodeAssistant`로 코드 수정 요청 후 `/diff` 확인.

## 5. 단위 테스트 코드 작성
* `tests/test_diff_viewer.py`
* `tests/test_claude_tool_use.py`
* `tests/test_genai_tool_use.py`

## 6. 릴리즈 노트 작성
* `docs/specs/releases/RELEASE_v1.0.028.md`
