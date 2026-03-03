---
description: Python 테스트 및 PowerShell 명령어 실행 규칙
---

# 명령어 실행 규칙 (Command Execution Rules)

이 프로젝트에서 명령어 실행 시 준수해야 할 규칙입니다.

## 0. 한글 인코딩 설정 (필수 선행)

Windows PowerShell 명령어 파이프라인에서 **한글이 깨지는 현상**을 방지하기 위해, 명령어 실행 전 반드시 다음 UTF-8 인코딩 3종 세트를 설정합니다. (`chcp 65001` 단독 사용 시 파이프라인에서 깨짐 현상 발생)

### 규칙
- **모든 `run_command` 호출 시** 명령어 앞에 다음 접두사를 반드시 붙여 실행합니다:
  `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING="utf-8";`
- 이는 콘솔 출력창 인코딩, 파이프라인 입출력 인코딩, Python 내부 스트림 인코딩을 일관되게 UTF-8로 맞춥니다.

### 사용 방법
```powershell
# 핵심 인코딩 프리셋을 변수나 직접 인라인으로 삽입하여 명령어 실행
$enc = '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING="utf-8";'

# 단일 명령어 실행
Invoke-Expression "$enc python -m unittest tests.test_module_name -v"
# 또는 직접 붙여넣기
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $env:PYTHONIOENCODING="utf-8"; python -m tests.test_command_suggestion 2>&1 | ForEach-Object { $_ }
```

### 잘못된 방법 (피해야 할 것)
```powershell
# chcp 65001 단독 사용 - 파이프라인(| ForEach-Object) 이후 한글이 깨져서 출력됨
chcp 65001; python -m tests.test_command_suggestion 2>&1 | ForEach-Object { $_ }
# 결과: [OK] ?꾩껜 紐낅졊?? 29媛?  ← 여전히 깨짐

# 설정 없이 실행
python -m tests.test_command_suggestion
```

## 1. Python 테스트 실행

### 올바른 방법
```powershell
# unittest 사용 (pytest 미설치 환경)
python -m unittest tests.test_module_name -v

# 특정 테스트 클래스 실행
python -m unittest tests.test_module_name.TestClassName -v

# 특정 테스트 메서드 실행
python -m unittest tests.test_module_name.TestClassName.test_method_name -v
```

### 잘못된 방법 (피해야 할 것)
```powershell
# pytest가 설치되어 있지 않음 - 사용 금지
python -m pytest tests/test_file.py

# 직접 실행 - import 오류 발생 가능
python tests/test_file.py
```

## 2. Python 모듈 Import 테스트

### 올바른 방법
```powershell
# 프로젝트 루트에서 실행
python -c "from src.module_name import ClassName; print('Import 성공')"
```

## 3. PowerShell 파이프라인 규칙

### 출력 제한
긴 출력을 생성하는 명령어는 반드시 출력을 제한합니다:

```powershell
# 앞부분만 보기
Get-Content file.txt | Select-Object -First 50

# 뒷부분만 보기
Get-Content file.txt | Select-Object -Last 30

# 문자열 검색
Get-Content file.txt | Select-String "pattern"
```

### 잘못된 방법 (피해야 할 것)
```powershell
# 전체 출력 - 너무 길어질 수 있음
Get-Content large_file.txt

# cat 별칭 사용 - 전체 출력됨
cat file.txt
```

## 4. 파일 경로 규칙

### Windows PowerShell에서
```powershell
# 상대 경로 사용 (권장)
python src\module_name.py

# 또는 따옴표로 감싸기
python ".\src\module_name.py"
```

### Python 모듈로 실행
```powershell
# 모듈로 실행 (권장)
python -m src.module_name
```

## 5. 가상환경 확인

### 가상환경 활성화 확인
```powershell
# 현재 Python 경로 확인
python -c "import sys; print(sys.executable)"

# 가상환경이 활성화되어 있는지 확인
$env:VIRTUAL_ENV
```

## 6. 파일 존재 확인

### 명령어 실행 전 확인
```powershell
# 파일 존재 확인
Test-Path "path\to\file.py"

# 디렉토리 존재 확인
Test-Path "path\to\directory" -PathType Container
```

## 7. 에러 출력 포함

### stderr 포함하여 출력
```powershell
# Python 실행 시 에러 포함
python script.py 2>&1 | Select-Object -First 50

# 에러만 보기
python script.py 2>&1 | Where-Object { $_ -match "Error|Exception|Traceback" }
```

## 8. 이 프로젝트의 테스트 실행 예시

### 기본 실행 (메소드별 결과 표시)
```powershell
# -v 옵션으로 verbose 모드 실행
python -m unittest tests.test_gemini_tool_use -v 2>&1 | ForEach-Object { $_ }

# 전체 테스트 (discover)
python -m unittest discover -s tests -v 2>&1 | ForEach-Object { $_ }
```

### 개별 테스트 모듈 실행
```powershell
# Claude 테스트
python -m unittest tests.test_claude_tool_use -v 2>&1 | ForEach-Object { $_ }

# GenAI 테스트
python -m unittest tests.test_genai_tool_use -v 2>&1 | ForEach-Object { $_ }

# Gemini 테스트
python -m unittest tests.test_gemini_tool_use -v 2>&1 | ForEach-Object { $_ }

# DiffViewer 테스트
python -m unittest tests.test_diff_viewer -v 2>&1 | ForEach-Object { $_ }
```

### 테스트 결과 요약만 보기
```powershell
python -m unittest tests.test_gemini_tool_use 2>&1 | Select-String -Pattern "^test_|ok$|FAIL$|ERROR$|Ran|OK$|FAILED"
```

## 9. 이 프로젝트의 어시스턴트 실행

```powershell
# Claude 어시스턴트
python claude-ai-chat-code.py

# GenAI 어시스턴트
python gen-ai-chat-code.py

# Gemini 어시스턴트
python gemini-ai-chat-code.py
```

## 10. 대화창에 진행사항 출력시 한글로 출력
- OpenChat Agent 대화창에 한글로 출력한다.