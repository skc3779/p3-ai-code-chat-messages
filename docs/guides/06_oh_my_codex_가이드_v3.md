# Oh My Codex (OMX) 실전 가이드

> 검증일: 2026년 6월 19일 (공식 사이트 + GitHub Releases 재검토 반영)
>
> 공식 OMX 최신 문서 버전: `v0.18.8` ([oh-my-codex.dev/docs.html](https://oh-my-codex.dev/docs.html))
>
> 이 문서를 검증한 로컬 환경: `oh-my-codex v0.18.11`, `codex-cli 0.137.0`
>
> OMX는 OpenAI 제품이 아니라, OpenAI Codex 위에 설치하는 별도 오픈소스 오케스트레이션 레이어입니다.

이 문서는 출처를 다음처럼 구분합니다.

- **Codex 자체 동작**: [OpenAI Codex 공식 문서](https://developers.openai.com/codex)
- **OMX 고유 동작**: [OMX 공식 문서](https://oh-my-codex.dev/docs.html), [OMX 공식 저장소](https://github.com/Yeachan-Heo/oh-my-codex), 설치된 `omx help`
- 블로그, 커뮤니티 게시물 등 제3자 페이지는 권위 있는 근거로 사용하지 않습니다.

---

## 목차

1. [OMX와 Codex의 관계](#1-omx와-codex의-관계)
2. [초기 프로젝트 셋업 가이드 ⭐](#2-초기-프로젝트-셋업-가이드-)
3. [설치와 업데이트](#3-설치와-업데이트)
4. [가장 먼저 알아야 할 실행 환경](#4-가장-먼저-알아야-할-실행-환경)
5. [빠른 시작 (권장)](#5-빠른-시작-권장)
6. [AGENTS.md, Skills, Agents](#6-agentsmd-skills-agents)
7. [작업 방식 선택 (권장)](#7-작업-방식-선택-권장)
8. [OMX Team](#8-omx-team)
9. [주요 OMX 워크플로 (권장)](#9-주요-omx-워크플로-권장)
10. [CLI 핵심 명령](#10-cli-핵심-명령)
11. [알림 플랫폼](#11-알림-플랫폼)
12. [안전한 권한 설정](#12-안전한-권한-설정)
13. [Windows 사용](#13-windows-사용)
14. [검증 중심 실전 워크플로](#14-검증-중심-실전-워크플로)
15. [잘못 알려지기 쉬운 내용](#15-잘못-알려지기-쉬운-내용)
16. [문제 해결](#16-문제-해결)
17. [공식 참고 링크](#17-공식-참고-링크)
18. [OMX 버전 히스토리](#18-omx-버전-히스토리)
19. [개정 이력](#19-개정-이력)

---

## 1. OMX와 Codex의 관계

### 1-1. Codex가 기본으로 제공하는 것

OpenAI Codex는 CLI, IDE 확장, Codex 앱, 클라우드 환경에서 코드를 읽고 수정하고 명령을 실행하는 코딩 에이전트입니다. 현재 Codex 자체에도 다음 기능이 있습니다.

- `AGENTS.md` 기반 계층형 프로젝트 지침
- `$skill` 형식으로 호출하는 Agent Skills
- 명시적으로 요청했을 때 병렬 실행하는 native subagents
- `/review`, `/plan`, `/permissions`, `/model` 등 기본 명령
- `config.toml` 기반 모델, 추론 수준, 샌드박스, 승인, MCP 설정
- CLI 세션 재개, 비대화형 `codex exec`, Codex cloud 작업
- Codex 앱의 병렬 스레드와 워크트리

따라서 "Codex는 단일 에이전트만 지원하고 OMX가 병렬 기능을 처음 추가한다"는 설명은 현재 기준으로 정확하지 않습니다.

### 1-2. OMX가 추가하는 것

OMX는 Codex의 공식 확장 표면을 이용해 다음 운영 계층을 추가합니다.

| 구분 | 공식 사이트 기준 수량 |
|---|---|
| Agent Prompts | 33개 |
| Skills | 37개 |
| MCP Servers | 5개 |

주요 추가 기능:

- 설치형 스킬과 역할별 agent prompt
- `autopilot`, `ralph`, `ultrawork`, `ultragoal`, `ultraqa`, `deep-interview` 등 장기 워크플로
- tmux pane과 `.omx/state/`를 사용하는 내구성 있는 Team 런타임
- HUD, 알림, 질문 UI, notepad, project memory, trace, wiki
- Claude/Gemini advisor 호출용 `omx ask`
- OMX 상태와 작업 수명주기를 다루는 CLI/API

핵심은 "Codex를 대체"하는 것이 아니라 "Codex 위에 반복 가능한 운영 규칙과 장기 상태를 추가"하는 것입니다.

---

## 2. 초기 프로젝트 셋업 가이드 ⭐

> 이 섹션은 새 프로젝트에서 OMX를 처음 사용할 때 **반드시 수행해야 하는 필수 셋업**을 단계별로 안내합니다.

### 2-1. 사전 요구사항 확인

```bash
# 필수 도구 확인
node --version      # Node.js 18+ 권장
npm --version       # npm 9+ 권장
git --version       # Git 2.30+
codex --version     # OpenAI Codex CLI가 설치되어 있어야 함

# Team/HUD를 사용할 경우 (선택)
tmux -V             # tmux 3.0+ 권장
```

Codex CLI가 설치되지 않았다면:

```bash
npm install -g @openai/codex
codex --version
```

### 2-2. OMX 설치 (권장: npm global)

> **권장 방법**: npm global 설치는 가장 일반적이고 검증된 설치 방법입니다.
> 대부분의 사용자는 이 방법만으로 충분합니다.

```bash
# Step 1: OMX 전역 설치
npm install -g oh-my-codex

# Step 2: 설치 확인
omx version

# Step 3: 전역 셋업 (사용자 홈에 skills, agents, hooks, 설정 설치)
omx setup --scope user

# Step 4: 설치 상태 진단
omx doctor
```

`omx doctor`에서 모든 항목이 ✅이면 전역 셋업이 완료된 것입니다.

### 2-3. 필수 전역 셋업 (한 번만 수행)

전역 셋업은 사용자 홈 디렉터리(`~/.codex/`)에 OMX 설정을 설치합니다. **모든 프로젝트에 공통으로 적용**됩니다.

```bash
# 전역 셋업 실행
omx setup --scope user
```

전역 셋업이 설치하는 항목:

| 경로 | 내용 |
|---|---|
| `~/.codex/AGENTS.md` | OMX 관리 구역이 포함된 전역 에이전트 지침 |
| `~/.codex/skills/` | OMX 설치 스킬 (37개) |
| `~/.codex/agents/` | OMX 에이전트 TOML 정의 |
| `~/.codex/hooks.json` | Native Codex hook 설정 |
| `~/.codex/config.toml` | 모델, 알림 등 설정 |

### 2-4. 필수 프로젝트별 셋업 (각 프로젝트마다 수행)

프로젝트별 셋업은 저장소 루트에 `.codex/`와 `.omx/` 디렉터리를 생성하고, 프로젝트 고유의 OMX 설정을 적용합니다.

```bash
# 프로젝트 디렉터리로 이동
cd /path/to/your/project

# Step 1: 프로젝트 범위 셋업
omx setup --scope project

# Step 2: 기존 AGENTS.md가 있으면 병합 모드 사용
omx setup --scope project --merge-agents

# Step 3: 설치 상태 확인
omx doctor

# Step 4: (선택) 경량 AGENTS.md 부트스트랩
omx agents-init .
```

프로젝트별 셋업이 생성하는 항목:

| 경로 | 내용 |
|---|---|
| `AGENTS.md` | OMX 관리 구역이 병합된 프로젝트 에이전트 지침 |
| `.codex/skills/` | 프로젝트 범위 스킬 |
| `.codex/agents/` | 프로젝트 범위 에이전트 |
| `.codex/hooks.json` | 프로젝트 범위 hook 설정 |
| `.omx/` | OMX 런타임 상태 디렉터리 |
| `.omx/state/` | 실행 모드 상태 파일 |
| `.omx/logs/` | 감사 로그 |
| `.omx/notepad.md` | 세션 간 지속 메모리 |
| `.omx/project-memory.json` | 기술 스택, 컨벤션, 아키텍처 지침 |

### 2-5. 셋업 완료 확인 체크리스트

```bash
# 전체 진단
omx doctor

# Team 기능까지 포함한 진단 (tmux 필요)
omx doctor --team

# 설치된 스킬과 에이전트 목록 확인
omx list
omx agents

# 활성 상태 확인
omx status
```

> **주의**: 기존에 수동으로 작성한 `AGENTS.md`가 있는 프로젝트에서는 반드시 `--merge-agents` 옵션을 사용하세요.
> `--force` 없이 실행하면 기존 파일을 덮어쓰지 않지만, 옵션 확인 없이 실행하면 기존 설정이 유실될 수 있습니다.

---

## 3. 설치와 업데이트

### 3-1. 사전 요구사항

- Node.js와 npm
- [OpenAI Codex CLI](https://developers.openai.com/codex/cli)
- Git
- Team/HUD를 사용할 경우 tmux가 동작하는 환경

Codex CLI 설치:

```bash
npm install -g @openai/codex
codex --version
```

OMX 설치:

```bash
npm install -g oh-my-codex
omx setup
omx doctor
```

### 3-2. 설치 범위

```bash
# 사용자 전체에 설치 (권장: 첫 설치 시)
omx setup --scope user

# 현재 프로젝트에 설치 (권장: 각 프로젝트 진입 시)
omx setup --scope project
```

기존 `AGENTS.md`를 보존하면서 OMX 관리 구역을 병합하려면:

```bash
omx setup --scope project --merge-agents
```

### 3-3. 업데이트 (권장)

> **권장 방법**: `omx update --stable`을 사용하면 npm stable 채널의 최신 버전으로 업데이트하고 setup을 자동으로 새로 고칩니다.
> 업데이트 후 반드시 `omx doctor`로 설치 상태를 확인하세요.

```bash
# 권장: stable 채널 업데이트
omx update --stable

# 또는 간편하게
omx update

# 개발 브랜치 기반 업데이트 (최신 기능 테스트 시)
omx update --dev

# 업데이트 결과 확인
omx version
omx doctor
```

릴리스 문서의 최신 버전과 로컬 `omx version`은 다를 수 있습니다. 문서의 숫자를 신뢰하기보다 두 값을 직접 확인하십시오.

업데이트 전에 [공식 Releases](https://github.com/Yeachan-Heo/oh-my-codex/releases)의 최신 변경과 호환성 메모를 확인합니다.

---

## 4. 가장 먼저 알아야 할 실행 환경

OMX 기능은 실행 표면에 따라 사용 가능 범위가 다릅니다.

| 환경 | native subagents | OMX `$skill` | OMX Team/HUD |
|---|---:|---:|---:|
| Codex CLI | 지원 | 지원 | tmux 또는 호환 런타임 연결 시 지원 |
| Codex 앱 | 지원 | 지원 | tmux Team 런타임은 직접 활성화 불가 |
| IDE 확장 | 기능별 차이 있음 | 지원 | tmux Team 런타임은 직접 활성화 불가 |
| OMX가 시작한 tmux CLI | 지원 | 지원 | 전체 지원 |

`$team`은 일반적인 프롬프트 패턴이 아니라 tmux 기반 운영 워크플로입니다. Codex 앱이나 tmux 밖의 세션에서 `$team`을 입력했다고 해서 worker pane이 자동으로 생기지는 않습니다.

Team이 필요하면 tmux가 연결된 OMX CLI에서 실행합니다.

```bash
omx
omx team 3:executor "작업 설명"
```

Codex 앱에서는 독립적인 병렬 작업에 native subagents를 사용하고, 내구성 있는 tmux worker가 꼭 필요할 때 OMX CLI로 전환하는 것이 실용적입니다.

---

## 5. 빠른 시작 (권장)

> 이 섹션은 OMX를 설치한 직후 **가장 일반적으로 사용하는 방법**을 순서대로 안내합니다.

### 5-1. 기본 진단 (권장: 매 세션 시작 전)

```bash
codex --version    # Codex CLI 버전 확인
omx version        # OMX 버전 확인
omx doctor         # 설치 상태 진단 - 모든 항목 ✅ 확인
omx status         # 현재 활성 모드 확인
```

> **팁**: `omx doctor`에서 ❌ 항목이 있으면 `omx setup --force`로 재설치하세요.

### 5-2. Codex/OMX 대화형 실행 (권장)

> **권장**: 일반적인 사용 시 `omx` 명령으로 시작하면 OMX 설정과 HUD 정책이 자동으로 적용됩니다.
> tmux 환경이면 HUD가 자동 연결되고, tmux가 아니면 `--direct` 모드로 fallback됩니다.

```bash
# 권장: OMX 설정과 HUD 정책을 적용해 Codex 시작
omx

# tmux/HUD 없이 직접 시작
omx --direct

# 기존 Codex 세션 재개
omx resume

# 높은 추론 수준으로 시작
omx --high
omx --xhigh
```

### 5-3. 스킬 실행 (권장)

> **권장**: `$skill-name` 형태로 프롬프트에 포함하면 해당 워크플로가 활성화됩니다.
> 이것이 OMX의 가장 일반적인 사용 패턴입니다.

**가장 많이 사용하는 스킬:**

| 스킬 | 설명 | 사용 시기 |
|---|---|---|
| `$autopilot` | 자율 실행 모드 | 명확한 작업을 자동으로 완료할 때 |
| `$ralph` | 끈기 있는 반복 실행 | 완료 조건이 충족될 때까지 반복할 때 |
| `$ralplan` | 합의형 계획 수립 | 위험·롤백·테스트 계획이 필요할 때 |
| `$deep-interview` | 요구사항 명확화 | 모호한 요구사항을 구체화할 때 |
| `$ultraqa` | 적대적 QA 검증 | 경계·실패·회귀 시나리오까지 검증할 때 |
| `$code-review` | 코드 리뷰 | 변경사항을 다각도로 검토할 때 |
| `$plan` | 전략적 계획 | 구현 전 계획을 세울 때 |
| `$cancel` | 활성 모드 취소 | 현재 OMX 워크플로를 종료할 때 |

**사용 예시:**

```text
$autopilot 사용자 프로필 편집 기능을 구현하고 검증해줘.

$ralph 모든 관련 테스트와 타입 검사가 통과할 때까지 이 회귀를 수정해줘.

$ralplan 결제 모듈 마이그레이션 계획을 위험과 롤백 전략까지 검토해줘.

$deep-interview 소셜 로그인 요구사항을 구현 전에 명확히 해줘.

$code-review 현재 변경사항을 버그, 회귀, 보안, 테스트 누락 순으로 검토해줘.
```

OMX 버전과 설치 모드에 따라 제공되는 스킬 목록이 달라질 수 있습니다.

```bash
omx list    # 설치된 스킬과 에이전트 목록 확인
```

### 5-4. 좋은 작업 요청 형식 (권장)

> **권장**: OpenAI 공식 best practices에 맞춰 다음 네 요소를 포함하면 결과가 안정적입니다.
> 이 형식은 Codex, OMX 워크플로 모두에서 효과적입니다.

```text
목표: 로그인 API에 rate limiting을 추가한다.
컨텍스트: src/auth와 기존 middleware 패턴을 따른다.
제약: 새 의존성을 추가하지 않고 공개 API를 바꾸지 않는다.
완료 조건: 관련 테스트, 타입 검사, 린트가 통과하고 변경 요약을 보고한다.
```

---

## 6. AGENTS.md, Skills, Agents

### 6-1. `AGENTS.md`

Codex는 작업 전에 `AGENTS.md` 지침 체인을 읽습니다.

- 전역 기본값: `~/.codex/AGENTS.md` 또는 `AGENTS.override.md`
- 저장소 규칙: 저장소 루트의 `AGENTS.md`
- 하위 경로 규칙: 작업 디렉터리에 가까운 파일이 우선
- 빌드, 테스트, 코드 스타일, 금지 사항, 완료 조건을 기록

Codex CLI의 `/init`으로 기본 파일을 만들 수 있으며, OMX에는 경량 부트스트랩 명령도 있습니다.

```bash
omx agents-init .
```

### 6-2. Skills

Skill은 `SKILL.md`와 선택적 스크립트·참고자료를 묶은 재사용 워크플로입니다.

- 명시적 호출: `$skill-name`
- 암시적 호출: skill의 `description`과 작업이 일치할 때
- Codex 공식 로컬 authoring 위치: `.agents/skills`, `~/.agents/skills`
- OMX 설치 스킬 위치는 설치 모드와 범위에 따라 `.codex/skills` 또는 사용자 Codex 홈을 사용할 수 있음

Skills와 오래된 custom prompts를 혼동하지 마십시오. OpenAI 문서에서 custom prompts는 deprecated이며, 재사용 워크플로에는 Skills 사용을 권장합니다.

### 6-3. Native subagents와 OMX agents

현재 Codex는 native subagents를 기본 지원합니다. 사용자가 "세 에이전트로 병렬 조사해"처럼 명시해야 생성됩니다.

```text
세 subagent를 사용해 병렬 검토해줘.
1. 보안 위험
2. 테스트 누락
3. 유지보수성
모두 끝날 때까지 기다린 뒤 파일 위치와 함께 통합 보고해줘.
```

Codex CLI에서는 `/agent`로 agent thread를 확인할 수 있습니다. custom agent는 사용자 `~/.codex/agents/` 또는 프로젝트 `.codex/agents/`의 TOML 파일로 정의합니다.

OMX가 제공하는 역할별 에이전트는 다음과 같이 분류됩니다:

| 분류 | 에이전트 |
|---|---|
| Build | `executor`, `test-engineer`, `debugger` |
| Review | `code-reviewer`, `critic`, `verifier`, `code-simplifier` |
| Domain | `researcher`, `dependency-expert`, `explore` |
| Product | `analyst`, `designer`, `writer` |
| Coordination | `planner`, `architect`, `git-master` |

실제 사용 가능한 목록을 고정된 문서 숫자로 추정하지 말고 확인합니다.

```bash
omx list
omx agents
```

---

## 7. 작업 방식 선택 (권장)

> **권장**: 아래 표에서 현재 상황에 맞는 방식을 선택하세요.
> 대부분의 일상 작업은 상위 4개 방식(직접 요청, $deep-interview, $ralplan, native subagents)으로 충분합니다.

| 상황 | 권장 방식 | 설명 |
|---|---|---|
| 한 파일의 명확한 수정 | **Codex에 직접 요청** (권장) | 가장 빠르고 간단한 방법. 별도 워크플로 불필요 |
| 모호한 요구사항 | `$deep-interview` (권장) | 인터뷰를 통해 범위, 제약, 수락 기준을 명확화 |
| 설계·위험·테스트 합의 | `$ralplan` (권장) | Planner → Architect → Critic 합의 플로우 |
| 독립적인 짧은 병렬 조사 | **Codex native subagents** (권장) | 읽기 중심의 병렬 작업에 가장 가벼움 |
| 명확한 작업의 자율 실행 | `$autopilot` | 인터뷰→계획→실행→QA를 묶은 자율 워크플로 |
| 최대 병렬 실행 | `$ultrawork` (`ulw`) | 5+ 동시 에이전트로 적극적 병렬화 |
| 단일 소유자 완료 반복 | `$ralph` | 완료 조건이 충족될 때까지 끈기 있게 반복 |
| tmux pane, 공유 상태, 장시간 worker | `$team` / `omx team` | 내구성 있는 tmux 기반 Team 런타임 |
| 여러 목표 장기 추적 | `$ultragoal` | durable goal 생성·재개·checkpoint |
| 적대적 시나리오 반복 검증 | `$ultraqa` | 실패·경계·회귀까지 동적 검증 |
| 반복 리서치 자동 탐색 | `omx autoresearch` | 목표 충족 시 자동 종료 |

모든 작업을 무조건 위임할 필요는 없습니다. OpenAI 공식 best practices도 직접 작업, 계획, subagents를 작업 크기에 맞게 선택하도록 안내합니다. 병렬화는 읽기·탐색·독립 검증에 특히 유리하고, 동일 파일을 여러 worker가 동시에 수정하면 충돌 비용이 커집니다.

---

## 8. OMX Team

### 8-1. 언제 사용하는가

Team은 다음 조건에서 가치가 있습니다.

- tmux worker pane을 직접 관찰해야 함
- 작업 상태와 mailbox가 세션보다 오래 유지되어야 함
- 여러 worker가 독립 작업을 수행하고 통합 증거를 남겨야 함
- 장시간 실행 후 `status`, `resume`, `shutdown`으로 수명주기를 제어해야 함

단순한 2~3개 병렬 읽기 작업은 native subagents가 더 가볍습니다.

### 8-2. 사전 확인

```bash
tmux -V
echo "$TMUX"
omx doctor --team
```

`$TMUX`가 비어 있으면 현재 리더 세션은 tmux 안에 있지 않습니다.

### 8-3. 시작과 종료

```bash
# 세 executor worker
omx team 3:executor "모듈별 변경과 검증을 병렬 수행"

# 상태 확인
omx team status <team-name>

# 기존 팀에 다시 연결
omx team resume <team-name>

# 모든 작업이 terminal 상태가 된 뒤 종료
omx team shutdown <team-name>
```

종료 전에 최소한 다음 상태를 확인합니다.

- `pending=0`
- `in_progress=0`
- `failed=0`, 또는 실패를 명시적으로 처리함

작업 중 `shutdown`을 실행하면 worker의 늦은 상태 기록이 실패할 수 있습니다.

### 8-4. worker CLI

공식 Team 문서는 `codex`, `claude`, **`gemini`** 세 가지 worker CLI를 지원합니다.

```bash
# 모든 worker를 Claude CLI로 실행
export OMX_TEAM_WORKER_CLI=claude
omx team 2:executor "문서와 테스트를 병렬 검토"

# Codex/Claude/Gemini 혼합
export OMX_TEAM_WORKER_CLI_MAP=codex,claude,gemini
omx team 3:executor "풀스택 구현"

# 모든 worker를 Gemini로
export OMX_TEAM_WORKER_CLI=gemini
omx team 2:architect "대규모 아키텍처 검토"

# 특정 모델 지정
export OMX_TEAM_WORKER_LAUNCH_ARGS="--model gemini-2.0-flash-exp"
omx team 1:executor "실험적 기능"
```

`N:executor`의 `executor`는 worker 역할이며 CLI 공급자 이름이 아닙니다. Gemini worker는 Team mode에서 공식 지원되며, `omx ask gemini` advisor 흐름과는 구분되는 별도 표면입니다.

### 8-5. 워크트리

**v0.10.0부터 Team worktree는 기본값으로 활성화**되었습니다. 각 worker는 자동으로 격리된 git worktree를 부여받으며, `--worktree` 플래그는 deprecated(no-op)입니다.

worktree 동작 방식:

1. `omx team` 시작 전 leader workspace가 커밋/스태시된 상태여야 합니다.
2. 각 worker는 `.omx/team/<name>/worktrees/worker-N`에 분리된 worktree를 받습니다.
3. worker는 자신의 worktree에만 커밋하며 write 충돌이 없습니다.
4. leader는 worker 커밋을 점진적으로 leader 브랜치에 병합합니다.
5. Team shutdown 시 worktree가 정리되고 브랜치가 삭제됩니다.

점진적 병합 전략:

| 전략 | 사용 시점 |
|---|---|
| Merge (`--no-ff -X theirs`) | worker가 leader보다 깨끗하게 ahead일 때 |
| Cherry-pick | history가 diverge했을 때 |
| Cross-worker rebase | worker 간 순차 의존성이 있을 때 |

```bash
# v0.10.0 이상: 워크트리는 기본값, 별도 플래그 불필요
omx team 3:executor "서로 독립적인 기능 구현"

# worker 워크트리 상태 확인
omx team status <team-name>
```

워크트리는 write 충돌을 방지하지만, 공유 인터페이스와 동일 파일 변경에서 발생하는 통합 충돌은 여전히 통합 검토가 필요합니다.

### 8-6. 동적 스케일링

`v0.7.0`에서 추가된 Phase 1 수동 스케일링:

```bash
# 동적 스케일링 활성화
export OMX_TEAM_SCALING_ENABLED=1
omx team 2:executor "task"

# 실행 중인 팀에 worker 추가/제거
# scale_down은 worker를 안전하게 drain한 후 제거
```

---

## 9. 주요 OMX 워크플로 (권장)

> 이 섹션은 **공식 문서에서 권장하는 4가지 핵심 워크플로 패턴**을 설명합니다.
> 대부분의 실전 작업은 이 4가지 패턴 중 하나로 처리할 수 있습니다.

### 9-1. Full-Auto from PRD (권장: 큰 기능 개발)

> **권장 워크플로**: 큰 기능 개발에 가장 적합합니다. 계획 → 병렬 실행 → 검증의 전체 사이클을 자동으로 처리합니다.

```text
$ralplan → $team → $ralph
```

1. `$ralplan`으로 Planner + Architect + Critic 합의를 통해 요구사항과 계획을 수립합니다.
2. `$team`으로 tmux worker를 병렬로 생성하여 구현합니다.
3. `$ralph`로 모든 것이 검증 완료될 때까지 지속합니다.

```text
$ralplan 결제 모듈 마이그레이션 계획을 위험과 롤백 전략까지 검토해줘.
```

계획이 승인되면:

```text
$team 3:executor 결제 모듈 마이그레이션을 백엔드, 프론트, 테스트 세 lane으로 수행해줘.
```

### 9-2. No-Brainer (권장: 명확한 작업)

> **권장 워크플로**: 범위가 명확하고 별도의 계획 합의가 필요 없을 때 사용합니다.

```text
$autopilot → $ultrawork → $ralph
```

1. `$autopilot`이 자율적으로 분석, 계획, 실행, QA를 수행합니다.
2. `$ultrawork`가 하위 작업을 병렬화합니다.
3. `$ralph`가 완료까지 반복합니다.

```text
$autopilot 사용자 프로필 편집 기능을 구현하고 검증해줘.
```

### 9-3. Fix / Debugging (권장: 버그 수정)

> **권장 워크플로**: 버그 수정과 디버깅에 최적화된 패턴입니다.

```text
$plan → $ralph → $ultraqa
```

1. `$plan`으로 문제를 조사하고 수정 전략을 세웁니다.
2. `$ralph`로 수정을 구현하고 반복 검증합니다.
3. `$ultraqa`로 적대적 시나리오까지 검증합니다.

```text
$plan 결제 NullPointerException의 원인을 분석하고 수정 전략을 세워줘.
```

### 9-4. Parallel Issue Handling (병렬 이슈 처리)

여러 이슈를 동시에 처리할 때:

```text
omx team (architect) → omx team (workers) → $ralplan → $ralph + $ultrawork → $ultraqa
```

1. architect worker로 모든 이슈를 분석하고 통합 계획을 세웁니다.
2. 별도 worktree에서 worker를 병렬 실행하여 각각 PR을 생성합니다.
3. `$ralplan`으로 충돌을 해결하고, `$ralph` + `$ultrawork`로 마무리합니다.

### 9-5. Deep Interview

요구사항이 모호하거나 "추측하지 말라"는 조건이 있을 때 사용합니다.

```text
$deep-interview 소셜 로그인 요구사항을 명확한 구현 명세로 바꿔줘.
```

명확한 범위, 비목표, 제약, 수락 기준을 얻은 뒤 계획 또는 구현으로 넘깁니다.

### 9-6. 취소

활성 OMX 모드를 종료할 때는 상태 파일을 임의 삭제하기보다 공식 취소 표면을 사용합니다.

```text
$cancel
```

또는:

```bash
omx cancel
```

---

## 10. CLI 핵심 명령

설치된 버전의 정확한 명령은 항상 다음으로 확인합니다.

```bash
omx help
```

### Core Commands

| 명령 | 용도 |
|---|---|
| `omx` | OMX 설정으로 대화형 Codex 실행 (HUD 자동 연결) |
| `omx setup` | skills, agents, hooks, 설정 설치/새로 고침. `--scope user\|project` 지원 |
| `omx doctor` | 설치 상태 진단. `--team`으로 worker 진단 포함 |
| `omx update` | stable/dev 업데이트 후 setup 새로 고침 |
| `omx version` | 버전 정보 표시 |
| `omx help` | 도움말 표시 |
| `omx status` | 활성 모드와 상태 확인 |
| `omx cancel` | 활성 실행 모드 취소 |
| `omx resume` | 이전 대화형 Codex 세션 재개 |
| `omx list` | 패키지된 skills와 agent prompt 목록 |
| `omx agents` | Codex native agent TOML 관리 |
| `omx agents-init .` | 저장소나 서브트리에 경량 AGENTS.md 부트스트랩 |

### Execution & Workflow

| 명령 | 용도 |
|---|---|
| `omx exec` | OMX 오케스트레이션 레이어를 통한 비대화형 Codex 실행 |
| `omx team` | tmux Team 수명주기 관리 |
| `omx ralph` | Ralph 활성 상태로 Codex 실행 |
| `omx ultragoal` | durable goal 생성·재개·checkpoint |
| `omx autoresearch` | 반복 리서치 자동 탐색 (목표 충족 시 자동 종료) |
| `omx ask` | Claude/Gemini advisor 호출 및 artifact 저장 |

### Inspection & Config

| 명령 | 용도 |
|---|---|
| `omx hud` | HUD 확인/감시 (`--watch`, `--json`) |
| `omx reasoning` | 추론 수준 확인/설정 (`low\|medium\|high\|xhigh`) |
| `omx sparkshell` | shell-native 검사 및 pane 요약 |
| `omx explore` | 읽기 전용 저장소 탐색 (sparkshell로 라우팅될 수 있음) |

### Hooks & Extensions

| 명령 | 용도 |
|---|---|
| `omx hooks init` | `.omx/hooks/`에 새 hook 플러그인 스캐폴드 |
| `omx hooks status` | 설치된 hook 플러그인 상태 확인 |
| `omx hooks validate` | hook 플러그인 구현 검증 |
| `omx tmux-hook init` | tmux 프롬프트 injection 초기화 |

> **참고**: 플러그인은 기본적으로 비활성화되어 있습니다. `OMX_HOOK_PLUGINS=1`로 활성화합니다.

### Launch Flags

| 플래그 | 용도 |
|---|---|
| `--high` / `--xhigh` | 높은/매우 높은 추론 수준 |
| `--yolo` | Codex yolo 모드로 실행 |
| `--madmax` | ⚠️ 위험: 승인과 샌드박스 우회 |
| `--spark` | Spark 모델로 Team worker 실행 |
| `--madmax-spark` | Spark 모델 + 승인 우회 |
| `-w, --worktree[=<name>]` | git worktree에서 격리 실행 |
| `--scope <user\|project>` | 설치 대상 제어 |
| `--force` | 강제 재설치 |
| `--dry-run` | 실행 없이 미리보기 |
| `--verbose` | 상세 출력 |

### Advisor (omx ask)

```bash
omx ask claude "이 diff의 위험을 검토해줘"
omx ask gemini "이 설계의 대안을 비교해줘"

# 역할 특화 호출
omx ask claude --agent-prompt executor "기능 X를 테스트와 함께 구현해줘"
omx ask gemini --agent-prompt planner "v0.9 롤아웃 계획 초안을 작성해줘"
```

Advisor 결과는 참고 의견입니다. 실제 저장소 변경과 검증의 책임은 현재 Codex/OMX 작업 흐름에 있습니다.

### `omx explore` 상태

`omx explore`는 공식 사이트(v0.18.8) CLI 레퍼런스에 등재되어 있습니다. 읽기 전용·shell 전용으로 제한되며 (허용 명령: `rg`, `grep`, `ls`, `find`, `wc`, `cat`, `head`, `tail`, `pwd`, `printf`), 파이프·리다이렉션·경로 이탈이 차단됩니다.

> **참고**: 로컬 `v0.18.11` AGENTS.md에는 `omx explore`가 deprecated로 표시되어 있습니다. 버전 확인 후 `omx sparkshell`을 대안으로 사용하십시오.

---

## 11. 알림 플랫폼

OMX는 세션 상태 변화(시작, 유휴, 사용자 입력 필요, 종료)를 외부 플랫폼으로 알릴 수 있습니다.

### 지원 플랫폼

| 플랫폼 | 주요 설정 | 설명 |
|---|---|---|
| **Telegram** | `botToken`, `chatId` | `parseMode` 지원 (Markdown/HTML), reply injection 가능 |
| **Discord (Webhook)** | `webhookUrl` | 단방향 알림, 커스텀 `username` 및 멘션 지원 |
| **Discord (Bot API)** | `botToken`, `channelId` | 양방향 권장, Send Messages 권한 필요 |
| **Slack** | `webhookUrl` | 커스텀 채널, username, 멘션 지원 |
| **Generic Webhook** | `url` | 임의 엔드포인트에 POST/PUT JSON, 커스텀 헤더 지원 |
| **OpenClaw** | `openclaw: { enabled: true }` | 프로그래머블 hook 오케스트레이션 |

### 이벤트

| 이벤트 | 발생 시점 |
|---|---|
| `session-start` | Codex 세션 시작 시 |
| `session-stop` | 세션 중지 시 (모드 완료 또는 사용자 인터럽트) |
| `session-end` | 세션 종료 시 |
| `session-idle` | 세션 유휴 시 (입력 대기) |
| `ask-user-question` | 에이전트가 사용자에게 질문할 때 |

### Verbosity 수준

| 수준 | 동작 |
|---|---|
| `verbose` | 모든 텍스트와 도구 호출 출력 |
| `agent` | 에이전트 호출 이벤트 (`ask-user-question` 포함) |
| `session` | 시작, 유휴, 중지, 종료 이벤트 + tmux tail snippet (기본값) |
| `minimal` | 시작, 중지, 종료만 |

### 빠른 설정

```bash
# 환경 변수로 설정 후 omx setup으로 config.toml에 저장
export OMX_TELEGRAM_BOT_TOKEN=xxx
export OMX_TELEGRAM_CHAT_ID=xxx
export OMX_DISCORD_WEBHOOK_URL=xxx
export OMX_SLACK_WEBHOOK_URL=xxx

omx setup
```

### Reply Injection

Telegram, Discord, Slack에서 답장하면 Codex 세션에 텍스트를 주입할 수 있습니다. tmux와 인증된 사용자 ID가 필요합니다.

---

## 12. 안전한 권한 설정

Codex의 **sandbox**와 **approval policy**는 서로 다른 제어입니다.

- sandbox: 기술적으로 접근·수정·네트워크 사용이 가능한 범위
- approval policy: 범위를 넘는 작업 전에 언제 사용자 승인을 받을지

권장 원칙:

1. 일반 작업은 기본 Auto/workspace 범위에서 수행합니다.
2. 외부 경로나 네트워크가 필요한 이유를 확인한 뒤 최소 범위만 허용합니다.
3. `--yolo`, OMX `--madmax`는 신뢰 경계를 크게 넓힙니다.
4. 단순히 "더 빠르다"는 이유로 full access를 기본값으로 쓰지 않습니다.
5. 중요한 변경은 git diff와 테스트로 검증합니다.

```bash
# 높은 추론 수준
omx --high
omx --xhigh

# 위험: 승인과 샌드박스 우회
omx --madmax
```

> **⚠️ `--madmax`는 성능 모드가 아니라 안전 제어 우회입니다.**

---

## 13. Windows 사용

### 13-1. Codex 자체

현재 OpenAI 공식 문서는 Windows에서 다음 방식을 모두 지원합니다.

- Windows용 Codex 앱
- Windows native Codex CLI
- IDE 확장
- WSL2 안의 Codex CLI

따라서 "Codex는 Windows native에서 동작하지 않으므로 반드시 WSL2를 사용해야 한다"는 설명은 틀립니다.

Windows native sandbox:

```toml
[windows]
sandbox = "elevated" # 권장
```

Windows 11이 권장 기준이며, WSL2는 Linux 도구 체인이 필요하거나 기존 개발 환경이 WSL에 있을 때 적합합니다.

### 13-2. OMX Team/HUD

Codex의 Windows native 지원과 OMX의 tmux Team 요구사항은 별개입니다.

- Codex 앱/CLI의 일반 작업과 native subagents: Windows native에서 가능
- OMX Team/HUD: WSL2의 tmux 또는 Windows native의 `psmux` 같은 tmux 호환 런타임 필요

WSL2 설치 (권장):

```powershell
wsl --install
```

WSL 안에서:

```bash
sudo apt-get update
sudo apt-get install -y tmux
npm install -g @openai/codex
npm install -g oh-my-codex
omx setup
omx doctor --team
```

성능이 중요하면 저장소를 `/mnt/c/...`보다 WSL 홈의 `~/code/...` 아래에 두는 것이 유리합니다.

---

## 14. 검증 중심 실전 워크플로

### 14-1. 작은 버그

```text
목표: 결제 NullPointerException을 수정한다.
컨텍스트: 오류 로그와 결제 모듈만 조사한다.
제약: 공개 API와 DB 스키마는 변경하지 않는다.
완료 조건: 재현 테스트를 추가하고 관련 테스트·타입 검사를 통과한다.
```

직접 Codex에 맡기고 별도 Team은 사용하지 않는 것이 보통 더 효율적입니다.

### 14-2. 복잡하고 모호한 기능

```text
$deep-interview 상품 리뷰 기능의 범위와 수락 기준을 명확히 해줘.
$ralplan 인터뷰 결과를 바탕으로 구현·마이그레이션·테스트 계획을 합의해줘.
```

계획이 승인된 뒤 `$ralph`, `$autopilot`, 또는 Team 중 작업 형태에 맞는 실행 방식을 선택합니다.

### 14-3. 독립적인 병렬 검토

```text
native subagent 세 개를 생성해 현재 PR을 병렬 검토해줘.
보안, 테스트 누락, 유지보수성을 각각 맡기고 모두 끝난 뒤 통합 보고해줘.
```

읽기 중심이고 결과만 통합하면 되는 작업에는 Team보다 가볍습니다.

### 14-4. 내구성 있는 병렬 구현

tmux 안에서:

```bash
omx team 3:executor "백엔드, 프론트엔드, 테스트 작업을 독립 lane으로 수행하고 검증 증거를 남겨라"
omx team status <team-name>
```

공유 파일과 인터페이스가 있으면 소유권을 먼저 나누고, 마지막에 통합 테스트를 담당하는 검증 lane을 둡니다.

### 14-5. 최종 완료 기준

- 요청한 동작이 실제로 바뀌었는가
- 관련 테스트가 새로 실행되어 통과했는가
- 타입 검사, 린트, 빌드 중 해당되는 검사가 통과했는가
- git diff에 관계없는 변경이 없는가
- 출처가 필요한 문서 주장은 공식 문서와 일치하는가
- 실행하지 못한 검사가 있다면 이유와 남은 위험을 보고했는가

---

## 15. 잘못 알려지기 쉬운 내용

| 주장 | 현재 기준 |
|---|---|
| Codex는 병렬 agent를 지원하지 않는다 | ❌ 틀림. Codex는 명시적 요청으로 native subagents를 실행할 수 있습니다. |
| OMX에서는 항상 agent에게 위임해야 한다 | ❌ 틀림. 작은 직접 작업은 직접 처리하는 것이 효율적입니다. |
| `/prompts:역할`이 유일한 agent 호출법이다 | ❌ 틀림. custom prompts는 OpenAI에서 deprecated이며, Skills와 native agents가 현재 주요 표면입니다. |
| Team worker는 worktree를 받으려면 `--worktree`가 필요하다 | ❌ 틀림. **v0.10.0부터 worktree는 기본값**입니다. `--worktree` 플래그는 deprecated(no-op)입니다. |
| worktree를 쓰면 병합 충돌이 없다 | ❌ 틀림. write 충돌은 방지되지만 공유 인터페이스 변경의 통합 충돌은 여전히 발생합니다. |
| Team worker CLI로 Gemini를 지정할 수 없다 | ❌ 틀림. **Gemini worker가 공식 지원**됩니다. `OMX_TEAM_WORKER_CLI=gemini`로 사용합니다. |
| Windows에서는 반드시 WSL2가 필요하다 | ❌ 틀림. Codex 앱/CLI는 Windows native를 지원합니다. 다만 WSL2+tmux가 Team/HUD에는 더 검증된 경로입니다. |
| `--madmax`는 최고 성능 옵션이다 | ❌ 틀림. 승인과 샌드박스를 우회하는 **위험 옵션**입니다. |
| 문서의 agent/skill 개수는 항상 고정이다 | ⚠️ 릴리스마다 바뀔 수 있습니다. `omx list`로 확인합니다. |

---

## 16. 문제 해결

### Q1. `$team`을 입력했는데 실행되지 않습니다

현재 세션이 Codex 앱 또는 tmux 밖의 CLI인지 확인합니다. Team은 attached tmux OMX CLI가 필요합니다.

```bash
echo "$TMUX"
omx doctor --team
```

### Q2. 로컬 버전이 문서와 다릅니다

```bash
omx version
omx update --stable
omx setup
omx doctor
```

### Q3. Codex가 `AGENTS.md`를 무시하는 것 같습니다

- 새 세션을 시작했는지 확인
- 현재 디렉터리와 저장소 루트를 확인
- 더 가까운 `AGENTS.override.md`가 덮어쓰는지 확인
- 파일이 비어 있지 않은지 확인
- 큰 지침 파일이 크기 제한으로 잘리지 않았는지 확인

### Q4. subagent가 생성되지 않습니다

Codex native subagents는 자동 생성되지 않습니다. "몇 개를 생성하고, 어떻게 나누고, 모두 기다린 뒤 무엇을 반환할지" 명시합니다.

### Q5. Team을 안전하게 종료하려면?

```bash
omx team status <team-name>
omx team shutdown <team-name>
```

`pending`과 `in_progress`가 0이 된 후 종료합니다.

### Q6. 설치가 꼬였습니다

```bash
omx doctor
omx doctor --team
omx setup --force
```

기존 사용자 작성 `AGENTS.md`가 있다면 무조건 덮어쓰기 전에 `--merge-agents`, 설치 범위, git diff를 확인합니다.

### Q7. 스킬이 동작하지 않습니다

```bash
# 설치된 스킬 확인
omx list

# 셋업 새로 고침
omx setup

# 프로젝트 범위로 재설치
omx setup --scope project --force
```

---

## 17. 공식 참고 링크

### OMX

- [OMX 공식 문서](https://oh-my-codex.dev/docs.html)
- [OMX 공식 GitHub 저장소](https://github.com/Yeachan-Heo/oh-my-codex)
- [OMX 공식 Releases](https://github.com/Yeachan-Heo/oh-my-codex/releases)

### OpenAI Codex

- [Codex 문서 홈](https://developers.openai.com/codex)
- [Codex Quickstart](https://developers.openai.com/codex/quickstart)
- [Codex CLI](https://developers.openai.com/codex/cli)
- [Codex CLI 기능](https://developers.openai.com/codex/cli/features)
- [Codex Best practices](https://developers.openai.com/codex/learn/best-practices)
- [AGENTS.md](https://developers.openai.com/codex/guides/agents-md)
- [Agent Skills](https://developers.openai.com/codex/skills)
- [Subagents](https://developers.openai.com/codex/subagents)
- [Subagent 개념과 모델 선택](https://developers.openai.com/codex/concepts/subagents)
- [MCP](https://developers.openai.com/codex/mcp)
- [설정 기초](https://developers.openai.com/codex/config-basic)
- [승인과 보안](https://developers.openai.com/codex/agent-approvals-security)
- [Sandbox](https://developers.openai.com/codex/concepts/sandboxing)
- [Windows](https://developers.openai.com/codex/windows)

---

## 18. OMX 버전 히스토리

> 아래 표는 [공식 Releases](https://github.com/Yeachan-Heo/oh-my-codex/releases)와 [공식 문서](https://oh-my-codex.dev/docs.html)를 기반으로 작성되었습니다.

| 버전 | 릴리스 날짜 | 주요 변경 |
|---|---|---|
| **v0.18.8** | 2026-06-01 | HUD/session ownership 내구성 강화, Autopilot replay 안전성, plugin hook/cache 엄격화, Team 런타임 safety, 릴리스/CI 증거 강화 |
| **v0.17.0** | 2026-05-12 | Hermes MCP bridge, `$design` 워크플로, plugin-mode discovery, Adversarial UltraQA 강화, runtime ownership hardening |
| **v0.16.4** | 2026-05-11 | 승인된 실행 handoff, context-pack metadata, Ralph/Ultragoal 완료 증거 필수화 |
| **v0.14.2** | 2026-04-21 | `omx question` 렌더링 안전성, 중복 MCP cleanup, deep-interview state hardening, Korean IME drift 라우팅 |
| **v0.14.1** | 2026-04-21 | Deep-interview Stop gating, question pane resilience, setup refresh recovery |
| **v0.14.0** | 2026-04-18 | 보안 hardening (경로 탐색 차단, CVE 패치), Stop-hook 정합성, Ralph 활성화/복구, explore reentry guards |
| **v0.13.1** | 2026-04-07 | Team status JSON 안정성, worker PID metadata, 릴리스 메타데이터 동기화 |
| **v0.12.0** | 2026-04-06 | Native Codex hooks (`hooks.json`), Bash guidance (`PreToolUse`/`PostToolUse`), Team 런타임 강화, Windows/tmux 안정성, 15개 언어 번역 문서 |
| **v0.11.13** | 2026-04-04 | mailbox 전달 안정성, leader nudge 큐, Windows/worktree HUD 안정성, deep-interview lock |
| **v0.11.12** | 2026-03-15 | `omx autoresearch` 추가, `omx exec` 래퍼, Team worktree 기본값, deep-interview intent-first, 점진적 merge tracking |
| **v0.10.0** | 2026-03-15 | **🔑 Team worktree 기본값 전환**, autoresearch, exec, intent-first deep-interview. 54 commits, 105 files |
| **v0.9.0** | — | `omx explore` (읽기 전용), `omx sparkshell`, `omx resume`, native archives 배포 |
| **v0.8.1** | — | Team CLI interop API, 통합 `configure-notifications` 스킬 |
| **v0.8.0** | — | `omx ask` (Claude/Gemini advisor), `$deep-interview`, `$web-clone` |
| **v0.7.6** | — | v0.7.5 핫픽스 |
| **v0.7.5** | — | `ralph auto-run` 정리, tmux session mode, per-worker 역할 라우팅 |
| **v0.7.3** | — | `$pipeline` orchestrator, `omx uninstall` |
| **v0.7.2** | — | Team shutdown `--force` 파싱 수정, `shutdown_gate_forced` 감사 이벤트 |
| **v0.7.0** | — | **🔑 Major**: 동적 스케일링, RALPLAN-DR, keyword trigger registry (31개), 알림 전면 개편, OpenClaw, MCP bootstrap, 1,472 tests / 308 suites |
| **v0.6.x** | — | 혼합 Team worker CLI (`OMX_TEAM_WORKER_CLI_MAP`), leader nudge fallback, Claude worker 시작 수정 |
| **v0.5.x** | — | Worktree orchestration, `omx ralph` CLI, cross-worktree state resolution, 보안 강화 |
| **v0.5.0** | — | Scope-aware setup (user/project), Spark routing, 카탈로그 정리 (deprecated 스킬 제거) |
| **v0.4.x** | — | Hook extensibility runtime, auto-nudge stall detection, worker-idle aggregation, Codex native multi-agent 등록 |

---

## 19. 개정 이력

| 날짜 | 버전 | 변경 내용 |
|---|---|---|
| 2026-06-12 | 초판 | 공식 문서 및 `omx help` 기반 초판 작성 (OMX v0.18.10 환경) |
| 2026-06-14 | 개정 1 | 공식 사이트 재검토 반영: Gemini worker, worktree 기본값, ultrawork, autoresearch, hooks, exec, 알림 플랫폼, omx explore 상태 명확화 |
| 2026-06-19 | 개정 2 | **구조적 개편**: ① **초기 프로젝트 셋업 가이드** 신설 (전역/프로젝트별 필수 셋업 단계별 안내), ② 목차별 **권장** 마커 추가 및 상세 설명 보강 (빠른 시작, 작업 방식 선택, 워크플로), ③ **OMX 버전 히스토리** 섹션 신설 (v0.4.x~v0.18.8 전체 릴리스 정리), ④ 공식 문서(oh-my-codex.dev/docs.html v0.18.8)와 GitHub Releases 교차 검증으로 내용 업데이트, ⑤ CLI 명령 테이블 카테고리별 재구성, ⑥ Team 동적 스케일링/점진적 병합 전략 추가, ⑦ Agent 역할 분류표 추가, ⑧ 알림 이벤트/Verbosity 상세 테이블 추가, ⑨ Q7 (스킬 미동작) 문제 해결 추가, ⑩ 불필요한 중복 내용 제거 및 가독성 개선 |

*최종 업데이트: 2026년 6월 19일 (기준 OMX 버전: v0.18.8 공식 문서 + v0.18.11 로컬)*
