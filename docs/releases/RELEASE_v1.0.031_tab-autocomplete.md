# Release Notes v1.0.031 - Tab Autocomplete & CLI Improvements

**릴리즈 일자**: 2026-02-13  
**버전**: v1.0.031

## 🎯 주요 변경사항

### ✨ 새로운 기능

#### 1. Tab 자동완성 도입 (readline)
- `prompt_toolkit`의 복잡성을 제거하고 표준 라이브러리인 `readline`을 도입했습니다.
- **Tab** 키를 사용하여 명령어 자동완성이 가능합니다.
  - `/work` + Tab → `/workspace`
  - `/tem` + Tab → `/template`

#### 2. 의존성 간소화
- `prompt_toolkit` 패키지가 의존성 목록에서 제거되었습니다.
- Python 표준 라이브러리만 사용하여 설치가 빠르고 플랫폼 호환성이 개선되었습니다.

#### 3. 입력 방식 변경
- **Enter**: 명령어 즉시 실행
- **/multiline**: 여러 줄 입력 모드

## 📝 변경된 파일

### 1. `requirements.txt`
```diff
- prompt_toolkit>=3.0.0
```

### 2. `src/cli_input.py`
- `readline` 기반으로 완전히 재작성되었습니다.
- `.cli_history` 파일 기반으로 히스토리 자동 저장/로드 기능이 개선되었습니다.

### 3. 메인 애플리케이션 파이
- `claude-ai-chat-code01.py`
- `gemini-ai-chat-code01.py`
- `gen-ai-chat-code01.py`

**변경 내용**:
- `CLIInputHandler` 변경 사항 반영
- 도움말 메시지 업데이트

## 💡 사용 방법

### Tab 자동완성
```
👤 You: /files[Tab] → /files
👤 You: /work[Tab] → /workspace
```

### 멀티라인 입력
```
👤 You: /multiline
📝 멀티라인 모드 (종료: /end)
... 긴 질문을 여기에
... 작성하세요
... /end
```

## 🔧 기술 세부사항

- `readline.parse_and_bind('tab: complete')`를 사용하여 Tab 자동완성을 활성화했습니다.
- Windows 환경에서는 `pyreadline3` 설치를 통해 동일한 기능을 사용할 수 있지만, 없어도 기본 입력 기능은 정상 동작합니다.

## 📚 관련 문서

- **FSD**: `docs/specs/requirements/FSD_v1.0.031_shift-enter-command-execution.md`

---

**개발자**: AI Code Assistant Team  
**테스트 상태**: ✅ 완료  
**권장 사항**: 의존성을 최신화(`pip install -r requirements.txt`)할 필요 없이 바로 실행 가능합니다.
