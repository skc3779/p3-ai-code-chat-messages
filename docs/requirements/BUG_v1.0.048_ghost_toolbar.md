# BUG v1.0.048 - 프롬프트 잔상(Ghost Toolbar) 현상

## 문서 정보
- **버전**: v1.0.048
- **작성일**: 2026-02-26
- **상태**: Draft
- **대상 파일**: `src/cli_input.py`
- **관련 버전**: FSD v1.0.047 (Gemini CLI 스타일 TUI)

---

## 1. 개요

### 1.1 버그 설명
FSD v1.0.047에서 전체 화면 너비의 인라인 명령어 제안 TUI를 위해 커스텀 `prompt_toolkit` Application과 Layout을 도입했습니다. 그러나 명령어를 입력하고 실행한 후, **이전 입력 사이클의 하단 상태 바(경로/모드/모델)가 터미널 위쪽에 잔상(아티팩트)으로 남는 현상**이 발생하고 있습니다.

### 1.2 재현 방법
1. 터미널에서 `python gemini-ai-chat-code01.py` 실행
2. 프롬프트 `> ` 상태에서 명령어(예: `/clear`) 입력 후 Enter
3. 명령어가 실행되고 새로운 `> ` 프롬프트가 뜸
4. 새로 뜬 프롬프트 **바로 위**에 이전 프롬프트 창의 `하단 상태 바` UI가 그대로 찍혀서 남아 있음
5. 매 명령어 입력마다 상태 바 찌꺼기가 터미널 내역에 누적됨

## 2. 원인 분석

`prompt_toolkit.Application`을 `full_screen=False` 모드로 사용 중입니다. 기본 `PromptSession`은 사용자 입력이 끝나면(`Enter` 키 등) 프롬프트 텍스트만 터미널 역사(history)에 남기고, 부가적인 UI(목록, 상태 바 등)는 화면에서 지우는(Erase) 후처리 로직을 갖추고 있습니다.

그러나 현재 v1.0.047 구현에서는 `Application`을 직접 구축(`_build_app`)하여 매번 `app.run()`으로 실행하고 `app.exit()`로 닫습니다. 이때 **`Application`이 종료될 때 화면 레이아웃에서 상태 바와 명령어 제안 영역을 지우지 않고 그대로 렌더링 된 텍스트를 터미널 화면 버퍼에 남기기 때문에** 고스트 툴바(잔상) 현상이 발생합니다.

## 3. 해결 방안 (수정 계획)

### 3.1 `erase_when_done` 설정 활성화

가장 간단한 방법은 커스텀 `Application`에 **종료 시 화면 지우기(`erase_when_done=True`)** 속성을 활성화하는 것입니다.

```diff
  return Application(
      layout=layout,
      key_bindings=kb,
      style=GEMINI_STYLE,
      full_screen=False,
+     erase_when_done=True,  # 종료 시 UI 잔상 제거
  )
```

그러나 이 옵션을 단독으로 켜면 **사용자가 입력한 프롬프트 라인(`> /foo`) 마저도 화면에서 사라지는** 문제(프롬프트 사라짐 현상)가 발생할 수 있습니다 (입력했던 줄이 흔적도 없이 사라지고 결과 출력만 나옴).

### 3.2 수동으로 프롬프트 흔적 남기기 (`print_container`)

`Application`을 종료(`exit`)하기 직전에, 우리가 원하는 정보(프롬프트 `>` 기호와 최종 입력값)만 터미널 버퍼에 예쁘게 남기도록 명시적으로 출력해줍니다.

`prompt_toolkit.shortcuts.print_formatted_text`를 활용하여 종료 직전이나 반환 직전에 직접 터미널에 프린트하는 구조가 제일 확실합니다.

#### 변경 포인트 1: `cli_input.py` 의 `Application` 초기화 인자
```python
        return Application(
            layout=layout,
            key_bindings=kb,
            style=GEMINI_STYLE,
            full_screen=False,
            erase_when_done=True,  # 상태 바, 제안 창 등 TUI 요소 전체 지우기
        )
```

#### 변경 포인트 2: `get_input` 반환 직전에 입력 텍스트 재출력
`erase_when_done=True` 때문에 `> 입력내용` 도 함께 사라지므로, 반환하기 전에 터미널에 한 줄 찍고 넘깁니다.

```python
    def get_input(self, prompt: str = "> ") -> str:
        # ... 기존 로직 ...
        app = self._build_app(prompt)
        app.run()
        
        final_text = (self._result or "").strip()
        
        # 지워진 프롬프트 텍스트를 일반 텍스트로 터미널에 다시 복원
        print(f"{prompt}{final_text}")
        
        return final_text
```

## 4. 기대 효과 및 검증 방법
- **효과**: 매 명령어 사이클이 끝난 자리에 이전 입력의 상태 바(회색 바)가 남는 지저분한 로그(잔상)를 제거합니다. 터미널에는 오직 `> 명령어`와 그 결과 출력만 깔끔하게 남게 됩니다.
- **검증**: `> /clear` 실행 시 이전 상태바가 안 남는지 화면을 확인합니다.
