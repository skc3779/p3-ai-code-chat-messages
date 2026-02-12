# FSD: 명령어 자동 완성 (P3-05)

> **문서 버전**: v1.0.028 
> **작성일**: 2026-01-25  
> **상태**: Draft  
> **관련 SRS**: SRS_Claude_Code_Assistant_Improvements_v1.0.016.md

---

## 1. 개요

### 1.1 목적
CLI 환경에서 명령어 입력 시 Tab 키를 이용한 자동 완성(Auto-completion) 기능을 제공하여 사용 편의성을 높입니다.

### 1.2 현재 문제
* 모든 명령어를 기억하거나 `/help`를 보고 수동으로 입력해야 함.
* 오타 발생 가능성이 높음.

---

## 2. 기능 요구사항

### 2.1 Tab 자동 완성
* `/` 입력 후 Tab 키를 누르면 사용 가능한 명령어 목록 표시 또는 자동 완성.
* 파일 경로 인자 입력 시 현재 디렉토리 기준 파일명 자동 완성.

### 2.2 히스토리 탐색
* 위/아래 화살표 키로 이전에 입력한 명령어 히스토리 탐색 가능.

---

## 3. 기술 설계

### 3.1 라이브러리
* `readline` (Linux/Mac) 또는 `pyreadline3` (Windows) 라이브러리 활용.
* 또는 더 강력한 UX를 위해 `prompt_toolkit` 도입 고려. (본 문서는 `prompt_toolkit` 권장)

### 3.2 통합 설계
* **공통 모듈**: `src/cli_input.py` (신규 권장)
    * `create_prompt_session()`: 자동 완성이 적용된 `PromptSession` 객체 생성 함수.
    * 공통 명령어 리스트(`['/help', '/read', ...]`) 관리.
* **적용 대상**:
    * `claude-ai-chat-code01.py`: 기존 `input()` 함수를 `PromptSession.prompt()`로 대체.
    * `gen-ai-chat-code01.py`: 기존 `input()` 함수를 `PromptSession.prompt()`로 대체.

---

## 4. 검증 계획
* `claude-ai-chat-code01.py` 실행 후 자동 완성 테스트.
* `gen-ai-chat-code01.py` 실행 후 자동 완성 테스트.

## 5. 단위 테스트 코드 작성
* `tests/test_cli_input.py`

## 6. 릴리즈 노트 작성
* `docs/specs/releases/RELEASE_v1.0.028.md`
