# RELEASE v1.0.102 — CodeExecutor 자식 프로세스 UTF-8 강제

| 항목 | 내용 |
|---|---|
| 릴리즈 버전 | v1.0.102 |
| 릴리즈 일자 | 2026-04-22 |
| 브랜치 | release_v1.0.100 |
| 요구 문서 | [FSD v1.0.102](../requirements/FSD_v1.0.102_code-executor-utf8-child-encoding.md) |

---

## 변경 요약

Windows 한국어 로캘(CP949) 에서 자식 Python 이 이모지를 `print()` 할 때 발생하던
`UnicodeEncodeError: 'cp949' codec can't encode character '\U0001f680' ...` 를 제거한다.
부모의 `os.environ` 은 그대로 두고, `subprocess.run(env=...)` 에 UTF-8 강제
환경 변수만 복사본으로 주입하는 방식이다. PowerShell 자식에는 UTF-8 프리앰블을
스크립트 선두에 삽입하고, 파싱 단계의 리터럴 손상을 막기 위해 `.ps1` 임시 파일만
BOM(`utf-8-sig`) 으로 기록한다.

---

## 변경 파일

### 신규

| 파일 | 설명 |
|---|---|
| [tests/test_code_executor_encoding.py](../../../tests/test_code_executor_encoding.py) | T-102-01 ~ T-102-11 + 보조 2건 (13 케이스) |

### 수정

| 파일 | 변경 내용 |
|---|---|
| [src/code_executor.py](../../../src/code_executor.py) | `PS_UTF8_PREAMBLE` 상수, `_wrap_code_for_shell()` 모듈 헬퍼, `CodeExecutor._build_child_env()` 인스턴스 메서드 추가. `execute()` 에 `env=` 전달·프리앰블 래핑·`.ps1` BOM 기록 연결. `DEFAULT_ENCODING` 의미 주석 보강 |

---

## 핵심 변경 내용

### 1. 자식 환경 변수 주입 — `_build_child_env()`

```python
def _build_child_env(self) -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = self.DEFAULT_ENCODING   # 자식 stdout/stderr
    env["PYTHONUTF8"] = "1"                           # open() 기본 인코딩까지 UTF-8
    env.setdefault("LC_ALL", "C.UTF-8")               # 사용자 설정 존중
    env.setdefault("LANG", "C.UTF-8")
    return env
```

- 부모의 `os.environ` 은 복사본만 생성 — 호출 전후로 동일.
- `PYTHONIOENCODING` / `PYTHONUTF8` 은 항상 덮어쓴다 (FR-102-06).
- `LC_ALL` / `LANG` 은 `setdefault` 로 사용자 환경을 존중 (FR-102-05).

### 2. PowerShell 프리앰블 — `PS_UTF8_PREAMBLE` + `_wrap_code_for_shell()`

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

- `chcp 65001` 의 `"Active code page: 65001"` 출력은 `> $null` 로 버림 (FR-102-09).

### 3. `.ps1` 전용 BOM 기록 (FSD §3.6 폴백 채택)

PowerShell 5.x 가 BOM 없는 UTF-8 `.ps1` 을 ANSI(CP949) 로 오인해 **한글/이모지
리터럴을 파싱 단계에서 손상** 시키는 회귀가 T-102-06 초기 실행에서 관측되어,
`.ps1` 에 한해 `utf-8-sig` 로 기록하는 폴백을 즉시 적용.

```python
file_encoding = 'utf-8-sig' if lang_config.get('ext') == '.ps1' else 'utf-8'
```

### 4. `execute()` 호출부 연결

```python
result = subprocess.run(
    cmd_parts,
    capture_output=True,
    encoding=self.DEFAULT_ENCODING,
    errors='replace',
    timeout=self.timeout,
    cwd=str(self.workspace_dir),
    env=self._build_child_env(),   # ← 신규
)
```

---

## 테스트 결과

```
tests/test_code_executor_encoding.py   13 passed
tests/test_code_executor.py             9 passed
------------------------------------------------------
합계                                   22 passed in 12.93s
```

| 테스트 ID | 시나리오 | 결과 |
|---|---|---|
| T-102-01 | `print('🚀 hello')` | ✅ |
| T-102-02 | `print('안녕 ✨ world')` | ✅ |
| T-102-03 | `open('a.txt','w')` 기본 인코딩 UTF-8 라운드트립 | ✅ |
| T-102-04 | 자식 `sys.stdout.encoding == 'utf-8'` | ✅ |
| T-102-05 | stderr 이모지 출력 | ✅ |
| T-102-06 | PowerShell `Write-Host '한글🚀'` | ✅ (`.ps1` BOM 폴백 적용 후) |
| T-102-07 | `chcp` 메시지가 stdout 에 누출되지 않음 | ✅ |
| T-102-08 | `_build_child_env()` 가 부모 `os.environ` 을 오염시키지 않음 | ✅ |
| T-102-09 | `LC_ALL=ko_KR.UTF-8` 존중 (`setdefault`) | ✅ |
| T-102-10 | 기본 `CODE_EXECUTOR_ENCODING=utf-8` 회귀 | ✅ |
| T-102-11 | 골든: `readme.md[:50]` (🚀 포함) `print()` | ✅ |
| 보조 | `_wrap_code_for_shell` python / ps1 분기 | ✅ / ✅ |

기존 `tests/test_code_executor.py` 9 케이스는 **수정 없이** 모두 통과 (NFR-102-03).

---

## 해결된 증상

```
👁  Observe #2
────────────────────────────────────────────────────────────
❌ 코드 실행 (python)
returncode=1
Traceback (most recent call last):
  File "C:\Users\...\tmpx0cpr1qr.py", line 6, in <module>
    print(f.read()[:50] + "...")
UnicodeEncodeError: 'cp949' codec can't encode character '\U0001f680' ...
```

→ 자식이 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` 로 기동되어
`sys.stdout.encoding` 이 `utf-8` 로 고정되므로 재발하지 않는다.

---

## 회귀 영향

- 부모 `os.environ` 미변경: 동일 프로세스의 다른 기능(API 클라이언트 등) 영향 없음.
- `encoding=` / `errors='replace'` 기존 디코딩 정책은 그대로 유지.
- Node.js(javascript) 자식은 기본 UTF-8 이므로 별도 변경 없음 — 회귀 없음 확인.
- 세 엔트리 포인트(`gemini-ai-chat-code.py` / `claude-ai-chat-code.py` /
  `gen-ai-chat-code.py`) 는 `CodeExecutor` 공유 — 모두 동일하게 혜택을 받는다.

---

## 이슈/후속

- PowerShell 사용자 코드의 에러 라인 번호가 프리앰블 2줄만큼 이동 (NFR-102-02).
- `.ps1` 의 BOM 기록은 FSD §3.6 의 2차 폴백이었으나 T-102-06 회귀 관측으로
  초기 구현부터 포함.
- `CODE_EXECUTOR_FORCE_BOM` 토글·Phase 2 항목은 현재 불필요.
