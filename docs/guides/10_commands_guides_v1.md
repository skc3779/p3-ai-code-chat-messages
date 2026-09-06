# AI Code Assistant — 명령어 가이드 v1

> 대상 파일: `claude-ai-chat-code.py` · `gemini-ai-chat-code.py` · `gen-ai-chat-code.py`
>
> 세 어시스턴트는 동일한 명령어 체계를 공유하며, 파일별 차이는 각 섹션 하단에 표기합니다.

---

## 목차

1. [파일 탐색](#1-파일-탐색)
2. [컨텍스트 읽기](#2-컨텍스트-읽기)
3. [에이전트 (자율 루프)](#3-에이전트-자율-루프)
4. [응답 처리](#4-응답-처리)
5. [대화 히스토리](#5-대화-히스토리)
6. [입력 모드](#6-입력-모드)
7. [시스템 명령](#7-시스템-명령)
8. [파일 감시](#8-파일-감시)
9. [설정](#9-설정)
10. [기타](#10-기타)
11. [파일별 차이점 요약](#11-파일별-차이점-요약)
12. [환경변수 레퍼런스](#12-환경변수-레퍼런스)

---

## 1. 파일 탐색

### `/files [ext...]`

작업 디렉토리의 파일 목록을 조회합니다.

| 형식 | 설명 |
|---|---|
| `/files` | 모든 파일 표시 (최대 50개 + 초과 건수) |
| `/files .py` | `.py` 파일만 표시 |
| `/files .py .js .ts` | 여러 확장자 필터 |

**출력 예시**
```
📁 파일 목록 (총 12개):
  📄 src/agent_runner.py (48.3KB, 2026-06-25 14:32)
  📄 src/cli_input.py (12.1KB, 2026-06-24 09:10)
```

**사용 사례**
- 현재 워크스페이스에 어떤 파일이 있는지 파악할 때
- 특정 확장자 파일만 골라서 목록을 확인할 때

---

### `/tree`

현재 워크스페이스의 디렉토리 트리를 출력합니다. `.gitignore` 및 내부 ignore 패턴이 반영됩니다.

```
> /tree

🌳 프로젝트 구조:
src/
  __init__.py
  agent_runner.py
  cli_input.py
docs/
  guides/
    10_commands_guides_v1.md
```

**사용 사례**
- 프로젝트 전체 구조를 빠르게 파악할 때
- AI에게 구조를 설명하기 전 직접 확인할 때

---

## 2. 컨텍스트 읽기

### `/read <pattern | [p1, p2, ...]>`

지정한 파일 패턴의 내용을 읽어 화면에 출력하고 대화 컨텍스트에 추가합니다.

| 형식 | 설명 |
|---|---|
| `/read src/agent_runner.py` | 단일 파일 |
| `/read src/*.py` | glob 패턴 |
| `/read [src/*.py, docs/*.md]` | 다중 패턴 (대괄호 구분) |

**예시**
```
> /read src/cli_input.py

# src/cli_input.py
...파일 내용...
```

```
> /read [src/*.py, docs/*.md]
```

**사용 사례**
- AI에게 특정 파일을 참고하도록 컨텍스트에 먼저 올릴 때
- 내용을 직접 확인한 뒤 질문을 이어갈 때

---

### `/context [옵션] <pattern | [p1, p2]> [질문]`

파일 컨텍스트를 포함하여 AI에게 바로 질문합니다.  
질문을 생략하면 멀티라인 입력 모드로 전환됩니다.

#### 옵션

| 옵션 | 설명 |
|---|---|
| `--large` 또는 `-l` | 대규모 컨텍스트 처리 (LargeContextProcessor 사용) |
| `-nt` | 파일 트리를 컨텍스트에서 제외 |

#### 패턴 형식

| 형식 | 예시 |
|---|---|
| 단일 glob | `src/*.py` |
| 다중 패턴 | `[src/*.py, docs/*.md]` |

**예시**
```
> /context src/*.py 이 코드를 리팩토링해줘
> /context --large src/*.py
> /context -nt [src/*.py, docs/*.md] README.md 파일을 작성해줘
> /context src/agent_runner.py
(질문 생략 시 멀티라인 입력 모드)
```

**사용 사례**
- 특정 파일 범위에 대해 즉시 AI에게 질문할 때
- 파일 컨텍스트 + 트리 구조를 함께 포함하여 리뷰 요청할 때
- `--large`로 토큰 한도를 초과하는 대형 코드베이스를 처리할 때

---

### `/auto_context [-qc] <pattern | [p1, p2]> [질문]`

매칭된 파일을 파일별로 순서대로 자동 처리합니다.  
처리 전에 매칭된 파일 목록을 보여주고 사용자 확인을 받습니다.

#### 옵션

| 옵션 | 별칭 | 설명 |
|---|---|---|
| `-qc` | `--quality-check` | 품질 검사 모드 활성화 |

#### 패턴 형식

| 형식 | 예시 |
|---|---|
| 단일 glob | `src/*.py` |
| 다중 패턴 | `[src/*.py, docs/*.md]` |

**예시**
```
> /auto_context src/*.py
> /auto_context -qc src/*.py 이 코드를 리팩토링해줘
> /auto_context [src/*.py, docs/*.md] README 작성해줘
> /auto_context original/*.md 한글로 번역해줘
```

**실행 흐름**
```
> /auto_context src/*.py 버그를 찾아줘

📂 매칭된 파일 5개:
  1. src/agent_runner.py
  2. src/cli_input.py
  ...

▶ 자동 처리를 시작하시겠습니까? (Y/n): Y
```

**사용 사례**
- 여러 파일에 동일한 작업(번역, 리뷰, 리팩토링)을 순차적으로 적용할 때
- `-qc`로 처리 결과의 품질을 자동으로 검증할 때

---

## 3. 에이전트 (자율 루프)

### `/agents [옵션] [pattern | [p1, p2, ...]]`

자율 에이전트 루프를 실행합니다. 목표를 멀티라인으로 입력하면 AI가 반복적으로 코드를 실행·수정하며 목표를 달성합니다.

#### 플래그

| 플래그 | 별칭 | 설명 |
|---|---|---|
| `-ba` | `--bypassApprovals` `--bypass-approvals` | 각 액션을 자동 승인 (확인 생략) |
| `-s N` | `--steps N` | 최대 반복 횟수 N으로 제한 (양의 정수) |
| `--policy <val>` | | 상호작용 정책 명시 설정 (`interactive` / `auto` 등) |

**정책 우선순위**: `--policy` 명시값 > `-ba`(→ auto) > 환경변수 `AGENT_INTERACTION_POLICY` > `interactive`

#### 패턴 형식

| 형식 | 예시 |
|---|---|
| 인수 없음 | `/agents` (전체 워크스페이스) |
| 단일 glob | `/agents src/*.py` |
| 다중 패턴 | `/agents [src/*.py, docs/*.md]` |

**예시**
```
> /agents
(목표 멀티라인 입력 후 /end)

> /agents src/*.py
> /agents -ba src/*.py
> /agents -s 10 src/*.py
> /agents --policy auto [src/*.py, tests/*.py]
```

**실행 흐름**
```
> /agents -ba src/*.py

🎯 목표를 입력하세요 — 컨텍스트 패턴: ['src/*.py']
> 모든 함수에 docstring을 추가하고 타입 힌트를 완성해줘
> /end

[에이전트 루프 시작...]
루프 도중: 's' 키 → 안전 중단 / Ctrl+C → 강제 중단
```

---

### `/agents stop`

현재 실행 중이 아닌 상태에서의 stop 호출 — 루프 도중에는 `s` 키 또는 `Ctrl+C`로 중단합니다.

```
> /agents stop
💡 에이전트는 현재 실행 중이 아닙니다. 루프 도중에는 's' 키(또는 Ctrl+C)로 안전하게 중단할 수 있습니다.
```

---

### `/agents list`

저장된 에이전트 세션 목록을 표시합니다.

```
> /agents list

📋 저장된 에이전트 세션:
  1. agent_20260625_143200_tetris.json   목표: 테트리스 게임 구현  (step_limit: 3 iterations)
  2. agent_20260624_091500_refactor.json 목표: 코드 리팩토링       (user_stop: 5 iterations)
```

---

### `/agents resume [N | filename]`

중단된 에이전트 세션을 복원하여 이어서 실행합니다.

| 형식 | 설명 |
|---|---|
| `/agents resume` | 가장 최근 세션 복원 |
| `/agents resume 2` | 목록에서 2번 세션 복원 |
| `/agents resume agent_20260625_143200_tetris.json` | 파일명으로 직접 지정 |

**예시**
```
> /agents resume 1

📂 세션 복원: agent_20260625_143200_tetris.json
  목표: 테트리스 게임 구현
  상태: step_limit (3 iterations 완료)
  저장된 파일 참조: src/game.py, src/board.py

[에이전트 루프 재개...]
```

**사용 사례**
- 스텝 한도(`-s N`)로 중단된 세션을 이어서 실행할 때
- Ctrl+C로 중단한 세션을 나중에 재개할 때

---

## 4. 응답 처리

### `/save`

마지막 AI 응답에서 코드 블록을 추출하여 파일로 저장합니다.

AI 응답에 `` @@@filename:path/to/file.ext `` 형식의 블록이 있어야 합니다.

```
> /save

✅ 총 3개 파일이 저장되었습니다.
```

**사용 사례**
- AI가 새 파일이나 수정된 파일을 응답한 뒤 실제로 디스크에 저장할 때

---

### `/run [lang]`

마지막 AI 응답에 포함된 코드 블록을 실행합니다.  
여러 블록이 있으면 각각 확인 후 선택적으로 실행합니다.

| 형식 | 설명 |
|---|---|
| `/run` | 기본 언어(python)로 실행 |
| `/run python` | Python으로 명시 실행 |
| `/run bash` | Bash로 명시 실행 |

**예시**
```
> /run

🔍 2개의 코드 블록을 발견했습니다.

============================================================
📌 [1] src/hello.py (python)
============================================================
   print("Hello, World!")
   ...

▶️  이 코드를 실행하시겠습니까? (y/N): y

🚀 python 코드 실행 중...
✅ 실행 성공!
📤 출력:
Hello, World!
```

**사용 사례**
- AI가 생성한 코드를 저장 없이 즉시 테스트할 때

---

### `/diff`

마지막 AI 응답의 코드 변경사항을 기존 파일과 비교하여 diff를 표시합니다.

```
> /diff

🔍 2개의 파일 변경 제안을 발견했습니다:

======================================================================
📄 [1] src/agent_runner.py
======================================================================
--- a/src/agent_runner.py
+++ b/src/agent_runner.py
@@ -10,6 +10,8 @@
+    # 새로 추가된 라인
...

💡 /apply 명령어로 변경사항을 적용할 수 있습니다.
```

**사용 사례**
- AI의 코드 수정 제안을 적용하기 전에 변경 내용을 검토할 때

---

### `/apply`

`/diff`로 확인한 코드 변경사항을 실제 파일에 적용합니다.

```
> /apply

✅ src/agent_runner.py 파일이 업데이트되었습니다.
💡 다른 변경사항이 있다면 /diff로 다시 확인하세요.
```

**사용 사례**
- `/diff` 검토 후 문제없음을 확인하고 실제 파일에 적용할 때

---

## 5. 대화 히스토리

### `/history`

현재 대화 히스토리를 출력합니다. 각 메시지를 앞 120자 미리보기로 표시합니다.

```
> /history

📜 대화 히스토리:
👤 [1]: src/*.py 파일을 리팩토링해줘...
🤖 [2]: 리팩토링을 진행하겠습니다. 다음과 같이 수정했습니다...
```

---

### `/history --remove <N>` 또는 `/history -r <N>`

히스토리 앞에서부터 N개 항목을 삭제합니다.

```
> /history --remove 5
✅ 히스토리 5개를 삭제했습니다. (남은 항목: 3개)

> /history -r 2
```

---

### `/history --delete <index>` 또는 `/history -d <index>`

지정한 인덱스(1-based)의 히스토리 항목 1개를 삭제하고 갱신된 목록을 표시합니다.

```
> /history --delete 3
✅ 히스토리 3번 항목을 삭제했습니다. (남은 항목: 4개)

> /history -d 1
```

---

### `/clear`

전체 대화 히스토리를 초기화합니다.

```
> /clear
✅ 대화 히스토리가 초기화되었습니다.
```

---

### `/save_history [filepath]`

현재 대화 히스토리를 JSON 파일로 저장합니다.

| 형식 | 설명 |
|---|---|
| `/save_history` | 자동 생성된 파일명으로 저장 (`history_YYYYMMDD_HHMMSS.json`) |
| `/save_history my_session.json` | 지정한 이름으로 저장 |

```
> /save_history
✅ 히스토리 저장됨: history_20260629_143000.json

> /save_history review_session.json
```

---

### `/load_history <filename>`

저장된 히스토리 파일을 불러와 현재 대화 컨텍스트에 적용합니다.

```
> /load_history history_20260629_143000.json
✅ 히스토리 로드됨: history_20260629_143000.json
   메시지 수: 8
```

---

### `/list_history`

저장된 히스토리 파일 목록을 표시합니다.

```
> /list_history

📋 저장된 히스토리 파일:
   - history_20260629_143000.json
   - review_session.json
```

---

## 6. 입력 모드

### `/multiline`

여러 줄 입력 모드로 전환합니다. `Esc+Enter` 또는 `/end`로 입력을 완료합니다.

```
> /multiline
(멀티라인 편집기 열림)
다음 요구사항으로 코드를 작성해줘:
1. 파일 읽기 기능
2. JSON 파싱
3. 에러 핸들링
/end
```

> **참고**: `gemini-ai-chat-code.py`에서는 일반 프롬프트에서 `/multiline`을 입력해도 동일하게 동작합니다.

**사용 사례**
- 긴 요구사항이나 코드 스니펫을 붙여넣을 때
- 여러 줄에 걸친 프롬프트를 작성할 때

---

### `/stream`

AI 응답을 스트리밍 모드(실시간 출력)로 변경합니다.

```
> /stream
✅ 스트리밍 모드로 변경되었습니다.
```

---

### `/nostream`

AI 응답을 논스트리밍 모드(전체 완료 후 출력)로 변경합니다.

```
> /nostream
✅ 논스트리밍 모드로 변경되었습니다.
```

---

## 7. 시스템 명령

### `/shell <cmd>` 및 `/shell! <cmd>`

시스템 셸 명령을 실행합니다. 실행 결과는 대화 히스토리에도 자동으로 추가됩니다.

| 명령어 | 설명 |
|---|---|
| `/shell <cmd>` | 안전 모드 — 허용 목록에 없는 위험 명령은 차단 |
| `/shell! <cmd>` | 위험 모드 — 모든 명령 허용 (이중 확인 필요) |
| `/shell --help` | 셸 실행기 도움말 표시 |
| `/shell -h` | 위와 동일 |

**예시**
```
> /shell git status
💻 명령어 실행: git status
✅ 실행 성공 (return code: 0)
📤 출력:
On branch main
...

> /shell git log --oneline -5

> /shell! rm -rf tmp/
⚠️  위험 모드: 모든 명령어가 허용됩니다.
▶️  정말 실행하시겠습니까? (y/N): y
```

**사용 사례**
- AI와 대화하면서 Git 상태 확인, 빌드, 테스트 실행 등을 인라인으로 처리할 때
- 실행 결과를 자동으로 대화 컨텍스트에 포함시킬 때

---

### `/workspace [path]`

작업 디렉토리를 변경하거나 현재 경로를 확인합니다.

| 형식 | 설명 |
|---|---|
| `/workspace` | 현재 작업 디렉토리 출력 |
| `/workspace /path/to/project` | 해당 디렉토리로 변경 |
| `/workspace ../other-project` | 상대 경로로 변경 |

```
> /workspace
📂 현재 작업 디렉토리: /mnt/c/03_sources/my-project

> /workspace ../other-project
✅ 작업 디렉토리 변경: /mnt/c/03_sources/other-project
```

**사용 사례**
- 세션 중에 다른 프로젝트로 전환할 때

---

## 8. 파일 감시

### `/watch <pattern>`

지정 패턴의 파일 변경을 감시합니다. 파일이 변경되면 자동으로 컨텍스트를 갱신합니다.

> `watchdog` 라이브러리 필요: `pip install watchdog`

```
> /watch src/*.py
✅ 파일 감시 시작: src/*.py
   현재 감시 패턴: ['src/*.py']
```

---

### `/unwatch <pattern>`

지정 패턴의 파일 감시를 중지합니다.

```
> /unwatch src/*.py
✅ 파일 감시 중지: src/*.py
```

---

### `/watch_list`

현재 감시 중인 패턴 목록과 감시 상태를 표시합니다.

```
> /watch_list

👁️  감시 중인 패턴:
   - src/*.py
   - docs/*.md
   상태: 🟢 실행 중
```

**사용 사례**
- 코드를 수정할 때마다 AI가 자동으로 변경 내용을 컨텍스트에 반영하게 할 때

---

## 9. 설정

### `/tokens [-k <number|default>]`

현재 토큰 사용량 보고서를 출력합니다. `-k` 옵션으로 메시지 보존 한도를 변경할 수 있습니다.

| 형식 | 설명 |
|---|---|
| `/tokens` | 토큰 사용 현황 보고서 출력 |
| `/tokens -k 50` | MAX_MESSAGES_TO_KEEP를 50으로 변경 |
| `/tokens -k default` | MAX_MESSAGES_TO_KEEP를 기본값으로 복원 |

```
> /tokens

📊 토큰 사용량 (Claude):
  현재 메시지 수: 12개
  예상 사용 토큰: 8,432 / 200,000
  MAX_MESSAGES_TO_KEEP: 20
  ...

> /tokens -k 30
✅ MAX_MESSAGES_TO_KEEP 이 30 로 변경되었습니다.
```

> 토큰 한도는 플랫폼마다 다릅니다:
> - Claude: `MAX_TOKENS_CLAUDE`
> - Gemini: `MAX_TOKENS_GEMINI`
> - GenAI: `MAX_TOKENS_GENAI`

---

### `/template <name>`

`.system_prompts/` 폴더의 YAML 템플릿으로 시스템 프롬프트를 변경합니다.

```
> /template code-review
✅ 시스템 프롬프트가 'code-review' 템플릿으로 변경되었습니다.

> /template translator
```

---

### `/template_list`

사용 가능한 시스템 프롬프트 템플릿 목록을 표시합니다. 현재 어시스턴트 타입에 맞는 템플릿이 자동으로 필터됩니다.

```
> /template_list

📋 사용 가능한 프롬프트 템플릿 (claude):
   - code-review [claude]: 코드 리뷰 전문가 모드
   - translator [공용]: 번역 전문가 모드
```

---

### `/template_show`

현재 적용 중인 시스템 프롬프트 템플릿 정보를 표시합니다.

```
> /template_show

📌 현재 적용 중인 템플릿:
   - name           : code-review
   - description    : 코드 리뷰 전문가 모드
   - assistant_type : claude
```

---

### `/template_reset`

시스템 프롬프트를 기본값으로 복귀합니다.

```
> /template_reset
✅ 기본 시스템 프롬프트로 복귀했습니다.
```

---

### `/llm_config <lang>` *(gen-ai-chat-code.py 전용)*

GenAI 어시스턴트의 LLM 언어별 파라미터 설정을 변경합니다.

| 형식 | 설명 |
|---|---|
| `/llm_config` | 현재 설정 표시 |
| `/llm_config Python` | Python 코드에 최적화된 파라미터 적용 |
| `/llm_config Java` | Java 코드에 최적화된 파라미터 적용 |

```
> /llm_config Python
✅ LLM 설정이 'Python' 로 적용되었습니다.
   temperature: 0.2
   top_p: 0.9
   ...

> /llm_config Java
```

---

## 10. 기타

### `/help`

명령어 도움말 메뉴를 출력합니다.

```
> /help

====================================================================================================
🤖 Claude Code Assistant - AI 코딩 어시스턴트
====================================================================================================
명령어:
  /files [ext]                      프로젝트 파일 목록 조회   예) .py .js
  /tree                             디렉토리 트리 출력
  ...
```

---

### `/quit`

프로그램을 종료합니다. `Ctrl+C`로도 종료할 수 있습니다.

```
> /quit
👋 프로그램을 종료합니다.
```

---

## 11. 파일별 차이점 요약

| 명령어 | claude-ai-chat-code.py | gemini-ai-chat-code.py | gen-ai-chat-code.py |
|---|:---:|:---:|:---:|
| `/multiline` | ✅ 명령어로 진입 | ✅ 입력 루프 상단 처리 | ✅ 명령어로 진입 |
| `/llm_config` | ❌ | ❌ | ✅ (전용) |
| `/agents` 역할 | `assistant_role="assistant"` | `assistant_role="model"` | `assistant_role="model"` |
| 토큰 플랫폼 | `MAX_TOKENS_CLAUDE` | `MAX_TOKENS_GEMINI` | `MAX_TOKENS_GENAI` |
| `/save` 파일 형식 힌트 | `` ```filename: `` | `` ```filename: `` | `@@@filename:` |
| API 설정 변수 | `ANTHROPIC_API_KEY` | `GEMINI_API_KEY` | `ENDPOINT_URL` + `YOUR_CLIENT_KEY` + `YOUR_CLIENT_SECRET` |

---

## 12. 환경변수 레퍼런스

### 공통

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `AI_VERSION` | `v1.0.040` | 배너에 표시될 버전 문자열 |
| `PRINT_BANNER` | (미설정=true) | `false`/`0`/`no`/`off` 로 배너 숨김 |
| `NO_COLOR` | (미설정) | 설정 시 ANSI 색상 출력 비활성화 |
| `AGENT_BYPASS_DEFAULT` | `false` | `true`로 설정 시 `/agents` 기본 정책이 auto |
| `AGENT_INTERACTION_POLICY` | `interactive` | 에이전트 기본 정책 (`interactive` / `auto`) |

### claude-ai-chat-code.py

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | (필수) | Anthropic API 키 |
| `CLAUDE_MODEL_ID` | `claude-sonnet-4-5` | 사용할 Claude 모델 ID |
| `CLAUDE_API_ENDPOINT` | `https://api.anthropic.com` | API 엔드포인트 |

### gemini-ai-chat-code.py

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `GEMINI_API_KEY` | (필수) | Google Gemini API 키 |
| `GEMINI_MODEL_ID` | `gemini-3.0-flash` | 사용할 Gemini 모델 ID |
| `GEMINI_API_ENDPOINT` | `https://aiplatform.googleapis.com/v1/publishers/google/` | API 엔드포인트 |

### gen-ai-chat-code.py

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `ENDPOINT_URL` | (필수) | GenAI API 엔드포인트 URL |
| `YOUR_CLIENT_KEY` | (필수) | 클라이언트 키 |
| `YOUR_CLIENT_SECRET` | (필수) | 클라이언트 시크릿 |
| `YOUR_MODEL_ID` | (선택) | 사용할 모델 ID |

---

*이 문서는 `claude-ai-chat-code.py`, `gemini-ai-chat-code.py`, `gen-ai-chat-code.py` 소스 코드 및 `src/command_registry.py`, `src/agents_command.py`를 기준으로 작성되었습니다.*
