# BUG: /save 명령어 파일 저장 실패 분석 및 개선

**문서 버전**: v1.0.001  
**작성일자**: 2026-01-19  
**수정일자**: 2026-01-19  
**대상 파일**: `claude-ai-chat-code01.py`  
**심각도**: Medium  
**상태**: ✅ 수정 완료

---

## 1. 증상

`/save` 명령어 실행 시 파일이 저장되지 않고 다음 메시지가 출력됨:

```
⚠️  저장된 파일이 없습니다.
💡 파일 형식: ```filename:path/to/file.ext
```

---

## 2. 원인 분석

### 2.1 현재 파일 추출 로직 (Lines 431-433)

```python
# ```filename:path/to/file.ext 형식 찾기
pattern = r'```filename:(.+?)\n(.*?)```'
matches = re.findall(pattern, response, re.DOTALL)
```

### 2.2 문제점

Claude AI가 실제로 생성하는 코드 블록 형식은 다음과 같은 **다양한 형태**를 가집니다:

| 기대 형식 | Claude AI 실제 출력 형식 |
|-----------|-------------------------|
| `` ```filename:path/file.py `` | `` ```python `` |
| - | `` ```javascript `` |
| - | `` ```markdown `` |
| - | `` ```json `` |

**Claude AI는 표준 마크다운 코드 블록 형식을 사용**하며, 커스텀 `filename:` 접두사를 사용하지 않습니다.

### 2.3 근본 원인

1. **시스템 프롬프트 미준수**: Claude AI가 시스템 프롬프트에서 지정한 `` ```filename: `` 형식을 항상 따르지 않음
2. **패턴 불일치**: 정규식 패턴이 Claude의 실제 응답 형식과 맞지 않음
3. **언어 식별자 충돌**: `` ```python ``, `` ```javascript `` 등 언어 식별자가 파일명으로 오인될 수 없음

---

## 3. 해결 방안

### 3.1 방안 A: 시스템 프롬프트 강화 (권장)

시스템 프롬프트를 더 명확하게 수정하여 Claude가 지정된 형식을 따르도록 유도:

```python
self.system_prompt = """당신은 전문 소프트웨어 개발 어시스턴트입니다.
사용자의 프로젝트 파일을 분석하고, 코드를 생성하거나 수정하며, 문서를 작성합니다.

[중요] 파일을 생성하거나 수정할 때는 반드시 다음 형식을 사용하세요:
```filename:경로/파일명.확장자
코드 내용
```

예시:
```filename:src/utils/helper.py
def hello():
    return "Hello, World!"
```

이 형식을 반드시 지켜야 사용자가 파일을 저장할 수 있습니다.
언어 식별자(python, javascript 등)를 사용하지 말고, 반드시 filename: 접두사를 사용하세요."""
```

### 3.2 방안 B: 다중 패턴 지원 (대안)

다양한 코드 블록 형식을 인식하도록 정규식 패턴 확장:

```python
def extract_and_save_files(self, response: str) -> List[str]:
    """AI 응답에서 파일을 추출하여 저장"""
    import re

    saved_files = []
    
    # 패턴 1: ```filename:path/to/file.ext 형식 (기본)
    pattern1 = r'```filename:(.+?)\n(.*?)```'
    matches = re.findall(pattern1, response, re.DOTALL)
    
    for filepath_str, content in matches:
        filepath_str = filepath_str.strip()
        self._save_file(filepath_str, content, saved_files)
    
    # 패턴 2: 파일 경로가 주석으로 표시된 경우
    # # 파일: path/to/file.ext
    # ```python
    # 코드
    # ```
    pattern2 = r'#\s*(?:파일|File|Path):\s*(.+?)\n```\w*\n(.*?)```'
    matches2 = re.findall(pattern2, response, re.DOTALL | re.IGNORECASE)
    
    for filepath_str, content in matches2:
        filepath_str = filepath_str.strip()
        if filepath_str not in [f for f in saved_files]:
            self._save_file(filepath_str, content, saved_files)
    
    return saved_files

def _save_file(self, filepath_str: str, content: str, saved_files: List[str]) -> None:
    """파일 저장 헬퍼 메서드"""
    filepath = self.file_manager.workspace_dir / filepath_str

    if filepath.exists():
        print(f"\n⚠️  파일이 이미 존재합니다: {filepath_str}")
        confirm = input("덮어쓰시겠습니까? (y/N): ").strip().lower()
        if confirm != 'y':
            print(f"⏭️  건너뛰기: {filepath_str}")
            return

    if self.file_manager.write_file(filepath, content.strip()):
        saved_files.append(filepath_str)
        print(f"✅ 파일 저장됨: {filepath_str}")
```

### 3.3 방안 C: 대화형 파일 저장 (사용자 UX 개선)

패턴 매칭 실패 시 사용자가 직접 파일명을 지정할 수 있도록 대화형 모드 추가:

```python
def extract_and_save_files(self, response: str) -> List[str]:
    """AI 응답에서 파일을 추출하여 저장"""
    import re

    # 기본 패턴 매칭
    pattern = r'```filename:(.+?)\n(.*?)```'
    matches = re.findall(pattern, response, re.DOTALL)

    # 일반 코드 블록 찾기 (filename: 없이)
    general_pattern = r'```(\w+)?\n(.*?)```'
    general_matches = re.findall(general_pattern, response, re.DOTALL)
    
    saved_files = []

    if matches:
        # 기존 로직
        for filepath_str, content in matches:
            # ... 저장 로직
            pass
    elif general_matches:
        print("\n📋 파일명이 지정되지 않은 코드 블록이 발견되었습니다:")
        for i, (lang, content) in enumerate(general_matches, 1):
            preview = content[:100].replace('\n', ' ')
            print(f"  [{i}] ({lang or 'text'}) {preview}...")
        
        print("\n각 코드 블록을 저장하려면 파일 경로를 입력하세요 (건너뛰기: Enter)")
        for i, (lang, content) in enumerate(general_matches, 1):
            filepath_str = input(f"  [{i}] 파일 경로: ").strip()
            if filepath_str:
                # 저장 로직
                pass
    
    return saved_files
```

---

## 4. 권장 수정 사항

### 4.1 즉시 적용 (방안 A + 일부 B)

#### 수정 위치: Lines 311-320

**수정 전:**
```python
self.system_prompt = """당신은 전문 소프트웨어 개발 어시스턴트입니다.
사용자의 프로젝트 파일을 분석하고, 코드를 생성하거나 수정하며, 문서를 작성합니다.

코드를 생성할 때는 다음 형식을 사용하세요:
# ```filename:path/to/file.ext
# 코드 내용
# ```

여러 파일을 생성할 때는 각 파일마다 위 형식을 반복하세요.
파일 경로는 프로젝트 루트를 기준으로 상대 경로를 사용하세요."""
```

**수정 후:**
```python
self.system_prompt = """당신은 전문 소프트웨어 개발 어시스턴트입니다.
사용자의 프로젝트 파일을 분석하고, 코드를 생성하거나 수정하며, 문서를 작성합니다.

[필수] 코드나 파일을 생성할 때는 반드시 아래 형식을 정확히 따르세요:

```filename:경로/파일명.확장자
코드 내용
```

예시:
```filename:src/main.py
print("Hello, World!")
```

```filename:README.md
# 프로젝트 제목
```

주의사항:
- 반드시 ```filename: 형식을 사용하세요 (```python, ```javascript 사용 금지)
- 여러 파일은 각각 별도의 코드 블록으로 작성하세요
- 파일 경로는 프로젝트 루트 기준 상대 경로를 사용하세요"""
```

---

## 5. 테스트 시나리오

### 5.1 성공 케이스

**입력:**
```
Python으로 Hello World 프로그램을 작성해줘
```

**기대 응답:**
```markdown
```filename:hello.py
print("Hello, World!")
```
```

**검증:**
- `/save` 실행 시 `hello.py` 파일 생성 확인

### 5.2 실패 케이스 (수정 전)

**입력:**
```
Python으로 Hello World 프로그램을 작성해줘
```

**실제 응답 (문제):**
```markdown
```python
print("Hello, World!")
```
```

**결과:**
- 패턴 불일치로 파일 추출 실패

---

## 6. 검증 체크리스트

- [ ] 시스템 프롬프트 수정 적용
- [ ] Claude가 `filename:` 형식으로 응답하는지 확인
- [ ] `/save` 명령어로 파일 저장 성공 여부 확인
- [ ] 다중 파일 저장 테스트
- [ ] 기존 파일 덮어쓰기 확인 다이얼로그 동작 확인

---

## 7. 참고

- **관련 파일**: `claude-ai-chat-code01.py`, `gen-ai-chat-code01.py`
- **관련 FSD**: `FSD_Claude_API_Migration_v1.0.001.md`
