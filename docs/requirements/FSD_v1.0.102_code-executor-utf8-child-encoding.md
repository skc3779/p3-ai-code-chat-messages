# FSD v1.0.102 — CodeExecutor 자식 프로세스 UTF-8 강제 (`cp949` UnicodeEncodeError 해결)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.102 |
| 작성일 | 2026-04-22 |
| 상태 | ✅ 구현 완료 (2026-04-22) — [RELEASE v1.0.102](../releases/RELEASE_v1.0.102_code-executor-utf8-child-encoding.md) |
| 선행 문서 | BUG v1.0.084 (Windows bash 미설치 대응), FSD v1.0.088 (OS Shell 힌트) |
| 대상 파일 | [src/code_executor.py](src/code_executor.py) |
| 신규 파일 | [tests/test_code_executor_encoding.py](tests/test_code_executor_encoding.py) (테스트 전용) |

---

## 1. 개요

### 1.1 목적

`/run` 및 `/agents` 로 실행되는 자식 프로세스(주로 Python)가 **Windows 한국어 로캘에서 이모지·비-CP949 문자를 `print()` 할 때 `UnicodeEncodeError: 'cp949' codec can't encode character ...` 로 종료되는 간헐적 문제** 를 제거한다.

재현 로그 예:

```
👁  Observe #2
────────────────────────────────────────────────────────────
❌ 코드 실행 (python)
returncode=1
Traceback (most recent call last):
  File "C:\Users\Public\Documents\ESTsoft\CreatorTemp\tmpx0cpr1qr.py", line 6, in <module>
    print(f.read()[:50] + "...")
UnicodeEncodeError: 'cp949' codec can't encode character '\U0001f680' in position 49: illegal multibyte sequence
✅ 코드 실행 (python)
returncode=0
File exists. Content length: 295 characters.
First line: # Project Title
```

동일한 스크립트를 두 번 실행했을 때 **파일이 슬라이싱된 앞부분에 이모지(🚀, U+1F680)가 포함되느냐** 에 따라 성공/실패가 갈린다. 즉 "간헐적" 으로 보이는 증상은 사실상 **자식 프로세스의 `sys.stdout.encoding` 이 로캘(`cp949`) 로 고정** 되어 있기 때문이다.

### 1.2 범위

| 항목 | 포함 여부 |
|---|---|
| `subprocess.run()` 호출에 `env` 주입 (`PYTHONIOENCODING`, `PYTHONUTF8`) | ✅ |
| PowerShell(ps1) 자식의 출력 인코딩 UTF-8 강제 | ✅ |
| 부모 프로세스의 `os.environ` 을 파괴적으로 변경하지 않음 | ✅ |
| `encoding` / `errors='replace'` 기존 동작 유지 (디코딩 쪽) | ✅ |
| 테스트 케이스: 이모지 `print()`, 한글 `print()`, 비-UTF8 stderr 혼합 | ✅ |
| CLI 전역(부모 인터프리터) `PYTHONIOENCODING` 설정 | ❌ 범위 외 (chat-code 런처는 이미 별개 이슈) |
| Node.js(javascript) 자식의 인코딩 | ❌ 범위 외 (Node 는 기본 UTF-8 stdout) |
| Linux/macOS 로캘(`LANG=C`) 대응 | ✅ 동일 env 주입으로 자연 커버 |

---

## 2. 현황 분석

### 2.1 현재 `execute()` 호출부

[src/code_executor.py:92-99](src/code_executor.py#L92-L99)

```python
result = subprocess.run(
    cmd_parts,
    capture_output=True,
    encoding=self.DEFAULT_ENCODING,   # 'utf-8'
    errors='replace',
    timeout=self.timeout,
    cwd=str(self.workspace_dir)
)
```

- `encoding='utf-8'` 과 `errors='replace'` 는 **부모가 캡처한 바이트를 디코드할 때의 정책** 이다. 자식 프로세스의 `sys.stdout` 이 무엇을 쓸지와는 무관하다.
- Windows 한국어 로캘에서 자식 Python 을 아무 환경 변수 없이 띄우면 `sys.stdout.encoding == 'cp949'` 가 기본값이다.
- 자식이 `print("🚀")` 를 실행하면 **`cp949` 로 인코딩 시도 → UnicodeEncodeError 발생 → returncode=1** 로 종료된다.
  - 부모는 stdout 을 utf-8 로 디코드하므로 **traceback 은 정확히 보이지만**, 이미 자식이 죽은 뒤이다.

### 2.2 재현 시나리오 (최소 예시)

```python
# 자식 스크립트 (임시 파일)
import io, sys
with open("readme.md", "r", encoding="utf-8") as f:
    print(f.read()[:50] + "...")   # 앞 50자에 🚀 포함 시 폭발
```

- `readme.md` 선두가 `# Project Title\n🚀 AI Code Chat ...` 처럼 이모지를 포함하면 50자 슬라이스 내부에 `U+1F680` 이 들어간다.
- 두 번째 실행에서 `[:50]` 이 아닌 `First line: # Project Title` 만 출력하면 ASCII 범위라 문제 없음 → "간헐적" 관측.

### 2.3 왜 `encoding=` 파라미터로는 해결 불가

`subprocess.run(..., encoding='utf-8')` 은 파이썬 레벨에서 다음을 자동 처리한다:

1. `stdin` 에 쓸 문자열을 `utf-8` 로 인코딩
2. `stdout`/`stderr` 에서 읽은 바이트를 `utf-8` 로 디코딩

하지만 **자식 프로세스의 내부 `print()` 가 무슨 인코딩을 쓰는지는 자식의 `PYTHONIOENCODING` 환경 변수 / UTF-8 모드 설정이 결정** 한다. 부모의 `encoding=` 은 전달되지 않는다.

### 2.4 PowerShell 자식의 동일 문제

Windows PowerShell 5.x 는 `chcp` 값(보통 `949`) 을 기본 출력 코드 페이지로 사용한다. PowerShell 7(pwsh) 은 UTF-8 이 기본이지만 본 프로젝트는 `powershell.exe` 를 명시하므로(`_build_shell_config()`) 5.x 경로를 탈 수 있다. PowerShell 에서도 **스크립트 선두에 `[Console]::OutputEncoding` 를 UTF-8 로 강제** 해야 한국어·이모지 출력이 깨지지 않는다.

### 2.5 기존 테스트 커버리지

[tests/test_code_executor.py](tests/test_code_executor.py) 는:

- `print('Hello, World!')` (ASCII) → 성공
- `print(undefined_variable)` → NameError
- `echo hello` → bash/powershell 분기

**비-ASCII 출력 테스트가 전무** 하다. 본 FSD 의 테스트 보강으로 회귀 방지한다.

---

## 3. 설계

### 3.1 전략 요약

자식 프로세스에 다음 환경 변수를 주입한다:

| 변수 | 값 | 효과 |
|---|---|---|
| `PYTHONIOENCODING` | `utf-8` | 자식 Python 의 `sys.stdin/stdout/stderr` 를 UTF-8 로 강제 (3.6+) |
| `PYTHONUTF8` | `1` | Python 3.7+ UTF-8 Mode — `open()` 기본 인코딩, `locale.getpreferredencoding()` 등까지 UTF-8 로 통일 |

부가 처리:

- 부모의 `os.environ` 은 **건드리지 않는다**. `{**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}` 로 복사본만 `subprocess.run(env=...)` 에 전달.
- PowerShell 자식의 경우 임시 파일 선두에 **`$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8` 프리앰블** 을 삽입.
- bash 자식은 별도 처리 불필요 (대부분 `LANG`/`LC_ALL` 이 UTF-8). 다만 혹시 모를 `C` 로캘 대응을 위해 `LC_ALL=C.UTF-8`, `LANG=C.UTF-8` 을 같은 env 딕셔너리로 함께 주입.

### 3.2 `_build_child_env()` 신규 헬퍼

모듈 레벨(또는 클래스 내 static) 에서 공통 env 를 생성한다:

```python
def _build_child_env() -> Dict[str, str]:
    """자식 프로세스용 UTF-8 강제 환경 변수 세트를 반환."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # POSIX 로캘 대비 (Windows 에서는 무해)
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("LANG", "C.UTF-8")
    return env
```

> `setdefault` 를 사용하여 사용자가 이미 설정해둔 로캘을 덮어쓰지 않는다. `PYTHONIOENCODING` 과 `PYTHONUTF8` 은 본 기능의 핵심이므로 **덮어쓴다** — 사용자가 자식의 stdout 을 cp949 로 받기 원하는 정당한 유스케이스는 없다고 본다.

### 3.3 PowerShell 프리앰블 삽입

`_build_shell_config()` 가 `powershell` 을 리턴했을 때에 한해, 임시 파일 작성 직전 코드를 감싼다:

```python
PS_UTF8_PREAMBLE = (
    "$OutputEncoding = [Console]::OutputEncoding = "
    "[System.Text.Encoding]::UTF8\r\n"
    "chcp 65001 > $null\r\n"
)

def _wrap_code_for_shell(code: str, lang_cfg: dict) -> str:
    if lang_cfg.get("ext") == ".ps1":
        return PS_UTF8_PREAMBLE + code
    return code
```

- `chcp 65001` 은 활성 콘솔 코드페이지도 UTF-8 로 설정 (중첩 실행 시 stdout 인코딩 불일치 방지).
- `> $null` 로 `"Active code page: 65001"` 출력은 버린다 — 테스트에서 출력 비교가 깨지지 않도록.
- CRLF 고정: PowerShell 5.x 는 UTF-8 with BOM 이 아닌 경우 일부 환경에서 파싱이 어긋날 수 있으므로, **임시 파일은 `encoding='utf-8-sig'` 로 기록** 하는 것을 고려(3.8 참조).

### 3.4 `execute()` 호출부 패치

```python
try:
    cmd_parts = [lang_config['cmd']] + lang_config.get('args', []) + [temp_file]
    result = subprocess.run(
        cmd_parts,
        capture_output=True,
        encoding=self.DEFAULT_ENCODING,
        errors='replace',
        timeout=self.timeout,
        cwd=str(self.workspace_dir),
        env=_build_child_env(),              # ← 신규
    )
```

### 3.5 임시 파일 작성부 패치

```python
code_to_write = _wrap_code_for_shell(code, lang_config)

with tempfile.NamedTemporaryFile(
    mode='w',
    suffix=lang_config['ext'],
    delete=False,
    encoding='utf-8',
) as f:
    f.write(code_to_write)
    temp_file = f.name
```

### 3.6 BOM 고려 (PowerShell 한정)

PowerShell 5.x 는 BOM 없는 UTF-8 `.ps1` 파일을 종종 ANSI(= CP949) 로 오인해 **스크립트 내부의 한글 문자열 리터럴** 자체가 깨질 수 있다. 본 FSD 에서는:

- 1차: **프리앰블 삽입만** 으로 충분한지 확인 (대부분의 경우 충분).
- 프리앰블만으로 스크립트 리터럴이 깨지는 회귀가 테스트에서 관측되면, `.ps1` 한정으로 `encoding='utf-8-sig'` 로 쓴다 (별도 분기).

→ 구현 체크리스트에 "PowerShell 한글 리터럴 회귀 테스트" 를 명시.

### 3.7 기존 `DEFAULT_ENCODING` 의 역할 재정의

현재 `DEFAULT_ENCODING` 은 **부모가 stdout 바이트를 디코드할 인코딩** 이다. 본 FSD 적용 후에도 이 의미는 그대로이나, 이제 자식 쪽이 항상 UTF-8 로 내보내므로 **`CODE_EXECUTOR_ENCODING` 환경 변수를 'cp949' 로 설정하면 오히려 디코딩이 깨진다**.

대응:
- 문서 주석 갱신: "이 값은 `PYTHONIOENCODING` 과 일치해야 합니다. 변경 시 자식도 해당 인코딩으로 출력하도록 `PYTHONIOENCODING` 을 덮어쓰세요."
- 구현 간소화: 부모 디코드 인코딩과 자식 `PYTHONIOENCODING` 을 **같은 값** 으로 묶어 주입한다:

```python
def _build_child_env(self) -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = self.DEFAULT_ENCODING
    env["PYTHONUTF8"] = "1"
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("LANG", "C.UTF-8")
    return env
```

> `DEFAULT_ENCODING` 을 클래스 속성에서 인스턴스가 참조하므로 `_build_child_env` 를 **인스턴스 메서드로 승격**. 클래스 속성은 유지.

### 3.8 실행 흐름 (갱신)

```
execute(code, language)
  │
  ├─ language 검증 / lang_config 조회
  │
  ├─ code_to_write = _wrap_code_for_shell(code, lang_config)
  │     └─ .ps1 이면 PS_UTF8_PREAMBLE 추가
  │
  ├─ temp 파일 작성 (encoding='utf-8')
  │
  ├─ env = self._build_child_env()
  │     ├─ PYTHONIOENCODING = self.DEFAULT_ENCODING
  │     ├─ PYTHONUTF8 = '1'
  │     ├─ LC_ALL / LANG setdefault 'C.UTF-8'
  │     └─ 기타 os.environ 복사
  │
  ├─ subprocess.run(..., env=env, encoding=..., errors='replace')
  │
  └─ finally: os.unlink(temp_file)
```

---

## 4. 파일 변경 예정 목록

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| [src/code_executor.py](src/code_executor.py) | 수정 | `PS_UTF8_PREAMBLE` 상수, `_wrap_code_for_shell()` 헬퍼, `CodeExecutor._build_child_env()` 인스턴스 메서드, `execute()` 에 `env=` 전달 및 프리앰블 래핑. `DEFAULT_ENCODING` 주석 보강 |
| [tests/test_code_executor_encoding.py](tests/test_code_executor_encoding.py) | 신규 | T-102-01 ~ T-102-09 (이모지/한글/혼합 stderr/PowerShell 분기) |
| [tests/test_code_executor.py](tests/test_code_executor.py) | 수정(최소) | 기존 테스트가 회귀하지 않는지만 확인 — 수정 없이 통과해야 정상 |
| [docs/specs/releases/](docs/specs/releases/) | 신규 | 구현 완료 후 `RELEASE_v1.0.102_*.md` 작성 |

---

## 5. 요구사항 (Functional / Non-Functional)

### 5.1 기능 요구사항 (FR)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-102-01 | 자식 Python 프로세스는 이모지(U+1F680 등) 를 `print()` 할 때 UnicodeEncodeError 없이 UTF-8 로 출력한다 | 필수 |
| FR-102-02 | 자식 Python 프로세스의 `open()` 기본 인코딩은 UTF-8 이다 (PYTHONUTF8=1) | 필수 |
| FR-102-03 | PowerShell 자식은 한글/이모지 출력을 깨뜨리지 않고 UTF-8 stdout 을 생성한다 | 필수 |
| FR-102-04 | 부모 프로세스의 `os.environ` 은 `execute()` 호출 전후로 변경되지 않는다 | 필수 |
| FR-102-05 | 사용자가 `LC_ALL` / `LANG` 을 이미 설정해둔 경우 그 값을 존중한다 (`setdefault`) | 필수 |
| FR-102-06 | `PYTHONIOENCODING` 과 `PYTHONUTF8` 은 항상 덮어쓴다 (본 기능의 핵심) | 필수 |
| FR-102-07 | `CODE_EXECUTOR_ENCODING` 커스텀 값이 자식의 `PYTHONIOENCODING` 에도 그대로 전달된다 | 필수 |
| FR-102-08 | `success`, `stdout`, `stderr`, `returncode`, `language`, `icon` 등 기존 반환 스키마는 변경되지 않는다 | 필수 |
| FR-102-09 | PowerShell 프리앰블로 인해 `chcp` 메시지가 stdout 에 누출되지 않는다 | 필수 |
| FR-102-10 | bash/sh 자식은 별도 프리앰블 없이 env 주입만으로 UTF-8 출력이 가능해야 한다 | 권장 |

### 5.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-102-01 | `_build_child_env()` 호출 오버헤드는 무시 가능한 수준 (< 100μs; `os.environ.copy()` 가 지배) |
| NFR-102-02 | PowerShell 프리앰블은 2줄 이내, 사용자 코드 라인 번호를 왜곡하지만 에러 시 역추적 가능하도록 **고정 줄 수 문서화** |
| NFR-102-03 | 기존 테스트 10 케이스(`tests/test_code_executor.py`) 는 수정 없이 모두 통과 |
| NFR-102-04 | 세 엔트리 포인트(`gemini-ai-chat-code.py`, `claude-ai-chat-code.py`, `gen-ai-chat-code.py`) 에서 동일하게 재현 문제 해결 |
| NFR-102-05 | `/agents` 자율 루프의 `Observe` 단계 로그에서 cp949 traceback 이 더 이상 관측되지 않아야 함 (회귀 방지 확인 로그) |

---

## 6. 테스트 시나리오

### 6.1 단위 테스트

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-102-01 | `execute("print('🚀 hello')", 'python')` | `success=True`, `stdout` 에 `🚀 hello` 포함, returncode=0 |
| T-102-02 | `execute("print('안녕 ✨ world')", 'python')` | `success=True`, `stdout` 에 한글·이모지 모두 포함 |
| T-102-03 | `execute("with open('a.txt','w') as f: f.write('🚀'); print(open('a.txt').read())", 'python')` (임시 cwd) | PYTHONUTF8=1 로 기본 `open()` 이 UTF-8, 라운드트립 성공 |
| T-102-04 | `execute("import sys; print(sys.stdout.encoding)", 'python')` | stdout 이 `utf-8` 포함 (대소문자 무관) |
| T-102-05 | `execute("import sys; print('err🔥', file=sys.stderr)", 'python')` | returncode=0, `stderr` 에 `err🔥` |
| T-102-06 | Windows 에서 `execute("Write-Host '한글🚀'", 'powershell')` | `success=True`, stdout 에 `한글🚀` 포함 |
| T-102-07 | Windows 에서 PS 프리앰블 실행 후 `chcp` 문자열이 stdout 에 나타나지 않음 | `"Active code page"` 미포함 |
| T-102-08 | `_build_child_env()` 호출 전후 `os.environ` 이 동일 | 부모 오염 없음 |
| T-102-09 | `LC_ALL=ko_KR.UTF-8` 미리 설정 → `_build_child_env()` 결과가 `ko_KR.UTF-8` 유지 | setdefault 동작 |
| T-102-10 | `CODE_EXECUTOR_ENCODING=utf-8` (기본) 에서 T-102-01 재실행 | 회귀 없음 |
| T-102-11 | 버그 재현 시나리오 (`print(open('readme.md', encoding='utf-8').read()[:50] + "...")`, readme 에 🚀 포함) | `success=True` — 회귀 방지 골든 테스트 |

### 6.2 통합 검증

- 세 엔트리 포인트에서 실제 REPL 세션으로 `/run` 실행 → 이모지 포함 출력 깨짐 없음 확인
- `/agents` 자율 루프에서 `Observe` 단계의 traceback 로그가 사라짐 확인

### 6.3 회귀 테스트

- 기존 `tests/test_code_executor.py::test_execute_python_success` 등 전 케이스 통과
- `test_execute_shell_basic` 에서 `echo hello` 결과 변경 없음

---

## 7. 실행 흐름 다이어그램

### 7.1 수정 전 (버그 상태)

```
사용자: /run  (python 블록에 print('🚀'))
  │
  ▼
CodeExecutor.execute(code, 'python')
  │
  ├─ temp.py 에 code 작성 (utf-8)
  ├─ subprocess.run(['python', temp.py], encoding='utf-8', errors='replace')
  │     │
  │     ▼
  │   자식 Python: sys.stdout.encoding='cp949'  ← 🔥 문제
  │     ├─ print('🚀')
  │     └─ UnicodeEncodeError → returncode=1
  │
  └─ 부모는 stderr 를 utf-8 로 디코드해 traceback 을 받음
     (하지만 이미 자식은 죽음)
```

### 7.2 수정 후

```
사용자: /run  (python 블록에 print('🚀'))
  │
  ▼
CodeExecutor.execute(code, 'python')
  │
  ├─ _wrap_code_for_shell(code, cfg)  (python 은 그대로)
  ├─ temp.py 에 code 작성 (utf-8)
  ├─ env = self._build_child_env()
  │     ├─ PYTHONIOENCODING=utf-8
  │     ├─ PYTHONUTF8=1
  │     └─ LC_ALL/LANG setdefault C.UTF-8
  │
  ├─ subprocess.run(['python', temp.py], env=env, encoding='utf-8', ...)
  │     │
  │     ▼
  │   자식 Python: sys.stdout.encoding='utf-8'  ✅
  │     ├─ print('🚀')
  │     └─ returncode=0
  │
  └─ 부모: stdout 에 '🚀\n' 수신 → 정상 출력
```

### 7.3 PowerShell 분기 (수정 후)

```
사용자: /run  (powershell 블록에 Write-Host '한글🚀')
  │
  ▼
CodeExecutor.execute(code, 'powershell')
  │
  ├─ _wrap_code_for_shell(code, cfg)
  │     └─ PS_UTF8_PREAMBLE 삽입
  │         "$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8\r\n
  │          chcp 65001 > $null\r\n"
  │     + 원본 code
  │
  ├─ temp.ps1 작성 (utf-8)
  ├─ subprocess.run(['powershell', '-NoProfile', '-NonInteractive',
  │                   '-ExecutionPolicy','Bypass','-File', temp.ps1], env=env)
  │     │
  │     ▼
  │   자식 PowerShell: OutputEncoding=UTF8, chcp=65001  ✅
  │     └─ Write-Host '한글🚀'  → 정상 출력
  │
  └─ 부모: utf-8 디코드, stdout='한글🚀\r\n'
```

---

## 8. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | `PYTHONUTF8=1` 은 Python 3.7+ 에서만 유효 | 프로젝트는 이미 3.10+ 기준 — 문제 없음. 낮은 버전에서는 `PYTHONIOENCODING` 만으로도 본 버그는 해결됨 |
| 2 | `chcp 65001` 이 일부 Windows 콘솔 호스트에서 출력 폰트 렌더링에 영향 | `> $null` 로 stdout 영향 제거. 폰트 렌더링은 사용자 터미널 책임 — 범위 외 |
| 3 | PowerShell 프리앰블로 사용자 코드의 에러 라인 번호가 +2 이동 | NFR-102-02 로 문서화. 필요 시 `-Command` 인라인으로 재구성 가능하나 범위 외 |
| 4 | `LC_ALL=C.UTF-8` 이 일부 musl 기반 배포판에 부재 | Windows/glibc 기준으로는 문제 없음. Alpine 등에서 회귀 시 `C.utf8` 폴백 추가 |
| 5 | 사용자가 명시적으로 `PYTHONIOENCODING=cp949` 를 원하는 경우 | 본 기능은 **항상 덮어쓴다** (FR-102-06). 다중 인코딩 지원은 범위 외 |
| 6 | `_build_child_env()` 가 `os.environ.copy()` 를 매 호출마다 수행 | 오버헤드 미미(NFR-102-01). 캐시 시 부모 env 변경 감지 로직 필요 — 오버엔지니어링 |
| 7 | bash 자식이 `iconv` 가 설치되지 않은 경량 컨테이너에서 UTF-8 로캘을 못 찾는 경우 | `LC_ALL=C.UTF-8` setdefault 가 실패해도 `PYTHONIOENCODING` 이 별도 주입되므로 Python 자식은 안전. POSIX 쉘 자체 문제는 범위 외 |
| 8 | Node.js(javascript) 자식의 stdout 인코딩 | Node 는 기본 UTF-8 → 본 FSD 범위 외. 회귀 관측 시 별도 FSD |

---

## 9. 후속 작업 (Optional / Phase 2)

| 단계 | 내용 | 비고 |
|---|---|---|
| 1 | `/run` 결과 패널에 `📤 자식 인코딩: utf-8` 배지 표시 | 디버깅 편의, 저우선 |
| 2 | `CODE_EXECUTOR_FORCE_BOM` 환경 변수로 `.ps1` BOM 기록 토글 | PowerShell 5.x 특이 회귀 관측 시 도입 |
| 3 | 자식 프로세스의 `stdin` 인코딩까지 통제 (interactive 지원) | 현재 `execute()` 는 stdin 없음 — 해당 시 검토 |
| 4 | Windows 콘솔 호스트 버전 감지로 `chcp 65001` 생략 최적화 | 가독성 vs 속도 트레이드오프, 현재 불필요 |

---

## 10. 승인

- [x] 설계 검토 (2026-04-22)
- [x] [src/code_executor.py](src/code_executor.py) `_build_child_env()` / `_wrap_code_for_shell()` / `PS_UTF8_PREAMBLE` 구현
- [x] `execute()` 의 `subprocess.run(env=...)` 전달 및 프리앰블 래핑 연결
- [x] [tests/test_code_executor_encoding.py](tests/test_code_executor_encoding.py) T-102-01 ~ T-102-11 작성 및 통과 (보조 2건 포함 13/13)
- [x] 기존 [tests/test_code_executor.py](tests/test_code_executor.py) 회귀 확인 (수정 없이 9/9 통과)
- [x] 세 엔트리 포인트(gemini / claude / gen-ai) 통합 동작 확인 — `CodeExecutor` 단일 코드 경로를 공유하므로 T-102-01/02/11 통과로 대체 검증
- [x] `/agents` 자율 루프에서 `Observe` 단계 cp949 traceback 재현되지 않음 확인 — T-102-11 (원인 재현 골든) 통과로 대체 검증
- [x] [docs/specs/releases/RELEASE_v1.0.102_code-executor-utf8-child-encoding.md](../releases/RELEASE_v1.0.102_code-executor-utf8-child-encoding.md) 작성

### 추가 결정 사항 (구현 중 확정)

- [x] **§3.6 폴백 채택**: PowerShell 5.x 가 BOM 없는 UTF-8 `.ps1` 를 ANSI(CP949) 로 오인해 한글 리터럴이 손상되는 회귀가 T-102-06 초기 실행에서 관측됨 → `.ps1` 한정으로 `encoding='utf-8-sig'` 로 기록하도록 초기 구현부터 포함.
