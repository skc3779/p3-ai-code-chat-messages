# GitHub Copilot Instructions

## 언어 설정
- 모든 응답과 진행사항은 **한글**로 출력한다.

---

## PowerShell 명령어 실행 규칙

### UTF-8 인코딩 (필수 선행 — 모든 명령어에 적용)

Windows PowerShell 파이프라인에서 한글 깨짐을 방지하기 위해, **모든 명령어 실행 전** 반드시 아래 인코딩 3종 세트를 앞에 붙인다.  
(`chcp 65001` 단독 사용 시 파이프라인에서 여전히 깨짐 발생 — 사용 금지)

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING="utf-8";
```

**올바른 예시:**
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING="utf-8"; python -m unittest tests.test_module_name -v 2>&1 | ForEach-Object { $_ }
```

**금지 패턴:**
```powershell
# ❌ chcp 단독 사용
chcp 65001; python -m unittest tests.test_module_name -v

# ❌ 인코딩 설정 없이 실행
python -m unittest tests.test_module_name -v
```

---

## Python 테스트 실행 규칙

### 테스트 프레임워크
- **pytest는 설치되어 있지 않으므로 사용 금지**
- 반드시 `python -m unittest` 사용

### 올바른 실행 방법

```powershell
# 모듈 전체 실행
python -m unittest tests.test_module_name -v

# 특정 클래스 실행
python -m unittest tests.test_module_name.TestClassName -v

# 특정 메서드 실행
python -m unittest tests.test_module_name.TestClassName.test_method_name -v

# 전체 테스트 discover
python -m unittest discover -s tests -v 2>&1 | ForEach-Object { $_ }
```

### 금지 패턴

```powershell
# ❌ pytest 사용 금지
python -m pytest tests/test_file.py

# ❌ 직접 실행 금지 (import 오류 발생)
python tests/test_file.py
```

---

## 이 프로젝트의 테스트 모듈

| 테스트 명령어 | 설명 |
|---|---|
| `python -m unittest tests.test_claude_tool_use -v` | Claude 도구 사용 테스트 |
| `python -m unittest tests.test_genai_tool_use -v` | GenAI 도구 사용 테스트 |
| `python -m unittest tests.test_gemini_tool_use -v` | Gemini 도구 사용 테스트 |
| `python -m unittest tests.test_diff_viewer -v` | DiffViewer 테스트 |

**실행 시 항상 인코딩 프리셋 포함:**
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING="utf-8"; python -m unittest tests.test_claude_tool_use -v 2>&1 | ForEach-Object { $_ }
```

**테스트 결과 요약만 볼 때:**
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING="utf-8"; python -m unittest tests.test_gemini_tool_use 2>&1 | Select-String -Pattern "^test_|ok$|FAIL$|ERROR$|Ran|OK$|FAILED"
```

---

## 이 프로젝트의 어시스턴트 실행

```powershell
# Claude 어시스턴트
python claude-ai-chat-code.py

# GenAI 어시스턴트
python gen-ai-chat-code.py

# Gemini 어시스턴트
python gemini-ai-chat-code.py
```

---

## Python 모듈 Import 테스트

```powershell
# 프로젝트 루트에서 실행
python -c "from src.module_name import ClassName; print('Import 성공')"
```

---

## PowerShell 파이프라인 출력 제한 규칙

긴 출력을 생성하는 명령어는 반드시 출력을 제한한다.

```powershell
# ✅ 앞부분만 보기
Get-Content file.txt | Select-Object -First 50

# ✅ 뒷부분만 보기
Get-Content file.txt | Select-Object -Last 30

# ✅ 패턴 검색
Get-Content file.txt | Select-String "pattern"

# ✅ Python 에러만 필터링
python script.py 2>&1 | Where-Object { $_ -match "Error|Exception|Traceback" }
```

**금지 패턴:**
```powershell
# ❌ 전체 출력 (너무 길어짐)
Get-Content large_file.txt

# ❌ cat 별칭 사용 (전체 출력됨)
cat file.txt
```

---

## 파일 경로 규칙

```powershell
# ✅ 상대 경로 사용 (권장)
python src\module_name.py

# ✅ 따옴표로 감싸기
python ".\src\module_name.py"

# ✅ 모듈로 실행 (권장)
python -m src.module_name
```

---

## 사전 확인 규칙

명령어 실행 전 파일/디렉토리 존재 여부를 확인한다.

```powershell
# 파일 존재 확인
Test-Path "path\to\file.py"

# 디렉토리 존재 확인
Test-Path "path\to\directory" -PathType Container

# 가상환경 확인
python -c "import sys; print(sys.executable)"
$env:VIRTUAL_ENV
```

---

## 프로젝트 구조

```
/
├── src/                    # 핵심 소스 모듈
├── tests/                  # unittest 테스트 모듈
├── ai-proxy/               # AI 프록시 서버
│   └── providers/          # AI 공급자 구현체
├── build_scripts/          # 빌드 PowerShell 스크립트
├── docs/specs/             # 사양 및 요구사항 문서
├── logs/                   # 실행 로그
├── claude-ai-chat-code.py  # Claude 어시스턴트 진입점
├── gen-ai-chat-code.py     # GenAI 어시스턴트 진입점
└── gemini-ai-chat-code.py  # Gemini 어시스턴트 진입점
```
