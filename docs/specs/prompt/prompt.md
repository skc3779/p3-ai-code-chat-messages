gen-ai-chat-code01.py
src/genai_assistant.py 
src/ignorer.py 
src/llm_config.py

claude-ai-chat-code01.py

---


```shell
python3 claude-ai-chat-code01.py

You: /read calulator.py

You: calculator.py 소스코드가 기능 분석해줘

❌ API Error: 400 - {"type":"error","error":{"type":"invalid_request_error","message":"messages: Unexpected role \"system\". The Messages API accepts a top-level `system` parameter, not \"system\" as an input message role."},"request_id":"req_011CXSyUgR4EhfV8dKsJ6Gzt"}

```

`history_entry = {"role": "system", "content": context }` 로  /read calculator.py 명령어로 history에 등록 후 다음 명령어를 실행하면 위와 같은 문제가 발생한다. 문제점을 분석 후 BUG 문서를 만들어줘 
- BUG 문서는 docs/specs/requirements 폴더에 저장해줘  

---

CALUDE를 이용한 리뷰 자동화 시스템 구축을 하려고 합니다.
- 앱 리뷰가 슬랙 채널에 수신됩니다.
- 재피어가 새로운 메시지를 감지합니다.


명령어에 멀티라인이 등록 될 수 있도록 FSD 문서를 작성해줘   
- FSD 문서는 docs/specs/requirements 폴더에 저장한다  
- claude-ai-chat-code01.py 파일을 참고하여 작성한다  
- `/multiline` 명령어를 사용하여 멀티라인 명령어를 등록할 수 있도록 한다  
- FSD_multiline_command_registration_v1.0.015.md에 만들어주고, 문서는 docs/specs/requirements 폴더에 저장해줘  
- FSD 문서의 내용이 너무 길지 않게 작성해줘  


----

현재의 소스코드를 분석해서 개선사항을 아래 README 파일에 업데이트 해줘.
@README-claude-ai-chat-code01.md와 @README-gen-ai-chat-code01.md 

---
claude-ai-chat-code01.py 로 시작하는   
Claude Code Assistant는 터미널에서 Anthropic Claude API를 활용하여 코드 작성, 리팩토링, 문서화 등을 지원하는 AI 코딩 어시스턴트이며, 프로젝트 파일 컨텍스트를 자동으로 분석하여 더 정확한 코드 생성을 지원하고 있어 본 소스코드를 분석해서 
추가적으로 기능 개선이 필요한 사항을 우선 순위별로 나열해줘
- 문서는 docs/specs/requirements 폴더에 SRS로 시작하는 v1.0.016 버전의 문서에 저장한다  

-- 

@SRS_Claude_Code_Assistant_Improvements_v1.0.016.md 에서 `토큰 수 계산 및 자동 트리밍 기능 추가` 중 자동 트리밍 기능 이 이해가 되지 않는다 무슨의미인지 자세히 보조문서를 만들어 설명해줘
-- 문서는 docs/specs/requirements 폴더에 REF로 시작하는 v1.0.016 버전의 문서에 저장한다  


---

@SRS_Claude_Code_Assistant_Improvements_v1.0.016.md 문서에서 P1-02, P1-03에 대한 개선사항을 구현해줘

### 2.1 P1 - Critical (즉시 수정 필요)

| ID | 개선 사항 | 현재 문제 | 개선 방안 | 처리 |
|----|-----------|----------|----------|---|
| P1-01 | `/read` 명령어 System Role 수정 | `role: "system"` 사용으로 API 오류 발생 | `role: "user"` 또는 세션 컨텍스트 방식으로 변경 | 구현완료 |
| P1-02 | 대화 히스토리 토큰 관리 | 히스토리 무제한 누적으로 토큰 초과 가능 | 토큰 수 계산 및 자동 트리밍 기능 추가 | 미구현 |
| P1-03 | API 오류 재시도 로직 | 네트워크 오류 시 즉시 실패 | 지수 백오프 재시도 로직 구현 | 미구현 |

---

구현 내용을 릴리즈 노트로 정리해줘
- 문서는 docs/releases 폴더에 RELEASE로 시작하는 v1.0.016 버전의 문서에 저장한다  
- RELEASE 문서의 내용이 너무 길지 않게 작성해줘  

---

`src/api_retry.py` 지수 백오프 재시도 로직이 어떻게 동작하는지 보조문서를 만들어 설명해줘
- 문서는 docs/specs/requirements 폴더에 REF로 시작하는 v1.0.016 버전의 문서에 저장한다  

---

`src/token_manager.py`  토큰 계산 및 자동 트리밍 중 claude-ai-chat-code01.py 와 gen-ai-chat-code01.py 의 최대 토큰의 크기가 다릅니다.
이에 claude-ai-chat-code01.py 와 gen-ai-chat-code01.py 실행 모드에 따라 DEFAULT_MAX_TOKENS값이 다르게 설정되도록 합니다.  
- Claude 컨텍스트 윈도우의 75%를 안전 한도로 설정  
    - DEFAULT_MAX_TOKENS = 150000  
- gen-ai 컨텍스트 윈도우의 75%를 안전 한도로 설정 
    - DEFAULT_MAX_TOKENS = 96000  

---

@SRS_Claude_Code_Assistant_Improvements_v1.0.016.md 문서에서 P2-01에 대한 개선사항을 FSD 문서로 작성해줘
- FSD 문서는 docs/specs/requirements 폴더에 FSD로 시작하는 v1.0.018 버전의 문서에 저장한다
- 문서의 내용이 길지 않게 작성해줘

### 2.2 P2 - High (2주 내 개선)

| ID | 개선 사항 | 현재 문제 | 개선 방안 |
|----|-----------|----------|----------|
| P2-01 | 대화 히스토리 저장/로드 | 세션 종료 시 히스토리 손실 | JSON 파일로 히스토리 영속화 |

---

구현 내용을 릴리즈 노트로 정리해줘
- 문서는 docs/releases 폴더에 RELEASE로 시작하는 v1.0.017 버전의 문서에 저장한다  
- RELEASE 문서의 내용이 길지 않게 작성해줘  


---

@SRS_Claude_Code_Assistant_Improvements_v1.0.016.md 문서에서 P2-03에 대한 개선사항을 FSD 문서로 작성해줘
- FSD 문서는 docs/specs/requirements 폴더에 FSD로 시작하는 v1.0.018 버전의 문서에 저장한다
- 문서의 내용이 길지 않게 작성해줘

### 2.2 P2 - High (2주 내 개선)

| ID | 개선 사항 | 현재 문제 | 개선 방안 |
|----|-----------|----------|----------|
| P2-03 | 파일 변경 감지 | 수동 `/read` 필요 | watchdog 기반 자동 컨텍스트 갱신 |


---

구현 내용을 릴리즈 노트로 정리해줘
- docs\specs\requirements\FSD_File_Change_Detection_v1.0.018.md
- docs\specs\requirements\FSD_Streaming_Error_Handling_v1.0.019.md
- 2건의 FSD 문서를 기반으로 docs/specs/releases 폴더에 RELEASE로 시작하는 v1.0.018, v1.0.019 버전의 릴리즈 노트를 작성한다  
- RELEASE 문서의 내용이 길지 않게 작성해줘  

---

미구현 개선사항을 claude-ai-chat-code01.py에 구현해줘
- docs\specs\requirements\FSD_File_Change_Detection_v1.0.018.md 에 대한 내용
- gen-ai-chat-code01.py 에는 FSD_File_Change_Detection_v1.0.018.md에 대한 내용이 구현되어 있습니다.
- claude-ai-chat-code01.py 에는 FSD_File_Change_Detection_v1.0.018.md에 대한 내용이 구현되어 있지 않습니다.

---


## file_watcher.py

```python
    def add_watch(self, pattern: str) -> bool:
        """
        감시 대상 패턴 추가
        
        Args:
            pattern: glob 패턴 (예: *.py, src/*.js)
            
        Returns:
            성공 여부
        """
        if not WATCHDOG_AVAILABLE:
            return False
            
        with self._lock:
            self.patterns.add(pattern)
            
            # Observer가 실행 중이면 핸들러 패턴 업데이트
            if self._handler:
                self._handler.patterns = self.patterns.copy()
                
            # 자동 시작
            if not self._running:
                self.start()
```                

```shell
# 사용자 명령 프롬프트
/watch *.py
```

사용자 명령 프롬프트 이후 `file_watcher.py` 의 add_watch `self.start()` 이후 시스템이 먹통이 된다. 
`file_watcher.py` 프로그램의 동작 원리를 분석해서 BUG 문서를 만들어 설명해줘
- 문서는 docs/specs/requirements 폴더에 BUG 로 시작하는 v1.0.021 버전의 문서에 저장한다  

---

@SRS_Claude_Code_Assistant_Improvements_v1.0.016.md 문서에서 P3-01, P3-02, P3-03, P3-05 에 대한 개선사항을 각각의 FSD 문서로 작성해줘
- FSD 문서는 docs/specs/requirements 폴더에 FSD로 시작하는 v1.0.020, v1.0.021, v1.0.022, v1.0.023 버전의 문서에 저장한다
- 문서의 내용이 길지 않게 작성해줘

### 2.3 P3 - Medium (1개월 내 개선)

| ID | 개선 사항 | 현재 문제 | 개선 방안 | 처리 |
|----|-----------|----------|----------|----|
| P3-01 | 프롬프트 템플릿 | 시스템 프롬프트 고정 | 사용자 정의 템플릿 시스템 | 미구현 |
| P3-02 | 플러그인 시스템 | 기능 확장 어려움 | 플러그인 아키텍처 도입 | 미구현 |
| P3-03 | 코드 diff 표시 | AI 수정 코드 전체 출력 | 기존 코드와 diff 비교 출력 | 미구현 |
| P3-04 | 비용 추적 | API 사용량 미추적 | 토큰/비용 계산 및 표시 | 제외 |
| P3-05 | 자동 완성 | 명령어 수동 입력 | Tab 자동 완성 지원 | 미구현 |

---

claude-ai-chat-code01.py , gen-ai-chat-code01.py 의 /tree 명령시 .ignore 파일을 다시 읽어 와서 반영하도록 개선해주고 RELEASE 문서를 작성해줘
- specs/releases 폴더에 RELEASE로 시작하는 v1.0.022 버전의 릴리즈 노트를 작성한다  
- RELEASE 문서의 내용이 길지 않게 작성해줘  


---

ignorer.py 의 .gitignore 파일에 .idea 폴더외 .idea/ 폴더도 동일하게 제외로 인식하도록 개선해줘
- [폴더명] [폴더명]/ 동일하게 인식되도록 개선한다
- specs/releases 폴더에 RELEASE로 시작하는 v1.0.023 버전의 릴리즈 노트를 작성한다  
- RELEASE 문서의 핵심은 포함하고 내용은 길지 않게 작성해줘  

---

## 콘솔

```console

👤 You: /read c:\03_sources\skc3779_srcs\p3-ai-code-chat-messages\.system-prompts\code-review.yaml
❌ 패턴 'c:\03_sources\skc3779_srcs\p3-ai-code-chat-messages\.system-prompts\code-review.yaml'에 해당하는 파일이 없습니다.

👤 You: /read code-review.yaml                                                                    

================================================================================
📄 파일: .system-prompts\code-review.yaml
================================================================================
```yaml
name: code-review
description: 시니어 개발자 관점의 코드 리뷰
system_prompt: |
  당신은 엄격하고 꼼꼼한 시니어 소프트웨어 엔지니어입니다.
  사용자가 제공한 코드를 다음 기준에 따라 리뷰하고 개선안을 제시하세요:

  1. 버그 및 잠재적 오류
  2. 성능 최적화 (시간 복잡도 등)
  3. 가독성 및 유지보수성 (명명 규칙, 모듈화)
  4. 보안 취약점

  구체적인 예시 코드와 함께, 친절하지만 단호한 어조로 조언해주세요.

  (주의: 코드 수정이나 생성이 필요한 경우, 파일 저장 형식 ```filename:...``` 을 준수해야 파일을 저장할 수 있습니다.)

```


👤 You: /read .system-prompt/code-review.yaml
❌ 패턴 '.system-prompt/code-review.yaml'에 해당하는 파일이 없습니다.

👤 You: /read .system-prompt\code-review.yaml
❌ 패턴 '.system-prompt\code-review.yaml'에 해당하는 파일이 없습니다.

👤 You: /read ./.system-prompt\code-review.yaml
❌ 패턴 './.system-prompt\code-review.yaml'에 해당하는 파일이 없습니다.

👤 You: /read .\.system-prompt\code-review.yaml
❌ 패턴 '.\.system-prompt\code-review.yaml'에 해당하는 파일이 없습니다.

👤 You: /read ./.system-prompt/code-review.yaml
❌ 패턴 './.system-prompt/code-review.yaml'에 해당하는 파일이 없습니다.

👤 You: /read ./.system-prompt/*.yaml          
❌ 패턴 './.system-prompt/*.yaml'에 해당하는 파일이 없습니다.


아직도 `콘솔`과 같이 `/read <파일명>` 명령어를 실행시 일부는 파일을 보여주지 않는 오류 현상이 발생해 좀더 파일명과 다양한 경로  표현에도 파일을 읽은 수 있도록 추가 개선해줘.
- specs/releases 폴더에 RELEASE로 시작하는 v1.0.025 버전의 릴리즈 노트를 작성한다  
- RELEASE 문서의 내용이 길지 않게 작성해 주는데 핵심 내용은 포함 해줘

---


`/context <파일패턴> <질문>` 명령어를 아래와 같이 개선해줘
- <파일패턴> :  [*.py, src/*.js, src/*.py] 와 같은 glob 패턴
- <질문> : 파일의 내용을 보고 <질문>에 대한 답변을 해줘

예1 : `/context [src/*.py] 이 코드를 리팩토링해줘`
예2 : `/context [./gen*.py, src/*.py, docs/*.md] 이 코드와 MD파일을 분석해서 README.md 파일을 작성해줘`


---


### 2.3 P3 - Medium (1개월 내 개선)

| ID | 개선 사항 | 현재 문제 | 개선 방안 | 처리 |
|----|-----------|----------|----------|----|
| P3-01 | 프롬프트 템플릿 | 시스템 프롬프트 고정 | 사용자 정의 템플릿 시스템 | 미구현 |
| P3-02 | 플러그인 시스템 | 기능 확장 어려움 | 플러그인 아키텍처 도입 | 미구현 |
| P3-03 | 코드 diff 표시 | AI 수정 코드 전체 출력 | 기존 코드와 diff 비교 출력 | 미구현 |
| P3-04 | 비용 추적 | API 사용량 미추적 | 토큰/비용 계산 및 표시 | 제외 |
| P3-05 | 자동 완성 | 명령어 수동 입력 | Tab 자동 완성 지원 | 미구현 |

---

claude-ai-chat-code01.py , gen-ai-chat-code01.py 의 /tree 명령시 .ignore 파일을 다시 읽어 와서 반영하도록 개선해주고 RELEASE 문서를 작성해줘
- specs/releases 폴더에 RELEASE로 시작하는 v1.0.022 버전의 릴리즈 노트를 작성한다  
- RELEASE 문서의 내용이 길지 않게 작성해줘  

---

새로 추가된 라이브러리에 대해 `requirements.txt` 에 포함 해줘. 

---

`/multiline` 을 제외한 사용자 명령어 입력시 `enter` 입력시 실행되는 형태를 `shift + enter` 로 FSD 문서를 만들어줘
- specs/requirements 폴더에 FSD로 시작하는 v1.0.031 버전의 문서를 작성한다  
- FSD 문서의 내용이 길지 않게 작성해줘

---


gemini-ai-chat-code01.py 의 /save 명령어의 BUG를 개선하는 문서를 만들어줘
- /save 시 프로젝트 소스코드의 위치를 workspace 경로로 인식하는 문제 발생.
- /workspace <파일경로> 의 위치를 base 경로로 설정되도록 한다. 
- gemini-ai-chat-code01.py, claude-ai-chat-code01.py 모두 동일한 문제가 있는지 검토한다.
- specs/requirements 폴더에 BUG v1.0.0042 버전으로 문서화한다.


---

gemini cli 처럼 명령 프롬프트 하단에 `/` 입력시 사용가능한 명령어 목록을 보여주도록 개선하는 FSD 문서를 만들어줘.
- `/s` 입력시 `/save` 명령어만 보여주는 것이 아니라 사용가능한 명령어 목록을 필터링해서 보여준다.
- `/` 입력시 사용가능한 명령어 목록을 보여준다.
- specs/requirements 폴더에 FSD v1.0.046 버전으로 문서화한다.


FSD 문서는 제미나이와 동일한 명령어 필터링 기능 등 잘 설명되고 있는지 확인하고 개선해줘
- 이미지의 필터링 구조를 잘설명하고 있는지 검토한다.
- 하단 좌측에 경로, 우측에 모델을 정보를 표현되어 있는지 검토한다.
- 기능과 관련없는 내용은 삭제한다.

---

🌳 프로젝트 구조:
📁 프로젝트 구조 (작업 디렉터리: C:\03_sources\ai_srcs\gemini-demos)
📁 gemini-demos/
├── 📁 .chat_history/
├── 📁 .system-prompts/
├── 📁 GDRB_NOTION/
├── 📁 src/
│   ├── 📁 models/
│   │   └── 📄 User.java
│   ├── 📁 utils/
│   │   └── 📄 MathHelper.java
│   └── 📄 MainApp.java
└── 📄 README.md
> /read README.md

❌ 오류 발생: 'FilePatternMatcher' object has no attribute 'match_patterns'
> /read README.md

파일을 읽는 기능이 제대로 동작하지 않는 문제를 개선하는 문서를 만들어줘
- specs/requirements 폴더에 BUG v1.0.0048 버전으로 문서화한다.

---

## `/context [파일패턴,...] 멀티라인 명령어 등록 기능 개선

```cmd
> /context [original/*.md]
📝 멀티라인 모드 (종료: /end)
... original 폴더에 있는 md 파일을 1개씩 한글로 번역해서 hangle 폴더에 동일한 파일명으로 저장해줘
... /end
```

위와 같은 `/context [파일패턴,...]` 명령 프롬프트를 제공시 한개씩 파일을 읽고 한글번역을 하고 자동으로 hangle 폴덩에 동일한 지시한 데로 동일한 파일명으로 자동 생성되도록 
기능을 개선하는 FSD 문서를 만들어줘.
- 번역을 예시로 들었지만 그외 `/context [original/*.md]` 파일 목록 이용한 요청 작업도 동일한 `작업 흐름`으로 진행되도록 한다.
- 케이스 1 : md 파일을 읽고 프로그램 소스코드 작성, md 파일을 읽고 요약문 작성, md 파일을 읽고 번역하기 등 다양한 작업이 가능하도록 한다.
- 케이스 2 : 파일 패턴은 단일 패턴도 가능하지만 동일 파일명 규칙의 여러 패턴도 가능하도록 한다. 예) [original/*.md, src/*.py]
- 케이스 3 : 요구 파일 패턴 당 생성되는 파일은 1개 이상일 수도 있다.
  ```filename: src/file1_service.java
    소스 내용
  ```
  ```filename: src/file1_interface.java
    소스 내용
  ```
- specs/requirements 폴더에 FSD로 시작하는 v1.0.049 버전의 문서를 작성한다
- gen-ai-chat-code01.py, claude-ai-chat-code01.py, gemini-ai-chat-code01.py 모두 동일한 기능이 구현되도록 한다.

## 작업 흐름

### 1 original 폴덩에 파일 목록을 확인한다.
```tree
📁 original/
├── 📄 PART 01_01 주제·제목 파악하기_문제지.md
├── 📄 PART 01_02 요지·주장 파악하기_문제지.md
└── 📄 PART 01_03 목적 파악하기_문제지.md
```

### 2 명령의 요구사항으로 대로 첫번째 `PART 01_01 주제·제목 파악하기_문제지.md` 파일을 읽는다.

### 3 읽은 파일을 한글로 번역하고 아래와같이 마크다운로 만든다.  
   ```filename: hangle/PART 01_01 주제·제목 파악하기_문제지.md
    번역 내용 ...
   ```

### 4 자동으로 hangle 폴더에 동일한 파일명으로 저장한다.

### 5 2~4 과정을 original 폴더에 있는 모든 md 파일에 대해서 반복한다.

### 6 모든 파일이 번역되고 저장되면 context 모드를 종료한다.

---

## `/context [파일패턴,...] 멀티라인 명령어 등록 기능 개선

```cmd
> /auto_context [original/*.md]
📝 멀티라인 모드 (종료: /end)
... original 폴더에 있는 md 파일을 1개씩 한글로 번역해서 hangle 폴더에 파일명 + 페이지 단위의 md 파일로 저장해줘
... /end
```

멀티라인 입력시 입력된 텍스트 삭제 및 수정이 가능하도록 기능을 개선해줘
- specs/requirements 폴더에 FSD로 시작하는 v1.0.050 버전의 문서를 작성한다
- `/context`, `/auto_context`, `/multiline` 명령어 입력시 입력 및 붙여넣기 텍스트 삭제 및 수정이 가능하도록 한다.
- gen-ai-chat-code01.py, claude-ai-chat-code01.py, gemini-ai-chat-code01.py 모두 동일한 기능이 구현되도록 한다.

```cmd
> /multiline
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
... a
텍스트 1
텍스트 2
텍스트 3

```

Meta+Enter로 멀티라인 종료 기능은 작동하지 않음, 신규라인에서 `/end` 입력시 자동삭제되고 위쪽 라인의 마지막 입력위치로 커서 이동되는 버그
- Meta+Enter: 전송 기능 필요 없음 제거 (mac, windows 충돌 이슈)
- `/end`로 만 종료되도록 기능을 개선하는 BUG 문서를 만들어줘
- specs/requirements 폴더에 BUG로 시작하는 v1.0.050 버전의 문서를 작성한다
- gen-ai-chat-code01.py, claude-ai-chat-code01.py, gemini-ai-chat-code01.py 모두 동일한 기능이 구현되도록 한다.

---

```cmd
> /multiline
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
... a
b
c
```

멀티라인 입력시 기존아래와 같이 입력이 이쁘게 되지 않음. 

```cmd
> /multiline
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
... a
... b
... c
... /end
```

---

FSD v1.0.049, v1.0.050, v1.0.051 버전에 대한 RELEASE 문서를 작성해줘
- specs/releases 폴더에 RELEASE로 각각의 버전의 릴리즈 노트를 작성한다  
- RELEASE 문서의 내용이 길지 않게 작성해줘  

--- 

제미나이 CLI처럼 ANSI Art (안시 아트) 를 이용해서 프로그램 실행시 이쁘게 출력되도록 개선해줘
- 문구는 `>> GEN AI CODE CHAT <<`
- specs/requirements 폴더에 FSD로 시작하는 v1.0.051 버전의 문서를 작성한다
- gen-ai-chat-code01.py, claude-ai-chat-code01.py, gemini-ai-chat-code01.py 모두 동일한 기능이 구현되도록 한다.

---

README-claude-ai-chat-code01.md README-gemini-ai-chat-code01.md README-gen-ai-chat-code01.md 파일의 내용을 업데이트 해줘
- specs/releases 및 specs/requirements 폴더의 파일들을 참고해서 업데이트 해줘

---

claude code, gemini, gen-ai 등 제공 업체의 API ENDPOINT를 사용하는 방식에서 `@ai-sdk/openai-compatible` 의 OpenAI 호환 공급자를 이용하는 방식으로 ENDPOINT를 단일화 하고자 합니다. `@ai-sdk/openai-compatible` 스펙에 대해 이해하기 쉽게 문서화를 해줘.
- claude code, gemini, gen-ai API ENDPOINT를 기준으로 가이드 샘플을 포함한다.
- `@ai-sdk/openai-compatible` 의 내용을 꼭 이해가 필요한 부분에 대해서는 강조하면서 체계적으로 정리한다.
- specs/api-specs 폴더에 SRS로 시작하는 v1.0.052 버전의 문서를 작성한다.


## 참고  
- OpenAI Compatible Providers : https://ai-sdk.dev/providers/openai-compatible-providers
- Vercel AI SDK : https://github.com/vercel/ai/tree/main/packages/openai-compatible

---

목표에 그린 흐름도가 내가 이해한 내용과 같은 지 확인해줘.

GenAI,Claude,Gemini Provider 는 OpenAI 호환 인터페이스를 지원하는 로컬 API ENDPOINT 이며, 
각각의 로컬 API ENDPOINT 에서 기존 GenAI,Claude,Gemini 의 API 서버로 요청을 전달하고 응답을 받는 방식으로 구현되는 방식으로 너가 해당문서를 작성한 것이 맞는지 검토해주고 만일 아니라면 수정해줘.

위 내용에 이해가 안되는 부분이 있다면 질문하면서 나의 피드백을 받아 처리해줘.



---

SRS_v1.0.052_openai-compatible-provider_v2.md 기준으로 코드를 전체 작성하기 전에.
로컬 프록시 서버 (Python FastAPI) 서버와 OpenCode 의 Custom Provider 를 이용한 로컬 API ENDPOINT가 잘 구축되었는지 먼저 해보고, 전체 코드를 개선하려구 합니다. 이에 `로컬 프록시 서버 (Python FastAPI) 서버` 구축을 위한 FSD 문서를 만들어줘.

- specs/requirements 폴더에 FSD로 시작하는 v1.0.052 버전의 문서를 작성한다
- SRS_v1.0.052_openai-compatible-provider_v2.md 참고한다.
- OpenCode Custom Provider 스펙 참고 : https://opencode.ai/docs/providers#custom  
- 위 내용에 이해가 안되는 부분이 있다면 질문하면서 나의 피드백을 받아 처리해줘.
