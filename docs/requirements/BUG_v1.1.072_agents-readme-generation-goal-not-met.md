# BUG v1.1.072 - /agents README 생성 요청이 파일 생성 없이 GOAL_NOT_MET으로 종료

## 1. 요약

`/agents`에서 `현재 프로젝트의 소스코드를 분석해서 README.md 파일을 생성해줘.`를 실행하고 PLAN 승인 게이트에서 `r`을 선택하면, 에이전트가 `README.md`를 생성하지 않고 탐색성 shell 명령만 반복한 뒤 `goal_not_met`으로 종료되는 문제가 확인되었다.

사용자 로그 기준으로 완료 기준은 `[권위/file_exists] README.md`로 정상 추출되었지만, 실제 실행은 `find`, `cat` 명령 반복에 머물렀고 최종 요약도 `생성/수정 파일: 없음`으로 종료되었다.

## 2. 영향

- 문서 생성, 신규 파일 생성, 구현 요청처럼 산출 파일이 명확한 `/agents` 작업이 실패할 수 있다.
- 사용자는 `run-auto`를 승인했는데도 에이전트가 실제 쓰기 액션으로 전환하지 않아 토큰과 시간을 소모한다.
- 실패 종료 사유가 `goal_not_met`으로 표시되지만, 왜 파일 생성 액션으로 전환하지 못했는지 충분히 드러나지 않는다.

## 3. 재현 시나리오

1. `gemini-ai-chat-code.py` 실행.
2. `/agents` 입력.
3. 목표 입력:
   ```text
   현재 프로젝트의 소스코드를 분석해서 README.md 파일을 생성해줘.
   ```
4. PLAN 승인 게이트에서 `r` 입력.
5. 에이전트가 `find`, `cat` 등 조회 명령을 반복하다 `goal_not_met`으로 종료.
6. `README.md`가 생성되지 않음.

## 4. 관찰 증거

- 사용자 로그:
  - 완료 기준: `[권위/file_exists] README.md`
  - 실행 액션: `find`, `cat` 위주의 shell 명령 6건
  - 종료: `stop_reason=goal_not_met`
  - 생성/수정 파일: 없음
- `.env`:
  - `MAX_MESSAGES_TO_KEEP=1`
  - 로그의 `히스토리 트리밍 필요: 메시지 수 초과 (2개 >= 1개)`와 일치한다.

## 5. 원인 분석

### C-072-01. 완료 기준은 추출되지만 첫 실행 프롬프트에는 권위 기준이 직접 포함되지 않음

근거:

- `AgentGoalEvaluator.extract_from_goal()`은 `README.md ... 생성/작성` 형태를 `file_exists` 기준으로 추출한다.  
  참조: `src/agent_goal_evaluator.py` `RE_FILE_MENTION`, `extract_from_goal()`
- `AgentRunner._initialize_acceptance_criteria()`는 추출된 기준을 `session.acceptance_criteria`에 저장하고 콘솔에 출력한다.  
  참조: `src/agent_runner.py` `_initialize_acceptance_criteria()`
- 그러나 `AgentRunner._build_iteration_prompt()`의 기본 프롬프트는 `[GOAL]`, `[PLAN]`, 최근 관찰, 선택적 `[REFINE_TARGETS]`만 포함한다. 첫 iteration에는 `probe_snapshot`이 없으므로 `README.md` 파일 생성이 검증 기준이라는 사실이 별도 `[ACCEPTANCE_CRITERIA]`로 강하게 주입되지 않는다.  
  참조: `src/agent_runner.py` `_build_iteration_prompt()`

추론:

- 모델은 PLAN의 “분석 후 작성” 문구를 따르며 탐색 액션을 반복할 수 있고, 시스템은 첫 액션에서 “반드시 README.md 생성으로 수렴하라”는 권위 기준을 충분히 전달하지 못한다.

### C-072-02. `run-auto`에서 미충족 기준 피드백이 너무 늦고 약함

근거:

- 미충족 기준은 iteration 종료 후 `_probe_criteria()`에서 평가되고, 다음 iteration에 `[REFINE_TARGETS]`로 들어간다.  
  참조: `src/agent_runner.py` `_probe_criteria()`, `_build_refine_targets()`
- `[AGENT_DONE]`을 선언했을 때만 `_finalize_goal()`의 `[GOAL_GATE]` 피드백이 강하게 동작한다.  
  참조: `src/agent_runner.py` `_finalize_goal()`, `_build_gate_feedback()`
- 사용자 로그에서는 모델이 `[AGENT_DONE]`을 선언하지 않고 탐색 명령을 계속 반복했으므로, 완료 게이트의 거부 피드백 경로가 핵심 제어 수단으로 작동하지 않는다.

추론:

- `README.md` 미존재 상태가 반복 확인되어도, 모델을 파일쓰기 액션으로 강제 전환하는 제어가 부족하다. 결과적으로 정체 가드가 먼저 종료한다.

### C-072-03. 성공한 조회 명령이 “진전”처럼 기록되어 반복 탐색을 억제하지 못함

근거:

- `find`, `cat` 같은 조회 명령은 성공 액션으로 기록된다.  
  참조: `src/agent_runner.py` `_exec_single_shell_command()`
- bypass 안전장치의 `_check_stagnation()`은 최근 N개 iteration에 성공 액션이 하나도 없을 때만 정체로 본다. 조회 명령이 성공하면 이 정체 판정에는 걸리지 않는다.  
  참조: `src/agent_runner.py` `_check_stagnation()`
- 실제 종료는 개선 루프의 `refine_round > AGENT_MAX_REFINE_ROUNDS` 경로로 발생했다.  
  참조: `src/agent_runner.py` `_update_refine_convergence()`, `_check_refine_convergence()`

추론:

- 산출물 기준(`README.md` 존재)에는 진전이 없지만, shell 성공 여부만 보면 진행처럼 보이는 상태가 만들어진다. 이 때문에 “읽기만 반복 중”이라는 더 구체적인 실패 진단과 조기 교정이 어렵다.

### C-072-04. Gemini가 잘못 낸 `sh\ncat ...` 액션이 무시되어도 명확한 실패 피드백이 없음

근거:

- 사용자 로그의 iteration 4는 `[ACTION]`이 사실상 `sh` 다음 줄 `cat ...` 형태였고 실행된 액션이 없었다.
- `AgentActionDispatcher`는 fenced block(````sh ... ````, `@@@filename`, `@@@patch`) 또는 `$ command` 라인만 shell/file/code 액션으로 파싱한다. 일반 텍스트 `sh\ncat ...`는 액션으로 인식되지 않는다.  
  참조: `src/agent_action_dispatcher.py` `_parse()`

추론:

- 모델이 형식을 조금 벗어나면 “실행된 액션 없음”으로만 지나가며, 다음 응답에서 올바른 `[ACTION:shell]` 또는 `$` 형식을 요구하는 강한 교정이 없다.

### C-072-05. 환경 설정 `MAX_MESSAGES_TO_KEEP=1`이 에이전트 반복 품질을 악화시킴

근거:

- `.env`에 `MAX_MESSAGES_TO_KEEP=1`이 설정되어 있다.
- `TokenManager.auto_trim_history()`는 메시지 수가 `MAX_MESSAGES_TO_KEEP` 이상이면 트리밍을 시도한다. 단 최소 2개 메시지는 유지한다.  
  참조: `src/token_manager.py` `MAX_MESSAGES_TO_KEEP`, `auto_trim_history()`
- 사용자 로그에 매 iteration `2개 >= 1개`, `4개 >= 1개` 트리밍 로그가 반복된다.

추론:

- 에이전트 전용 history가 매 호출 전 최근 1쌍 수준으로 잘리며, 이전 탐색 결과와 실패 흐름을 모델이 안정적으로 누적하기 어렵다. 단, `session.iterations[-2:]` 관찰은 별도 프롬프트에 포함되므로 이것만으로 단독 원인이라고 보기는 어렵고 기여 요인으로 판단한다.

### C-072-06. PLAN 단계가 모델 기준(`@@@criteria`) 생성을 요구하지 않음

근거:

- `AgentGoalEvaluator.parse_model_criteria()`는 PLAN의 `@@@criteria` 블록을 파싱할 수 있다.
- 하지만 `AgentRunner._build_initial_prompt()`는 번호 매긴 PLAN만 요청하고 `@@@criteria` 작성을 요구하지 않는다.  
  참조: `src/agent_runner.py` `_build_initial_prompt()`

추론:

- `README.md`의 존재 여부만 검증되고, 내용 품질 기준(`프로젝트 소개`, `설치`, `실행`, `디렉토리 구조` 포함 등)은 자동 기준에 들어가지 않는다. 이는 “파일은 생성했지만 부실한 README”를 통과시킬 수 있는 별도 품질 리스크다.

## 6. 우선순위

| 우선순위 | 항목 | 심각도 | 근거 |
|---|---|---:|---|
| P1 | 완료 기준을 iteration 프롬프트에 항상 명시하고, 미충족 `file_exists`는 파일 생성 액션을 강하게 요구 | 높음 | 이번 버그의 직접 실패 경로 |
| P1 | 산출물 미생성 상태에서 조회 명령만 반복될 때 “탐색 정체”로 분류하고 파일쓰기 전환 피드백 주입 | 높음 | 성공 shell 때문에 일반 bypass 정체 감지가 작동하지 않음 |
| P2 | 파싱 불가 ACTION에 실패 ActionResult를 남기고 self-correction 유도 | 중간 | `sh\ncat ...` 같은 형식 오류가 조용히 무시됨 |
| P2 | `/agents` 실행 중 provider history trim 하한을 안전값으로 보정하거나 agent history는 자체 보존 정책 적용 | 중간 | `MAX_MESSAGES_TO_KEEP=1` 환경에서 반복 품질 악화 |
| P3 | PLAN 프롬프트에 `@@@criteria` 생성을 요구하고 README 내용 기준까지 검증 | 중간 | 파일 존재만으로 성공 처리될 수 있음 |

## 7. 수정 제안

1. `_build_iteration_prompt()`에 `[ACCEPTANCE_CRITERIA]` 블록을 항상 포함한다.
   - 예: `file_exists README.md`가 미충족이면 `다음 ACTION에서 README.md를 생성하거나 그 이유를 명확히 보고하라`를 포함.
2. `_probe_criteria()` 결과가 `file_exists` 미충족이고 최근 액션이 모두 조회성 shell이면 다음 iteration에 강한 `[GOAL_GATE]` 또는 `[REFINE_TARGETS]`를 즉시 주입한다.
3. `AgentActionDispatcher.dispatch()`에서 액션 텍스트가 비어 있지 않은데 파싱 결과가 없으면 실패 결과를 반환한다.
   - 예: `ActionResult(kind="code", target="dispatcher", success=False, detail="파싱 가능한 ACTION 없음 ...")`
4. `/agents` 실행 중에는 `TokenManager.MAX_MESSAGES_TO_KEEP`가 1처럼 낮아도 최소 안전 하한을 적용하거나, agent loop의 `session.agent_history`는 provider 일반 대화 trim 설정과 분리한다.
5. `_build_initial_prompt()`에서 `@@@criteria` 블록 생성을 요청해 내용 기준을 보강한다.

## 8. 검증 계획

- 단위 테스트:
  - 목표 `README.md 파일을 생성해줘`에서 첫 iteration 프롬프트가 `[ACCEPTANCE_CRITERIA] README.md`를 포함하는지 확인.
  - `file_exists README.md` 미충족 + 최근 액션이 `find/cat`뿐이면 다음 프롬프트가 파일 생성 전환 지시를 포함하는지 확인.
  - malformed action `sh\ncat README.md`가 “실행된 액션 없음”이 아니라 dispatcher 실패로 기록되는지 확인.
  - `MAX_MESSAGES_TO_KEEP=1` 환경에서도 `/agents`의 필수 목표/기준/최근 관찰이 보존되는지 확인.
- 통합 테스트:
  - fake assistant가 초기에 탐색 명령을 2회 반복한 뒤, 미충족 기준 피드백을 보고 `@@@filename:README.md`를 생성하는 시나리오.
  - 최종 `stop_reason=done`, 생성/수정 파일에 `README.md` 포함.

## 9. 현재 결론

이번 현상은 단일 파서 오류라기보다 `/agents`의 목표 기준 피드백 루프가 신규 파일 생성 작업에 충분히 강하게 작동하지 않는 복합 문제로 판단된다.

가장 직접적인 결함은 `README.md` 존재 기준을 추출해 놓고도 매 iteration의 실행 프롬프트에 권위 기준으로 항상 노출하지 않는 점이다. 여기에 낮은 history 보존 설정(`MAX_MESSAGES_TO_KEEP=1`), 조회 명령 성공을 실제 산출물 진전과 구분하지 못하는 정체 판정, malformed ACTION 무시가 결합되어 파일 생성 없이 `goal_not_met`으로 종료된다.

