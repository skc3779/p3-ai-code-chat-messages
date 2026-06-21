# REP v1.1.022 — `/agents` 기능 분석 및 개선사항 도출

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.1.031 |
| 작성일 | 2026-06-21 |
| 참조 FSD | v1.0.083, v1.0.085, v1.0.086, v1.0.087, v1.0.088, v1.0.100, v1.0.101 |
| 목적 | `/agents` 전체 기능 현황 정리 및 개선사항 도출 |

---

## 1. `/agents` 기능 전체 개요

### 1.1 개요

`/agents` 는 사용자가 제시한 **상위 목표(High-level goal)** 를 AI 가 스스로 계획 수립(PLAN) → 실행(ACT) → 관찰(OBSERVE) → 자가 수정(Self-Correction) 사이클로 반복하며 달성하는 **자율 에이전트 루프** 기능이다.

기존 `/context` (단발 질의응답) 및 `/auto_context` (파일 단위 for-loop) 와의 근본적 차이점은 **반복 실행 + 자가 수정 + Human-in-the-Loop** 이다.

---

## 2. 기능 항목별 표 정리

### 2.1 핵심 루프 기능 (FSD v1.0.083)

| 기능 ID | 기능명 | 설명 | 구현 상태 |
|---|---|---|---|
| F-01 | **PLAN 수립 (CoT)** | 첫 iteration 에서 AI 가 목표를 세분화한 번호 매긴 계획 목록 생성 | 📝 설계 완료 |
| F-02 | **ReAct 루프** | 매 iteration 을 `[REASON] → [ACT] → [OBSERVE]` 3블록으로 구조화 | 📝 설계 완료 |
| F-03 | **Self-Correction** | 코드 실행 실패(stderr/returncode≠0) 시 최대 3회 자동 수정 재시도 | 📝 설계 완료 |
| F-04 | **파일 자동 저장** | ` ```filename:<경로>` 블록 → `FileManager.write_file()` 자동 실행 | 📝 설계 완료 |
| F-05 | **코드 자동 실행** | ` ```python/bash/javascript` 블록 → `CodeExecutor` 자동 실행 | 📝 설계 완료 |
| F-06 | **쉘 명령 실행** | `$ <cmd>` 라인 → `TerminalExecutor` 실행 (위험 명령 단건 승인 포함) | 📝 설계 완료 |
| F-07 | **Human-in-the-Loop** | 매 iteration 종료 후 `[c]ontinue / [f]eedback / [s]top` 프롬프트 | 📝 설계 완료 |
| F-08 | **사용자 피드백 주입** | `f` 선택 시 멀티라인 피드백 → 다음 iteration `[USER_FEEDBACK]` 블록으로 주입 | 📝 설계 완료 |
| F-09 | **자동 종료 판정** | AI 응답에 `[AGENT_DONE]` 토큰 포함 시 정상 종료 | 📝 설계 완료 |
| F-10 | **최대 iteration 하드 상한** | `AGENT_MAX_ITERATIONS` (기본 10) 도달 시 강제 종료 | 📝 설계 완료 |
| F-11 | **히스토리 격리** | 에이전트 대화는 별도 `agent_history` 에 누적 (메인 히스토리 오염 방지) | 📝 설계 완료 |
| F-12 | **히스토리 압축** | `AGENT_COMPACT_AFTER` (기본 5) 초과 시 AI 에 요약 압축 요청 | 📝 설계 완료 |
| F-13 | **파일 컨텍스트 주입** | `/agents <pattern>` 형식으로 파일 패턴 지정 → 초기 PLAN 프롬프트에 `[FILE_CONTEXT]` 주입 | 📝 설계 완료 |
| F-14 | **위험 명령 세션 자동 승인** | `A` 선택 시 현재 에이전트 세션 한정 위험 명령 자동 승인 | 📝 설계 완료 |
| F-15 | **Ctrl+C 안전 종료** | `KeyboardInterrupt` 포착 → 요약 출력 후 정상 종료 (프로세스 전체 종료 방지) | 📝 설계 완료 |

### 2.2 멀티 Provider 지원 (FSD v1.0.085)

| 기능 ID | 기능명 | 설명 | 구현 상태 |
|---|---|---|---|
| F-16 | **Claude 엔트리 포인트 지원** | `claude-ai-chat-code.py` 에 `/agents` 분기 추가 | 📋 사전 분석 |
| F-17 | **GenAI 엔트리 포인트 지원** | `gen-ai-chat-code.py` 에 `/agents` 분기 추가 | 📋 사전 분석 |
| F-18 | **공용 함수 추출** | `src/agents_command.py` 에 `handle_agents_command()` 통합 (세 엔트리 포인트 코드 중복 제거) | 📋 사전 분석 |
| F-19 | **GenAI 히스토리 타입 통일** | `List[str]` → `List[Dict]` 로 변환하여 `AgentRunner` 타입 호환 | 📋 사전 분석 |
| F-20 | **Claude Tool Use 비활성화** | 에이전트 호출 시 Claude Tool Use 충돌 방지를 위해 `disable_tools=True` 적용 | 📋 사전 분석 |
| F-21 | **어시스턴트 역할 이름 매핑** | Gemini(`model`) vs Claude(`assistant`) role 명칭 차이 → `assistant_role` 파라미터로 흡수 | 📋 사전 분석 |

### 2.3 세션 직렬화 / 재개 (FSD v1.0.086)

| 기능 ID | 기능명 | 설명 | 구현 상태 |
|---|---|---|---|
| F-22 | **세션 JSON 직렬화** | `AgentSession` 전체를 JSON 파일로 저장 (`dataclasses.asdict()` + 커스텀 Enum encoder) | 📋 사전 분석 |
| F-23 | **세션 자동 저장** | 루프 종료 및 `KeyboardInterrupt` 발생 시 자동 저장 | 📋 사전 분석 |
| F-24 | **중간 저장 (Interval)** | `AGENT_AUTO_SAVE_INTERVAL` (기본 3) iteration 마다 중간 저장 | 📋 사전 분석 |
| F-25 | **`/agents resume`** | 가장 최근 저장 세션 복원 후 중단 지점부터 루프 재개 | 📋 사전 분석 |
| F-26 | **`/agents resume <filename>`** | 지정 세션 파일 복원 | 📋 사전 분석 |
| F-27 | **`/agents list`** | 저장된 세션 목록 (목표, 상태, iteration 수, 날짜) 출력 | 📋 사전 분석 |
| F-28 | **세션 수량 관리** | `AGENT_MAX_SAVED_SESSIONS` (기본 5) 초과 시 오래된 세션 자동 삭제 | 📋 사전 분석 |
| F-29 | **Resume 안전 초기화** | 복원 시 `auto_approve_*` 플래그 및 `bypass_approvals` 강제 초기화 | 📋 사전 분석 |

### 2.4 비동기 Stop (FSD v1.0.087)

| 기능 ID | 기능명 | 설명 | 구현 상태 |
|---|---|---|---|
| F-30 | **비동기 Stop 리스너** | 루프 실행 중 별도 daemon 스레드에서 's' 키 입력 감지 | 📋 사전 분석 |
| F-31 | **체크포인트 기반 중단** | 's' 키 감지 후 현재 작업 완료 시점(iteration 경계)에서 안전 종료 | 📋 사전 분석 |
| F-32 | **플랫폼 분기 처리** | Windows: `msvcrt.kbhit()`, Unix: `select.select()` 으로 플랫폼별 non-blocking 입력 | 📋 사전 분석 |
| F-33 | **TTY 감지 Fallback** | `sys.stdin.isatty()` 가 False 면 리스너 비활성화 → `Ctrl+C` 전용 모드 | 📋 사전 분석 |

### 2.5 OS 쉘 힌트 주입 (FSD v1.0.088)

| 기능 ID | 기능명 | 설명 | 구현 상태 |
|---|---|---|---|
| F-34 | **에이전트 시스템 프롬프트 OS 힌트** | `AgentRunner._build_system_prompt()` 에 `[실행 환경]` 섹션 추가 (Windows ↔ bash 분기) | 📋 사전 분석 |
| F-35 | **ACT 섹션 쉘 언어 분기** | Windows: `powershell`, 기타: `bash` 를 코드 블록 예시에 동적 반영 | 📋 사전 분석 |
| F-36 | **`os_utils.py` 공유 모듈** | 3개 어시스턴트 파일의 중복 `_get_os_shell_hint()` → `src/os_utils.py` 로 통합 | 📋 사전 분석 |

### 2.6 Bypass Approvals (FSD v1.0.100)

| 기능 ID | 기능명 | 설명 | 구현 상태 |
|---|---|---|---|
| F-37 | **루프 중 Bypass 진입** | `_ask_continue()` 에서 `[b]ypass` 선택 → 이후 iteration 자율 진행 | 📋 사전 분석 |
| F-38 | **시작 시 Bypass 진입** | `/agents -ba` 또는 `--bypassApprovals` 플래그로 첫 iteration 부터 자율 실행 | 📋 사전 분석 |
| F-39 | **시간 예산 안전장치 (S2)** | `AGENT_BYPASS_TIMEOUT` (기본 30분) 초과 시 강제 종료 | 📋 사전 분석 |
| F-40 | **진행 정체 탐지 (S3)** | 최근 N iteration 모두 성공 액션 0건 → `BYPASS_STAGNATION` 종료 | 📋 사전 분석 |
| F-41 | **반복 루프 탐지 (S4)** | 최근 K iteration ACT 텍스트 해시 동일 → `BYPASS_LOOP_DETECTED` 종료 | 📋 사전 분석 |
| F-42 | **위험 액션 한도 (S5)** | `AGENT_BYPASS_MAX_DANGEROUS` (기본 5) 초과 시 해당 명령 실행 전 중단 | 📋 사전 분석 |
| F-43 | **Bypass 상태 UI** | 각 iteration 헤더에 `[BYPASS i/N · elapsed HH:MM]` 경과 시간 표시 | 📋 사전 분석 |

### 2.7 Iteration 제어 / Resume 인덱스 (FSD v1.0.101)

| 기능 ID | 기능명 | 설명 | 구현 상태 |
|---|---|---|---|
| F-44 | **Iteration 즉석 오버라이드** | `/agents -s <N>` 또는 `--steps <N>` 으로 해당 실행만 `max_iterations` 변경 | ✅ 구현 완료 |
| F-45 | **Resume 숫자 인덱스** | `/agents resume 2` 처럼 `/agents list` 의 `#` 번호로 바로 재개 | ✅ 구현 완료 |
| F-46 | **플래그 조합 지원** | `-ba -s N [pattern]` 과 같이 모든 플래그 독립적 조합 가능 | ✅ 구현 완료 |
| F-47 | **`effective_max_iterations` 직렬화 제외** | 런타임 캐시 필드는 JSON 세션에 저장하지 않아 Resume 시 재설정 강제 | ✅ 구현 완료 |

---

## 3. 기능 구현 상태 요약

| 구분 | 건수 | FSD | 비고 |
|---|---|---|---|
| ✅ 구현 완료 | 4 | v1.0.101 | `-s N`, Resume 인덱스, 플래그 조합, 직렬화 제외 |
| 📝 설계 완료 (구현 대기) | 15 | v1.0.083 | 핵심 루프 전체 기능 |
| 📋 사전 분석 (구현 대기) | 28 | v1.0.085 ~ v1.0.100 | Provider 확장, 세션 저장, 비동기 stop 등 |
| **합계** | **47** | | |

---

## 4. 기능 간 의존 관계

```
[v1.0.083] 핵심 루프 (Gemini 전용)
    │
    ├──→ [v1.0.085] 멀티 Provider 확장 (Claude, GenAI)
    │        └──→ [v1.0.088] OS 쉘 힌트 (공유 모듈 추출)
    │
    ├──→ [v1.0.086] 세션 직렬화/Resume
    │        └──→ [v1.0.101] Resume 인덱스 지원 ✅
    │
    ├──→ [v1.0.087] 비동기 Stop
    │        └──→ [v1.0.100] Bypass Approvals (비동기 stop 재사용)
    │
    └──→ [v1.0.100] Bypass Approvals
             └──→ [v1.0.101] -s 플래그 조합 ✅
```

---

## 5. 개선사항 도출

### 5.1 기능 공백 / 미구현 항목

| # | 개선항목 | 출처 | 설명 | 우선순위 |
|---|---|---|---|---|
| I-01 | **멀티 Provider 구현 조속화** | FSD 085 | Gemini 전용으로 설계 완료된 루프가 Claude/GenAI 에는 미적용. 실사용자의 Provider 선택권 제한 | 🔴 높음 |
| I-02 | **세션 저장/재개 구현** | FSD 086 | `Ctrl+C` 중단 시 모든 진행이 폐기되어 장시간 에이전트 실행 시 리스크 큼 | 🔴 높음 |
| I-03 | **OS 쉘 힌트 구현** | FSD 088 | Windows 환경에서 에이전트가 bash 명령 생성 → 실행 실패 반복. 즉각 개선 필요 | 🔴 높음 |
| I-04 | **비동기 Stop 구현** | FSD 087 | 루프 실행 중 `Ctrl+C` 외 안전 중단 수단 없음. 특히 Windows에서 UX 불안 | 🟡 중간 |
| I-05 | **Bypass Approvals 구현** | FSD 100 | 장시간 자율 실행 시나리오 (밤새 리팩토링 등) 를 위한 핵심 기능 미구현 | 🟡 중간 |
| I-06 | **Token Budget 안전장치** | FSD 100 §4.6 | Bypass 모드에서 시간 예산 외 토큰 누적 비용 제어 수단 없음. `token_manager.py` 연계 필요 | 🟡 중간 |
| I-07 | **Tool Calling(함수 호출) 도입** | FSD 083 §11 | 현재 ACT 블록은 텍스트 파싱 기반 → Gemini `functionDeclarations` 로 구조화 JSON 전환 시 신뢰성 향상 | 🟢 낮음 |
| I-08 | **비동기 Feedback** | FSD 087 이슈#7 | 루프 실행 중 피드백은 `_ask_continue()` 동기 입력만 가능. 비동기 채널로는 stop/continue 만 지원 예정 | 🟢 낮음 |

### 5.2 아키텍처 / 설계 개선

| # | 개선항목 | 출처 | 설명 | 우선순위 |
|---|---|---|---|---|
| I-09 | **`conversation_history` 교체 방식 개선** | FSD 083 이슈#3, FSD 085 P2 | `_call_model()` 내에서 `assistant.conversation_history` 를 임시 교체/원복하는 방식은 재진입에 취약. `chat()` 에 `history` 파라미터를 추가하는 방안(FSD 085 방안 C) 으로 장기 리팩토링 권장 | 🟡 중간 |
| I-10 | **Per-file 패턴 모드 미지원** | FSD 083 이슈#10 | `<pattern>` 모드는 전체 파일을 한 컨텍스트로 합산. 파일별 1-by-1 처리가 필요하면 여전히 `/auto_context` 를 써야 함. `/agents --per-file <pattern>` 옵션 도입 검토 | 🟢 낮음 |
| I-11 | **asyncio 전면 전환 검토** | FSD 087 §8 | 현재 스레드 기반 비동기 I/O 는 stdin 경합 문제 내포. 장기 로드맵으로 `asyncio` + `aiohttp` 전환 설계 시작 권장 | 🟢 낮음 |
| I-12 | **Self-Correction 범위 한계** | FSD 083 이슈#7 | 직전 iteration 실패에만 발동. 여러 iteration 에 걸친 논리 오류는 사용자 피드백(`f`)에 의존. Reflexion 스타일 장기 메모리 메커니즘 검토 필요 | 🟡 중간 |

### 5.3 보안 / 안전성 개선

| # | 개선항목 | 출처 | 설명 | 우선순위 |
|---|---|---|---|---|
| I-13 | **세션 파일 보안 강화** | FSD 086 §3.9 | 현재 `agent_history` 에 코드·파일 내용·쉘 결과가 평문 JSON 으로 저장됨. `.gitignore` 추가만으로는 부족. `AGENT_SESSION_ENCRYPT=true` 선택적 암호화 검토 | 🟡 중간 |
| I-14 | **Bypass 반복 루프 탐지 고도화** | FSD 100 이슈#2 | 현재는 ACT 텍스트 완전 해시 동일만 탐지. 주석 한 줄 차이로 회피 가능. 정규화 + 편집 거리 기반 유사도 탐지로 개선 필요 | 🟢 낮음 |
| I-15 | **파일 자동 덮어쓰기 경고** | FSD 083 이슈#8 | ` ```filename:` 블록이 기존 파일을 확인 없이 덮어씀. 중요 파일 손실 우려. 시스템 프롬프트에 `git commit 후 실행 권장` 안내 필요 | 🟡 중간 |

### 5.4 UX / 사용성 개선

| # | 개선항목 | 출처 | 설명 | 우선순위 |
|---|---|---|---|---|
| I-16 | **`/agents stop` 실제 비동기 중단** | FSD 083 이슈#2 | 현재 루프 실행 중에는 메인 루프가 블로킹이므로 `/agents stop` 입력 자체가 불가. FSD 087 비동기 Stop 구현 후 해소 가능 | 🟡 중간 |
| I-17 | **Bypass Level 세분화** | FSD 100 §4.5 | 현재 Bypass 는 "전부 자동 승인(L2)" 만 설계. soft bypass(L1): 파일 변경만 자동, 위험 shell 은 여전히 확인 모드 도입 검토 | 🟢 낮음 |
| I-18 | **Resume 인덱스 안정화** | FSD 101 이슈#3 | `/agents list` 출력 후 새 세션이 저장되면 인덱스가 이동할 수 있음. 해시 기반 안정적 세션 ID 도입 검토 | 🟢 낮음 |
| I-19 | **멀티 에이전트 협업** | FSD 083 비-목표 | 단일 에이전트 설계로 고정. 병렬 iteration 및 에이전트 간 협업은 명시적 비-목표. 향후 독립 FSD 필요 | 🟢 낮음 |
| I-20 | **Bypass 전용 감사 로그** | FSD 100 §4.4 | 사용자 부재 시 실행된 모든 액션 이력 추적 수단 없음. `.agent_sessions/bypass_<ts>.log` 형태로 사람이 읽을 수 있는 감사 로그 파일 생성 필요 | 🟡 중간 |

---

## 6. 개선 우선순위 로드맵 (제안)

```
Phase 1 — 즉각 개선 (1~2 sprint)
  I-03  OS 쉘 힌트 에이전트 프롬프트 주입     ← 간단, 즉각 체감 효과
  I-01  Claude/GenAI Provider 확장 구현      ← 선행 분석 완료, 구현 진입
  I-09  conversation_history 파라미터 전달  ← Claude 확장 선제 조건

Phase 2 — 안정성 강화 (2~3 sprint)
  I-02  세션 직렬화/Resume 구현             ← 장시간 실행 안전망
  I-04  비동기 Stop 리스너 구현             ← UX 체감 개선
  I-15  파일 덮어쓰기 경고 (git backup 안내)

Phase 3 — 자율화 고도화 (3~4 sprint)
  I-05  Bypass Approvals 구현              ← I-04 완료 후 진행
  I-06  Token Budget 안전장치              ← token_manager.py 연계
  I-20  Bypass 감사 로그
  I-12  Self-Correction 범위 확장

Phase 4 — 장기 아키텍처 (별도 FSD)
  I-07  Tool Calling 도입 (functionDeclarations)
  I-11  asyncio 전면 전환
  I-19  멀티 에이전트 협업
```

---

## 7. 환경 변수 전체 현황

| 변수명 | 기본값 | 관련 FSD | 설명 |
|---|---|---|---|
| `AGENT_MAX_ITERATIONS` | 10 | 083 | 루프 최대 반복 횟수 |
| `AGENT_SELF_CORRECT_MAX` | 3 | 083 | 코드 실행 실패 시 자가 수정 최대 횟수 |
| `AGENT_COMPACT_AFTER` | 5 | 083 | `agent_history` 압축 기준 iteration 수 |
| `AGENT_CODE_TIMEOUT` | 30 | 083 | `CodeExecutor` 실행 timeout (초) |
| `AGENT_DONE_TOKEN` | `[AGENT_DONE]` | 083 | 자율 종료 신호 토큰 |
| `AGENT_MAX_SAVED_SESSIONS` | 5 | 086 | 최대 저장 세션 수 |
| `AGENT_AUTO_SAVE_INTERVAL` | 3 | 086 | N iteration 마다 중간 저장 |
| `AGENT_BYPASS_TIMEOUT` | 1800 | 100 | Bypass 진입 후 최대 경과 시간 (초) |
| `AGENT_BYPASS_STAGNATION_N` | 3 | 100 | 진행 정체 탐지 연속 무진행 한도 |
| `AGENT_BYPASS_LOOP_N` | 3 | 100 | 반복 루프 탐지 창 크기 |
| `AGENT_BYPASS_MAX_DANGEROUS` | 5 | 100 | Bypass 중 위험 shell 누적 한도 |
| `AGENT_BYPASS_DEFAULT` | false | 100 | (선택) 기본 bypass 모드 on |
| `AGENT_BYPASS_CONFIRM_PLAN` | true | 100 | (선택) Bypass 시작 전 PLAN 확인 프롬프트 |

---

## 8. 신규 파일 / 변경 파일 전체 목록 (설계 기준)

| 파일 | 유형 | 관련 FSD |
|---|---|---|
| `src/agent_runner.py` | **신규** | 083, 087, 100, 101 |
| `src/agents_command.py` | **신규** | 085, 100, 101 |
| `src/agent_session_store.py` | **신규** | 086, 101 |
| `src/agent_input_listener.py` | **신규** | 087 |
| `src/os_utils.py` | **신규** | 088 |
| `gemini-ai-chat-code.py` | 수정 | 083 |
| `claude-ai-chat-code.py` | 수정 | 085 |
| `gen-ai-chat-code.py` | 수정 | 085 |
| `src/claude_assistant.py` | 수정 | 085, 088 |
| `src/gemini_assistant.py` | 수정 | 088 |
| `src/genai_assistant.py` | 수정 | 085, 088 |
| `src/command_registry.py` | 수정 | 083, 101 |
| `tests/test_agent_runner.py` | **신규** | 083 |
| `tests/test_agents_flags.py` | **신규** | 101 |
| `.env.example` | 수정 | 083, 086 |
| `.gitignore` | 수정 | 086 |

---

*문서 작성: REP v1.1.022 / 2026-06-21*
