# FSD v1.0.046 - Slash Command Suggestions (인라인 명령어 제안)

## 문서 정보
- **버전**: v1.0.046
- **작성일**: 2026-02-25
- **상태**: Draft
- **대상 파일**: 
  - `src/cli_input.py`
  - `src/command_registry.py` (신규)
  - `gemini-ai-chat-code01.py`
  - `claude-ai-chat-code01.py`
  - `gen-ai-chat-code01.py`
- **참조**: Gemini CLI의 Slash Command Suggestion UI

---

## 1. 개요

### 1.1 목적
명령 프롬프트에서 `/` 입력 시 사용 가능한 명령어 목록을 **프롬프트 하단에 인라인으로 표시**하고, 추가 문자 입력 시 목록을 **실시간 필터링**하여 보여주는 기능을 구현합니다. Google Gemini CLI의 슬래시 명령어 제안 UI를 참고합니다.

### 1.2 배경
현재 시스템은 `readline` 기반 Tab 자동완성만 지원합니다 (FSD v1.0.031 참조).
- `/` 입력 후 Tab을 눌러야 명령어 목록을 볼 수 있음
- 어떤 명령어가 있는지 사전에 파악하기 어려움
- `/help`를 별도로 실행해야 전체 명령어 확인 가능

Gemini CLI는 `/` 입력만으로 전체 명령어 목록을 프롬프트 하단에 표시하고, 추가 입력 시 실시간 필터링합니다.

### 1.3 범위
- `/` 입력 시 명령어 목록 인라인 표시
- 추가 입력 시 실시간 필터링 (예: `/s` → `/save`, `/save_history`, `/stream`, `/shell`, `/shell!`)
- 방향키(↑↓)로 명령어 선택, Tab/Enter로 자동 입력
- 하단 상태 바에 작업 경로 및 모델 정보 표시
- 스크롤 인디케이터 및 페이지네이션

---

## 2. 요구사항

### 2.1 기능 요구사항

#### FR-1: 명령어 제안 목록 트리거
| 조건 | 동작 |
|------|------|
| 프롬프트에 `/` 입력 | 전체 명령어 목록 표시 |
| 프롬프트에 `/s` 입력 | `/s`로 시작하는 명령어만 필터링 표시 |
| 프롬프트에 `/save` 입력 | `/save`로 시작하는 명령어만 필터링 표시 |
| 필터 결과가 0건 | 제안 목록 숨김 |
| `/` 없이 일반 텍스트 입력 | 제안 목록 표시하지 않음 |
| 명령어 입력 후 스페이스 | 제안 목록 닫힘 (인자 입력 단계) |

#### FR-2: 명령어 목록 표시 형식

Gemini CLI 레이아웃을 참고한 전체 화면 구성:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  > /█                                         ← 입력 프롬프트   │
│                                                                 │
│  files            프로젝트 파일 목록            ← 명령어 목록     │
│  tree             프로젝트 구조 보기                              │
│  read             파일 읽기                                      │
│  context          컨텍스트 포함하여 질문                          │
│  save             AI 응답에서 파일 추출 및 저장                   │
│  workspace        작업 디렉토리 변경                              │
│  stream           스트리밍 모드 활성화                            │
│  nostream         논스트리밍 모드 활성화                          │
│  ▼                                             ← 스크롤 표시    │
│  (1/28)                                        ← 페이지네이션   │
│─────────────────────────────────────────────────────────────────│
│  C:\path\to\project        /model Gemini 3     ← 하단 상태 바   │
└─────────────────────────────────────────────────────────────────┘
```

**레이아웃 구성 요소:**

| 요소 | 위치 | 설명 |
|------|------|------|
| 입력 프롬프트 | 상단 | `> /` 형태, 사용자 입력 영역 |
| 명령어 목록 | 프롬프트 하단 | 명령어 이름(좌측 정렬) + 설명(우측) |
| 스크롤 인디케이터 | 목록 하단 | `▼` — 아래에 더 많은 항목이 있음을 표시 |
| 페이지네이션 | 스크롤 표시 아래 | `(1/28)` — 현재 페이지/전체 항목 수 |
| 하단 상태 바 | 화면 최하단 | 좌측: 작업 경로, 우측: 모델 정보 |

#### FR-3: 실시간 필터링

`/` 뒤에 문자를 추가 입력하면 **해당 접두사(prefix)와 일치하는 명령어만 필터링**하여 표시합니다.

**필터링 예시 `/s` 입력:**
```
  > /s█

  save             AI 응답에서 파일 추출 및 저장
  save_history     대화 히스토리 파일로 저장
  stream           스트리밍 모드 활성화
  shell            쉘 명령어 실행 (안전 모드)
  shell!           쉘 명령어 실행 (위험 허용)
  (5/28)
```

**필터링 예시 `/sa` 입력:**
```
  > /sa█

  save             AI 응답에서 파일 추출 및 저장
  save_history     대화 히스토리 파일로 저장
  (2/28)
```

**필터링 예시 `/te` 입력:**
```
  > /te█

  template         시스템 프롬프트 템플릿 변경
  template_list    사용 가능한 템플릿 목록
  template_reset   기본 시스템 프롬프트로 복귀
  tokens           토큰 사용량 확인
  tree             프로젝트 구조 보기
  (5/28)
```

**필터 동작 규칙:**
| 입력 | 필터 결과 | 설명 |
|------|----------|------|
| `/` | 28개 전체 | 전체 명령어 표시 |
| `/s` | 5개 | `s`로 시작하는 명령어 |
| `/sa` | 2개 | `sa`로 시작하는 명령어 |
| `/save` | 2개 | `save`로 시작하는 명령어 (`save`, `save_history`) |
| `/save_` | 1개 | `save_`로 시작하는 명령어 (`save_history`만) |
| `/xyz` | 0개 | 일치 없음 → 제안 목록 숨김 |

#### FR-4: 명령어 선택 및 입력
| 키 입력 | 동작 |
|---------|------|
| `↑` / `↓` | 제안 목록에서 명령어 선택 (하이라이트 이동) |
| `Tab` | 선택된 명령어를 프롬프트에 자동 입력 |
| `Enter` | 선택된 명령어를 프롬프트에 입력 후 실행 |
| `ESC` | 제안 목록 닫기 |
| 일반 문자 입력 | 실시간 필터링 계속 |
| `Backspace` | `/`까지 지우면 전체 목록, `/` 자체를 지우면 제안 닫기 |

#### FR-5: 스크롤 인디케이터 및 페이지네이션

목록이 화면에 모두 표시되지 않을 경우:
- `▼` : 아래에 더 많은 항목이 존재함을 표시
- `▲` : 위에 더 많은 항목이 존재함을 표시 (스크롤 다운 후)
- `(현재표시위치/전체항목수)` : 페이지네이션 정보

```
  save             AI 응답에서 파일 저장
  save_history     히스토리 파일로 저장
  stream           스트리밍 모드 활성화
  ▼
  (1/28)
```

#### FR-6: 하단 상태 바

화면 최하단에 고정된 상태 바를 표시합니다:

```
  C:\03_sources\...\p3-ai-code-chat-messages            /model Gemini 3
  ├── 좌측: 작업 경로 (workspace)              ├── 우측: 현재 모델 정보
```

| 위치 | 표시 내용 | 예시 |
|------|----------|------|
| 좌측 | 현재 작업 디렉토리 경로 (긴 경우 `...`으로 축약) | `C:\03_sources\...\p3-ai-code-chat-messages` |
| 우측 | 현재 사용 중인 AI 모델 정보 | `/model Gemini 3` |

### 2.2 비기능 요구사항

#### NFR-1: 성능
- 키 입력마다 필터링이 수행되므로 지연 없이 즉시 반응해야 함
- 명령어 목록이 30개 미만이므로 성능 이슈 없을 것으로 예상

#### NFR-2: 하위 호환성
- 기존 Tab 자동완성 기능 유지
- 기존 `readline` 기반 히스토리 기능 유지
- `prompt_toolkit` 미설치 환경에서는 기존 readline 방식으로 폴백

#### NFR-3: 플랫폼 호환성
- Windows, Linux, macOS에서 동작
- `prompt_toolkit` 라이브러리로 크로스 플랫폼 지원

---

## 3. 설계

### 3.1 명령어 레지스트리

명령어와 설명을 중앙에서 관리하는 레지스트리를 신설합니다:

```python
# src/command_registry.py (신규)

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CommandInfo:
    """슬래시 명령어 정보"""
    name: str           # 명령어 이름 (예: '/save')
    description: str    # 명령어 설명 (예: 'AI 응답에서 파일 추출 및 저장')
    usage: str = ""     # 사용법 (예: '/save')


class CommandRegistry:
    """슬래시 명령어 레지스트리"""
    
    def __init__(self):
        self._commands: List[CommandInfo] = []
        self._register_default_commands()
    
    def _register_default_commands(self):
        """기본 명령어 등록"""
        self._commands = [
            CommandInfo('/files', '프로젝트 파일 목록', '/files [ext]'),
            CommandInfo('/tree', '프로젝트 구조 보기', '/tree'),
            CommandInfo('/read', '파일 읽기', '/read <pattern>'),
            CommandInfo('/context', '컨텍스트 포함하여 질문', '/context <pattern> [질문]'),
            CommandInfo('/save', 'AI 응답에서 파일 추출 및 저장', '/save'),
            CommandInfo('/workspace', '작업 디렉토리 변경', '/workspace [path]'),
            CommandInfo('/stream', '스트리밍 모드 활성화', '/stream'),
            CommandInfo('/nostream', '논스트리밍 모드 활성화', '/nostream'),
            CommandInfo('/history', '대화 히스토리 보기', '/history'),
            CommandInfo('/clear', '대화 히스토리 초기화', '/clear'),
            CommandInfo('/save_history', '대화 히스토리 파일로 저장', '/save_history [name]'),
            CommandInfo('/load_history', '저장된 히스토리 로드', '/load_history <name>'),
            CommandInfo('/list_history', '저장된 히스토리 목록', '/list_history'),
            CommandInfo('/run', '마지막 응답의 코드 실행', '/run [lang]'),
            CommandInfo('/diff', '코드 변경사항 Diff 표시', '/diff'),
            CommandInfo('/apply', 'Diff 내용을 파일에 적용', '/apply'),
            CommandInfo('/multiline', '멀티라인 입력 모드', '/multiline'),
            CommandInfo('/tokens', '토큰 사용량 확인', '/tokens'),
            CommandInfo('/shell', '쉘 명령어 실행 (안전 모드)', '/shell <cmd>'),
            CommandInfo('/shell!', '쉘 명령어 실행 (위험 허용)', '/shell! <cmd>'),
            CommandInfo('/template', '시스템 프롬프트 템플릿 변경', '/template <name>'),
            CommandInfo('/template_list', '사용 가능한 템플릿 목록', '/template_list'),
            CommandInfo('/template_reset', '기본 시스템 프롬프트로 복귀', '/template_reset'),
            CommandInfo('/watch', '파일 변경 감시 시작', '/watch <pattern>'),
            CommandInfo('/unwatch', '파일 변경 감시 중지', '/unwatch <pattern>'),
            CommandInfo('/watch_list', '감시 중인 패턴 목록', '/watch_list'),
            CommandInfo('/help', '도움말 보기', '/help'),
            CommandInfo('/quit', '종료', '/quit'),
        ]
    
    def get_commands(self) -> List[CommandInfo]:
        """전체 명령어 목록 반환"""
        return self._commands
    
    def get_command_names(self) -> List[str]:
        """명령어 이름만 반환"""
        return [cmd.name for cmd in self._commands]
    
    def filter_commands(self, prefix: str) -> List[CommandInfo]:
        """접두사로 명령어 필터링"""
        return [cmd for cmd in self._commands if cmd.name.startswith(prefix)]
```

### 3.2 CLIInputHandler 개선 (prompt_toolkit 기반)

```python
# src/cli_input.py 개선안

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import HTML
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False

from src.command_registry import CommandRegistry


class SlashCommandCompleter(Completer):
    """슬래시 명령어 자동완성 + 인라인 제안"""
    
    def __init__(self, registry: CommandRegistry):
        self.registry = registry
    
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        
        # 명령어 부분만 동작 (인자 입력 중이면 제안하지 않음)
        if ' ' in text:
            return
        
        if not text.startswith('/'):
            return
        
        # 접두사 필터링
        matched = self.registry.filter_commands(text)
        
        for cmd in matched:
            yield Completion(
                cmd.name,
                start_position=-len(text),
                display=cmd.name,
                display_meta=cmd.description,
            )


class CLIInputHandler:
    """CLI 입력 처리 클래스"""
    
    def __init__(self, history_file: str = ".cli_history"):
        self.registry = CommandRegistry()
        
        if PROMPT_TOOLKIT_AVAILABLE:
            # prompt_toolkit 세션 (타이핑 중 자동 제안 활성화)
            self.session = PromptSession(
                completer=SlashCommandCompleter(self.registry),
                complete_while_typing=True,
            )
            self._use_prompt_toolkit = True
        else:
            # readline 폴백
            self._use_prompt_toolkit = False
            self._setup_readline(history_file)
    
    def get_input(self, prompt: str = "👤 You: ") -> str:
        """사용자 입력 받기"""
        try:
            if self._use_prompt_toolkit:
                return self.session.prompt(prompt).strip()
            else:
                return input(prompt).strip()
        except EOFError:
            return "/quit"
        except KeyboardInterrupt:
            print()
            return ""
```

### 3.3 하단 상태 바 구현

`prompt_toolkit`의 `bottom_toolbar` 기능을 활용하여 하단 상태 바를 구현합니다:

```python
from prompt_toolkit.formatted_text import HTML

class CLIInputHandler:
    def __init__(self, workspace: str = "", model_name: str = ""):
        self.workspace = workspace
        self.model_name = model_name
        
        self.session = PromptSession(
            completer=SlashCommandCompleter(self.registry),
            complete_while_typing=True,
            bottom_toolbar=self._get_toolbar,  # 하단 상태 바
        )
    
    def _get_toolbar(self):
        """하단 상태 바 생성"""
        # 경로가 길면 축약
        path = self.workspace
        if len(path) > 40:
            path = path[:10] + "\\..." + path[-27:]
        
        return HTML(
            f'<b>{path}</b>'
            f'<right><b>/model {self.model_name}</b></right>'
        )
```

### 3.4 의존성 변경

#### requirements.txt 추가
```diff
+ prompt_toolkit>=3.0.0
```

---

## 4. 테스트 시나리오

### 4.1 명령어 제안 동작 테스트
| # | 시나리오 | 입력 | 기대 결과 |
|---|---------|------|----------|
| 1 | 전체 목록 표시 | `/` 입력 | 전체 명령어 목록 (28개) 표시 |
| 2 | 접두사 필터링 | `/s` 입력 | `save, save_history, stream, shell, shell!` 5개 표시 |
| 3 | 상세 필터링 | `/sa` 입력 | `save, save_history` 2개 표시 |
| 4 | 매칭 없음 | `/xyz` 입력 | 제안 목록 숨김 |
| 5 | 일반 텍스트 | `hello` 입력 | 제안 목록 표시하지 않음 |
| 6 | 인자 입력 | `/save ` (스페이스 포함) 입력 | 제안 목록 숨김 |

### 4.2 키 조작 테스트
| # | 시나리오 | 동작 | 기대 결과 |
|---|---------|------|----------|
| 1 | 방향키 선택 | `/` → `↓` 반복 | 하이라이트가 아래로 이동 |
| 2 | Tab 선택 | `/s` → `↓` → `Tab` | 선택된 명령어가 프롬프트에 자동 입력 |
| 3 | Enter 실행 | `/s` → `↓` → `Enter` | 선택된 명령어 실행 |
| 4 | ESC 닫기 | `/` → `ESC` | 제안 목록 닫힘 |
| 5 | Backspace | `/s` → `Backspace` | `/` 상태로 돌아가 전체 목록 표시 |

### 4.3 상태 바 테스트
| # | 시나리오 | 기대 결과 |
|---|---------|----------|
| 1 | 초기 표시 | 하단에 작업 경로(좌측) + 모델명(우측) 표시 |
| 2 | `/workspace` 변경 후 | 좌측 경로 정보 갱신 |
| 3 | 긴 경로 | `C:\03_sources\...\project-name` 형태로 축약 표시 |

### 4.4 호환성 테스트
| # | 시나리오 | 환경 | 기대 결과 |
|---|---------|------|----------|
| 1 | prompt_toolkit 설치 | Windows/Linux/macOS | 인라인 제안 UI + 상태 바 동작 |
| 2 | prompt_toolkit 미설치 | Windows/Linux/macOS | readline Tab 자동완성 폴백 |

---

## 5. 파일 변경 목록

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/command_registry.py` | **신규** | 명령어 레지스트리 (이름, 설명, 사용법 관리) |
| `src/cli_input.py` | **수정** | prompt_toolkit 기반 인라인 제안 + 상태 바 적용 |
| `src/__init__.py` | **수정** | `CommandRegistry` export 추가 |
| `gemini-ai-chat-code01.py` | **수정** | CLIInputHandler에 workspace, model 정보 전달 |
| `claude-ai-chat-code01.py` | **수정** | 동일 적용 |
| `gen-ai-chat-code01.py` | **수정** | 동일 적용 |
| `requirements.txt` | **수정** | `prompt_toolkit>=3.0.0` 추가 |

---

## 6. 승인

- [ ] 개발자 검토
- [ ] 테스트 완료
- [ ] 문서 업데이트 완료
