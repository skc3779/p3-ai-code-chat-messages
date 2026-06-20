# Oh My ClaudeCode (OMC) 실전 가이드

> 기준일: 2026-06-18
> 기준 OMC 버전: **v4.14.7** (2026-06-14 릴리즈)
> 제품 근거: [OMC 공식 저장소](https://github.com/Yeachan-Heo/oh-my-claudecode) · [OMC 공식 레퍼런스](https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/REFERENCE.md) · [OMC 공식 웹사이트](https://yeachan-heo.github.io/oh-my-claudecode-website)
> 기반 동작 근거: [Anthropic Claude Code 공식 문서](https://code.claude.com/docs/en/overview)

---

## 변경 이력

| 날짜 | 버전 | OMC 기준 버전 | 변경 내용 |
|:---|:---|:---|:---|
| 2026-06-18 | v3 | v4.14.7 | 공식 문서(README, REFERENCE.md, ARCHITECTURE.md, MIGRATION.md, CHANGELOG.md) 전면 재검증. 에이전트 수 19개로 정정, Cursor 프로바이더·Slack 알림·`/goal` 워크플로우·Native Team Worktree Mode·`omc wait`·`/skill`·`/skillify`·`deepsearch`·`ultrathink`·Company Context via MCP·OpenClaw 연동 등 최신 기능 반영. 초기 프로젝트 셋업 가이드 신규 추가. 권장 방법 상세화 |
| 2026-06-14 | v2 | v4.14.7 | 공식 문서 기준으로 전면 갱신. v4.1.7 이후 swarm 제거·team 정식화, v4.4.0 이후 Codex/Gemini MCP 서버 제거·CLI-first 팀 런타임 전환, /ccg·/ask·/ultragoal 스킬 추가, npm 설치 경고 안내, 환경변수·설정 범위·Stop Callback 섹션 추가 반영 |
| 2026-06-12 | v1 | - | 최초 작성 |

---

## 문서 읽기 전에

**Oh My ClaudeCode(OMC)**는 Claude Code 위에서 동작하는 서드파티 멀티 에이전트 오케스트레이션 플러그인/런타임입니다.

- **Claude Code 공식 기능**: 플러그인, 스킬, 서브에이전트, 훅, 권한, 메모리, 실험적 Agent Teams, `/goal`
- **OMC 확장 기능**: `autopilot`, `ralph`, `ultrawork`, `team`, `ralplan`, `ultraqa`, `ultragoal`, `deep-interview`, `/ask`, `/ccg`, `/skill`, `/skillify`, `deepsearch`, `ultrathink`, HUD, 상태 관리 등

두 영역은 관련되어 있지만 동일하지 않습니다. 특히 OMC의 `/team`과 터미널의 `omc team`은 서로 다른 실행 표면입니다.

> OMC는 변경 속도가 빠릅니다. 고정된 버전 번호나 에이전트/스킬 개수보다 현재 저장소의 README와 `/omc-help` 출력을 우선하세요.

---

## 목차

1. [OMC가 하는 일](#1-omc가-하는-일)
2. [초기 프로젝트 셋업 가이드 (필수)](#2-초기-프로젝트-셋업-가이드-필수)
3. [설치와 업데이트](#3-설치와-업데이트)
4. [명령 실행 위치 구분](#4-명령-실행-위치-구분)
5. [핵심 워크플로우](#5-핵심-워크플로우)
6. [Team 모드](#6-team-모드)
7. [스킬과 에이전트](#7-스킬과-에이전트)
8. [Hooks와 상태 관리](#8-hooks와-상태-관리)
9. [CLAUDE.md와 메모리](#9-claudemd와-메모리)
10. [권한과 보안](#10-권한과-보안)
11. [설정 범위와 환경변수](#11-설정-범위와-환경변수)
12. [알림 및 모니터링](#12-알림-및-모니터링)
13. [문제 해결](#13-문제-해결)
14. [빠른 참조](#14-빠른-참조)
15. [공식 출처](#15-공식-출처)

---

## 1. OMC가 하는 일

OMC는 Claude Code의 플러그인, 스킬, 에이전트, 훅을 조합하여 다음 작업을 지원합니다.

- 요구사항 분석부터 구현·검증까지 이어지는 자율 워크플로우
- 역할별 전문 에이전트 위임 (19개 에이전트, 4개 레인)
- 독립 작업의 병렬 실행
- 완료 조건을 만족할 때까지 반복하는 지속 실행
- `.omc/` 디렉터리를 이용한 작업 상태와 근거 보존
- HUD와 trace를 이용한 진행 상황 확인
- 비용 최적화를 위한 스마트 모델 라우팅 (Haiku/Sonnet/Opus 자동 배정)

### OMC를 쓰기 좋은 경우

| 상황 | 권장 접근 |
|:---|:---|
| 작은 질문이나 한 파일 수정 | 일반 Claude Code 대화 |
| 구현 전에 변경 범위를 검토 | Claude Code Plan mode 또는 OMC `plan` |
| 요구사항이 모호함 | OMC `deep-interview` |
| 명확한 기능을 처음부터 끝까지 구현 | **OMC `autopilot` (권장)** |
| 완료 기준을 반드시 충족 | OMC `ralph` |
| 독립 작업을 병렬 배정 | OMC `/team` 또는 `ultrawork` |
| 테스트·빌드·린트 실패를 반복 수정 | OMC `ultraqa` |
| 장기 목표 분해 및 추적 | OMC `ultragoal` |
| 교차 검증용 외부 AI 검토 | OMC `/ask` 또는 `/ccg` |
| 네이티브 크로스 턴 완료 조건 | Claude Code `/goal` |

병렬 작업은 항상 빠른 것이 아닙니다. 같은 파일을 여러 작업자가 수정하거나 작업 순서 의존성이 크면 단일 세션이 더 안전합니다.

---

## 2. 초기 프로젝트 셋업 가이드 (필수)

새 프로젝트에서 OMC를 처음 사용할 때 반드시 완료해야 하는 셋업 절차입니다.

### 2.1 사전 준비 (필수 요건)

| 요건 | 확인 방법 |
|:---|:---|
| Claude Code CLI 설치 | `claude --version` |
| Claude Max/Pro 구독 또는 Anthropic API 키 | `ANTHROPIC_API_KEY` 환경변수 또는 구독 확인 |
| Node.js 18 이상 (npm CLI 사용 시) | `node --version` |
| tmux 설치 (팀 모드 사용 시) | `tmux -V` |

```bash
# 설치 확인
claude --version
claude doctor
```

### 2.2 OMC 설치 — 권장: 플러그인 방식

> **이 방식이 공식 권장 설치 방법입니다.** REFERENCE.md에 따르면 "Only the Claude Code Plugin method is supported"로 플러그인 방식만 완전히 지원됩니다.

Claude Code 세션을 먼저 실행한 뒤, 아래 명령을 **한 줄씩** 순서대로 입력합니다(두 줄을 한꺼번에 붙여 넣으면 실패합니다).

**Step 1: 마켓플레이스 등록**

```text
/plugin marketplace add https://github.com/Yeachan-Heo/oh-my-claudecode
```

**Step 2: 플러그인 설치**

```text
/plugin install oh-my-claudecode
```

**Step 3: 플러그인 로드 확인**

```text
/reload-plugins
```

**Step 4: 설치 확인**

```text
/plugin list
```

> 설치 결과에서 `oh-my-claudecode`가 `Installed` 탭에 표시되면 성공입니다.

### 2.3 필수 셋업 — 전역 설정

OMC 플러그인 설치 후 반드시 셋업을 실행해야 합니다. 셋업은 `CLAUDE.md`에 OMC 동작에 필요한 설정(에이전트 위임, 키워드 감지, 모델 라우팅 등)을 자동 작성합니다.

#### 전역 설정 (모든 프로젝트에 적용)

```text
/setup
```

또는:

```text
/omc-setup
```

> 전역 설정은 `~/.claude/CLAUDE.md`에 저장됩니다. 이 파일이 이미 존재하면 **덮어쓰기**됩니다. 기존 내용을 보존하려면 프로젝트 범위 설정을 사용하세요.

#### 셋업이 활성화하는 기능

| 기능 | 셋업 전 | 셋업 후 |
|:---|:---|:---|
| 에이전트 위임 | 수동만 가능 | 작업에 따라 자동 위임 |
| 키워드 감지 | 비활성 | `ultrawork`, `ralph`, `deepsearch` 등 자동 감지 |
| Todo 지속 실행 | 기본 동작 | 강제 완료 보장 |
| 모델 라우팅 | 기본값 | 스마트 티어 선택 (Haiku/Sonnet/Opus) |
| 스킬 조합 | 없음 | 자동 조합 |

### 2.4 필수 셋업 — 프로젝트별 설정 (권장)

> **프로젝트별 설정이 권장됩니다.** 전역 설정을 보존하면서 프로젝트마다 독립적인 OMC 구성을 유지할 수 있습니다.

```text
/oh-my-claudecode:omc-setup --local
```

이 명령은:
- `./.claude/CLAUDE.md`에 프로젝트 전용 설정을 저장합니다
- 전역 `~/.claude/CLAUDE.md`를 그대로 보존합니다
- 해당 프로젝트에서만 적용됩니다

#### 설정 우선순위

```
./.claude/CLAUDE.md (프로젝트)  →  우선  →  ~/.claude/CLAUDE.md (전역)
```

프로젝트 설정이 존재하면 전역 설정보다 **항상 우선**합니다.

### 2.5 Agent Teams 활성화 (Team 모드 사용 시)

OMC의 `/team` 인세션 모드를 사용하려면 Claude Code의 실험적 Agent Teams 기능을 활성화해야 합니다.

`~/.claude/settings.json` 파일을 편집합니다:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

> Agent Teams가 비활성화된 경우 OMC는 경고를 출력하고 가능한 경우 비-팀 실행으로 폴백합니다.

### 2.6 프로젝트 컨텍스트 설정 (권장)

프로젝트의 `.claude/CLAUDE.md`에 프로젝트별 지침을 추가하면 OMC가 더 정확하게 동작합니다.

```markdown
# Project Context

This is a TypeScript monorepo using:

- Bun runtime
- React for frontend
- PostgreSQL database

## Conventions

- Use functional components
- All API routes in /src/api
- Tests alongside source files
```

### 2.7 셋업 완료 확인

모든 셋업이 완료되면 다음 명령으로 정상 동작을 확인합니다.

```text
/omc-doctor
/omc-help
```

```bash
# 터미널에서
omc --version
```

### 셋업 체크리스트

- [ ] Claude Code 설치 확인 (`claude --version`)
- [ ] OMC 플러그인 설치 (`/plugin install oh-my-claudecode`)
- [ ] 전역 셋업 (`/setup` 또는 `/omc-setup`)
- [ ] 프로젝트별 셋업 (`/oh-my-claudecode:omc-setup --local`) — 권장
- [ ] Agent Teams 활성화 (Team 모드 사용 시)
- [ ] 프로젝트 컨텍스트 작성 (`.claude/CLAUDE.md`)
- [ ] OMC 진단 확인 (`/omc-doctor`)

---

## 3. 설치와 업데이트

### 3.1 Claude Code 설치 확인

```bash
claude --version
claude doctor
```

Anthropic 공식 설치 방법:

```bash
# Windows
winget install Anthropic.ClaudeCode

# npm (Node.js 18 이상 필요)
npm install -g @anthropic-ai/claude-code
```

### 3.2 OMC 플러그인 설치 — 권장

> **공식 REFERENCE.md 기준**: "Only the Claude Code Plugin method is supported." 플러그인 방식만 완전히 지원됩니다.

설치 절차는 [2.2 OMC 설치 — 권장: 플러그인 방식](#22-omc-설치--권장-플러그인-방식)을 참고하세요.

Anthropic 공식 문서상 플러그인은 사용자, 프로젝트, 로컬 범위로 설치할 수 있습니다. 팀 전체가 같은 플러그인을 사용해야 한다면 설치 범위와 `.claude/settings.json` 공유 여부를 함께 검토하세요.

### 3.3 OMC CLI/Runtime 설치

tmux 기반 `omc team`, `omc ask`, `omc wait` 등 CLI 표면이 필요하면 OMC 공식 npm 패키지를 설치합니다.

```bash
npm i -g oh-my-claude-sisyphus@latest
```

> **패키지명 안내**: 프로젝트 브랜드는 `oh-my-claudecode`이지만, npm 패키지명은 역사적 이유로 `oh-my-claude-sisyphus`입니다. 설치 후 `omc` 명령(또는 `oh-my-claudecode`)을 사용합니다.

```bash
omc --version
omc setup
```

> **npm 경고 안내**: 설치 중 `deprecated prebuild-install@7.1.3` 경고가 출력될 수 있습니다. 이는 내부 의존성(`better-sqlite3 → prebuild-install`)에서 발생하며 현재 업스트림 해결책이 없습니다. 설치 자체는 성공합니다. ([관련 이슈 #2913](https://github.com/Yeachan-Heo/oh-my-claudecode/issues/2913))

> 플러그인 설치와 npm CLI 설치는 실행 표면이 다릅니다. Claude Code 세션 안의 스킬은 플러그인이 제공하고, 터미널의 `omc ...` 명령은 CLI 패키지가 제공합니다.

### 3.4 업데이트

**플러그인 방식 (권장):**

```text
/plugin marketplace update omc
/setup
```

**CLI 방식:**

```bash
npm i -g oh-my-claude-sisyphus@latest
omc setup
```

> 마켓플레이스 자동 업데이트가 활성화되지 않은 경우 `/plugin marketplace update omc`를 직접 실행해야 합니다. 업데이트 후에는 반드시 `/setup`(또는 `/oh-my-claudecode:omc-setup`)을 재실행하여 최신 CLAUDE.md 변경사항을 적용하세요.

업데이트 후 문제가 생기면:

```text
/omc-doctor
```

### 3.5 셋업 재실행이 필요한 시점

- **최초 설치 후**: 플러그인 설치 직후 반드시 실행
- **업데이트 후**: 최신 설정 반영을 위해 재실행
- **다른 머신에서**: Claude Code를 사용하는 각 머신에서 실행
- **새 프로젝트에서**: `/oh-my-claudecode:omc-setup --local` 실행

---

## 4. 명령 실행 위치 구분

| 표면 | 실행 위치 | 예시 |
|:---|:---|:---|
| Claude Code 내장 명령 | Claude Code 세션 | `/help`, `/plugin`, `/memory`, `/agents`, `/goal` |
| OMC 인세션 스킬 | Claude Code 세션 | `/autopilot`, `/ralph`, `/team`, `/omc-doctor`, `/ask`, `/ccg`, `/skill`, `/skillify` |
| OMC 자연어/키워드 | Claude Code 세션 | `autopilot: 인증 API 구현`, `ralph`, `ulw`, `ralplan`, `deepsearch`, `ultrathink` |
| OMC CLI | Bash, Zsh, tmux | `omc setup`, `omc team ...`, `omc ask ...`, `omc wait` |

### 자주 생기는 오류

```bash
# 잘못된 위치: 터미널은 /plugin을 모릅니다.
/plugin install oh-my-claudecode
```

`/plugin`, `/setup`, `/team`은 먼저 `claude`를 실행한 뒤 Claude Code 세션 안에서 입력해야 합니다.

반대로 `omc team ...`은 Claude Code의 슬래시 명령이 아니라 터미널 명령입니다.

---

## 5. 핵심 워크플로우

OMC 공식 저장소가 현재 안내하는 대표 실행 모드는 다음과 같습니다.

| 모드 | 목적 | 추천 상황 |
|:---|:---|:---|
| `deep-interview` | 질문을 통해 요구사항 명확화 | 아이디어가 모호하거나 가정이 많을 때 |
| `plan` / `ralplan` | 구현 전 계획과 비판적 검토 | 아키텍처·마이그레이션·고위험 변경 |
| **`autopilot` (권장)** | 아이디어부터 동작하는 코드까지 자율 실행 | 범위가 명확한 기능 개발 |
| `ralph` | 검증 완료까지 지속 실행 | 명시적 품질·성능·완료 기준 |
| `ultrawork` | 비-Team 방식의 최대 병렬 처리 | 독립적인 다수 수정 |
| `team` | 공유 작업 목록 기반 다중 에이전트 조정 | 역할 분리가 가능한 복합 작업 |
| `ultraqa` | 테스트·검증·수정 반복 | 품질 게이트 통과가 핵심인 작업 |
| `ultragoal` | 장기 목표 분해·추적·진행 관리 | 큰 프로젝트를 단계별로 완수 |

### 5.1 Deep Interview

```text
/deep-interview "결제 후 환불과 부분 취소를 지원하는 주문 시스템"
```

소크라테스식 질의를 통해 숨겨진 가정을 드러내고, 명확도를 가중 차원으로 측정하여 코드 작성 전에 정확히 무엇을 만들지 확정합니다. 자동 리서치 기능이 필요하면 `--autoresearch` 플래그를 추가합니다.

```text
/deep-interview --autoresearch "경쟁 제품 분석과 기능 설계"
```

> `omc autoresearch`는 **폐기(hard-deprecated)**되었습니다. 대신 `/deep-interview --autoresearch ...` 또는 `/oh-my-claudecode:autoresearch`를 사용하세요.

### 5.2 Plan과 Ralplan

```text
/plan "JWT 인증을 세션 기반 인증으로 마이그레이션"
```

```text
/ralplan "모놀리스를 서비스 단위로 분리하는 계획 수립"
```

> `ralplan`은 `/oh-my-claudecode:plan --consensus`의 별칭으로, Critic 에이전트가 계획을 반복 검토하는 합의형 계획 모드입니다.

> `plan this` / `plan the` 키워드 트리거는 제거되었습니다. `ralplan` 키워드 또는 명시적 `/oh-my-claudecode:plan`을 사용하세요.

Claude Code 자체 Plan mode도 사용할 수 있습니다.

```bash
claude --permission-mode plan
```

세션 중에는 `Shift+Tab` 또는 `/plan`으로 Plan mode에 진입할 수 있습니다.

### 5.3 Autopilot — 권장

> **가장 일반적으로 사용하는 워크플로우입니다.** 범위가 명확한 기능 개발에 최적화되어 있으며, 아이디어에서 동작하는 코드까지 자율적으로 파이프라인을 실행합니다.

#### 사용 방법

**슬래시 명령 (명시적):**

```text
/autopilot "작업 생성·조회·수정·삭제 REST API와 테스트 구현"
```

**자연어 키워드 (간편):**

```text
autopilot: 작업 관리 REST API와 테스트를 구현해줘
```

#### Autopilot이 수행하는 단계

1. **요구사항 분석**: 작업 범위와 목표를 파악
2. **계획 수립**: 구현 단계를 자동 설계
3. **에이전트 위임**: 적합한 에이전트(executor, architect 등)에 작업 분배
4. **코드 구현**: 실제 코드 작성 및 파일 수정
5. **검증**: 테스트 실행 및 결과 확인

#### Autopilot 활용 팁

- 작업 설명은 **구체적**일수록 좋습니다. "API 구현"보다 "사용자 인증 JWT 기반 REST API와 단위 테스트 구현"이 더 정확한 결과를 얻습니다
- 요구사항이 모호하면 먼저 `deep-interview`나 `plan`을 사용하세요
- `ralph`와 결합하면 autopilot 완료 후 검증까지 자동으로 이어갑니다

### 5.4 Ralph

```text
/ralph "모든 타입 오류를 제거하고 전체 테스트와 빌드를 통과시켜라"
```

Ralph는 검증된 완료 상태까지 반복하는 지속 실행 모드입니다. **측정 가능한 종료 조건을 가진 반복 검증 루프**로 사용하는 편이 안전합니다.

> `ralph`는 `ultrawork`를 포함합니다. ralph 모드를 활성화하면 ultrawork의 병렬 실행이 자동으로 포함됩니다.

좋은 종료 조건:

- `npm test` 성공
- `npm run build` 성공
- 타입 오류 0개
- 특정 성능 벤치마크 통과
- 코드 리뷰의 blocking finding 0개

현재 실행 모드를 취소할 때:

```text
/cancel
```

또는 자연어로:

```text
cancelomc
stopomc
```

### 5.5 Ultrawork

```text
/ultrawork "서로 독립적인 서비스 모듈 8개에 입력 검증과 단위 테스트 추가"
```

자연어 키워드: `ulw`

같은 파일을 여러 작업자가 수정해야 하거나 앞 작업 결과가 뒤 작업의 입력이면 병렬화 이점이 줄어듭니다.

### 5.6 UltraQA

```text
/ultraqa "테스트, 빌드, 린트, 타입 검사를 모두 통과할 때까지 진단하고 수정"
```

품질 게이트를 명확히 지정해야 불필요한 반복을 줄일 수 있습니다.

### 5.7 Ultragoal

```text
/ultragoal "전체 인증 시스템을 OAuth2로 마이그레이션하는 장기 계획 수립 및 실행"
```

큰 목표를 세부 목표(goal)로 분해하고, 각 목표의 상태를 `.omc/ultragoal/` 아래에 추적합니다. 여러 세션에 걸쳐 진행하는 장기 프로젝트에 적합합니다.

CLI에서 직접 목표를 관리할 수도 있습니다.

```bash
omc ultragoal create-goals --auto-plan-id "migration-brief.md"
omc ultragoal status
omc ultragoal list-plans
```

> 멀티 플랜 레이아웃: `--plan-id <id>` 또는 `--auto-plan-id`를 사용하면 `.omc/ultragoal/plans/{planId}/` 아래에 독립적으로 저장되어 병렬 세션 간 충돌이 발생하지 않습니다.

### 5.8 Goal 워크플로우 가이드

OMC와 Claude Code 모두 "목표 완료"를 위한 다양한 루프 메커니즘을 제공합니다. **세션당 하나의 루프 권한만 사용하세요.**

| 루프 메커니즘 | 소유자 | 용도 |
|:---|:---|:---|
| Claude Code `/goal` | Claude Code 네이티브 | 크로스 턴 완료 조건 |
| `ralph` | OMC | 단일 에이전트 검증 완료 |
| `/team` | OMC | 병렬 스테이지 실행 |
| `ultraqa` | OMC | 품질 게이트 반복 사이클링 |
| `ultragoal` (아티팩트 전용) | OMC | 지속 목표 아티팩트와 근거 없이 루프 없는 폴백 |

> `/goal` 동작은 [Claude Code /goal 문서](https://code.claude.com/docs/en/goal)와 [Anthropic Claude Code changelog](https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md)를 참고하세요.

### 5.9 Ask — 외부 AI 어드바이저

```text
/ask codex "이 인증 모듈의 보안 취약점을 검토해줘"
/ask gemini "UI 컴포넌트의 접근성을 평가해줘"
/ask cursor "이 구현 계획을 적용해줘"
```

또는 CLI에서:

```bash
omc ask codex "review this patch"
omc ask gemini "review UI accessibility"
omc ask cursor "apply this implementation plan"
```

지원 프로바이더: `claude`, `codex`, `gemini`, `grok`, `cursor`

> v4.14.7에서 Cursor 프로바이더가 새로 추가되었습니다.

### 5.10 CCG — 트리플 모델 어드바이저

```text
/ccg 이 PR을 아키텍처(Codex)와 UI 컴포넌트(Gemini) 관점에서 각각 검토해줘
```

`/ccg`는 `/ask codex`와 `/ask gemini`를 동시에 실행한 뒤 Claude가 결과를 종합합니다.

### 5.11 Deepsearch와 Ultrathink

자연어로 바로 사용할 수 있는 매직 키워드입니다.

```text
deepsearch for auth middleware
```

```text
ultrathink about this architecture
```

---

## 6. Team 모드

> **v4.1.7 이후**: `swarm` 키워드와 스킬이 제거되었습니다. `team`을 직접 사용하세요.

### 6.1 Claude Code 세션 안의 `/team` — 권장

> **인세션 팀 오케스트레이션의 권장 방법입니다.** Claude Code의 네이티브 Agent Teams 기능을 활용하여 역할별 에이전트를 자동으로 조정합니다.

```text
/team 3:executor "백엔드, 프론트엔드, 테스트를 역할별로 구현하고 통합 검증"
```

#### Team 파이프라인 단계

OMC Team은 다음 스테이지 파이프라인을 순서대로 실행합니다:

```text
team-plan → team-prd → team-exec → team-verify → team-fix (loop)
```

1. **team-plan**: 작업 분석 및 계획 수립
2. **team-prd**: 요구사항 정의서(PRD) 생성
3. **team-exec**: 실제 코드 구현 (병렬 에이전트 실행)
4. **team-verify**: 결과 검증 (테스트, 빌드, 린트)
5. **team-fix**: 검증 실패 시 수정 후 team-verify로 반복

#### 필수 설정

`~/.claude/settings.json`:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### 6.2 터미널의 `omc team`

> **v4.4.0 이후**: Codex/Gemini MCP 서버(`x`, `g` 프로바이더)가 제거되었습니다. CLI-first 팀 런타임(`omc team ...`)을 사용하여 실제 tmux worker pane을 생성합니다.

```bash
omc team 2:codex "인증 모듈의 보안과 아키텍처 검토"
omc team 2:gemini "UI 접근성과 반응형 레이아웃 검토"
omc team 2:grok "코드 리뷰 및 분석 교차 검증"
omc team 1:claude "결제 흐름 구현"
```

| 표면 | 작업자 | 최적 용도 |
|:---|:---|:---|
| `omc team N:codex "..."` | N개 Codex CLI pane | 코드 리뷰, 보안 분석, 아키텍처 |
| `omc team N:gemini "..."` | N개 Gemini CLI pane | UI/UX 설계, 문서, 대규모 컨텍스트 작업 |
| `omc team N:grok "..."` | N개 Grok Build CLI pane | 코드 리뷰, 분석 교차 검증 |
| `omc team N:claude "..."` | N개 Claude CLI pane | tmux에서의 범용 Claude 작업 |

필수 조건:
- 활성 tmux 세션 필요 (Windows: [psmux](https://github.com/marlocarlo/psmux) 사용 가능)
- 선택한 작업자 CLI 설치 필요

팀 관리:

```bash
omc team status <team-name>
omc team shutdown <team-name>
```

Workers는 작업이 완료되면 자동으로 종료됩니다(유휴 리소스 없음).

### 6.3 Native Team Worktree Mode (신규, Opt-In)

`omc team` 런타임 v2에 opt-in 워커 워크트리 모드가 추가되었습니다. 워크트리 기반 워커는 전용 git 워크트리에서 실행되며, 작업 라이프사이클과 상태 파일은 리더 워크스페이스의 팀 전용 조정 루트에 유지됩니다.

자세한 내용은 [Native Team Worktree Mode](https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/TEAM-WORKTREE-MODE.md) 문서를 참고하세요.

### 6.4 두 Team 표면 비교

| 항목 | `/team` (권장) | `omc team` |
|:---|:---|:---|
| 실행 위치 | Claude Code 세션 | tmux가 연결된 터미널 |
| 작업자 | Claude Code 네이티브 팀 | Claude/Codex/Gemini/Grok CLI 프로세스 |
| 주요 목적 | OMC 인세션 다중 에이전트 워크플로우 | 외부 CLI 작업자를 pane 단위로 조정 |
| 필수 조건 | Agent Teams 활성화 권장 | tmux와 대상 CLI |

> `/omc-teams`는 레거시 호환 경로이며 이제 `omc team ...`으로 라우팅됩니다. 새 작업에는 `/team` 또는 `omc team`을 사용하세요.

---

## 7. 스킬과 에이전트

### 7.1 Claude Code 스킬 구조

Anthropic 공식 권장 구조:

```text
.claude/
└── skills/
    └── deploy-check/
        └── SKILL.md
```

예시:

```markdown
---
name: deploy-check
description: 배포 전 필수 검증을 실행한다
disable-model-invocation: true
---

1. 테스트를 실행한다.
2. 빌드와 타입 검사를 실행한다.
3. 변경된 환경 변수와 마이그레이션을 확인한다.
4. 실패 항목이 있으면 배포하지 않고 원인을 보고한다.
```

호출:

```text
/deploy-check
```

### 7.2 OMC 스킬 관리

OMC는 학습된 스킬을 자동 추출하고 관리하는 기능을 제공합니다.

```text
/skill list              # 스킬 목록 조회
/skill add               # 스킬 추가
/skill remove            # 스킬 삭제
/skill edit              # 스킬 편집
/skill search            # 스킬 검색
/skillify                # 세션에서 재사용 가능한 패턴 자동 추출
```

스킬 저장 위치:

| 위치 | 용도 |
|:---|:---|
| `.omc/skills/` | 프로젝트 범위 OMC 스킬 (커밋 가능) |
| `~/.omc/skills/` | 사용자 전역 스킬 |
| `.claude/skills/` | Claude Code 워크스페이스 스킬 |
| `.agents/skills/` | 호환성 스킬 |

> 프로젝트 로컬 스킬을 git 워크트리에서 생성하고 커밋하지 않으면, 해당 워크트리 삭제 시 함께 사라집니다.

### 7.3 서브에이전트

Claude Code의 커스텀 서브에이전트 위치:

```text
# 사용자 범위
~/.claude/agents/

# 프로젝트 범위
.claude/agents/
```

서브에이전트는 별도 컨텍스트에서 집중 작업을 수행하고 결과를 부모 세션에 반환합니다.

### 7.4 OMC 에이전트 — 19개, 4개 레인

OMC는 **19개의 전문 에이전트**를 **4개 레인**으로 조직합니다.

#### Build/Analysis 레인

| 에이전트 | 기본 모델 | 역할 |
|:---|:---|:---|
| `explore` | Haiku | 코드베이스 탐색, 파일/심볼 매핑 |
| `analyst` | Opus | 요구사항 분석, 숨겨진 제약 발견 |
| `planner` | Opus | 작업 시퀀싱, 실행 계획 생성 |
| `architect` | Opus | 시스템 설계, 인터페이스 정의, 트레이드오프 분석 |
| `debugger` | Sonnet | 근본 원인 분석, 빌드 오류 해결 |
| `executor` | Sonnet | 코드 구현, 리팩토링 |
| `verifier` | Sonnet | 완료 검증, 테스트 적절성 확인 |
| `tracer` | Sonnet | 근거 기반 인과 추적, 경쟁 가설 분석 |

#### Review 레인

| 에이전트 | 기본 모델 | 역할 |
|:---|:---|:---|
| `security-reviewer` | Sonnet | 보안 취약점, 신뢰 경계, 인증/인가 검토 |
| `code-reviewer` | Opus | 종합 코드 리뷰, API 계약, 하위 호환성 |

#### Domain 레인

| 에이전트 | 기본 모델 | 역할 |
|:---|:---|:---|
| `test-engineer` | Sonnet | 테스트 전략, 커버리지, 불안정 테스트 강화 |
| `designer` | Sonnet | UI/UX 아키텍처, 인터랙션 설계 |
| `writer` | Haiku | 문서화, 마이그레이션 노트 |
| `qa-tester` | Sonnet | 대화형 CLI/서비스 런타임 검증 (tmux) |
| `scientist` | Sonnet | 데이터 분석, 통계 연구 |
| `git-master` | Sonnet | Git 작업, 커밋, 리베이스, 히스토리 관리 |
| `document-specialist` | Sonnet | 외부 문서, API/SDK 레퍼런스 조회 |
| `code-simplifier` | Opus | 코드 명료화, 단순화, 유지보수성 개선 |

#### Coordination 레인

| 에이전트 | 기본 모델 | 역할 |
|:---|:---|:---|
| `critic` | Opus | 계획과 설계의 갭 분석, 다각도 검토 |

#### 모델 라우팅 가이드

| 티어 | 모델 | 특성 | 비용 |
|:---|:---|:---|:---|
| LOW | Haiku | 빠르고 저비용 | 낮음 |
| MEDIUM | Sonnet | 성능과 비용의 균형 | 중간 |
| HIGH | Opus | 최고 수준 추론 | 높음 |

> v4.14.7에서 Claude Fable 5 티어 별칭과 모델 ID 지원이 추가되었습니다.

에이전트 동작을 커스터마이즈하려면 `~/.claude/agents/` 아래의 에이전트 파일을 편집합니다.

```yaml
---
name: architect
description: 커스텀 아키텍처 설명
tools: Read, Grep, Glob, Bash, Edit
model: opus # or sonnet, haiku
---
커스텀 시스템 프롬프트 내용...
```

> 번들된 OMC 에이전트 프롬프트에는 `effort:` 프론트매터 필드가 포함되지 않습니다. 런타임 effort는 명시적 오버라이드가 없으면 부모 Claude Code 세션에서 상속됩니다.

역할 수와 모델 라우팅은 버전에 따라 바뀔 수 있으므로 다음을 현재 기준으로 확인하세요.

```text
/omc-help
/agents
```

---

## 8. Hooks와 상태 관리

### 8.1 Claude Code Hooks

Claude Code Hooks는 생명주기 이벤트에 반응하는 사용자 정의 명령, HTTP 엔드포인트 또는 LLM 프롬프트입니다.

OMC가 주로 활용하는 이벤트:

| 이벤트 | 용도 |
|:---|:---|
| `UserPromptSubmit` | 키워드 감지와 스킬 라우팅 |
| `SessionStart` | 초기화와 프로젝트 컨텍스트 로드 |
| `PreToolUse` | 도구 실행 전 검증 |
| `PostToolUse` | 성공 결과 처리 |
| `PostToolUseFailure` | 실패 복구 |
| `SubagentStart` / `SubagentStop` | 에이전트 추적 |
| `PreCompact` | 압축 전 중요 정보 보존 |
| `Stop` | 지속 실행 모드의 완료 조건 확인 |
| `SessionEnd` | 세션 정리 |

> 훅은 사용자 입력과 도구 호출에 자동 반응합니다. 출처를 검토하지 않은 플러그인의 훅은 설치 전에 반드시 확인하세요.

### 8.2 OMC 상태

OMC는 프로젝트의 `.omc/` 아래에 실행 상태와 근거를 저장합니다.

```text
.omc/
├── state/
│   └── sessions/<session-id>/   # 세션 범위 상태 (최우선)
├── plans/
├── specs/
├── notepad.md
├── project-memory.json
├── research/
├── logs/
├── skills/                      # OMC 학습 스킬
├── sessions/*.json              # 세션 요약
├── handoffs/                    # team 단계 간 핸드오프 (팀 스킬 전용 기록)
├── artifacts/ask/               # /ask 어드바이저 출력
├── ultragoal/                   # ultragoal 계획 및 ledger
│   └── plans/{planId}/          # 멀티 플랜 레이아웃
└── notepads/<plan-name>/        # 계획별 노트패드
```

> `.omc/handoffs/`는 team 스킬만 기록합니다. 다른 코드는 읽기 전용으로만 접근합니다. 핸드오프 파일은 `TeamDelete`와 세션 취소 후에도 의도적으로 보존됩니다 — 사후 분석 아티팩트입니다.

---

## 9. CLAUDE.md와 메모리

### 9.1 CLAUDE.md — 권장 작성법

> **모든 프로젝트에서 CLAUDE.md를 작성하는 것이 권장됩니다.** 이 파일은 매 세션 시작 시 로드되어 Claude와 OMC의 동작 기반이 됩니다.

`CLAUDE.md`에는 매 세션에 필요한 짧고 안정적인 지침을 작성합니다.

적합한 내용:

- 빌드·테스트 명령 (`npm test`, `npm run build`)
- 코드 스타일 규칙
- 프로젝트 구조 설명
- 금지된 작업
- 반드시 지켜야 할 검증 절차
- 사용하는 기술 스택

부적합한 내용:

- 긴 단계형 실행 절차 → 스킬로 분리
- 한 번만 필요한 작업 설명
- 자주 바뀌는 상태 보고
- 파일별 세부 규칙 → `.claude/rules/`로 분리

### 9.2 Claude Code Auto Memory

Anthropic 공식 문서 기준 auto memory는 다음 위치에 저장됩니다.

```text
~/.claude/projects/<project>/memory/
```

`MEMORY.md`의 처음 200줄 또는 25KB 중 먼저 도달하는 범위가 세션 시작 시 로드됩니다. auto memory는 로컬 머신에 저장되며 다른 컴퓨터나 클라우드 환경과 자동 공유되지 않습니다.

메모리 확인:

```text
/memory
```

---

## 10. 권한과 보안

### 10.1 민감 파일 차단

`.claude/settings.json` 예시:

```json
{
  "permissions": {
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)",
      "Read(./config/credentials.json)"
    ]
  }
}
```

권한 차단은 `CLAUDE.md`의 자연어 지시보다 강한 통제 수단입니다.

### 10.2 플러그인 설치 전 확인

Claude Code의 `/plugin` 화면에서 다음 항목을 검토하세요.

- 포함된 스킬과 에이전트
- 등록되는 훅
- MCP/LSP 서버
- 설치 범위
- 플러그인 출처와 업데이트 시점

### 10.3 자동 승인에 대한 주의

권한은 Anthropic 공식 `permissions.allow`, `permissions.ask`, `permissions.deny` 규칙과 permission mode 문서를 기준으로 설정합니다.

---

## 11. 설정 범위와 환경변수

### 11.1 설정 우선순위

```
./.claude/CLAUDE.md (프로젝트)  →  우선  →  ~/.claude/CLAUDE.md (전역)
```

### 11.2 주요 환경변수

| 변수 | 기본값 | 설명 |
|:---|:---|:---|
| `OMC_STATE_DIR` | (미설정) | 중앙화된 상태 디렉터리. 설정 시 워크트리 삭제 후에도 상태가 보존됩니다. |
| `OMC_PARALLEL_EXECUTION` | `true` | 병렬 에이전트 실행 활성화/비활성화 |
| `OMC_CODEX_DEFAULT_MODEL` | (프로바이더 기본값) | Codex CLI 작업자의 기본 모델 |
| `OMC_GEMINI_DEFAULT_MODEL` | (프로바이더 기본값) | Gemini CLI 작업자의 기본 모델 |
| `OMC_GROK_DEFAULT_MODEL` | (프로바이더 기본값) | Grok Build CLI 작업자의 기본 모델 |
| `OMC_LSP_TIMEOUT_MS` | `15000` | LSP 요청 타임아웃(ms). 대규모 저장소에서는 늘릴 것. |
| `OMC_MIGRATE_LEGACY_STATE` | (미설정) | `1`로 설정 시 레거시 상태를 세션 범위로 1회 마이그레이션 |
| `OMC_DISABLE_MULTIREPO` | (미설정) | `1`로 설정 시 워크스페이스 마커 해석 비활성화 |
| `OMC_BRIDGE_SCRIPT` | (자동 감지) | Python 브릿지 스크립트 경로 |
| `OMC_PLUGIN_ROOT` | (미설정) | `claude --plugin-dir <path>` 사용 시 HUD 번들 경로 해결 |
| `DISABLE_OMC` | (미설정) | 값을 설정하면 모든 OMC 훅 비활성화 |
| `OMC_SKIP_HOOKS` | (미설정) | 건너뜀 훅 이름을 쉼표로 구분하여 나열 |

#### 상태 중앙화 예시

```bash
# ~/.bashrc 또는 ~/.zshrc
export OMC_STATE_DIR="$HOME/.claude/omc"
```

워크트리 삭제 후에도 OMC 상태가 `~/.claude/omc/{project-hash}/`에 보존됩니다.

#### 멀티-레포 워크스페이스 설정

부모 디렉터리가 git 저장소가 아닌 경우 `.omc-workspace` 마커를 생성합니다.

```bash
cd /path/to/my-workspace
echo '{}' > .omc-workspace
```

```json
{ "id": "my-org-project" }
```

이렇게 하면 여러 하위 저장소가 하나의 `.omc/`를 공유합니다.

**상태 경로 해석 순서** (`getOmcRoot()`):

1. `OMC_STATE_DIR` (중앙화)
2. `.omc-workspace` 마커 (멀티-레포 워크스페이스)
3. `git rev-parse --show-toplevel` (모노레포 / 단일 레포)
4. `process.cwd()` (최후 수단)

---

## 12. 알림 및 모니터링

### 12.1 Stop Callback 알림

작업 완료 시 Telegram·Discord·Slack 알림을 설정할 수 있습니다.

```bash
# Telegram 설정
omc config-stop-callback telegram --enable --token <bot_token> --chat <chat_id> --tag-list "@alice,bob"

# Discord 설정
omc config-stop-callback discord --enable --webhook <url> --tag-list "@here,123456789012345678,role:987654321098765432"

# Slack 설정
omc config-stop-callback slack --enable --webhook <url> --tag-list "<!here>,<@U1234567890>"

# 태그 추가/제거
omc config-stop-callback telegram --add-tag charlie
omc config-stop-callback discord --remove-tag @here
omc config-stop-callback discord --clear-tags

# 현재 설정 확인
omc config-stop-callback telegram --show
```

태그 동작:

- **Telegram**: `alice`가 `@alice`로 정규화
- **Discord**: `@here`, `@everyone`, 숫자형 사용자 ID, `role:<id>` 지원
- **Slack**: `<@MEMBER_ID>`, `<!channel>`, `<!here>`, `<!everyone>`, `<!subteam^GROUP_ID>` 지원
- `file` 콜백은 태그 옵션 무시

### 12.2 Rate Limit Wait

Claude Code 세션의 레이트 리밋이 리셋될 때 자동 재개를 설정할 수 있습니다.

```bash
omc wait              # 상태 확인, 가이드 제공
omc wait --start      # 자동 재개 데몬 활성화
omc wait --stop       # 데몬 비활성화
```

> 필수 조건: tmux (세션 감지용)

### 12.3 HUD 모니터링

실시간 오케스트레이션 메트릭을 확인할 수 있습니다.

```text
/oh-my-claudecode:hud setup
```

설정 예시 (`settings.json`):

```json
{
  "omcHud": { "preset": "focused" }
}
```

```bash
# 터미널에서 라이브 HUD 렌더링
omc hud
```

세션 기록 확인:
- 세션 요약: `.omc/sessions/*.json`
- 리플레이 로그: `.omc/state/agent-replay-*.jsonl`

### 12.4 OpenClaw 연동

Claude Code 세션 이벤트를 [OpenClaw](https://openclaw.ai/) 게이트웨이로 전달하여 자동화된 응답과 워크플로우를 구성할 수 있습니다.

빠른 설정 (권장):

```text
/oh-my-claudecode:configure-notifications
# → "openclaw" 입력 → "OpenClaw Gateway" 선택
```

---

## 13. 문제 해결

### 설치 확인

```bash
claude --version
claude doctor
omc --version
```

Claude Code 세션 안에서:

```text
/plugin list
/omc-doctor
/omc-help
```

### 플러그인 명령이 보이지 않을 때

```text
/reload-plugins
/plugin list
```

그래도 보이지 않으면 marketplace와 plugin 설치 상태를 `/plugin`의 `Marketplaces`, `Installed`, `Errors` 탭에서 확인합니다.

### 업데이트 후 동작이 이상할 때

```text
/plugin marketplace update omc
/setup
/omc-doctor
```

### Team이 시작되지 않을 때

**`/team` (인세션):**

1. Claude Code 버전을 확인합니다.
2. `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 설정을 확인합니다.
3. OMC 설정을 다시 실행합니다 (`/setup`).

**`omc team` (터미널):**

1. tmux 안에서 실행 중인지 확인합니다.
2. `omc`와 작업자 CLI가 PATH에 있는지 확인합니다.
3. `omc team status <team-name>`으로 런타임 상태를 확인합니다.

### npm 설치 경고 (`deprecated prebuild-install`)

정상적인 경고입니다. 설치 자체는 성공합니다. [이슈 #2913](https://github.com/Yeachan-Heo/oh-my-claudecode/issues/2913)에서 추적 중입니다.

### 공식 이슈 확인

- [OMC GitHub Issues](https://github.com/Yeachan-Heo/oh-my-claudecode/issues)
- [Claude Code 오류 레퍼런스](https://code.claude.com/docs/en/errors)
- [OMC Discord](https://discord.gg/sj4exxQ9v)

---

## 14. 빠른 참조

### Claude Code 세션 안

```text
/setup                         OMC 초기 설정
/omc-doctor                    OMC 진단
/omc-help                      현재 OMC 명령 확인
/deep-interview "요구사항"      요구사항 명확화
/plan "작업"                   계획 수립
/ralplan "작업"                합의형 계획
/autopilot "작업"              자율 구현 (권장)
/ralph "완료 조건"             완료까지 검증 반복
/ultrawork "독립 작업 묶음"     병렬 실행
/team 3:executor "작업"        네이티브 팀 오케스트레이션 (권장)
/ultraqa "품질 게이트"         QA 반복
/ultragoal "장기 목표"         장기 목표 분해·추적
/ask codex "작업"              Codex 어드바이저
/ask gemini "작업"             Gemini 어드바이저
/ask cursor "작업"             Cursor 어드바이저
/ccg "작업"                    Codex+Gemini 혼합 어드바이저
/skill list                    스킬 목록 조회
/skillify                      재사용 패턴 추출
/cancel                        활성 OMC 모드 취소
```

### 매직 키워드

```text
autopilot: <작업>              자율 구현
ralph                          검증 반복 모드
ulw                            병렬 실행 모드
ralplan                        합의형 계획
deepsearch <대상>              심층 검색
ultrathink <주제>              심층 사고
cancelomc / stopomc            OMC 취소
```

### Bash / Zsh 터미널

```text
claude --version               Claude Code 버전
claude doctor                  Claude Code 진단
omc --version                  OMC CLI 버전
omc setup                      OMC CLI 설정
omc team 2:codex "작업"        tmux Codex CLI 팀 시작
omc team 2:gemini "작업"       tmux Gemini CLI 팀 시작
omc team 2:grok "작업"         tmux Grok CLI 팀 시작
omc team status <name>         팀 상태 확인
omc team shutdown <name>       완료된 팀 종료
omc ask codex "작업"           CLI Codex 어드바이저
omc ask cursor "작업"          CLI Cursor 어드바이저
omc ultragoal create-goals     Ultragoal 목표 생성
omc ultragoal status           Ultragoal 상태 확인
omc wait --start               레이트 리밋 자동 재개
omc hud                        라이브 HUD 렌더링
omc config-stop-callback ...   Stop Callback 설정
```

### 권장 작업 흐름

```text
1. 요구사항이 모호하면 /deep-interview
2. 고위험 변경이면 /plan 또는 /ralplan
3. 한 명이 충분하면 /autopilot          ← 가장 일반적 (권장)
4. 독립 역할이 여러 개면 /team           ← 팀 작업 시 (권장)
5. 종료 조건이 엄격하면 /ralph 또는 /ultraqa
6. 장기 프로젝트면 /ultragoal
7. 외부 검토가 필요하면 /ask 또는 /ccg
8. 테스트·빌드·린트·타입 검사 결과로 완료 확인
```

---

## 15. 공식 출처

### Oh My ClaudeCode

- [공식 GitHub 저장소 및 최신 README](https://github.com/Yeachan-Heo/oh-my-claudecode)
- [공식 Reference](https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/REFERENCE.md)
- [공식 Architecture](https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/ARCHITECTURE.md)
- [공식 Migration Guide](https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/MIGRATION.md)
- [공식 Performance Monitoring](https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/PERFORMANCE-MONITORING.md)
- [Model × Agent Compatibility Matrix](https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/agents/model-compatibility.md)
- [Native Team Worktree Mode](https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/docs/TEAM-WORKTREE-MODE.md)
- [CLI Reference](https://yeachan-heo.github.io/oh-my-claudecode-website/docs/#cli-reference)
- [Recommended Workflows](https://yeachan-heo.github.io/oh-my-claudecode-website/docs/#workflows)
- [Release Notes](https://yeachan-heo.github.io/oh-my-claudecode-website/docs/#release-notes)
- [공식 웹사이트 문서](https://yeachan-heo.github.io/oh-my-claudecode-website)
- [공식 Issues](https://github.com/Yeachan-Heo/oh-my-claudecode/issues)
- [OMC Discord](https://discord.gg/sj4exxQ9v)
- [Security Guide](https://github.com/Yeachan-Heo/oh-my-claudecode/blob/main/SECURITY.md)

### Anthropic Claude Code

- [Overview](https://code.claude.com/docs/en/overview)
- [설치와 업데이트](https://code.claude.com/docs/en/setup)
- [플러그인 설치](https://code.claude.com/docs/en/discover-plugins)
- [스킬](https://code.claude.com/docs/en/skills)
- [서브에이전트](https://code.claude.com/docs/en/sub-agents)
- [Agent Teams](https://code.claude.com/docs/en/agent-teams)
- [Goal](https://code.claude.com/docs/en/goal)
- [Hooks reference](https://code.claude.com/docs/en/hooks)
- [설정](https://code.claude.com/docs/en/settings)
- [권한](https://code.claude.com/docs/en/permissions)
- [Permission modes와 Plan mode](https://code.claude.com/docs/en/permission-modes)
- [CLAUDE.md와 auto memory](https://code.claude.com/docs/en/memory)

### 선택적 외부 AI CLI

> OMC는 외부 AI 프로바이더 없이도 완전히 동작합니다. 아래는 교차 검증이 필요한 경우에만 선택적으로 설치합니다.

- [Gemini CLI](https://github.com/google-gemini/gemini-cli) — `npm install -g @google/gemini-cli`
- [Codex CLI](https://github.com/openai/codex) — `npm install -g @openai/codex`
- [Grok Build](https://build.grok.com)

---

*최종 검토: 2026-06-18 · OMC v4.14.7 기준 · 공식 OMC README(main 브랜치), REFERENCE.md, ARCHITECTURE.md, MIGRATION.md, CHANGELOG.md, Anthropic Claude Code 최신 공식 문서를 기준으로 갱신*
