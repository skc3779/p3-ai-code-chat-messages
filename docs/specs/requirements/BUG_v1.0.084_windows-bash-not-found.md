# BUG v1.0.084 - Windows 환경에서 `/run`, `/agents` 명령 실행 시 bash 없음 오류

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.084 |
| 제목 | `코드 실행 (bash)` — Windows 환경에서 bash 미설치로 코드 실행 실패 |
| 작성일 | 2026-04-18 |
| 상태 | 분석 완료 |
| 관련 명령 | `/run`, `/agents` |
| 수정 대상 | [src/code_executor.py](../../../src/code_executor.py), [gemini-ai-chat-code.py](../../../gemini-ai-chat-code.py), [claude-ai-chat-code.py](../../../claude-ai-chat-code.py), [gen-ai-chat-code.py](../../../gen-ai-chat-code.py) |

---

## 1. 버그 설명

### 1.1 증상

`gemini-ai-chat-code.py`, `claude-ai-chat-code.py`, `gen-ai-chat-code.py` 중 하나를 Windows에서 실행하여 AI에게 bash 스크립트 작성을 요청한 뒤 `/run` 또는 `/agents`를 실행하면 다음 오류가 발생합니다:

```
⚙️  코드 실행 (bash)...
❌ 실행 환경 없음: bash가 설치되어 있지 않습니다.
```

또는 `FileNotFoundError: [WinError 2] 지정된 파일을 찾을 수 없습니다: 'bash'` 예외가 발생하여 코드 블록이 실행되지 않습니다.

### 1.2 재현 조건

1. Windows 환경에서 CLI 실행:
   ```
   python gemini-ai-chat-code.py
   ```
2. AI에게 시스템 명령 또는 쉘 스크립트 작성 요청:
   ```
   현재 디렉토리의 파일 목록을 출력하는 스크립트 작성해줘
   ```
3. AI가 `bash` 코드 블록으로 응답:
   ````
   ```bash
   ls -la
   ```
   ````
4. `/run` 실행
5. **결과**: `bash` 실행 파일을 찾지 못해 오류 발생

### 1.3 원인 분석

#### 근본 원인: `SUPPORTED_LANGUAGES`에 bash 명령어가 OS 무관하게 하드코딩

**코드 위치: `src/code_executor.py` L16-23**

```python
SUPPORTED_LANGUAGES = {
    'python': {'cmd': 'python', 'ext': '.py', 'icon': '🐍'},
    'py':     {'cmd': 'python', 'ext': '.py', 'icon': '🐍'},
    'javascript': {'cmd': 'node', 'ext': '.js', 'icon': '📜'},
    'js':     {'cmd': 'node', 'ext': '.js', 'icon': '📜'},
    'bash':   {'cmd': 'bash', 'ext': '.sh', 'icon': '🖥️'},  # ← 문제
    'sh':     {'cmd': 'bash', 'ext': '.sh', 'icon': '🖥️'},  # ← 문제
}
```

`bash`와 `sh` 언어 태그 모두 `cmd: 'bash'`로 하드코딩되어 있습니다. Linux/macOS에서는 bash가 기본 설치되어 있어 정상 동작하지만, **Windows에서는 bash가 기본 미설치**이므로 `subprocess.run(['bash', temp_file])` 호출 시 `FileNotFoundError`가 발생합니다.

#### 이차 원인: AI 프롬프트에 OS별 쉘 선택 지침 없음

AI는 쉘 스크립트 작성 요청을 받으면 OS 환경을 고려하지 않고 `bash` 코드 블록을 생성합니다. CLI 시작 시 OS 정보를 시스템 프롬프트에 주입하는 로직이 없으므로 AI가 적절한 쉘을 선택할 수 없습니다.

---

## 2. 상세 분석

### 2.1 BUG-01: `SUPPORTED_LANGUAGES` bash/sh 명령어 하드코딩 (Critical)

#### 코드 위치: `src/code_executor.py` L21-22, L56-62

```python
# src/code_executor.py L56-62 — 실행 호출부
result = subprocess.run(
    [lang_config['cmd'], temp_file],   # Windows: ['bash', 'C:/Temp/xxx.sh']
    capture_output=True,
    text=True,
    timeout=self.timeout,
    cwd=str(self.workspace_dir)
)
```

Windows에서 `bash`는 기본 PATH에 없으므로 `FileNotFoundError`가 발생합니다. 코드는 이를 캐치하여 `실행 환경 없음` 메시지를 반환하지만, 대안 쉘 시도 없이 그대로 실패합니다.

#### OS별 기본 쉘 비교

| OS | 기본 쉘 | 기본 설치 | 코드 실행 방식 |
|----|--------|---------|--------------|
| Linux | `bash` | ✅ 항상 | `bash script.sh` |
| macOS | `zsh` (bash 제공) | ✅ 항상 | `bash script.sh` |
| Windows | `powershell` / `cmd` | ✅ 항상 | `powershell -File script.ps1` |
| Windows (WSL) | `bash` | ⚠️ 선택적 설치 | `bash script.sh` |

### 2.2 BUG-02: AI 시스템 프롬프트에 OS 환경 정보 미포함 (High)

AI가 `bash` 코드 블록을 생성하면 `/run`과 `/agents` 모두 영향받습니다. CLI 초기화 시 OS 정보를 시스템 프롬프트에 주입하지 않아 AI가 Windows/Linux를 구분하지 못합니다.

#### `/run` 명령 흐름 (`gemini-ai-chat-code.py` L510-527)

```
사용자: "파일 목록 스크립트 작성"
  → AI 응답: ```bash\nls -la\n```
  → /run 실행
  → code_executor.execute(code, language='bash')
  → subprocess.run(['bash', temp_file])  ← Windows에서 실패
```

#### `/agents` 명령 흐름 (`src/agent_runner.py` L387-417)

```
에이전트 Act 단계에서 bash 코드 블록 생성
  → _run_code_blocks() 호출
  → code_executor.execute(code, lang='bash')
  → subprocess.run(['bash', temp_file])  ← Windows에서 실패
  → ActionResult(success=False)
  → 에이전트 루프 실패 처리
```

### 2.3 BUG-03: bash 코드 블록의 Windows 비호환 명령어 (Medium)

bash 스크립트 내 `ls`, `grep`, `cat` 등의 명령어는 PowerShell에서 다른 구문을 사용합니다. 단순히 실행기를 PowerShell로 바꿔도 스크립트 내용 자체가 Windows 비호환일 수 있습니다. AI에게 OS를 알려줘야 Windows 호환 스크립트를 생성할 수 있습니다.

---

## 3. 수정 방안

### 3.1 방안 A: `CodeExecutor` OS 감지 및 쉘 자동 선택 (권장)

`SUPPORTED_LANGUAGES`를 인스턴스 초기화 시점에 OS에 따라 동적으로 구성합니다.

#### 수정 전 (`src/code_executor.py` L16-23)

```python
SUPPORTED_LANGUAGES = {
    'python': {'cmd': 'python', 'ext': '.py', 'icon': '🐍'},
    'py':     {'cmd': 'python', 'ext': '.py', 'icon': '🐍'},
    'javascript': {'cmd': 'node', 'ext': '.js', 'icon': '📜'},
    'js':     {'cmd': 'node', 'ext': '.js', 'icon': '📜'},
    'bash':   {'cmd': 'bash', 'ext': '.sh', 'icon': '🖥️'},
    'sh':     {'cmd': 'bash', 'ext': '.sh', 'icon': '🖥️'},
}
```

#### 수정 후

```python
import platform

def _build_shell_config() -> dict:
    """OS에 따라 쉘 실행 설정을 반환"""
    if platform.system() == 'Windows':
        return {
            'cmd': 'powershell',
            'args': ['-NoProfile', '-NonInteractive', '-File'],
            'ext': '.ps1',
            'icon': '🪟',
        }
    else:
        return {
            'cmd': 'bash',
            'args': [],
            'ext': '.sh',
            'icon': '🖥️',
        }

class CodeExecutor:
    BASE_LANGUAGES = {
        'python': {'cmd': 'python', 'ext': '.py', 'icon': '🐍'},
        'py':     {'cmd': 'python', 'ext': '.py', 'icon': '🐍'},
        'javascript': {'cmd': 'node', 'ext': '.js', 'icon': '📜'},
        'js':     {'cmd': 'node', 'ext': '.js', 'icon': '📜'},
    }

    def __init__(self, workspace_dir: Path, timeout: int = 30):
        self.workspace_dir = workspace_dir
        self.timeout = timeout
        shell_cfg = _build_shell_config()
        self.SUPPORTED_LANGUAGES = {
            **self.BASE_LANGUAGES,
            'bash':       shell_cfg,
            'sh':         shell_cfg,
            'shell':      shell_cfg,
            'powershell': shell_cfg,  # Windows에서 직접 powershell 블록도 지원
            'ps1':        shell_cfg,
        }
        self._shell_args = shell_cfg.get('args', [])
```

#### `execute()` 메서드 subprocess 호출부 수정

```python
# src/code_executor.py execute() 메서드 내 subprocess.run 호출부

cmd_parts = [lang_config['cmd']] + self._shell_args + [temp_file] \
    if hasattr(self, '_shell_args') and lang_config['cmd'] in ('bash', 'powershell') \
    else [lang_config['cmd'], temp_file]

result = subprocess.run(
    cmd_parts,
    capture_output=True,
    text=True,
    timeout=self.timeout,
    cwd=str(self.workspace_dir)
)
```

### 3.2 방안 B: CLI 시작 시 시스템 프롬프트에 OS 정보 주입 (권장, A와 병행)

각 CLI(`gemini-ai-chat-code.py`, `claude-ai-chat-code.py`, `gen-ai-chat-code.py`) 초기화 시 OS 환경 정보를 시스템 프롬프트에 추가하여 AI가 올바른 쉘 코드 블록을 생성하도록 합니다.

#### 적용 위치: 각 CLI의 `assistant` 초기화 직전 또는 시스템 프롬프트 구성부

```python
import platform
import sys

def get_os_shell_hint() -> str:
    """현재 OS에 맞는 쉘 사용 지침 반환"""
    if platform.system() == 'Windows':
        return (
            "현재 실행 환경: Windows OS. "
            "쉘 스크립트 작성 시 반드시 PowerShell 구문을 사용하고 "
            "코드 블록 언어 태그를 `powershell` 또는 `ps1`로 지정하세요. "
            "bash, sh 코드 블록은 이 환경에서 실행되지 않습니다."
        )
    else:
        return (
            f"현재 실행 환경: {platform.system()} OS. "
            "쉘 스크립트 작성 시 bash 구문을 사용하고 "
            "코드 블록 언어 태그를 `bash` 또는 `sh`로 지정하세요."
        )
```

시스템 프롬프트 말미에 `get_os_shell_hint()` 반환값을 추가합니다.

---

## 4. 영향 분석

### 4.1 영향 범위

| 모듈 | 메서드 | 영향 | 설명 |
|------|--------|:----:|------|
| `src/code_executor.py` | `execute()` | 🔴 Critical | bash 하드코딩으로 Windows에서 FileNotFoundError |
| `src/agent_runner.py` | `_run_code_blocks()` | 🔴 Critical | code_executor 호출로 동일 실패 |
| `gemini-ai-chat-code.py` | `/run` 핸들러 | 🔴 Critical | bash 코드 블록 실행 불가 |
| `claude-ai-chat-code.py` | `/run` 핸들러 | 🔴 Critical | 동일 |
| `gen-ai-chat-code.py` | `/run` 핸들러 | 🔴 Critical | 동일 |
| 시스템 프롬프트 구성 | 초기화 | 🟡 High | OS 정보 미포함으로 AI가 bash 블록 생성 |

### 4.2 데이터 흐름 분석

```
[현재 — 실패 흐름 (Windows)]
사용자: "파일 목록 보여줘"
  → AI 응답: ```bash\nls -la\n```
  → /run 또는 /agents
    → code_executor.execute(code, 'bash')
      → SUPPORTED_LANGUAGES['bash']['cmd'] = 'bash'  ← 하드코딩
        → subprocess.run(['bash', temp_file.sh])
          → FileNotFoundError: bash not found
            → {'success': False, 'error': '실행 환경 없음: bash가 설치되어 있지 않습니다.'}

[수정 후 — 정상 흐름 (Windows)]
사용자: "파일 목록 보여줘"
  → 시스템 프롬프트: "현재 환경: Windows, powershell 사용"
    → AI 응답: ```powershell\nGet-ChildItem\n```
  → /run 또는 /agents
    → code_executor.execute(code, 'powershell')
      → SUPPORTED_LANGUAGES['powershell']['cmd'] = 'powershell'  ← OS 감지
        → subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-File', temp_file.ps1])
          → returncode=0 → 정상 출력
```

---

## 5. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `src/code_executor.py` | **수정** | `_build_shell_config()` 추가, `SUPPORTED_LANGUAGES`를 인스턴스 변수로 전환, subprocess 호출부에 shell args 적용 |
| `gemini-ai-chat-code.py` | **수정** | 시스템 프롬프트에 `get_os_shell_hint()` 주입 |
| `claude-ai-chat-code.py` | **수정** | 동일 |
| `gen-ai-chat-code.py` | **수정** | 동일 |

---

## 6. 검증 시나리오

### 6.1 수동 검증

| # | OS | 시나리오 | 예상 결과 | 판정 |
|---|----|---------|----------|:----:|
| 1 | Windows | AI에게 "파일 목록 출력 스크립트" 요청 후 `/run` | AI가 `powershell` 블록 생성, `Get-ChildItem` 정상 실행 | ⬜ |
| 2 | Windows | AI에게 "디렉토리 생성 스크립트" 요청 후 `/run` | `powershell` 블록 생성 및 실행 성공 | ⬜ |
| 3 | Windows | `/agents` 실행 후 파일 관련 목표 입력 | 에이전트가 powershell 블록 생성 및 실행 | ⬜ |
| 4 | Linux | AI에게 "파일 목록 출력 스크립트" 요청 후 `/run` | AI가 `bash` 블록 생성, `ls -la` 정상 실행 | ⬜ |
| 5 | Linux | `/agents` 실행 | 에이전트가 bash 블록 생성 및 실행 | ⬜ |
| 6 | Windows | python 코드 블록 실행 | 기존과 동일하게 python 정상 실행 | ⬜ |

### 6.2 엣지 케이스

| # | 시나리오 | 예상 결과 |
|---|---------|----------|
| 1 | Windows에서 AI가 여전히 `bash` 블록 생성 (프롬프트 지침 미적용 시) | `bash`→`powershell` 폴백으로 실행 시도 또는 명확한 오류 메시지 안내 |
| 2 | WSL 환경 (Windows + bash 설치됨) | `platform.system() == 'Windows'`이므로 powershell 사용 (WSL 내부 실행 시에는 Linux 경로) |
| 3 | PowerShell 미설치 환경 (비정상 Windows) | `실행 환경 없음: powershell가 설치되어 있지 않습니다.` 메시지 반환 |

---

## 7. 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v1.0.084 | 2026-04-18 | 최초 작성: Windows 환경에서 bash 하드코딩으로 인한 코드 실행 실패 버그 분석 |
