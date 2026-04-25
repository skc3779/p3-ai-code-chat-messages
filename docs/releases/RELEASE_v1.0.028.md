# RELEASE v1.0.028

## ✨ 주요 변경 사항

### 1. 명령어 자동 완성 기능 (Autocomplete) - P3-05
- CLI 환경에서 **Tab 키**를 이용한 명령어 자동 완성 기능이 추가되었습니다.
- **주요 기능**:
    - **명령어 자동 완성**: `/` 입력 후 Tab을 누르면 `/help`, `/files` 등의 명령어가 자동 완성됩니다.
    - **파일 경로 자동 완성**: `/files`, `/read` 등의 명령에서 파일 경로 입력 시 Tab으로 자동 완성됩니다.
    - **히스토리 탐색**: 위/아래 화살표 키(⬆️, ⬇️)로 이전에 입력한 명령어를 다시 불러올 수 있습니다.
- `prompt_toolkit` 라이브러리를 사용하여 더욱 풍부한 CLI 경험을 제공합니다.
- **신규 모듈**: `src/cli_input.py`

### 2. `/context` 명령어 개선 (v1.0.027 포함)
- 다중 파일 패턴 지원 (`[pattern1, pattern2]` 형식)이 적용되었습니다.

### 3. TerminalExecutor 개선
- **허용 명령어 확장**: Windows PowerShell 및 CMD 환경에 맞춰 `whoami`, `hostname`, `date`, `time`, `more` 등의 안전 명령어를 추가했습니다.
- **위험 명령어 추가**: `robocopy`, `icacls`, `attrib`, `diskpart`, `reg` 등 Windows 전용 위험 명령어를 차단 목록에 추가했습니다.
- **인코딩 문제 해결**: `subprocess.run`에 `encoding='utf-8'`, `errors='replace'` 옵션을 추가하여 Windows cp949 인코딩 오류를 해결했습니다.

### 4. 테스트 코드 추가
- `tests/test_genai_tool_use.py`: GenAI Tool Use 기능 단위 테스트 추가.
- `tests/test_terminal_executor.py`: 허용 명령어 검증 테스트 추가 (`test_all_allowed_commands_are_permitted`).

---
**업데이트 날짜**: 2026-02-05
**작성자**: Antigravity

