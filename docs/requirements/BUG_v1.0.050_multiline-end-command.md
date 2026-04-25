# BUG v1.0.050 - 멀티라인 입력 `/end` 종료 및 Meta+Enter 버그

## 문서 정보
- **버전**: v1.0.050
- **작성일**: 2026-02-26
- **상태**: Fixed
- **관련 FSD**: FSD v1.0.050 (멀티라인 텍스트 편집 기능 개선)
- **대상 파일**: `src/cli_input.py`

---

## 1. 증상

### 증상 1: Meta+Enter 미작동
`Meta+Enter`(Alt+Enter)로 멀티라인 입력을 전송하려 하면 작동하지 않음.
- macOS와 Windows에서 Meta 키 처리 방식이 다름 (OS 간 충돌 이슈)
- `prompt_toolkit`에서 `escape, enter` 시퀀스가 환경에 따라 일관되지 않게 동작

### 증상 2: `/end` 입력 시 텍스트 자동 삭제 + 커서 이동 버그
```
> /multiline
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
... 텍스트 1
... 텍스트 2
... /end    ← 입력 즉시 /end 줄이 삭제되고 위쪽 라인 끝으로 커서 이동
```
- `/end` 입력 후 정상 종료되지 않고, `/end` 줄만 사라지며 편집 모드가 계속됨
- `_on_ml_text_changed` 콜백에서 `buf.text`를 수정하면 재귀적 text_changed 이벤트가 발생
- `_ml_should_exit` 플래그는 설정되나, Application을 종료하는 메커니즘이 없음

---

### 증상 3: 멀티라인 입력시 입력이 이쁘게 되지 않음.

```cmd
> /multiline
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
... a
b
c
```

- 멀티라인 입력시 기존 아래와 같이 입력이 이쁘게 되지 않음. 

```cmd
> /multiline
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
... a
... b
... c
... /end
```


## 2. 원인

### 원인 1: Meta+Enter
`@kb.add('escape', 'enter')` 바인딩이 macOS/Windows 터미널에서 일관되게 동작하지 않음.
→ **해결**: Meta+Enter 기능 제거

### 원인 2: `/end` 감지
`_on_ml_text_changed` 콜백 내에서:
1. `/end` 줄 감지 → `buf.text` 수정 (줄 제거) → 재귀적 text_changed 발생
2. `_ml_should_exit = True` 설정되나 Application 이벤트 루프에서 확인하지 않음
3. Application이 종료되지 않고 편집 모드 유지

## 3. 수정 방안

### 3.1 Meta+Enter 제거
- `@kb.add('escape', 'enter')` 바인딩 삭제
- `@kb.add('escape', eager=True)` (Esc 취소) 유지

### 3.2 `/end` 종료 방식 변경
`_on_ml_text_changed` 콜백에서 `buf.text`를 수정하는 대신, **Enter 키 바인딩에서 `/end` 감지** 방식으로 변경:
- Enter 입력 시 마지막 줄이 `/end`인지 확인
- `/end`가 감지되면 해당 줄을 제거한 텍스트를 결과로 설정하고 `app.exit()` 호출
- `/end`가 아니면 일반 줄바꿈 수행

### 3.3 안내 메시지 변경
```
변경 전: 📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
변경 후: 📝 멀티라인 모드 (/end로 종료, Esc 취소)
```

### 3.4 하단 안내 바 변경
```
변경 전: Meta+Enter: 전송 | /end: 종료 | Esc: 취소
변경 후: /end: 전송 | Esc: 취소
```

---

## 4. 영향 범위

| 파일 | 영향 |
|------|------|
| `src/cli_input.py` | `get_multiline()` 메서드 수정 |
| `gen-ai-chat-code01.py` | 변경 없음 (`get_multiline()` 호출만 하므로) |
| `claude-ai-chat-code01.py` | 변경 없음 |
| `gemini-ai-chat-code01.py` | 변경 없음 |

---

## 5. 수정 내역
- `src/cli_input.py` `get_multiline()`:
  - Meta+Enter 바인딩 삭제
  - Enter 키 바인딩에서 `/end` 감지 → 줄 제거 후 `app.exit()`
  - `_on_ml_text_changed` 콜백에서 `/end` 감지 로직 삭제
  - 안내 메시지 변경
