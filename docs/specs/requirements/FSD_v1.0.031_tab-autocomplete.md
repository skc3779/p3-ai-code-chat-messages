# FSD v1.0.031 - Tab Autocomplete

## 문서 정보
- **버전**: v1.0.031
- **작성일**: 2026-02-13
- **대상 파일**: 
  - `src/cli_input.py`
  - `requirements.txt`

## 1. 개요

### 1.1 목적
`prompt_toolkit` 의존성을 제거하고 표준 라이브러리 `readline`을 사용한 Tab 자동완성으로 변경합니다.

### 1.2 범위
- `prompt_toolkit` 제거
- `readline` 사용 (Python 표준 라이브러리)
- Tab 자동완성 구현

## 2. 요구사항

### 2.1 기능 요구사항

#### FR-1: Tab 자동완성
- `/work` + Tab → `/workspace`
- `/tem` + Tab → `/template`
- 부분 일치하는 명령어 제안

## 3. 설계

### 3.1 의존성 변경

#### requirements.txt
```diff
- prompt_toolkit>=3.0.0
```

### 3.2 구현 방법

#### Tab 자동완성 (readline)
```python
import readline

class CLIInputHandler:
    def __init__(self):
        self.commands = [
            '/help', '/quit', '/files', '/tree', '/read', '/context',
            '/save', '/workspace', '/stream', '/nostream', 
            '/history', '/clear', '/save_history', '/load_history', '/list_history',
            '/run', '/multiline', '/tokens', '/shell', '/shell!',
            '/template', '/template_list', '/template_reset',
            '/watch', '/unwatch', '/watch_list',
            '/llm_config', '/diff', '/apply'
        ]
        
        # Tab 자동완성 설정
        readline.parse_and_bind('tab: complete')
        readline.set_completer(self._completer)
        
        # 히스토리 로드
        try:
            readline.read_history_file('.cli_history')
        except FileNotFoundError:
            pass
    
    def _completer(self, text, state):
        """Tab 자동완성"""
        options = [cmd for cmd in self.commands if cmd.startswith(text)]
        return options[state] if state < len(options) else None
    
    def get_input(self, prompt="👤 You: "):
        """사용자 입력"""
        try:
            user_input = input(prompt).strip()
            if user_input:
                readline.write_history_file('.cli_history')
            return user_input
        except EOFError:
            return "/quit"
        except KeyboardInterrupt:
            return ""
```

## 4. 테스트 시나리오

### 4.1 Tab 자동완성 테스트
1. `/work` 입력 후 Tab → `/workspace` 확인
2. `/tem` 입력 후 Tab → `/template` 확인
3. `/h` 입력 후 Tab → 여러 옵션 확인

## 5. 참고사항

### 5.1 readline 모듈
- Python 표준 라이브러리
- Unix/Linux/macOS: 기본 지원
- Windows: `pyreadline3` 권장 (선택사항)

**Windows fallback**:
```python
try:
    import readline
except ImportError:
    # Windows에서 readline 없으면 기본 동작
    pass
```
