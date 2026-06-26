# BUGF v1.1.071 — `/agents` stop 키 및 TUI 입력 복귀 불량

## 1. 요약

`gemini-ai-chat-code.py`에서 `/agents` 실행 중 `s`를 입력하면 의도한 비동기 중단 대신 `KeyboardInterrupt` 경로로 보이거나, 종료 후 TUI의 `>` 명령창이 키 입력을 정상 처리하지 못하는 문제가 있었다.

## 2. 영향 범위

- 엔트리포인트: `gemini-ai-chat-code.py`, `claude-ai-chat-code.py`, `gen-ai-chat-code.py`
- 공통 모듈: `src/agent_input_listener.py`, `src/cli_input.py`
- 루프 제어: `src/agent_runner.py`
- 환경: Unix/WSL TTY + prompt_toolkit TUI 조합에서 재현 가능성이 높음

## 3. 재현 증상

### B-071-01: `/agents` 실행 중 `s` 입력 시 정상 stop 경로 미동작

실행 중 화면:

```text
🤖 AI가 답변을 고민 중입니다... s [s]top ? (a):
```

기대:

- `s` 단일 키 입력으로 `AgentStopReason.USER_STOP` 처리
- traceback 없이 `✅/⚠️ 에이전트 종료` 요약 출력
- 메인 TUI 입력 프롬프트로 복귀

실제:

- Unix/WSL 구현이 `sys.stdin.readline()` 기반이라 Enter 전까지 `s`가 리스너에 전달되지 않음
- 이후 동기 `input()` 또는 Ctrl+C 경로와 섞이며 `KeyboardInterrupt`처럼 관측될 수 있음

### B-071-02: `/agents` 완료 후 TUI `>` 입력창이 멈춘 것처럼 보임

실행 완료 후 화면:

```text
============================================================
✅ 에이전트 종료 (stop_reason=done, 3 iterations)
📁 생성/수정 파일 (4):
- pyproject.toml
- pytop/engine.py
- pytop/tui.py
- pytop/main.py
============================================================
> 
```

기대:

- `/agents` 종료 직후 다음 `>` 프롬프트에서 키보드 입력 및 slash command 실행 가능

실제:

- 커서만 깜빡이고 입력이 먹지 않는 것처럼 보임
- 원인 후보는 `/agents` 비동기 리스너가 터미널 입력 모드를 원복하지 못한 상태에서 prompt_toolkit TUI가 재시작되는 경로

## 4. 원인 분석

### C-071-01: Unix 리스너가 라인 단위 입력만 소비

`src/agent_input_listener.py`의 Unix 구현은 `select.select()` 후 `sys.stdin.readline()`을 호출했다. 이 방식은 canonical 모드에서 Enter가 입력되기 전까지 반환되지 않으므로, 안내 문구의 “`s` 키로 중단” UX와 실제 구현이 맞지 않았다.

### C-071-02: 리스너 종료 시 터미널 상태 복구 보장이 약함

기존 `stop()`은 `_active.clear()` 후 스레드 참조만 제거하고 join/터미널 복구를 수행하지 않았다. 향후 단일 키 입력을 위해 cbreak/nonblocking 모드를 사용하려면 종료와 pause 경계에서 원복이 반드시 필요하다.

### C-071-03: `/agents` 종료 후 prompt_toolkit 런타임 상태 초기화 부재

`CLIInputHandler`는 매 입력마다 새 `Application`을 만들지만, `/agents`처럼 외부 루프가 장시간 stdin을 소유한 뒤 돌아오는 경로에서는 내부 suggestion/buffer 상태를 명시적으로 리셋하지 않았다.

### C-071-04: 초기 PLAN 생성 직후 stop 체크포인트 누락

iteration 루프 내부 모델 호출 뒤에는 `_check_async_stop()`이 있었지만, 신규 세션의 초기 PLAN 생성 직후에는 같은 체크포인트가 없었다. 따라서 사용자가 PLAN 생성 대기 중 `s`를 누르면 stop 플래그가 설정되어도 승인 프롬프트로 계속 진행할 수 있었다.

## 5. 수정 내용

- `src/agent_input_listener.py`
  - Unix/WSL에서 `tty.setcbreak()` + nonblocking `os.read()`로 단일 키 입력을 즉시 감지
  - `s/q/p/i` 우선순위 처리 유지
  - `stop()` 및 리스너 종료 `finally`에서 터미널 속성/파일 플래그 복구
  - pause 경계에서도 리스너 중단과 복구가 일어나도록 유지

- `src/cli_input.py`
  - `reset_runtime_state()` 추가
  - prompt_toolkit suggestion, 선택 인덱스, 스크롤, 결과, buffer 상태 초기화

- `src/agent_runner.py`
  - 신규 세션 초기 PLAN 모델 호출 직후 `_check_async_stop()`을 호출
  - PLAN 승인 프롬프트 진입 전에 `s` 입력을 `USER_STOP`으로 수렴

- `gemini-ai-chat-code.py`, `claude-ai-chat-code.py`, `gen-ai-chat-code.py`
  - `/agents` 처리 직후 `reset_runtime_state()` 호출
  - provider별 `/agents` 복귀 동작 차이 방지

## 6. 회귀 테스트

- `tests/test_agent_input_listener.py`
  - Unix/WSL에서 Enter 없이 `b"s"` 단일 키가 stop 플래그로 처리되는지 검증
  - `stop()`이 저장된 터미널 속성을 복구하는지 검증
  - 신규 세션 PLAN 생성 중 `s` 입력 시 승인 프롬프트 없이 `USER_STOP` 되는지 검증

- `tests/test_cli_input_runtime_reset.py`
  - `/agents` 종료 후 다음 TUI 입력을 위해 prompt_toolkit 런타임 상태가 초기화되는지 검증

## 7. 추가 검토 결과

- `/agents` 분기가 세 provider 엔트리포인트에 복제되어 있어 Gemini만 수정하면 같은 버그가 Claude/GenAI에 남는다. 공통 모듈 수정과 세 엔트리포인트 후처리 호출을 함께 적용했다.
- 기존 `docs/requirements`가 표준 폴더로 보이나, 요청 경로가 `docs/reuirements`였으므로 본 BUGF 문서는 해당 경로에 저장했다.

## 8. 완료 기준

- `/agents` 실행 중 `s` 단일 키 입력으로 traceback 없이 `user_stop` 종료
- `/agents` 정상 완료 또는 중단 후 `>` 프롬프트에서 키보드 명령 입력 가능
- 관련 단위 테스트 통과
