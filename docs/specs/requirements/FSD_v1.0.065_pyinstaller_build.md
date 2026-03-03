# FSD v1.0.065 - PyInstaller를 이용한 실행 파일(.exe) 빌드 환경 구축

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.065 |
| 제목 | PyInstaller를 이용한 실행 파일(.exe) 빌드 환경 구축 |
| 작성일 | 2026-03-03 |
| 상태 | 설계 완료 |
| 대상 소스 | `gen-ai-chat-code.py`, `claude-ai-chat-code.py`, `gemini-ai-chat-code.py` |
| 관련 스크립트 | `build_genai.ps1` (또는 `.bat`), `build_claude.ps1`, `build_gemini.ps1`, `build_all.ps1` 등 |

---

## 1. 개요 (Overview)

현재 Python 스크립트 형태로 실행되는 3종의 AI 챗봇 어시스턴트(`gen-ai-chat-code.py`, `claude-ai-chat-code.py`, `gemini-ai-chat-code.py`)를 사용자가 Python 환경 없이도 단독 실행할 수 있도록 `PyInstaller`를 이용하여 단일 실행 파일(`.exe`)로 패키징하는 빌드 환경을 구축합니다.

### 1.1 개선 목표

| # | 목표 | 설명 |
|---|------|------|
| 1 | 단일 파일 빌드 | 의존성 패키지와 Python 인터프리터를 포함한 단일 `.exe` 파일로 빌드 |
| 2 | 보안 및 최적화 | UPX 압축 및 난독화 Key 적용, 콘솔 숨김 처리 등 적용 |
| 3 | 빌드 스크립트화 | 각 모델별로 규격화된 자동화 빌드 스크립트 작성 |
| 4 | 산출물 분리 | 빌드 산출물(`dist`, `build`, `spec`) 경로를 체계적으로 분리 및 관리 |

---

## 2. 설계 (Design)

### 2.1 PyInstaller 주요 옵션 매핑

사용자의 요구사항에 따라 다음과 같은 PyInstaller 옵션을 기본으로 적용합니다.

| 옵션 | 설명 | 비고 |
|------|------|------|
| `--onefile` | 하나의 `.exe` 파일로 빌드 | 배포 편의성 |
| `--noconsole` | 콘솔창(터미널)이 뜨지 않도록 숨김 처리 | **[주의사항 참조]** |
| `--icon=<아이콘경로>` | 실행 파일 아이콘 지정 | `assets/icon.ico` 등 적용 |
| `--name=<파일명>` | 생성될 실행 파일명 지정 | 예: `ClaudeAssistant` |
| `--distpath=<경로>` | 최종 `.exe` 파일이 저장될 경로 | 예: `./build_output/dist` |
| `--workpath=<경로>` | 임시 빌드 파일이 저장될 경로 | 예: `./build_output/build` |
| `--specpath=<경로>` | `.spec` 파일이 저장될 경로 | 예: `./build_output/spec` |
| `--clean` | 빌드 전 PyInstaller 캐시 정리 | 깨끗한 빌드 보장 |
| `--upx-dir=<경로>` | UPX 압축 도구 경로 지정 | 실행 파일 용량 최적화용 (선택) |

### 2.2 부가 옵션 (추가 필요사항)

실제 빌드 및 실행 시 안정성을 위해 다음 옵션 및 설정이 추가로 필요할 수 있습니다.
- `--add-data`: `.env`, `.env.example`, `assets` 등 런타임에 필요한 리소스 파일 포함.
- `--hidden-import`: 동적으로 로드되는 패키지가 누락되는 것을 방지.
- **파이썬 내 리소스 경로 처리**: PyInstaller로 빌드된 후 실행 시 임시 폴더(`_MEIPASS`)에 압축이 풀리므로, `os.path.abspath(os.path.dirname(__file__))` 대신 `sys._MEIPASS`를 참조하는 로직이 소스코드 내에 추가 반영되어야 합니다.

### 2.3 빌드 스크립트 설계 (`scripts/` 폴더 내 작성 예정)

모든 빌드 스크립트는 PowerShell(`.ps1`) 또는 Batch(`.bat`) 파일로 작성합니다.

#### 빌드 디렉토리 구조
```text
[Project Root]
 ┣ build_scripts/
 ┃ ┣ build_genai.ps1
 ┃ ┣ build_claude.ps1
 ┃ ┣ build_gemini.ps1
 ┃ ┗ build_all.ps1
 ┣ build_output/         (빌드 작업 공간 및 결과물 - .gitignore 처리)
 ┃ ┣ dist/               (최종 .exe 저장)
 ┃ ┣ build/              (임시 파일 저장)
 ┃ ┗ spec/               (.spec 파일 저장)
 ┗ assets/
   ┗ icon.ico            (공통 아이콘)
```

#### 빌드 스크립트 예시 (개념도)
```powershell
# build_claude.ps1
$UPX_DIR = "C:\tools\upx"

pyinstaller --noconfirm `
    --onefile `
    --icon="assets/icon.ico" `
    --name="ClaudeChatAssistant" `
    --distpath="build_output/dist" `
    --workpath="build_output/build" `
    --specpath="build_output/spec" `
    --clean `
    --upx-dir=$UPX_DIR `
    claude-ai-chat-code.py
```

---

## 3. 요구사항 (Requirements)

### 3.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|--------:|
| REQ-065-001 | 3개의 메인 스크립트(`gen-ai`, `claude`, `gemini`)에 대한 개별 빌드 스크립트를 작성한다. | 필수 |
| REQ-065-002 | 모든 빌드 스크립트는 `--onefile`, `--noconsole`, `--clean` 옵션을 포함해야 한다. | 필수 |
| REQ-065-003 | 빌드 산출물이 프로젝트 루트에 오염을 주지 않도록 `--distpath`, `--workpath`, `--specpath`를 분리 지정한다. | 필수 |
| REQ-065-004 | 빌드 최적화 및 보호를 위해 `--upx-dir` 매개변수가 스크립트 내에 포함되도록 구성한다. (PyInstaller v6.0부터 `--key` 옵션은 제거됨) | 필수 |
| REQ-065-005 | 각 실행 파일에 `--icon` 옵션을 통해 고유 아이콘 또는 공통 아이콘을 지정한다. | 필수 |
| REQ-065-006 | 생성될 실행 파일의 이름(`--name`)은 각각 식별 가능한 이름으로 지정한다 (예: `GenAIAssistant`, `ClaudeAssistant`, `GeminiAssistant`). | 필수 |

### 3.2 비기능/그 외 필요사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| NREQ-065-001 | 런타임 환경(`.env` 파일, 기타 리소스)이 누락되지 않도록 경로 매핑 또는 `--add-data` 처리를 검토하고 필요시 적용한다. | 필수 적용 권장 |
| NREQ-065-002 | `.gitignore`에 `build_output/` 및 관련 빌드 찌꺼기 파일이 등록되도록 한다. | 유지보수성 |
| NREQ-065-003 | `UPX` 도구 및 `pyinstaller` 설치 가이드가 프로젝트 문서에 명시되어야 한다. | 환경셋업 |

---

## 4. ⚠️ 주의사항 및 제약사항 (Caveats)

### 1. `--noconsole` 옵션과 CLI 애플리케이션 충돌 문제
현재 제공되는 3종의 챗봇 스크립트(`gen-ai-chat-code.py`, `claude-ai-chat-code.py`, `gemini-ai-chat-code.py`)는 터미널(콘솔창) 위에서 사용자와 상호작용하는 **명령줄 인터페이스(CLI) 기반 애플리케이션**입니다.

빌드 옵션으로 `--noconsole`을 적용할 경우 발생하는 현상과 권장 해결책은 다음과 같습니다:
- **발생 현상**: GUI(윈도우 폼, PyQt 등)가 없는 상태에서 콘솔창까지 숨김 처리되므로, 애플리케이션이 백그라운드 프로세스로만 실행됩니다. 사용자는 챗봇의 응답을 볼 수 없고 입력도 할 수 없게 됩니다.
- **권장 해결책**:
  1. **현재 아키텍처 (CLI 형태 유지)**: 터미널 기반의 텍스트 상호작용이 필수적이므로, 최종 빌드 스크립트 적용 시에는 `--noconsole` 옵션을 **반드시 제외**해야 정상적인 챗봇 사용이 가능합니다.
  2. **향후 확장 (GUI 도입 시)**: 만약 추후 PyQt, Tkinter 또는 웹 기반 UI 등을 도입하여 별도의 채팅창 그래픽 인터페이스를 제공하게 될 경우에는 `--noconsole` 옵션을 적용하는 것이 적합합니다.

> **💡 결론**: 본 FSD 문서 설계 상에는 요구사항 전시에 따라 `--noconsole` 옵션을 우선 포함해 두었으나, 실제 빌드 스크립트를 작성하고 실행 파일을 생성하는 `EXECUTION` 단계에서는 해당 옵션을 **제외한 상태로 빌드**하여 사용성 문제를 방지하겠습니다.

### 2. 암호화 키(`--key`) 옵션 미지원 (PyInstaller v6.0+)
기존 설계에 포함되었던 파이썬 바이트코드 암호화용 `--key` 옵션은 PyInstaller v6.0 버전부터 **공식적으로 제거(레거시)** 되었습니다. 따라서 실제 작성된 빌드 스크립트에는 `--key` 인자가 포함되지 않습니다.

---

## 5. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.065 | 2026-03-03 | - | 최초 작성: PyInstaller를 이용한 각 AI 챗봇 실행 파일 빌드 스펙 정의 |
