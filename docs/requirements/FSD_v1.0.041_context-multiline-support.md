# FSD v1.0.041 - Context Command Multiline Support

## 문서 정보
- **버전**: v1.0.041
- **작성일**: 2026-02-13
- **대상 파일**: 
  - `claude-ai-chat-code01.py`
  - `gemini-ai-chat-code01.py`
  - `gen-ai-chat-code01.py`

## 1. 개요

### 1.1 목적
`/context` 명령어 사용 시 질문 부분을 멀티라인으로 입력할 수 있도록 개선합니다.

### 1.2 배경
현재 `/context` 명령어는 다음과 같이 사용합니다:
```
/context src/*.py 이 코드를 리팩토링해줘
```

긴 질문이나 복잡한 요구사항을 작성할 때 한 줄로 입력하기 어렵습니다.

### 1.3 범위
- `/context` 명령어 파싱 로직 수정
- 패턴만 입력 시 멀티라인 모드 자동 진입
- 기존 한 줄 입력 방식도 유지 (하위 호환성)

## 2. 요구사항

### 2.1 기능 요구사항

#### FR-1: 멀티라인 입력 지원
**현재**:
```
/context src/*.py 이 코드를 리팩토링해줘
```

**변경 후**:
```
/context src/*.py
📝 질문을 입력하세요 (/end로 종료):
... 이 코드를 리팩토링해줘
... 다음 사항을 고려해서:
... - 성능 최적화
... - 가독성 향상
... /end
```

#### FR-2: 하위 호환성
기존 한 줄 입력 방식도 계속 지원:
```
/context src/*.py 간단한 질문
```

#### FR-3: 자동 모드 전환
- 패턴만 입력: 멀티라인 모드 진입
- 패턴 + 질문: 즉시 실행

## 3. 설계

### 3.1 구현 방법

#### 3.1.1 기존 코드
```python
elif command == '/context':
    if not args:
        print("❌ 사용법: /context <파일패턴> <질문>")
        continue
    context_parts = args.split(maxsplit=1)
    if len(context_parts) < 2:
        print("❌ 질문을 입력하세요.")
        continue
    patterns = context_parts[0].split(',')
    question = context_parts[1]
    last_response = assistant.chat(
        question, streaming=streaming,
        include_context=True, file_patterns=patterns
    )
```

#### 3.1.2 개선된 코드
```python
elif command == '/context':
    if not args:
        print("❌ 사용법: /context <파일패턴> [질문]")
        print("💡 질문을 생략하면 멀티라인 입력 모드로 전환됩니다.")
        continue
    
    context_parts = args.split(maxsplit=1)
    patterns = context_parts[0].split(',')
    
    # 질문이 포함된 경우 (한 줄 입력)
    if len(context_parts) >= 2:
        question = context_parts[1]
    else:
        # 질문이 없는 경우 (멀티라인 입력)
        print("📝 질문을 입력하세요 (/end로 종료):")
        lines = []
        while True:
            line = input("... ")
            if line.strip() == '/end':
                break
            lines.append(line)
        question = '\n'.join(lines)
        
        if not question.strip():
            print("❌ 질문을 입력하세요.")
            continue
    
    last_response = assistant.chat(
        question, streaming=streaming,
        include_context=True, file_patterns=patterns
    )
```

### 3.2 사용 예시

#### 예시 1: 한 줄 입력 (기존 방식)
```
👤 You: /context src/*.py 이 코드를 설명해줘
```

#### 예시 2: 멀티라인 입력 (새로운 방식)
```
👤 You: /context src/*.py
📝 질문을 입력하세요 (/end로 종료):
... 이 프로젝트의 구조를 분석하고
... 다음 내용을 포함한 문서를 작성해줘:
... 1. 주요 클래스 설명
... 2. 데이터 흐름
... 3. 개선 제안
... /end
```

#### 예시 3: 여러 패턴 + 멀티라인
```
👤 You: /context src/*.py,tests/*.py
📝 질문을 입력하세요 (/end로 종료):
... 테스트 커버리지를 분석하고
... 추가 테스트가 필요한 부분을 알려줘
... /end
```

## 4. 테스트 시나리오

### 4.1 한 줄 입력 테스트
1. `/context src/*.py 간단한 질문` 입력
2. 즉시 실행 확인
3. AI 응답 확인

### 4.2 멀티라인 입력 테스트
1. `/context src/*.py` 입력 (질문 생략)
2. 멀티라인 모드 진입 확인
3. 여러 줄 질문 입력
4. `/end` 입력
5. AI 응답 확인

### 4.3 빈 질문 테스트
1. `/context src/*.py` 입력
2. 멀티라인 모드 진입
3. `/end` 바로 입력 (빈 질문)
4. 오류 메시지 확인

### 4.4 여러 패턴 테스트
1. `/context src/*.py,tests/*.py` 입력
2. 멀티라인 모드 진입 확인
3. 질문 입력 후 실행

## 5. 도움말 업데이트

### 5.1 기존 도움말
```
/context <pattern>  - 컨텍스트 포함하여 질문 (예: /context src/*.py)
```

### 5.2 개선된 도움말
```
/context <pattern> [질문]  - 컨텍스트 포함하여 질문
                             질문 생략 시 멀티라인 입력 모드
                             예: /context src/*.py
                                 /context src/*.py 간단한 질문
```

## 6. 장점

### 6.1 사용성 향상
- ✅ 긴 질문을 여러 줄로 작성 가능
- ✅ 복잡한 요구사항을 구조화하여 입력
- ✅ 가독성 향상

### 6.2 하위 호환성
- ✅ 기존 한 줄 입력 방식 유지
- ✅ 기존 사용자 영향 없음

### 6.3 일관성
- ✅ `/multiline` 명령어와 동일한 패턴
- ✅ 직관적인 사용법

## 7. 참고사항

### 7.1 다른 명령어 적용 가능성
이 패턴은 다른 명령어에도 적용 가능합니다:
- `/read <pattern>` - 파일 읽기 후 질문
- `/shell <command>` - 명령어 실행 후 질문

### 7.2 CLIInputHandler 활용
`CLIInputHandler.get_multiline_legacy()` 메서드를 재사용할 수 있습니다:
```python
question = cli_handler.get_multiline_legacy()
```

## 8. 승인

- [ ] 개발자 검토
- [ ] 테스트 완료
- [ ] 문서 업데이트 완료
