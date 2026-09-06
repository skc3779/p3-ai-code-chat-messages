Hugging Face에서 보이는 `Tools`, `Structured Output`, `Text Generation`, `Vision` 같은 표시는 단순히 “이 모델이 똑똑하다”는 의미가 아니라, **그 모델을 애플리케이션에서 어떤 방식으로 사용할 수 있는지**를 나타냅니다.

특히 앞에서 설명한 **OpenAI-Compatible API**와 연결해서 보면 이해하기 쉽습니다.

## 1. `Tools` 지원

Hugging Face의 `Tools`는 일반적으로 **Tool Use / Function Calling**을 의미합니다.

즉 모델이 직접 외부 프로그램을 실행하는 게 아니라, 사용자의 질문을 보고:

1. 어떤 Tool을 사용해야 하는지 판단하고
2. Tool 이름과 파라미터를 구조화해서 출력하고
3. 애플리케이션이 실제 Tool을 실행하고
4. Tool 실행 결과를 다시 모델에 전달하면
5. 모델이 최종 답변을 생성

하는 구조입니다. Hugging Face 공식 문서에서도 Tool을 “사용자가 제공한 함수 중 모델이 호출할 것을 선택하는 방식”으로 설명합니다. ([Hugging Face][1])

예를 들어 다음 Tool이 있다고 하겠습니다.

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "도시의 현재 날씨 조회",
    "parameters": {
      "type": "object",
      "properties": {
        "city": {
          "type": "string"
        }
      },
      "required": ["city"]
    }
  }
}
```

사용자가:

```text
서울 오늘 날씨 알려줘
```

라고 질문하면 Tools 지원 모델은 단순히 상상해서 답하지 않고 대략:

```json
{
  "name": "get_weather",
  "arguments": {
    "city": "서울"
  }
}
```

와 같은 Tool Call을 만들어냅니다.

실제 흐름은:

```text
사용자
  │
  │ "서울 오늘 날씨 알려줘"
  ↓
LLM
  │
  │ get_weather(city="서울") 호출 필요
  ↓
Application
  │
  ├─→ Weather API
  │
  ←─ 26도 / 흐림
  │
  ↓
LLM
  │
  ↓
"현재 서울은 26도이고 흐립니다."
```

입니다.

중요한 것은 **모델 자체가 Weather API에 접속하는 것은 아니라는 점**입니다. Hugging Face 문서에서도 모델은 Tool의 실제 코드가 아니라 Tool 이름, 설명, 인수 등의 schema를 보고 호출을 결정하며, 실제 실행은 애플리케이션이 담당한다고 설명합니다. ([Hugging Face][2])

---

## 2. Tools가 중요한 이유

일반 Chat 모델은 기본적으로:

```text
질문 → 답변
```

입니다.

Tools 모델은:

```text
질문
 ↓
판단
 ↓
Tool 선택
 ↓
외부 시스템 호출
 ↓
결과 확인
 ↓
최종 답변
```

이 가능해집니다.

따라서 다음과 같은 Agent 시스템을 만들 수 있습니다.

```text
                    ┌─ 사내 DB 조회
                    │
                    ├─ REST API 호출
사용자 → LLM Agent ─┼─ 파일 검색
                    │
                    ├─ MCP Server
                    │
                    ├─ 검색엔진
                    │
                    └─ 사내 시스템
```

기업 시스템에서 보면 이 기능이 상당히 중요합니다.

예를 들어:

```text
"IF-20260906001 인터페이스 장애 원인 찾아줘"
```

라고 하면 LLM이:

```text
1. get_interface_info()
2. get_execution_log()
3. get_error_log()
4. search_similar_incident()
```

같은 Tool을 순차적으로 호출할 수도 있습니다.

---

# 3. `Structured Output`

이것도 상당히 중요한 항목입니다.

Structured Output은 모델에게 단순히:

```text
JSON으로 답해줘
```

라고 요청하는 수준이 아닙니다.

미리 정의한 **JSON Schema에 맞는 결과를 출력하도록 제약**하는 기능입니다. Hugging Face Inference Providers도 JSON Schema 기반 Structured Output을 지원하며, 이를 통해 파싱 가능한 구조를 안정적으로 받을 수 있다고 설명합니다. ([Hugging Face][3])

예를 들어:

```json
{
  "type": "object",
  "properties": {
    "errorCode": {
      "type": "string"
    },
    "cause": {
      "type": "string"
    },
    "severity": {
      "type": "string",
      "enum": ["LOW", "MEDIUM", "HIGH"]
    }
  },
  "required": [
    "errorCode",
    "cause",
    "severity"
  ]
}
```

를 지정하면 결과가:

```json
{
  "errorCode": "ORA-12541",
  "cause": "TNS Listener가 실행되지 않음",
  "severity": "HIGH"
}
```

형태가 되도록 강제할 수 있습니다.

일반 프롬프트 방식:

```text
JSON으로 출력해줘
```

는 모델이 가끔:

```text
분석 결과는 다음과 같습니다.

{
   ...
}
```

처럼 불필요한 문자열을 섞거나 JSON 문법을 틀릴 수 있습니다.

Structured Output은 이를 애플리케이션 수준에서 훨씬 안정적으로 사용할 수 있게 해줍니다.

---

# 4. Tools와 Structured Output은 다른 기능

둘을 혼동하기 쉽습니다.

| 기능                       | 목적                   |
| ------------------------ | -------------------- |
| Tools / Function Calling | 외부 기능을 호출            |
| Structured Output        | 모델 응답 형식을 Schema에 맞춤 |

예를 들어:

```text
사용자:
"IF001 인터페이스 최근 오류 확인해줘"
```

Tools:

```json
{
  "name": "get_interface_log",
  "arguments": {
    "interfaceId": "IF001"
  }
}
```

Tool 실행 결과:

```json
{
  "error": "ORA-12541"
}
```

그 결과를 받은 모델에게 Structured Output을 적용하면:

```json
{
  "interfaceId": "IF001",
  "errorCode": "ORA-12541",
  "severity": "HIGH",
  "recommendation": "Oracle Listener 상태 확인"
}
```

처럼 만들 수 있습니다.

따라서 Agent 시스템에서는 두 기능을 **같이 사용하는 경우가 많습니다.**

---

# 5. `Text Generation`

가장 기본적인 LLM 기능입니다.

```text
Text
 ↓
LLM
 ↓
Text
```

예:

```text
"Oracle ORA-12541 오류를 설명해줘."
```

→

```text
ORA-12541은 Oracle Listener와 연결할 수 없는 경우...
```

Hugging Face에서 `Text Generation` 또는 `text-generation` pipeline tag가 있다면 일반적으로 Transformer 기반 causal language model로 텍스트 생성을 수행할 수 있다는 의미입니다.

Model Card 자체의 `pipeline_tag`, `library_name`, `tags` 같은 메타데이터가 모델의 검색과 실행 환경을 설명하는 데 사용됩니다. ([Hugging Face][4])

---

# 6. `Conversational` / Chat

Text Generation과 비슷하지만 **대화형으로 fine-tuning된 모델**입니다.

일반적으로:

```json
[
  {
    "role": "system",
    "content": "You are a helpful assistant."
  },
  {
    "role": "user",
    "content": "Oracle에 대해 설명해줘."
  }
]
```

형태의 message 구조를 받습니다.

실제로 LLM 내부에서는 `role/content` 구조 자체를 이해하는 것이 아니라 Chat Template이 이를 특정 token sequence로 변환합니다. Hugging Face Transformers도 이 부분을 명확히 설명합니다. ([Hugging Face][5])

예를 들어 내부적으로는:

```text
<|system|>
You are a helpful assistant.
<|end|>
<|user|>
Oracle에 대해 설명해줘.
<|end|>
<|assistant|>
```

같은 형태가 될 수 있습니다.

이 때문에 모델마다 **Chat Template이 상당히 중요합니다.**

---

# 7. `Vision`

Vision 또는 Image-Text-to-Text 계열이면 이미지 입력을 이해할 수 있는 모델입니다.

예:

```text
       ┌─ 이미지
       │
사용자 ┼─ "이 화면의 오류가 무엇인지 설명해줘"
       │
       ↓
     Vision LLM
       ↓
     텍스트 답변
```

예를 들어:

```text
Screenshot
   +
"이 Oracle 오류를 분석해줘"
```

→ 이미지에 표시된 오류를 보고 분석하는 것입니다.

Hugging Face의 multimodal chat model은 `text`, `image`, 경우에 따라 `video`, `audio` 등의 content type을 함께 처리하도록 설계됩니다. ([Hugging Face][6])

---

# 8. `Image-Text-to-Text`

Vision과 관련된 Hugging Face의 보다 구체적인 task 분류입니다.

입력:

```text
Image + Text
```

출력:

```text
Text
```

예:

```text
[장애 화면 이미지]

"이 화면에서 오류 코드를 찾아서 해결 방법 알려줘."
```

→

```text
ORA-12541 오류가 표시되어 있습니다.
Oracle Listener를 확인하십시오.
```

따라서 다음과 같은 모델들이 이 계열에 들어갈 수 있습니다.

```text
Qwen-VL 계열
Gemma Vision 계열
Llama Vision 계열
InternVL
등
```

---

# 9. `Thinking` / Reasoning

요즘 모델에서 아주 중요한 구분입니다.

Reasoning 모델은 일반 Chat 모델보다:

```text
문제
 ↓
내부 추론
 ↓
답변
```

에 더 많은 계산을 사용하는 모델입니다.

대표적인 용도는:

```text
코딩
수학
복잡한 분석
계획
문제 해결
Agent
```

입니다.

다만 Hugging Face에서 모델 이름에:

```text
Reasoning
Thinking
R1
```

등이 있다고 해서 공통 API 표준을 의미하는 것은 아닙니다.

모델별로:

```text
thinking token
reasoning_content
<think>...</think>
```

등의 표현 방식이 다를 수 있습니다.

---

# 10. `MCP`와 Tools

최근에는 이것도 함께 봐야 합니다.

MCP는:

**Model Context Protocol**

입니다.

Tools가:

```text
LLM
 ↓
function
```

이라는 개념이라면 MCP는 Tool들을 표준화된 방식으로 제공하는 **Tool Server Protocol**에 가깝습니다.

구조를 보면:

```text
                LLM
                 │
              Tools
                 │
            MCP Client
                 │
        ┌────────┼────────┐
        ↓        ↓        ↓
     GitHub     DB      Files
      MCP       MCP      MCP
     Server    Server   Server
```

입니다.

Hugging Face의 Responses API도 현재 remote MCP tools를 포함한 agentic 기능을 제공하고 있습니다. ([Hugging Face][7])

---

# 11. `Safetensors`

이건 **모델 기능이 아닙니다.**

모델 Weight 저장 형식입니다.

예:

```text
model.safetensors
```

기존:

```text
pytorch_model.bin
```

대신 많이 사용됩니다.

주요 장점은:

* 안전한 serialization
* 빠른 로딩
* mmap 활용
* pickle 기반 arbitrary code 실행 위험 감소

정도로 이해하면 됩니다.

---

# 12. `GGUF`

이것 역시 모델 능력이 아니라 **모델 배포/양자화 파일 형식**입니다.

특히:

```text
llama.cpp
LM Studio
Ollama
Jan
LocalAI
```

등에서 많이 사용합니다.

예:

```text
Qwen3-30B-A3B-Q4_K_M.gguf
```

에서:

```text
Q4_K_M
```

은 대략 4bit 계열 quantization을 의미합니다.

사용하시는 **LM Studio + RTX 5080 Laptop 16GB VRAM** 환경에서는 Hugging Face 모델을 볼 때 `GGUF` 유무와 Quantization 종류가 상당히 중요합니다.

---

# 13. `Transformers`

이것 역시 모델의 지능 기능을 뜻하는 것은 아닙니다.

```text
Transformers
```

가 표시되어 있다면 보통 Hugging Face의:

```python
from transformers import AutoModelForCausalLM
from transformers import AutoTokenizer
```

등으로 모델을 직접 로드할 수 있다는 뜻입니다.

예:

```python
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/..."
)
```

---

# 14. `Inference Providers`

이것도 모델 자체의 특성과 분리해서 봐야 합니다.

Hugging Face는 여러 외부 inference provider를 하나의 인터페이스로 제공합니다.

예:

```text
                    ┌─ Cerebras
                    ├─ Groq
Hugging Face API ───┼─ DeepInfra
                    ├─ Together
                    ├─ Fireworks
                    └─ 기타
```

같은 모델이라도 Provider에 따라 지원 기능이 달라질 수 있습니다.

실제로 Hugging Face API에는 Provider별로:

```text
supports_tools
supports_structured_output
context_length
pricing
latency
throughput
```

등의 정보를 제공할 수 있습니다. ([Hugging Face][8])

이 부분이 특히 중요합니다.

예를 들어 모델 자체가 Tool Calling을 학습했다고 해도:

```text
Model
  Tools 지원 O
```

인데 사용하는 inference provider가:

```text
supports_tools = false
```

이면 API에서 그 기능을 바로 사용하지 못할 수도 있습니다.

따라서 실제로는:

```text
Model capability
        +
Runtime/Server capability
        +
API capability
```

세 가지를 같이 봐야 합니다.

---

# 15. OpenAI-Compatible 관점에서 보면

가장 중요한 기능을 이렇게 매핑할 수 있습니다.

| Hugging Face 표시    | OpenAI-Compatible API 관점      |   중요도 |
| ------------------ | ----------------------------- | ----: |
| Text Generation    | completions                   |   ★★★ |
| Conversational     | chat/completions              | ★★★★★ |
| Tools              | tools / tool_calls            | ★★★★★ |
| Function Calling   | tools / function              | ★★★★★ |
| Structured Output  | response_format / JSON Schema | ★★★★★ |
| Vision             | image input                   |  ★★★★ |
| Reasoning          | reasoning 기능                  |  ★★★★ |
| Embeddings         | `/embeddings`                 |  ★★★★ |
| Safetensors        | Weight format                 |   ★★★ |
| GGUF               | Local inference format        |  ★★★★ |
| Transformers       | Python runtime                |   ★★★ |
| Inference Provider | 실행 서비스                        |  ★★★★ |

---

# 16. 실제 모델을 선택한다면 제가 보는 우선순위

기업용 LLM 또는 Agent를 구성한다면 단순 Benchmark보다 다음 항목을 먼저 보는 것이 좋습니다.

```text
① Chat / Instruction 모델인가
        ↓
② Tools / Function Calling 지원
        ↓
③ Structured Output 지원
        ↓
④ OpenAI-Compatible API 지원
        ↓
⑤ Context Length
        ↓
⑥ Reasoning 성능
        ↓
⑦ Multimodal 필요 여부
        ↓
⑧ Quantization / GGUF
        ↓
⑨ VRAM 요구량
        ↓
⑩ License
```

특히 사용 목적이 향후 **사내 연계 포털 + MCP + 로그 분석 + Agent**라면,

```text
Tools
Structured Output
OpenAI-Compatible
MCP 연계
긴 Context
Reasoning
```

을 핵심으로 보는 것이 좋습니다.

그리고 여기서 중요한 차이는:

```text
Tool 지원 모델
     ≠
Agent 완제품
```

입니다.

모델은:

```text
"getOracleLog(interfaceId='IF001')를 호출해야겠다"
```

라고 판단하는 역할이고,

실제로:

```text
Oracle 조회
REST 호출
MQ 조회
WebMethods 상태 확인
로그 검색
```

을 수행하는 것은 **Agent Runtime / Application / MCP Server**입니다.

따라서 전체 구조는 궁극적으로:

```text
                       ┌─ Oracle Tool
                       │
                       ├─ MQ Tool
User
 ↓                     ├─ WebMethods Tool
Agent Application      │
 ↓                     ├─ APIC Tool
OpenAI-Compatible API  │
 ↓                     ├─ Log Search Tool
Qwen / Llama / etc.    │
 ↓                     └─ MCP Tools
Tool Call 판단
```

이 됩니다.

이 관점에서 보면 Hugging Face에서 모델을 볼 때 **`Tools` 표시가 있는지가 앞으로 Agent 용도로 사용할 수 있는지를 판단하는 상당히 중요한 기준**이 됩니다. 다만 그것만 보지 말고 실제 사용하는 **vLLM, LM Studio, Ollama, TGI 또는 Hugging Face Inference Provider가 해당 Tool Calling 형식을 제대로 지원하는지도 함께 확인**해야 합니다. ([Hugging Face][1])

[1]: https://huggingface.co/docs/transformers/main/chat_extras?utm_source=chatgpt.com "Tool use · Hugging Face"
[2]: https://huggingface.co/docs/transformers/main/chat_template_tools_and_documents?utm_source=chatgpt.com "Expanding Chat Templates with Tools and Documents · Hugging Face"
[3]: https://huggingface.co/docs/inference-providers/guides/structured-output?utm_source=chatgpt.com "Structured Outputs with Inference Providers · Hugging Face"
[4]: https://huggingface.co/docs/hub/models-adding-libraries?utm_source=chatgpt.com "Integrate your library with the Hub · Hugging Face"
[5]: https://huggingface.co/docs/transformers/chat_templating?utm_source=chatgpt.com "Chat templates · Hugging Face"
[6]: https://huggingface.co/docs/transformers/main/chat_templating_multimodal?utm_source=chatgpt.com "Multimodal chat templates · Hugging Face"
[7]: https://huggingface.co/docs/inference-providers/en/guides/responses-api?utm_source=chatgpt.com "Responses API (beta) · Hugging Face"
[8]: https://huggingface.co/docs/inference-providers/hub-api?utm_source=chatgpt.com "Hub API · Hugging Face"
