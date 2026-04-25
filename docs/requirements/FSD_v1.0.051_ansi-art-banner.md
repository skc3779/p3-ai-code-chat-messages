# FSD v1.0.051 - ANSI Art 배너 (Startup Banner)

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.051 |
| 제목 | ANSI Art 배너 (Startup Banner) |
| 작성일 | 2026-02-27 |
| 상태 | 확정 |
| 적용 파일 | gen-ai-chat-code01.py, claude-ai-chat-code01.py, gemini-ai-chat-code01.py |

---

## 1. 개요 (Overview)

프로그램 실행 시 Gemini CLI 스타일의 ANSI Art 배너를 출력하여 사용자 경험(UX)을 향상시킨다.  
배너는 색상, 그라데이션, 박스 문자(Unicode box-drawing characters)를 활용한 시각적으로 매력적인 형태로 구성된다.

---

## 2. 배경 (Background)

기존 프로그램은 단순 텍스트 기반의 메뉴(`print_menu()`)를 실행 시 출력하였다.  
Gemini CLI와 같은 현대적인 CLI 도구들은 실행 시 ANSI 이스케이프 코드를 활용한 컬러풀한 배너를 출력하여 브랜드 아이덴티티를 강조하고 사용자에게 좋은 첫인상을 준다.

---

## 3. 요구사항 (Requirements)

### 3.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| REQ-051-001 | 프로그램 실행 시 ANSI Art 배너를 출력해야 한다 | 필수 |
| REQ-051-002 | 배너 문구는 `>> GEN AI CODE CHAT <<` 이어야 한다 | 필수 |
| REQ-051-003 | 배너는 ANSI 이스케이프 코드를 사용한 컬러 출력이어야 한다 | 필수 |
| REQ-051-004 | 배너는 `print_banner()` 함수로 구현되며 `main()` 실행 시작 시 호출되어야 한다 | 필수 |
| REQ-051-005 | 배너는 `print_menu()` 이전에 출력되어야 한다 | 필수 |
| REQ-051-006 | 세 파일(gen-ai, claude-ai, gemini-ai) 모두 동일한 `print_banner()` 함수를 포함해야 한다 | 필수 |
| REQ-051-007 | ANSI 컬러를 지원하지 않는 환경에서도 예외 없이 동작해야 한다 (graceful fallback) | 필수 |
| REQ-051-008 | 배너는 터미널 너비 80자 기준으로 디자인되어야 한다 | 권장 |

### 3.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NREQ-051-001 | 배너 출력은 0.1초 이내에 완료되어야 한다 (성능) |
| NREQ-051-002 | 외부 라이브러리에 의존하지 않고 Python 표준 `sys`, `os` 모듈만 사용해야 한다 |
| NREQ-051-003 | Windows 터미널(PowerShell, cmd, Windows Terminal), macOS, Linux 모두 지원해야 한다 |

---

## 4. 설계 (Design)

### 4.1 ANSI 컬러 코드

```
ESC[<n>m 형식의 ANSI 이스케이프 코드 사용:
  - ESC = \033 (octal) 또는 \x1b (hex)
  - 0  : Reset
  - 1  : Bold
  - 36 : Cyan (밝은 하늘색)
  - 35 : Magenta (분홍/보라)
  - 32 : Green  
  - 33 : Yellow
  - 34 : Blue
  - 96 : Bright Cyan
  - 95 : Bright Magenta
  - 92 : Bright Green
  - 93 : Bright Yellow
```

### 4.2 배너 구조

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║    ██████╗ ███████╗███╗   ██╗     █████╗ ██╗                                ║
║   ██╔════╝ ██╔════╝████╗  ██║    ██╔══██╗██║                                ║
║   ██║  ███╗█████╗  ██╔██╗ ██║    ███████║██║                                ║
║   ██║   ██║██╔══╝  ██║╚██╗██║    ██╔══██║██║                                ║
║   ╚██████╔╝███████╗██║ ╚████║    ██║  ██║██║                                ║
║    ╚═════╝ ╚══════╝╚═╝  ╚═══╝    ╚═╝  ╚═╝╚═╝                               ║
║                                                                              ║
║              >> GEN AI CODE CHAT <<                                          ║
║              🤖 AI-Powered Code Assistant                                    ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### 4.3 color_support 감지 로직

```python
def _supports_color() -> bool:
    """현재 터미널이 ANSI 컬러를 지원하는지 확인"""
    import sys, os
    # NO_COLOR 환경변수 확인 (표준 no-color.org 규약)
    if os.environ.get('NO_COLOR'):
        return False
    # stdout이 TTY인지 확인
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    # Windows에서 ANSI 지원 확인
    if sys.platform == 'win32':
        return os.environ.get('TERM') is not None or \
               os.environ.get('WT_SESSION') is not None or \
               os.environ.get('COLORTERM') is not None
    return True
```

### 4.4 print_banner() 함수 구현

```python
def print_banner():
    """ANSI Art 배너 출력 - >> GEN AI CODE CHAT <<"""
    use_color = _supports_color()
    
    # ANSI 컬러 정의
    CYAN    = '\033[96m' if use_color else ''
    MAGENTA = '\033[95m' if use_color else ''
    GREEN   = '\033[92m' if use_color else ''
    YELLOW  = '\033[93m' if use_color else ''
    BLUE    = '\033[94m' if use_color else ''
    BOLD    = '\033[1m'  if use_color else ''
    RESET   = '\033[0m'  if use_color else ''
    
    banner_lines = [
        # ... ASCII Art 라인들
    ]
    
    print()
    for line in banner_lines:
        print(line)
    print()
```

---

## 5. 구현 계획 (Implementation Plan)

### 5.1 변경 파일

| 파일 | 변경 내용 |
|------|----------|
| `gen-ai-chat-code01.py` | `_supports_color()`, `print_banner()` 함수 추가, `main()` 내 `print_banner()` 호출 |
| `claude-ai-chat-code01.py` | 동일 |
| `gemini-ai-chat-code01.py` | 동일 |

### 5.2 호출 위치

```python
def main():
    load_environment()
    print_banner()   # ← 새로 추가: 환경 로드 후, 메뉴 출력 전
    # ... 기존 코드
    print_menu()
```

---

## 6. 테스트 계획 (Test Plan)

| ID | 테스트 케이스 | 예상 결과 |
|----|--------------|----------|
| TC-051-001 | Windows Terminal에서 실행 | ANSI 컬러 배너 정상 출력 |
| TC-051-002 | PowerShell에서 실행 | ANSI 컬러 배너 정상 출력 |
| TC-051-003 | NO_COLOR=1 환경변수 설정 후 실행 | 색상 없는 일반 텍스트 배너 출력 |
| TC-051-004 | 파이프 출력(`python gen-ai-chat-code01.py | cat`) | 색상 코드 없이 출력됨 |
| TC-051-005 | 세 파일 모두 동일한 배너 출력 확인 | 동일 배너 확인 |

---

## 7. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.051 | 2026-02-27 | - | 최초 작성 |
