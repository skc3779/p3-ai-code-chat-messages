# FSD v1.0.031 - Shift+Enter Command Execution

## 문서 정보
- **버전**: v1.0.031
- **작성일**: 2026-02-12
- **대상 파일**: 
  - `claude-ai-chat-code01.py`
  - `gemini-ai-chat-code01.py`
  - `gen-ai-chat-code01.py`
  - `src/cli_input.py`

## 1. 개요

### 1.1 목적
현재 `/multiline`을 제외한 모든 명령어는 `Enter` 키로 실행됩니다. 이를 `Shift+Enter`로 변경하여 사용자가 여러 줄의 입력을 자연스럽게 작성할 수 있도록 개선합니다.

### 1.2 범위
- CLI 입력 처리 로직 수정 (`src/cli_input.py`)
- 멀티라인 입력 모드 제거 또는 기본 동작으로 통합

## 2. 요구사항

### 2.1 기능 요구사항

#### FR-1: 기본 입력 동작 변경
- **현재**: `Enter` 키 입력 시 명령어 즉시 실행
- **변경**: `Enter` 키 입력 시 새로운 줄 추가
- **실행**: `Shift+Enter` 키 조합으로 명령어 실행

#### FR-2: `/multiline` 명령어 처리
- `/multiline` 명령어는 기존 동작 유지 (선택적)
- 또는 `/multiline` 명령어 제거 (기본 동작이 멀티라인이므로)

#### FR-3: 프롬프트 표시
- 첫 번째 줄: `👤 You: `
- 이후 줄: `... ` (continuation prompt)

### 2.2 비기능 요구사항

#### NFR-1: 호환성
- `prompt_toolkit` 라이브러리 활용
- 기존 자동완성 기능 유지
- 히스토리 기능 유지

#### NFR-2: 사용성
- 사용자가 직관적으로 멀티라인 입력 가능
- `Shift+Enter` 조합이 명확하게 동작

## 3. 설계

### 3.1 수정 대상

#### 3.1.1 `src/cli_input.py`
```python
# prompt_toolkit의 KeyBindings 사용
from prompt_toolkit.key_binding import KeyBindings

# multiline 설정 추가
# Shift+Enter로 실행, Enter로 줄바꿈
```

#### 3.1.2 메인 파일들
- `claude-ai-chat-code01.py`
- `gemini-ai-chat-code01.py`
- `gen-ai-chat-code01.py`

**변경 사항**:
- `/multiline` 명령어 처리 로직 제거 또는 수정
- 도움말 메시지 업데이트

### 3.2 구현 방법

#### 3.2.1 `prompt_toolkit` 설정
```python
# KeyBindings 정의
bindings = KeyBindings()

@bindings.add('enter')
def _(event):
    """Enter: 새 줄 추가"""
    event.current_buffer.insert_text('\n')

@bindings.add('s-enter')  # Shift+Enter
def _(event):
    """Shift+Enter: 명령어 실행"""
    event.current_buffer.validate_and_handle()
```

#### 3.2.2 PromptSession 설정
```python
self.session = PromptSession(
    history=FileHistory(self.history_file),
    completer=self.completer,
    style=self.style,
    multiline=True,  # 멀티라인 활성화
    key_bindings=bindings,  # 커스텀 키바인딩
    prompt_continuation='... '  # 연속 프롬프트
)
```

## 4. 테스트 시나리오

### 4.1 기본 동작 테스트
1. 프로그램 실행
2. `👤 You: ` 프롬프트에서 텍스트 입력
3. `Enter` 키 입력 → 새 줄 추가 확인
4. 추가 텍스트 입력
5. `Shift+Enter` 입력 → 명령어 실행 확인

### 4.2 명령어 테스트
1. `/help` 입력 후 `Shift+Enter` → 도움말 출력
2. `/files` 입력 후 `Shift+Enter` → 파일 목록 출력
3. 일반 질문 여러 줄 입력 후 `Shift+Enter` → AI 응답 확인

### 4.3 자동완성 테스트
1. `/` 입력 → 명령어 자동완성 동작 확인
2. `Tab` 키로 자동완성 선택
3. `Shift+Enter`로 실행

## 5. 마이그레이션 가이드

### 5.1 사용자 안내
- 릴리스 노트에 변경사항 명시
- 도움말 메시지에 `Shift+Enter` 사용법 추가

### 5.2 도움말 업데이트
```
💡 입력 방법:
  - Enter: 새 줄 추가 (멀티라인 입력)
  - Shift+Enter: 명령어 실행
```

## 6. 참고사항

### 6.1 `prompt_toolkit` 문서
- [KeyBindings](https://python-prompt-toolkit.readthedocs.io/en/master/pages/advanced_topics/key_bindings.html)
- [Multiline Input](https://python-prompt-toolkit.readthedocs.io/en/master/pages/asking_for_input.html#multiline-input)

### 6.2 대안 고려사항
- `Ctrl+Enter` 조합도 고려 가능
- 설정 파일로 키바인딩 커스터마이징 옵션 제공

## 7. 승인

- [ ] 개발자 검토
- [ ] 테스트 완료
- [ ] 문서 업데이트 완료
