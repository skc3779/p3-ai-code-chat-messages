Gemini의 Vertex ai api를 이용하여 복잡한 작업에 대해 AI가 스스로 계획(Plan)을 세우고 단계별로 수행하는 에이전트를 구현하기 위한 FSD 기술문서를 작성해줘. 
에이전트의 기능은 아래와 같습니다. 
- 단순히 한 번의 질문에 한 번의 답을 내놓는 '제로샷(Zero-shot)' 방식이 아니라, AI가 **추론(Reasoning) -> 실행(Action) -> 관찰(Observation) -> 수정(Refinement)**의 사이클을 반복하며 스스로 문제를 해결해 나가는 방식입니다.
- 이 과정에 사용되는 핵심 기술/전략
    - CoT (Chain of Thought): 문제를 해결하기 위해 단계별로 생각을 나열하는 기법입니다. "테트리스를 만들려면 먼저 보드를 정의하고, 블록 모양을 만들고..." 식으로 계획을 세우는 단계가 이에 해당합니다.
    - ReAct (Reason + Act): "생각"과 "행동"을 결합한 구조입니다.
        - Reason: "현재 블록 회전 로직이 빠졌으니 보충해야겠다."
        - Act: 코드를 작성하거나 수정함.
    - Self-Correction (자기 수정): 코드를 실행해보고 에러가 나면 그 에러 내용을 다시 프롬프트로 넣어 해결책을 찾는 과정입니다.
- 자기 성찰 및 반복 개선 (Self-Reflection & Iterative Refinement) 
    - 작성한 코드가 올바른지 스스로 검토하거나, 실행 중 발생한 오류 메시지를 보고 AI가 다시 모델에게 "이 부분에서 에러가 났으니 수정해줘"라고 요청하는 과정을 반복적으로 수행합니다.
- 사용자가 던진 "python으로 테트리스 작성해줘"라는 막연한 목표를 달성하기 위해, **자율 에이전트(Autonomous Agent)**를 활용하여 **루프(Loop)**를 돌며 결과물을 고도화하는 **'에이전트 기반 코드 생성 프로세스'**라고 이해하시면 된다.
- 진행 과정중에 사용자가 개입하여 피드백을 주면, 에이전트는 이를 반영하여 수정하고 다시 실행하는 과정을 반복한다.
- 결과 도출과정을 사용자에게 투명하게 보여주며, 사용자가 원하면 언제든지 개입하여 피드백을 줄 수 있도록 한다.
- `/agents` 명령을 입력하면 에이전트가 실행되고, `/agents stop` 명령을 입력하면 에이전트가 중지된다.
- `/agents` 시 현재의 multiline 형식으로 입력받는다.
- `/agents` 명령은 1단계로 gemini-ai-chat-code.py 소스 코드에 반영하고자 한다.
- 요구사항을 너가 충분히 검토하고 깊게 생각해서 정리한 후 추가로 궁금한 사항이 있으면 나에게 물어보고 최종 결과를 docs/reqs 폴더에 FSD v1.0.082 문서로 작성한다.

---

요구사항 이해 요약
핵심 기능

/agents → multiline 입력으로 목표 수신 → 에이전트 루프 시작
루프 = Plan(CoT) → Reason → Act(코드 작성/실행/파일 저장/쉘) → Observe(결과 관찰) → Reflect(자기검토) → Refine(수정) 반복
/agents stop 으로 중단, 사용자 피드백 개입 가능
1단계: gemini-ai-chat-code.py만 반영 (Vertex AI API 사용)
기존 자산 재사용 가능

GeminiCodeAssistant.chat() (이미 Vertex AI endpoint 사용 중)
CodeExecutor / TerminalExecutor / FileManager.write_file / ResponseParser.parse_and_save
CLIInputHandler.get_multiline()
ContextProcessor의 재시도 패턴

---

 확인이 필요한 사항 (11개)
A. API / 아키텍처
Vertex AI 접근 방식: 현재 GeminiCodeAssistant는 이미 aiplatform.googleapis.com REST endpoint + API key를 사용 중입니다. 에이전트도 기존 GeminiCodeAssistant.chat()을 그대로 재사용하면 될까요? 아니면 Vertex AI SDK(google-cloud-aiplatform) + 서비스 계정으로 별도 클라이언트를 새로 만들까요?

에이전트 로직 배치 위치: src/agent_runner.py 같은 신규 모듈로 분리하고 gemini-ai-chat-code.py에서는 호출만 할까요, 아니면 엔트리 포인트 파일에 모두 인라인으로 넣을까요? (기존 ContextProcessor 스타일을 따르면 전자가 자연스럽습니다.)

B. 루프 종료 조건
루프 종료 조건 우선순위: 다음 중 어느 것을 기본 종료 조건으로 삼을까요? (복수 가능)

(a) AI가 [AGENT_DONE] 같은 종료 토큰 출력
(b) 최대 반복 횟수 도달 (env AGENT_MAX_ITERATIONS, 기본 10?)
(c) 코드 실행이 에러 없이 성공
(d) 사용자가 /agents stop 또는 Ctrl+C 입력
Self-Correction 최대 횟수: 코드 실행 실패 시 동일 이슈에 대해 몇 회까지 자동 수정 시도 후 포기할까요? (예: 3회)

C. 액션 권한 (안전)
에이전트가 자율 수행할 액션 범위: 다음 중 허용 범위는?

✅ 파일 쓰기 (write_file)
✅ Python/JS/Bash 코드 실행 (CodeExecutor, 임시파일, 30초 timeout)
❓ 쉘 명령 실행 (TerminalExecutor) — 허용 시 --safe 모드만? /shell! 같은 위험 명령도?
❓ 파일 삭제/이동
파일 저장 확인 여부: 매 iteration마다 파일을 저장할 때 사용자 확인을 받을까요, 자동 저장할까요? (기존 /auto_context는 자동 저장)

D. 사용자 개입 UX
피드백 개입 시점: 다음 중 어느 모델을 선호하시나요?

(i) 턴 사이 프롬프트 모델 (권장): 매 iteration 끝에 "계속 / 피드백 입력 / 중단" 선택지 제공. 피드백 입력 시 다음 iteration의 프롬프트에 주입.
(ii) Ctrl+C 일시정지 모델: 루프 중 Ctrl+C → 피드백 입력 → resume (구현 복잡)
(iii) 턴 사이 기본 자동 진행, 사용자가 "interrupt" 단축키 입력 시에만 프롬프트
진행 상황 표시 수준:

(a) 모든 Reason/Act/Observe 전문 스트리밍 출력
(b) 요약 + 선택적 확장 ([+] show reasoning)
(c) 단계 제목만 (🧠 Reason / 🔨 Act / 👁 Observe) + 코드/결과
E. 상태 관리
에이전트 대화 히스토리 관리: 에이전트 루프 내 Reason/Act/Observe 메시지를

(a) 기존 assistant.conversation_history에 누적 (토큰 폭주 우려)
(b) 별도 agent_history 리스트로 격리하고 루프 종료 후 요약본만 메인 히스토리에 추가
(c) 매 루프 시 전체 히스토리를 Agent 전용 시스템 프롬프트로 요약해 주입
세션 재개/저장: 루프 도중 중단된 에이전트 상태(plan, 현재 step, 중간 결과)를 JSON으로 저장해 재개할 필요가 있나요? 아니면 1단계에선 "stop = 폐기"?

F. 문서/버전
FSD 버전 번호 확인:
이미 docs/specs/releases/RELEASE_v1.0.082.md(api_logger 관련)가 존재합니다.
docs/reqs 폴더는 없습니다. 실제 FSD 경로는 docs/specs/requirements/입니다.
(a) 요청대로 docs/specs/requirements/FSD_v1.0.082_agents-autonomous-loop.md 로 생성 (릴리스 문서와는 별개)
(b) 다른 번호(예: v1.0.083)로 생성
어느 쪽으로 할까요?
위 11개 중 답변하기 어려운 항목이 있으면 "A번은 기본값으로 가자" 같이 말씀해주셔도 좋습니다. 제 제안 기본값은:

1→재사용, 2→src/agent_runner.py, 3→(a)+(b)+(d), 4→3회, 5→파일쓰기+코드실행만(쉘/삭제 제외), 6→자동저장, 7→(i), 8→(c), 9→(b), 10→폐기, 11→(a)

---

A. API / 아키텍처
1. 그대로 재사용 (claude-ai-chat-code.py,gen-ai-chat-code.py 로 최종 결과물을 바탕으로 확장 예정임)
2. src/agent_runner.py 같은 신규 모듈로 분리하고 gemini-ai-chat-code.py에서는 호출

B. 루프 종료 조건
3. 모두 사용
(a) AI가 [AGENT_DONE] 같은 종료 토큰 출력 -> AI가 답변하도록 질문으로 유도해야됨(?).
(b) 최대 반복 횟수 도달 (env AGENT_MAX_ITERATIONS, 기본 10?)
(d) 사용자가 /agents stop 또는 Ctrl+C 입력
Self-Correction 최대 횟수: 코드 실행 실패 시 동일 이슈에 대해 3회까지 자동 수정 시도 후 포기\

C. 액션 권한 (안전)
5. 에이전트가 자율 수행할 액션 범위
✅ 파일 쓰기 (write_file)
✅ Python/JS/Bash 코드 실행 (CodeExecutor, 임시파일, 30초 timeout)
❓ 쉘 명령 실행 (TerminalExecutor) — 허용 시 --safe 허용 /shell! 같은 위험 명령도은 사용자에게 사용 요청 단건 승인과 이후 자동승인 제공
❓ 파일 삭제/이동 (사용자에게 사용 요청 단건 승인과 이후 자동승인 제공)
6. 자동 저장

D. 사용자 개입 UX
7. (i) 턴 사이 프롬프트 모델 (권장): 매 iteration 끝에 "계속 / 피드백 입력 / 중단" 선택지 제공. 피드백 입력 시 다음 iteration의 프롬프트에 주입.
8. (c) 단계 제목만 (🧠 Reason / 🔨 Act / 👁 Observe) + 코드/결과

E. 상태 관리
9. (b) 별도 agent_history 리스트로 격리하고 루프 종료 후 요약본만 메인 히스토리에 추가
10. 1단계에선 "stop = 폐기"

F. 문서/버전
11. (b) 다른 번호(예: v1.0.083)로 생성


---

## 📄 작성된 문서 요약

위치: docs/specs/requirements/FSD_v1.0.083_agents-autonomous-loop.md (요청하신 docs/reqs 는 존재하지 않아 기존 FSD 저장소로 변경)

### 핵심 설계

- 신규 모듈 src/agent_runner.py — AgentRunner / AgentSession / IterationRecord / ActionResult / AgentStopReason
- Provider 독립 — assistant.chat() 인터페이스만 요구 → 2단계 Claude/GenAI 확장 용이
- 루프 구조 PLAN(CoT) → [Reason/Act/Observe] × N → 요약 append
- 종료 3-way [AGENT_DONE] / AGENT_MAX_ITERATIONS=10 / Ctrl+C
- Self-Correction 코드 실패 시 최대 3회 자동 수정
- 액션 3종 ```filename: 자동저장, ```lang 자동실행, $ cmd 쉘 (위험 명령은 y/N/A 단건·세션 승인)
- 턴 사이 프롬프트 [c]ontinue / [f]eedback / [s]top
- 히스토리 격리 agent_history 별도 누적 → 종료 시 요약 1쌍만 메인 conversation_history 에 append
- 17개 FR + 6개 NFR, 15개 테스트 시나리오, Mermaid 시퀀스 다이어그램, 5개 출력 예시를 포함합니다.


---

📝 추가된 내용 요약
섹션	추가/변경
2.1.1 (신규)	호출 형식 2가지 비교표 + 동작 철학(/context 와 동일, /auto_context 1-by-1 아님)
2.2	ContextBuilder.build_context(), FilePatternMatcher 재사용 자산 추가
3.1 요구사항	FR-083-018 ~ FR-083-023 (6개) 신규 추가 — 패턴 파싱 규칙, 멀티라인 강제, [FILE_CONTEXT] 주입, 0개 매칭 처리, 동일 루프 원칙
4.1.1 / 4.1.2	AgentSession 에 file_patterns/matched_files 필드, run() 시그니처에 file_patterns 파라미터, 사전 매칭 검사 로직
4.1.4 → 4.1.4 & 4.1.4.1	_build_initial_prompt() 와 _build_iteration_prompt() 분리 — 전자는 [FILE_CONTEXT] 전문, 후자는 [FILE_CONTEXT_REF] 요약만 (토큰 절약)
4.2	엔트리 포인트 코드에 [p1, p2] / 공백 구분 / 단일 패턴 3가지 파서 + 사용 예시 5줄 표
4.3	/help 사용법을 /agents [pattern | [p1, p2, ...] | stop] 로 갱신
5.1 / 5.2	전체 플로우 및 시퀀스 다이어그램에 pattern 분기 추가
7.6 / 7.7 (신규)	실전 리팩토링 에이전트 예시, 0개 매칭 에러 예시
8 테스트	T-16 ~ T-22 (7개) 신규 추가
10 이슈	#9 토큰 한도 초과, #10 /auto_context 와의 차이 — 2건 추가


```powershell
python -c "import ast; ast.parse(open('src/agent_runner.py', encoding='utf-8').read()); print('agent_runner.py OK')" && python -c "import ast; ast.parse(open('gemini-ai-chat-code.py', encoding='utf-8').read()); print('gemini-ai-chat-code.py OK')" && python -c "import ast; ast.parse(open('src/command_registry.py', encoding='utf-8').read()); print('command_registry.py OK')" && python -c "import ast; ast.parse(open('src/__init__.py', encoding='utf-8').read()); print('__init__.py OK')"

python -c "from src.agent_runner import AgentRunner, AgentSession, AgentStopReason, IterationRecord, ActionResult; print('imports OK')"

```

```markdown
    🧠 Reason (correct 1)
    ────────────────────────────────────────────────────────────
    이전 단계에서 Bash 쉘 스크립트 실행 환경이 Windows 시스템에서 제대로 동작하지 않아 오류가 발생했습니다. 따라서 OS에 독립적인 Python 스크립트를 사용하여 파일이 올바른 파일명(`2026년*.md` 패턴)으로 생성되었는지 확인하고, 그 내용을 출력하여 올바르게 작성되었는지 검증하겠습니다.

    🔨 Act (correct 1)
    ────────────────────────────────────────────────────────────
    ```python
    import glob
    import os

    # 2026년으로 시작하는 md 파일 찾기
    files = glob.glob("2026년*.md")

    if files:
        for file in files:
            print(f"--- Found File: {file} ---")
            # 파일 크기 확인
            size = os.path.getsize(file)
            print(f"Size: {size} bytes\n")

            # 파일 내용 출력
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                print(content)
            print("-" * 40)
    else:
        print("No files matching '2026년*.md' found.")
    ```

    ⚙️  코드 실행 (python)...

    👁 Observe #4
    ────────────────────────────────────────────────────────────
    ❌ 코드 실행 (bash)
    returncode=127
    /bin/bash: C:UsersPublicDocumentsESTsoftCreatorTemptmp5ll564_f.sh: No such file or directory
    ✅ 코드 실행 (python)
    ```
```

---


## 후속 작업 (2단계)

| 단계 | 내용 | 별도 FSD |
|---|---|---|
| 1 | `claude-ai-chat-code.py`, `gen-ai-chat-code.py` 에 동일 `/agents` 분기 복제 | FSD v1.0.085 예정 |
| 2 | 세션 상태 JSON 직렬화 + `/agents resume` | FSD v1.0.086 예정 |
| 3 | 비동기 `/agents stop` (루프 중 입력 수신) | FSD v1.0.087 예정 |

`후속 작업 (2단계)` 에서 각 단계를 구현하기 전에 문제점 사전 분석을 위한 docs/reqs 폴더에 각각의 FSD 문서를 작성한다.

---

Let me first examine the existing codebase structure and relevant files to understand the current implementation before drafting the FSD documents.

Listed directory p3-ai-code-chat-messages
Listed directory requirements
Viewed FSD_v1.0.083_agents-autonomous-loop.md:1-800
Viewed FSD_v1.0.083_agents-autonomous-loop.md:800-1112
Viewed agent_runner.py:1-674
Viewed gemini-ai-chat-code.py:1-676

Now let me look at the Claude and GenAI entrypoints, and the prompt_agents.md for more context:

Viewed claude-ai-chat-code.py:1-749
Viewed gen-ai-chat-code.py:1-776
Viewed prompt_agents.md:1-221

Now let me also check the Assistant classes to understand the API interface differences:

Searched for "class ClaudeCodeAssistant"
Searched for "class GenAICodeAssistant"
Searched for "def chat"
Viewed claude_assistant.py:1-539
Viewed genai_assistant.py:1-463
Viewed gemini_assistant.py:1-382

Now I have a thorough understanding of the codebase. Let me create the three FSD documents. Note that the FSD numbers in `prompt_agents.md` are v1.0.085/086/087, but `FSD_v1.0.083` already mentions v1.0.084/085/086 in its section 11. I'll follow the numbers from the user's prompt_agents.md (v1.0.085, v1.0.086, v1.0.087).

Created FSD_v1.0.085_agents-multi-provider-replication.md
Created FSD_v1.0.086_agents-session-serialization-resume.md
Created FSD_v1.0.087_agents-async-stop.md

세 개의 FSD 문서가 모두 작성되었습니다. 각 문서의 핵심 내용을 요약합니다:

---

## 📄 작성된 FSD 문서 요약

### 1. [FSD v1.0.085](file:///c:/03_sources/skc3779_srcs/p3-ai-code-chat-messages/docs/specs/requirements/FSD_v1.0.085_agents-multi-provider-replication.md) — `/agents` 멀티 Provider 분기 복제

**핵심 문제점 7건 식별:**

| 우선순위 | 문제 | 내용 |
|---|---|---|
| 🔴 P1 | GenAI 히스토리 비호환 | `List[str]` vs `List[Dict]` — AgentRunner 와 타입 불일치 |
| 🟡 P2 | Claude role 명 차이 | `"model"` vs `"assistant"` — 에이전트 요약 append 시 |
| 🟡 P3 | Claude Tool Use 충돌 | 에이전트 루프 중 재귀 호출 발생 가능 |
| 🟢 P4 | 엔트리 포인트 코드 중복 | `agents_command.py` 공용 함수 추출 권장 |
| 🟡 P5 | GenAI `chat()` 히스토리 방식 | P1과 연동 |

---

### 2. [FSD v1.0.086](file:///c:/03_sources/skc3779_srcs/p3-ai-code-chat-messages/docs/specs/requirements/FSD_v1.0.086_agents-session-serialization-resume.md) — 세션 상태 JSON 직렬화 + `/agents resume`

**핵심 문제점 9건 식별:**

| 우선순위 | 문제 | 내용 |
|---|---|---|
| 🔴 P1 | 중첩 dataclass 직렬화 | `IterationRecord` → `ActionResult` 재귀 변환 필요 |
| 🔴 P2 | Enum 역직렬화 | `AgentStopReason` 문자열 ↔ Enum 왕복 |
| 🟡 P3 | `agent_history` 파일 크기 | 수백 KB ~ 수 MB 가능 |
| 🟡 P4 | Resume 시 파일 상태 불일치 | 저장 이후 파일 변경/삭제 감지 |
| 🟡 P5 | 루프 재개 위치 | `run()` 에 `resume_session` 파라미터 추가 필요 |

---

### 3. [FSD v1.0.087](file:///c:/03_sources/skc3779_srcs/p3-ai-code-chat-messages/docs/specs/requirements/FSD_v1.0.087_agents-async-stop.md) — 비동기 `/agents stop`

**핵심 문제점 7건 식별:**

| 우선순위 | 문제 | 내용 |
|---|---|---|
| 🔴 P1 | 비동기 입력 수신 방식 | 5가지 방안 비교 (리스너 스레드 권장) |
| 🔴 P2 | 스레드 안전성 | `conversation_history` 임시 교체 중 경합 |
| 🟡 P3 | Windows `msvcrt` 호환성 | Git Bash / WSL 환경 fallback 필요 |
| 🟡 P4 | 스트리밍 중 화면 깨짐 | 입력 에코 비활성화 또는 분리 라인 안내 |
| 🟡 P5 | `_ask_continue()` 와의 stdin 경합 | 리스너 일시 정지 전략 |

---

위 요구 문서를 구현하고, 테스트 코드 작성하고, 완료 시 docs/specs/releases 폴더에 RELEASE 로 시작하는 문서를 작성해줘.



당신은 자율 코딩 에이전트입니다. 주어진 상위 목표를 달성하기 위해\n스스로 계획을 세우고 단계별로 실행합니다.\n\n[응답 형식 — 반드시 준수]\n첫 번째 응답(계획 수립)은 번호 매긴 목록으로 전체 PLAN 을 나열하세요.\n이후 매 반복(iteration) 응답은 다음 세 블록을 순서대로 포함해야 합니다.\n\n[REASON]\n현재 상태를 분석하고 이번 단계에서 무엇을 할지 논리적으로 서술\n(바로 직전 [OBSERVE] 결과를 반드시 참조)\n\n[ACT]\n이번 단계에서 수행할 구체적 행동:\n- 파일 생성/수정:  ```filename:<경로>   ...   ```   블록\n- 코드 실행:       ```python / ```bash / ```javascript 블록 (파일명 없음 → 임시 실행)\n- 쉘 명령 실행:    라인 시작에 `$ <명령>` (한 줄에 한 명령)\n\n[OBSERVE]\n위 ACT 를 실행했을 때 기대되는 결과를 간단히 서술\n(실제 실행 결과는 시스템이 다음 프롬프트에 주입합니다)\n\n[완료 판정]\n목표를 완전히 달성했다고 판단되면 응답 맨 끝에 정확히 다음 한 줄을 추가:\n  [AGENT_DONE]\n\n[Self-Correction]\n[OBSERVE] 또는 시스템이 제공한 실행 결과에 오류가 포함된 경우,\n다음 [REASON] 에서 원인을 진단하고 [ACT] 에서 수정 버전을 제시하세요.\n\n[주의]\n- 코드 블록 밖에서 장황하게 설명하지 마세요.\n- 한 iteration 에서 너무 많은 파일/명령을 시도하지 말고 1~3 개로 쪼개세요.\n- 위험 명령(rm, mv, del, move 등)은 반드시 필요한 경우에만 사용하세요. 사용자가 거부할 수 있습니다.\n- 실행 전 중요한 파일은 git commit 으로 백업되어 있다고 가정하세요.\n"


---

`agents` 의 시스템 프롬프트에도 `_get_os_shell_hint()` 를 호출하여 현재 OS 에 맞는 쉘 힌트를 포함하도록 FSD 문서를 작성해줘.
- `claude-ai-chat-code.py`, `gen-ai-chat-code.py`, `gemini-ai-chat-code.py` 의 `_get_os_shell_hint()` 함수를 참고해줘.
- docs/specs/requirements 폴더에 FSD v1.0.088_agents-os-shell-hint.md 로 작성해줘.

---

`FSD v1.0.100 — 에이전트 Bypass Approvals (사용자 개입 없는 자율 실행 모드)` 일 때 적용된 기능에 파일 overwrite 를 사용자에게 물어보지 말고 바로 덮어쓰기 기능을 반영해 주는 FSD 문서를 작성해줘.
- `/agents` 모드가 `Bypass Approvals` 일 때만 적용한다.
- docs/specs/requirements 폴더에 FSD v1.0.103 문서로 작성한다.


---

FSD 문서를 구현하고 문서내 `13. 승인` 올바르게 처리해줘

---


`terminal_executor.py` 의 `_execute_command_safely()` 함수에서 `get_os_shell_hint()` 함수를 호출하여 `system_prompt` 에 현재 OS 에 맞는 쉘 힌트를 포함하도록 해줘. 
- 이 기능을 구현하기 위한 FSD 문서를 docs/specs/requirements 폴더에 FSD v1.0.104_terminal-executor-os-shell-hint.md 로 작성해줘.

---

`terminal_executor.py` 를 아래 조건에 맞게 개선해줘.
- 현재 실행 쉘이 Windows 환경일 때와 Linux/Mac 환경일 때를 확인하는 함수를 만들고 결과 값을 반환해줘.
  - 확인한 결과는 "Windows PowerShell", "Windows CMD", "Linux", "Mac" 으로 반환해줘.
- DANGEROUS_COMMANDS 를 "Windows PowerShell" , "Windows CMD", "Linux", "Mac" 환경에 꼭 필요한 것만 정리해줘.
- 명령어 검증은 DANGEROUS_COMMANDS 경우만 사용하고, ALLOWED_COMMANDS, ALLOWED_POWERSHELL_CMDLETS 는 제거해줘.
- shell_help를 "Windows PowerShell" , "Windows CMD", "Linux", "Mac" 환경에 맞게 정리해줘.
- docs/specs/releases 폴더에 완료 시 RELEASE v1.0.105 문서로 정리해줘.
- `terminal_executor.py` 참조 파일 목록
  ```
  claude-ai-chat-code.py
  gemini-ai-chat-code.py
  gen-ai-chat-code.py
  test_bypass_approvals.py
  agent_runner.py
  ```

---

`agent_runner.py` 의 _build_system_prompt() 의 시스템 명령을 AI 모델이 이해 못하고 잘못된 응답을 하는 경우가 있어서, 시스템 명령을 좀 더 구체적이고 명확하게 작성하는 FSD 문서를 작성해줘.
- src/agent_*.py, src/os_utils.py, src/terminal_executor.py, src/code_executor.py 를 중점으로 참고한다. 
- [ACT] 의 `코드 실행`과 `쉘 명령 실행`를 구분하여 명확하게 답변을 하지 못하는 경우가 발생한다.
  - 예시 "```powershell\n  $ <명령>\n ```\n" 와 `코드 실행`과 `쉘 명령 실행`를 함께 사용하는 경우가 많음.
  - `코드 실행`과 `쉘 명령 실행`이 정상적으로 실행되지 않는 경우가 발생함. 
- `/agents`를 위한 시스템 명령에 AI 모델이 이해하기 쉬운 구체적인 지침과 예를 작성한다.
- "터미널 명령어 실행 - 안전한 쉘 명령 실행 환경" 의 내용을 `/agents`를 위한 시스템 명령에 포함하여 AI 모델이 정확하게 쉘 명령어를 사용할 수 있도록 한다.
- 현재의 시스템 명령의 `코드 실행`과 `쉘 명령 실행`에 대한 깊게 생각하고 AI 모델이 이해하기 쉬운 구체적인 지침과 예를 포함하여 수정하는 FSD 문서를 작성해줘.
- `[ACT]` 블록에 올바른 처리를 위해 `agent_runner.py` 에 대한 다양한 케이스의 단위 테스트 코드를 작성해줘.
- `코드 실행`과 `쉘 명령 실행` 관련하여 기존 연관 소스코드 개선이 필요하면 깊게 생각하고 같이 반영하여 작성해줘.
- 만일 `코드 실행`과 `쉘 명령 실행`를 AI 모델이 구분하지 못하는 경우를 해결하기 위한 더 좋은 개선안이 있으면 적극적으로 제안하고 반영해줘.
    - AI 모델 시스템 명령 및 소스코드 개선 모두를 포함 한다.
- docs/specs/requirements 폴더에 FSD v1.0.107 로 작성해줘.

---

[ACT] 의 `코드 실행`과 `쉘 명령 실행`를 구분하여 명확하게 응답하지 못하더라도, 아래와 같이 판단하여 처리 될 수 있도록 개선해줘.


---

## 참고자료 `/agent` 의 기능구현 FSD
docs/requirements/FSD_v1.0.083_agents-autonomous-loop.md 
docs/requirements/FSD_v1.0.085_agents-multi-provider-replication.md 
docs/requirements/FSD_v1.0.086_agents-session-serialization-resume.md 
docs/requirements/FSD_v1.0.087_agents-async-stop.md 
docs/requirements/FSD_v1.0.088_agents-os-shell-hint.md 
docs/requirements/FSD_v1.0.100_agents-bypass-approvals.md 
docs/requirements/FSD_v1.0.101_agents-max-iterations-and-resume-index.md

## 참고자료 `/agent` 의 기능구현 FSD 정리 문서
docs/reports/REP_v1.1.032_agents-feature-analysis.md

위 FSD 파일들과 정리 문서는 현재 시스템에 구현된 `/agent` 의 기능에 대한 문서입니다. 

## 현재 구현된 `/agent` 명령어 목록

| 명령어 | 설명 | 사용법 | 예시 / 대상 |
| :--- | :--- | :--- | :--- |
| **`/agents`** | 자율 에이전트 루프 실행<br>(목표 멀티라인, 루프 중 's' 키 또는 Ctrl+C 로 중단) | `/agents [-ba\|--bypassApprovals] [-s <N>] [pattern \| [p1,p2,...] \| stop]` | `[src/*.py, docs/*.md]` |
| **`/agents resume`** | 마지막(또는 지정 인덱스/파일) 에이전트 세션 복원 | `/agents resume [N \| filename]` | `agent_20260421_123045_tetris.json` 또는 `2` |
| **`/agents list`** | 저장된 에이전트 세션 목록 표시 | `/agents list` | - |


## 요구사항

현재 시스템에 구현된 `/agent`는 기능이 완벽하지 않습니다.
목표를 주어 주면 반복적(loop)으로 작업을 수행하여 최종 목표(`goal`)를 달성하는 자율 에이전트 시스템을 구현하고자 합니다.

- Goal (목적지): 에이전트가 도달해야 하는 명확하고 **검증 가능한 종료 상태(Verifiable end state)**입니다.
  - 특징: 이전 턴(Turn)의 작업이 끝나자마자 다음 턴을 즉시 시작합니다. 평가자가 목표 달성을 확인하기 전까지 멈추지 않습니다.
  # 용도: AI가 코드를 직접 뜯어고쳐야 하는 내부 통제권이 있는 작업
  - 즉, "무엇이 달성되면 이 작업이 끝나는가?"를 정의합니다.
  - 단, `goal` 자체를 해석하고 판단하는 과정은 AI의 판단에 맡깁니다.

- `Goal` 의 특징과 용도를 참고하여 기존 소스코드의 문제점을 개선해 주시기 주세요.
- 그외 개선사항
    - 다음과 같은 **목표**를 제시하는 경우 테스트 코드 정상체크, 보고서 작성 누락하는 경우가 발생한다.
    - 소스 코드가 너무 단순하고 몇개의 소스로만 구현이 된다. 
    ```
    공학용 계산기 프로그램을 python 으로 구현하는데 구현전 TDD 목록을 작성하고 해당 목록에 맞게 구현후 모든 기능이 완료되면 모든 테스트 코드가 정상적으로 통과하는지 검증하고 모두 완료되면 완료 보고서를 작성해줘.
    ```
    - 아래와 같은 **목표**를 제시하는 경우 소스코드 개선 미비, 테스트 코드 정상체크, 보고서 작성 누락하는 경우가 발생한다.
    ```
    API 서버와 앱 서버를 연동해서 ABC 소스에 기능을 수정/삭제 기능을 다음조건에 맞게 추가해줘
        - 기능 개선 완료후 테스트 코드를 작성하고 검증한다.
        - 모든 기능 개선 완료후 완료 보고서를 작성한다.
    ```
- docs/requirements 폴더에 REP + v1.1.023 문서로 작성한다.

## `Goal` 참고 링크 :
- [Goal](https://code.claude.com/docs/en/goal)

---

@docs/requirements/REP_v1.1.032_agents-goal-driven-evaluator-gate.md 
@src/agent_runner.py  

AgentRunner._build_system_prompt()에 `== 선택지 A-2. 파일 패치 (기존 파일의 부분 수정) ==\n` 와 관련하여 소스코드 개선 작업 시 시스템 프롬프트에 작성된 방식으로 동작이 잘 이루어지지 않고 있다. 예상되는 원인은 소스코드 길이가긴 파일의 경우 수정 전 소스와 LLM이 수정을 위해 생성한 코드가 일치하지 않아 패턴 이식이 안되어 수정이 불가능한 경우가 발생하게 되고, 이로인해 AGENT_MAX_ITERATIONS 횟수를 초과하는 경우가 발생한다.

- 해당 문제를 개선 할 수 있는 최적의 방법을 제안하고 개선안을 반영해줘.
- docs/requirements 폴더의REP_v1.1.032_agents-goal-driven-evaluator-gate.md 개선사항, 검증 및 테스트 케이스도 FSD 문서에 같이 포함하여 작성해줘.

---

docs/requirements/REP_v1.1.032_agents-goal-driven-evaluator-gate.md
docs/requirements/REP_v1.1.033_agents-patch-fuzzy-matching.md

- 위 두개의 문서는 현재 시스템에 구현 `/agent` 의 기능에 대한 문서입니다. 
- 아래 순번데로 처리해줘
    1. `REP_v1.1.032_agents-goal-driven-evaluator-gate.md`를 FSD문서를 검토하고 개선사항이 있으면 체크리스트 포함 문서를 개선한 다음 구현하고 모두 완료했는지 검증해줘.
    2. `REP_v1.1.033_agents-patch-fuzzy-matching.md`는 구현까지 되어 있습니다. FSD문서를 다시한번 검토하고 개선사항이 있으면 체크리스트 포함 개선하고 모두 완료했는지 검증해줘.
