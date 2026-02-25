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

## 3. 구현 내용 및 설계 사항 (최종 반영)

### 3.1 `prompt_toolkit` 커스텀 레이아웃 (핵심)

`prompt_toolkit`의 기본 `CompletionsMenu` 드롭다운 팝업 방식 대신, 전체 터미널 화면 너비를 사용하는 **커스텀 `Application` 및 `Layout` 계층 구조**를 도입하여 Gemini CLI와 동일한 인라인 목록을 구현했습니다.

#### 3.1.1 레이아웃 구조 (`HSplit` 기반)

전체 UI는 위에서 아래로 세로 분할(`HSplit`)되는 3개의 계층(`Window`)으로 구성됩니다.

1. **입력 영역 (`BufferControl`)**: `> ` 프롬프트와 사용자의 입력 텍스트를 표시합니다.
2. **제안 표시 영역 (`ConditionalContainer` + `FormattedTextControl`)**: 조건에 따라 나타나며, 필터링된 명령어 목록을 보여줍니다.
3. **하단 상태 바 영역 (`FormattedTextControl`)**: 항상 표시되며, 현재 작업 경로, 모드, 모델 정보를 포함합니다.

#### 3.1.2 입력 및 필터링 메커니즘 (`Buffer.on_text_changed`)

입력 `Buffer`의 텍스트가 변경될 때마다 필터링이 수행됩니다.
- 입력값이 `/`로 시작하고 띄어쓰기가 없을 때: `CommandRegistry.filter_commands` 호출
- 제안 목록이 조건부 컨테이너를 통해 즉시 화면에 노출 (전체 화면 너비 활용)

#### 3.1.3 포맷팅 및 동적 렌더링 (`FormattedTextControl`)

`FormattedTextControl`에 콜백 함수(`_render_suggestions`, `_render_toolbar`)를 연결하여, 커서 이동이나 브라우저 크기 조절 시마다 터미널 치수(`shutil.get_terminal_size()`)를 고려하여 동적으로 다시 그리도록 적용했습니다.

- **명령어 이름 표시:** 명령어 이름의 슬래시(`/`) 접두사를 없애고(`lstrip('/')`), 가장 긴 명령어 길이에 맞춰 동적으로 간격을 띄워(`name_width`) 정렬합니다.
- **테두리 제거:** 기본 프레임을 쓰지 않고 단순 텍스트 패딩만으로 Gemini CLI 같은 테두리 없는 "플랫화된(Flat)" UI를 완성했습니다.
- **상태 바 하이라이트:** 3영역(좌, 중, 우) 간의 여백(`gap1`, `gap2`)을 동적으로 계산하여 끝과 끝에 정렬합니다.

### 3.2 스타일(Style) 적용 내역

명령어 제목과 설명을 명확히 구분하기 위한 어두운 테마 기반 스타일:

```python
GEMINI_STYLE = Style.from_dict({
    'cmd-name':         'bold #e0e0e0',          # 기본 명령어 (단순 밝은회색)
    'cmd-name-selected':'bold bg:#3a3a3a #ffffff', # 선택된 명령어 반전 (흰색/bg회색)
    'cmd-desc':         '#707070',               # 설명 (dim)
    'cmd-desc-selected':'bg:#3a3a3a #909090',    # 선택된 설명
    'scroll-indicator':  '#505050',
    'pagination':        '#606060',
    'toolbar':           'bg:#1a1a2e #a0a0a0',   # 하단 상태 바 배경
    'toolbar-path':      'bold',
    'toolbar-center':    'italic',
    'toolbar-model':     'bold',
})
```

### 3.3 키 바인딩 제어 (`KeyBindings`)

명령어 목록 컨트롤을 위한 커스텀 키 설정 내역입니다:
- **`Up` / `Down`**: 명령어 선택 인덱스(`_selected_idx`) 증가/감소. 최대 가시 영역에 도달 시 스크롤 변수(`_scroll_offset`) 점진적 갱신.
- **`Tab`**: 현재 선택된 명령어를 치환(완성)한 후 뒤에 띄어쓰기 한 칸 추가하고, 목록 비활성화.
- **`Enter`**: 제안 영역이 열려있는 상태라면 Tab과 동일하게 완성 수행(`completion confirm`); 이미 완성 상태이거나 제안 영역이 닫혀 있다면 명령어 또는 대화를 AI로 전송.
- **`Esc`**: 제안 영역 끄기 (`_show_suggestions = False`). 비어있는 상태에서 누를 경우 현재 입력값 전체 취소 및 즉시 반환.

### 3.4 대안 접근 평가 (`prompt_toolkit Completer`) vs 최종 구현 방향

FSD 계획 시 고려했던 `PromptSession` + 커스텀 Completer 드롭다운 스타일 지정 방식(`CompleteStyle.MULTI_COLUMN` 등)은, *"/ 접두사를 제외하고 보여주면서 실제 완성은 접두사까지 하도록"* 하는 세부 제어나 *목록 하단에 `(1/16)` 형태의 페이지네이션 등을 삽입*하는데 극히 제약적이었습니다. 이에 따라 최종적으로 **저수준 `Application` API 조작 기반**으로 구현 우회하여 Gemini CLI 요구사항을 완벽히 수용했습니다.

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
