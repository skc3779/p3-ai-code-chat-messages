# FSD v1.0.047 - Gemini CLI 스타일 TUI 개선

## 문서 정보
- **버전**: v1.0.047
- **작성일**: 2026-02-25
- **상태**: Draft
- **선행 문서**: FSD v1.0.046 (Slash Command Suggestions)
- **대상 파일**: 
  - `src/cli_input.py`
  - `src/command_registry.py`
  - `gemini-ai-chat-code01.py`
  - `claude-ai-chat-code01.py`
  - `gen-ai-chat-code01.py`
- **참조**: Gemini CLI TUI

---

## 1. 개요

### 1.1 목적
FSD v1.0.046에서 구현한 슬래시 명령어 제안 기능의 **TUI(Terminal User Interface)를 Gemini CLI와 동일한 스타일**로 개선합니다.

### 1.2 현재 문제 (v1.0.046)

FSD v1.0.046 구현은 `prompt_toolkit`의 기본 드롭다운 Completer를 사용하여 Gemini CLI와 시각적으로 다릅니다.

| 항목 | v1.0.046 현재 | Gemini CLI (목표) |
|------|-------------|------------------|
| 명령어 목록 위치 | 입력 **위에** 팝업 박스로 표시 | 입력 **아래에** 인라인으로 표시 |
| 명령어 표시 형식 | `/save` (슬래시 접두사 포함) | `save` (슬래시 없이 이름만) |
| 프롬프트 스타일 | `👤 You: /s` | `> /s` |
| 목록 스타일 | 팝업 드롭다운 (테두리 있음) | 플랫 인라인 목록 (테두리 없음) |
| 명령어 이름 스타일 | 일반 텍스트 | **볼드/컬러** (강조) |
| 설명 스타일 | 메타 텍스트 (우측 희미) | 일반 텍스트 (명령어 옆 나란히) |
| 스크롤 인디케이터 | 없음 | `▼` 아이콘 |
| 페이지네이션 | 없음 | `(1/16)` 표시 |
| 상단 바 | 없음 | `? for shortcuts` + 파일 정보 |
| 하단 상태 바 | 2영역 (경로, 모델) | 3영역 (경로, 중앙 정보, 모델) |

### 1.3 범위
- 명령어 제안 목록을 입력 **아래에 인라인**으로 표시
- 명령어 이름에서 `/` 접두사 제거하여 표시
- 명령어 이름에 볼드/컬러 스타일 적용
- 스크롤 인디케이터(`▼`) 및 페이지네이션(`(N/M)`) 추가
- 하단 상태 바 3영역 구성 개선
- 프롬프트 스타일 변경 (`> `)

---

## 2. 요구사항

### 2.1 기능 요구사항 (변경/추가분)

#### FR-1: 명령어 목록 인라인 표시 (핵심 변경)

**현재 (v1.0.046)** — prompt_toolkit 기본 드롭다운:
```
  ┌──────────────────────────────────────────┐
  │ /save             AI 응답에서 파일 저장   │  ← 입력 위에 팝업
  │ /stream           스트리밍 모드 활성화    │
  │ /save_history     히스토리 파일로 저장    │
  │ /shell            쉘 명령어 실행 (안전)   │
  │ /shell!           쉘 명령어 실행 (위험)   │
  └──────────────────────────────────────────┘
  👤 You: /s█
```

**목표 (v1.0.047)** — Gemini CLI 스타일 인라인:
```
  > /s█
                                                         ← 입력 아래에 인라인
  save             AI 응답에서 파일 추출 및 저장
  stream           스트리밍 모드 활성화
  save_history     대화 히스토리 파일로 저장
  shell            쉘 명령어 실행 (안전 모드)
  shell!           쉘 명령어 실행 (위험 허용)
  ▼
  (5/29)
```

**구현 포인트:**
- `prompt_toolkit`의 기본 `CompletionMenu`를 사용하지 않고 **커스텀 레이아웃** 구성
- 입력 아래 영역에 필터링된 명령어 목록을 직접 렌더링
- `prompt_toolkit`의 `HSplit`, `Window`, `FormattedTextControl` 등을 활용

#### FR-2: 명령어 표시 형식 변경

**현재**: `/save`, `/stream` (슬래시 접두사 포함)
**변경**: `save`, `stream` (슬래시 없이 이름만 표시)

```
  save             AI 응답에서 파일 추출 및 저장     ← / 없이 이름만
  stream           스트리밍 모드 활성화
  save_history     대화 히스토리 파일로 저장
```

> **주의**: 표시만 `/` 없이 하고, 실제 자동완성 입력값은 `/save` 형태를 유지

#### FR-3: 명령어 이름 볼드/컬러 스타일

Gemini CLI에서는 명령어 이름이 **밝은 색상(볼드)**으로 강조되고, 설명은 일반 색상입니다.

```
  save             AI 응답에서 파일 추출 및 저장
  ^^^^             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  볼드/컬러         일반 색상 (회색 또는 dim)
```

`prompt_toolkit`의 `FormattedText` 또는 `HTML` 스타일링 활용:
```python
# 예시
('class:command-name', 'save')
('class:command-desc', '  AI 응답에서 파일 추출 및 저장')
```

#### FR-4: 프롬프트 스타일 변경

**현재**: `👤 You: /s`
**변경**: `> /s`

```python
# 현재
user_input = session.prompt("👤 You: ")

# 변경
user_input = session.prompt("> ")
```

> **참고**: 기존 `👤 You:` 프롬프트를 사용하는 메인 파일 3개 모두 변경 필요

#### FR-5: 스크롤 인디케이터 및 페이지네이션

목록 하단에 표시:
```
  save             AI 응답에서 파일 추출 및 저장
  stream           스트리밍 모드 활성화
  save_history     대화 히스토리 파일로 저장
  shell            쉘 명령어 실행 (안전 모드)
  shell!           쉘 명령어 실행 (위험 허용)
  ▼                                                  ← 아래에 더 있음
  (1/16)                                             ← 페이지/전체
```

| 표시 | 상태 |
|------|------|
| `▼` | 아래에 더 많은 항목 존재 |
| `▲` | 위에 더 많은 항목 존재 (스크롤 다운 후) |
| `(1/16)` | 현재 페이지 위치 / 필터 결과 수 |

- 한 번에 표시할 최대 항목 수: **8개** (Gemini CLI 기준)
- 목록이 8개 이하이면 `▼` 숨김

#### FR-6: 하단 상태 바 3영역

**현재 (v1.0.046)** — 2영역:
```
  C:\03_sources\...\p3-ai-code-chat-messages                    /model gemini-3-pro-preview
  ├── 좌측: 경로                                                ├── 우측: 모델
```

**변경 (v1.0.047)** — Gemini CLI 스타일 3영역:
```
  C:\03_sources\...\p3-ai-code-chat-messages     no sandbox (see /docs)     /model Auto (Gemini 3)
  ├── 좌측: 경로                     ├── 중앙: 상태 정보        ├── 우측: 모델
```

| 위치 | 내용 | 본 프로젝트 적용 |
|------|------|-----------------|
| 좌측 | 작업 경로 | `C:\03_sources\...\p3-ai-code-chat-messages` |
| 중앙 | 부가 정보 | 스트리밍 모드 (`streaming` / `nostream`) |
| 우측 | 모델 정보 | `/model <모델명>` |

```python
def _get_toolbar(self):
    return HTML(
        f' <b>{path}</b>'
        f'         <style bg="gray">{center_info}</style>'
        f'<right><b>/model {self.model_name}</b></right>'
    )
```

#### FR-7: 상단 정보 바 (선택사항)

Gemini CLI에는 상단에도 정보 바가 있습니다:
```
  ? for shortcuts                                              1 GEMINI.md file
  shift+tab to accept edits
```

본 프로젝트 적용:
```
  /help로 도움말                                               streaming mode
```

> **우선순위**: Low — 하단 상태 바와 인라인 목록 개선이 더 중요

---

## 3. 설계

### 3.1 prompt_toolkit 커스텀 레이아웃 (핵심)

`prompt_toolkit`의 기본 Completer 드롭다운 대신 **커스텀 `full_screen` 또는 `Layout`**을 사용하여 Gemini CLI와 동일한 인라인 목록을 구현합니다.

#### 3.1.1 접근 방식: `prompt_toolkit` Application 레이아웃

```python
from prompt_toolkit.layout import Layout, HSplit, Window, FormattedTextControl
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.filters import Condition
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import FormattedText


class GeminiStyleCLI:
    """Gemini CLI 스타일 TUI"""
    
    def __init__(self, registry, workspace="", model_name=""):
        self.registry = registry
        self.workspace = workspace
        self.model_name = model_name
        self.current_filter = ""
        self.filtered_commands = []
        self.selected_index = 0
        self.max_visible = 8  # 한 번에 표시할 최대 항목 수
        self.scroll_offset = 0
        
        self._build_layout()
    
    def _build_layout(self):
        """레이아웃 구성"""
        # 입력 영역
        self.input_area = TextArea(
            prompt="> ",
            multiline=False,
        )
        
        # 명령어 제안 영역 (입력 아래)
        self.suggestion_control = FormattedTextControl(
            self._get_suggestion_text
        )
        
        # 하단 상태 바
        self.toolbar_control = FormattedTextControl(
            self._get_toolbar_text
        )
        
        # 레이아웃
        self.layout = Layout(
            HSplit([
                # 입력 영역
                self.input_area,
                # 명령어 제안 (조건부 표시)
                ConditionalContainer(
                    Window(self.suggestion_control),
                    filter=Condition(lambda: len(self.filtered_commands) > 0)
                ),
                # 하단 상태 바
                Window(self.toolbar_control, height=1),
            ])
        )
    
    def _get_suggestion_text(self):
        """명령어 제안 목록 텍스트 생성"""
        result = []
        
        # 표시할 명령어 범위 계산
        visible = self.filtered_commands[
            self.scroll_offset:self.scroll_offset + self.max_visible
        ]
        
        for i, cmd in enumerate(visible):
            actual_index = self.scroll_offset + i
            display_name = cmd.name.lstrip('/')  # / 제거
            
            # 선택된 항목 하이라이트
            if actual_index == self.selected_index:
                style = 'class:command-selected'
            else:
                style = 'class:command-name'
            
            result.append((style, f"  {display_name:<18}"))
            result.append(('class:command-desc', f"{cmd.description}\n"))
        
        # 스크롤 인디케이터
        total = len(self.filtered_commands)
        if self.scroll_offset + self.max_visible < total:
            result.append(('class:scroll-indicator', "  ▼\n"))
        
        # 페이지네이션
        page = (self.scroll_offset // self.max_visible) + 1
        total_pages = (total + self.max_visible - 1) // self.max_visible
        result.append(('class:pagination', f"  ({page}/{total_pages})\n"))
        
        return FormattedText(result)
    
    def _get_toolbar_text(self):
        """하단 상태 바 텍스트"""
        path = self.workspace
        if len(path) > 40:
            path = path[:15] + "\\..." + path[-22:]
        
        model_info = f"/model {self.model_name}" if self.model_name else ""
        center_info = "streaming"
        
        return FormattedText([
            ('class:toolbar-path', f" {path}"),
            ('class:toolbar-center', f"     {center_info}"),
            ('class:toolbar-model', f"     {model_info}"),
        ])
```

#### 3.1.2 스타일 정의

```python
from prompt_toolkit.styles import Style

gemini_style = Style.from_dict({
    # 명령어 이름 (볼드/컬러)
    'command-name': 'bold #d4d4d4',
    'command-selected': 'bold bg:#3a3a3a #ffffff',
    'command-desc': '#808080',
    
    # 스크롤 & 페이지네이션
    'scroll-indicator': '#606060',
    'pagination': '#606060',
    
    # 하단 상태 바
    'toolbar-path': 'bold #a0a0a0',
    'toolbar-center': '#707070',
    'toolbar-model': 'bold #a0a0a0',
})
```

#### 3.1.3 키 바인딩

```python
kb = KeyBindings()

@kb.add('up')
def _(event):
    """명령어 선택 위로 이동"""
    cli.selected_index = max(0, cli.selected_index - 1)
    # 스크롤 조정
    if cli.selected_index < cli.scroll_offset:
        cli.scroll_offset = cli.selected_index

@kb.add('down')
def _(event):
    """명령어 선택 아래로 이동"""
    total = len(cli.filtered_commands)
    cli.selected_index = min(total - 1, cli.selected_index + 1)
    # 스크롤 조정
    if cli.selected_index >= cli.scroll_offset + cli.max_visible:
        cli.scroll_offset = cli.selected_index - cli.max_visible + 1

@kb.add('tab')
def _(event):
    """선택된 명령어를 입력에 적용"""
    if cli.filtered_commands:
        cmd = cli.filtered_commands[cli.selected_index]
        event.app.current_buffer.text = cmd.name + ' '
        event.app.current_buffer.cursor_position = len(cmd.name) + 1

@kb.add('escape')
def _(event):
    """제안 목록 닫기"""
    cli.filtered_commands = []
```

### 3.2 대안: prompt_toolkit Completer 커스터마이징

`Application` 전체를 커스텀하지 않고, 기존 `PromptSession`의 Completer 표시 방식만 변경하는 접근:

```python
from prompt_toolkit.layout.menus import CompletionsMenu

# 드롭다운 대신 MultiColumnCompletionsMenu 사용
session = PromptSession(
    completer=SlashCommandCompleter(registry),
    complete_while_typing=True,
    # 완성 메뉴를 아래에 표시하도록 커스텀
    complete_style=CompleteStyle.MULTI_COLUMN,
)
```

> **한계**: `prompt_toolkit`의 내장 CompletionsMenu는 레이아웃 위치(위/아래)를 간단히 전환할 수 있지만, Gemini CLI처럼 `/` 없이 이름만 표시하거나 페이지네이션을 추가하기 어려움.
> **결론**: 커스텀 레이아웃(3.1 방식) 권장.

---

## 4. 비교 다이어그램

### 4.1 v1.0.046 (현재) vs v1.0.047 (목표)

```
=== v1.0.046 (현재 구현) ===                 === v1.0.047 (Gemini CLI 스타일 목표) ===

  ┌─────────────────────────────┐
  │ /save       AI 응답 저장    │             > /s█
  │ /stream     스트리밍 활성    │
  │ /save_history 히스토리 저장  │             save             AI 응답에서 파일 추출 및 저장
  │ /shell      쉘 실행 (안전)  │             stream           스트리밍 모드 활성화
  │ /shell!     쉘 실행 (위험)  │             save_history     대화 히스토리 파일로 저장
  └─────────────────────────────┘             shell            쉘 명령어 실행 (안전 모드)
  👤 You: /s█                                 shell!           쉘 명령어 실행 (위험 허용)
                                              ▼
                                              (1/16)
  C:\path\to\project  /model gemini...        C:\path\to\project    streaming    /model gemini...
```

### 4.2 변경 항목 요약

```
  [프롬프트]     👤 You:  →  >
  [목록 위치]    입력 위 팝업  →  입력 아래 인라인
  [목록 테두리]  있음 (┌─┐)  →  없음 (플랫)
  [명령어 형식]  /save  →  save  (/ 제거)
  [명령어 스타일] 일반 텍스트  →  볼드/컬러 강조
  [스크롤]       없음  →  ▼ 인디케이터
  [페이지네이션]  없음  →  (1/16) 표시
  [상태 바]      2영역  →  3영역 (경로/정보/모델)
```

---

## 5. 파일 변경 목록

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/cli_input.py` | **대폭 수정** | `PromptSession` → 커스텀 `Application` 레이아웃으로 전환 |
| `src/command_registry.py` | **소폭 수정** | 표시용 이름(/ 제거) 속성 추가 |
| `gemini-ai-chat-code01.py` | **수정** | 프롬프트 `> ` 변경, 스트리밍 상태 전달 |
| `claude-ai-chat-code01.py` | **수정** | 동일 적용 |
| `gen-ai-chat-code01.py` | **수정** | 동일 적용 |

---

## 6. 테스트 시나리오

### 6.1 시각적 테스트

| # | 시나리오 | 기대 결과 |
|---|---------|----------|
| 1 | `> /` 입력 | 프롬프트 **아래에** 전체 명령어 인라인 표시, `/` 없이 이름만 |
| 2 | `> /s` 입력 | `save, stream, save_history, shell, shell!` 5개 인라인 표시 |
| 3 | 명령어 이름 스타일 | **볼드/컬러**로 강조, 설명은 dim 색상 |
| 4 | 8개 초과 목록 | `▼` 스크롤 인디케이터 + `(1/N)` 페이지네이션 표시 |
| 5 | 하단 상태 바 | 좌측:경로, 중앙:스트리밍모드, 우측:`/model <모델명>` |
| 6 | 프롬프트 | `>` 형태 |

### 6.2 기능 테스트

| # | 시나리오 | 기대 결과 |
|---|---------|----------|
| 1 | ↑↓ 방향키 | 명령어 선택 이동 (하이라이트) |
| 2 | Tab | 선택된 명령어 자동 입력 |
| 3 | Enter | 선택된 명령어 실행 |
| 4 | ESC | 제안 목록 닫기 |
| 5 | 스크롤 | 8개 초과 시 목록 스크롤 |
| 6 | `/workspace` 변경 | 하단 상태 바 경로 갱신 |

---

## 7. 승인

- [ ] 개발자 검토
- [ ] 테스트 완료
- [ ] 문서 업데이트 완료
