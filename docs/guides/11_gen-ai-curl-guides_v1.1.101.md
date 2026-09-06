### 1. API 호출 규격 요약

- **엔드포인트 URL**: `POST {ENDPOINT_URL}/openapi/chat/v1/messages`
  - `.env` 기준: `https://scisportal.samsungif.com/rest/getAI/openapi/chat/v1/messages`
- **인증 헤더**:
  - `X-Lego-Client-Id`: `.env`의 `YOUR_CLIENT_KEY`
  - `X-Lego-Client-Secret`: `.env`의 `YOUR_CLIENT_SECRET`
  - `Content-Type: application/json`
- **요청 Body 필드**:
  - `modelIds`: 사용할 모델 ID 리스트 (`[YOUR_MODEL_ID]`)
  - `contents`: 사용자 및 이전 대화 메시지 문자열 배열 (`List[str]`)
  - `systemPrompt`: 시스템 프롬프트 문자열
  - `isStream`: 스트리밍 여부 (`true` 또는 `false`)
  - `llmConfig`: 모델 하이퍼파라미터 객체 (`temperature`, `top_k`, `top_p`, `repetition_penalty`, `max_new_tokens`)

---

### 2. cURL 명령어 예시

#### 옵션 A. 기본 논스트리밍(Non-Streaming) 호출

응답을 한 번에 JSON으로 수신할 때 사용하는 명령어입니다.

```bash
curl -X POST "https://scisportal.samsungif.com/rest/getAI/openapi/chat/v1/messages" \
  -H "Content-Type: application/json" \
  -H "X-Lego-Client-Id: API_CLIENT_APP" \
  -H "X-Lego-Client-Secret: abcxxxxxxxx" \
  -d '{
    "modelIds": ["019a-xxxx-xxxxx"],
    "contents": [
      "간단한 Python hello world 예제 코드를 작성해줘."
    ],
    "systemPrompt": "당신은 전문 소프트웨어 개발 어시스턴트입니다.",
    "isStream": false,
    "llmConfig": {
      "temperature": 0.30,
      "top_k": 12,
      "top_p": 0.90,
      "repetition_penalty": 1.20,
      "max_new_tokens": 10240
    }
  }'
```

---

#### 옵션 B. 스트리밍(Streaming / SSE) 호출

실시간 토큰 출력을 보려면 `isStream`을 `true`로 설정하고, cURL의 버퍼링 방지 옵션(`-N` / `--no-buffer`)을 함께 지정합니다.

```bash
curl -N -X POST "https://scisportal.samsungif.com/rest/getAI/openapi/chat/v1/messages" \
  -H "Content-Type: application/json" \
  -H "X-Lego-Client-Id: API_CLIENT_APP" \
  -H "X-Lego-Client-Secret: abcxxxxxxxx" \
  -d '{
    "modelIds": ["019a-xxxx-xxxxx"],
    "contents": [
      "간단한 Python hello world 예제 코드를 작성해줘."
    ],
    "systemPrompt": "당신은 전문 소프트웨어 개발 어시스턴트입니다.",
    "isStream": true,
    "llmConfig": {
      "temperature": 0.30,
      "top_k": 12,
      "top_p": 0.90,
      "repetition_penalty": 1.20,
      "max_new_tokens": 10240
    }
  }'
```

---

#### 옵션 C. `.env` 환경 변수를 로드하여 동적으로 실행하는 셸 명령어

`.env` 파일에 실제 유효한 Key/Secret/ModelID가 들어있는 경우, 셸에서 바로 환경변수를 로드하여 호출할 수 있습니다.

```bash
# .env 환경 변수 export
set -a
source .env
set +a

# cURL 실행
curl -X POST "${ENDPOINT_URL}/openapi/chat/v1/messages" \
  -H "Content-Type: application/json" \
  -H "X-Lego-Client-Id: ${YOUR_CLIENT_KEY}" \
  -H "X-Lego-Client-Secret: ${YOUR_CLIENT_SECRET}" \
  -d "{
    \"modelIds\": [\"${YOUR_MODEL_ID}\"],
    \"contents\": [
      \"간단한 Python hello world 예제 코드를 작성해줘.\"
    ],
    \"systemPrompt\": \"당신은 전문 소프트웨어 개발 어시스턴트입니다.\",
    \"isStream\": false,
    \"llmConfig\": {
      \"temperature\": 0.30,
      \"top_k\": 12,
      \"top_p\": 0.90,
      \"repetition_penalty\": 1.20,
      \"max_new_tokens\": 10240
    }
  }"
```

---

### 3. PowerShell 명령어 예시

Windows PowerShell 또는 PowerShell Core(pwsh)에서 `Invoke-RestMethod`를 사용하는 예시입니다. 한글 인코딩 처리를 위해 UTF-8 바이트 인코딩 및 ContentType 명시가 포함되어 있습니다.

#### 옵션 A. PowerShell 스크립트 형태 (변수 활용)

```powershell
$endpointUrl = "https://scisportal.samsungif.com/rest/getAI/openapi/chat/v1/messages"

$headers = @{
    "Content-Type"         = "application/json; charset=utf-8"
    "X-Lego-Client-Id"     = "API_CLIENT_APP"
    "X-Lego-Client-Secret" = "abcxxxxxxxx"
}

$bodyObj = @{
    modelIds     = @("019a-xxxx-xxxxx")
    contents     = @("간단한 Python hello world 예제 코드를 작성해줘.")
    systemPrompt = "당신은 전문 소프트웨어 개발 어시스턴트입니다."
    isStream     = $false
    llmConfig    = @{
        temperature        = 0.30
        top_k              = 12
        top_p              = 0.90
        repetition_penalty = 1.20
        max_new_tokens     = 10240
    }
}

# UTF-8 JSON 직렬화
$jsonBody = $bodyObj | ConvertTo-Json -Depth 5
$utf8Bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)

# API 호출
$response = Invoke-RestMethod -Uri $endpointUrl `
    -Method Post `
    -Headers $headers `
    -Body $utf8Bytes

# 응답 출력
$response | ConvertTo-Json -Depth 5
```

#### 옵션 B. `.env` 파일 로드 후 호출 (PowerShell)

```powershell
# .env 파일 파싱 후 환경변수 등록
Get-Content .env | Where-Object { $_ -match '^[^#].+=.+' } | ForEach-Object {
    $key, $val = $_ -split '=', 2
    $val = $val.Trim('"').Trim("'")
    [System.Environment]::SetEnvironmentVariable($key.Trim(), $val)
}

$endpointUrl = "$($env:ENDPOINT_URL)/openapi/chat/v1/messages"

$headers = @{
    "Content-Type"         = "application/json; charset=utf-8"
    "X-Lego-Client-Id"     = $env:YOUR_CLIENT_KEY
    "X-Lego-Client-Secret" = $env:YOUR_CLIENT_SECRET
}

$bodyObj = @{
    modelIds     = @($env:YOUR_MODEL_ID)
    contents     = @("간단한 Python hello world 예제 코드를 작성해줘.")
    systemPrompt = "당신은 전문 소프트웨어 개발 어시스턴트입니다."
    isStream     = $false
    llmConfig    = @{
        temperature        = 0.30
        top_k              = 12
        top_p              = 0.90
        repetition_penalty = 1.20
        max_new_tokens     = 10240
    }
}

$jsonBody = $bodyObj | ConvertTo-Json -Depth 5
$utf8Bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonBody)

$response = Invoke-RestMethod -Uri $endpointUrl -Method Post -Headers $headers -Body $utf8Bytes
$response | ConvertTo-Json -Depth 5
```

---

### 4. `.http` 파일 포맷 (VS Code REST Client / IntelliJ HTTP Client)

VS Code의 **REST Client** 확장이나 IntelliJ / WebStorm의 **HTTP Client**에서 바로 실행할 수 있는 포맷입니다. (파일 확장자 `.http` 또는 `.rest`로 저장하여 사용)

```http
### 환경 변수 정의
@baseUrl = https://scisportal.samsungif.com/rest/getAI
@clientId = API_CLIENT_APP
@clientSecret = abcxxxxxxxx
@modelId = 019a-xxxx-xxxxx

### 1. GenAI 논스트리밍(Non-Streaming) 요청
POST {{baseUrl}}/openapi/chat/v1/messages
Content-Type: application/json
X-Lego-Client-Id: {{clientId}}
X-Lego-Client-Secret: {{clientSecret}}

{
  "modelIds": [
    "{{modelId}}"
  ],
  "contents": [
    "간단한 Python hello world 예제 코드를 작성해줘."
  ],
  "systemPrompt": "당신은 전문 소프트웨어 개발 어시스턴트입니다.",
  "isStream": false,
  "llmConfig": {
    "temperature": 0.30,
    "top_k": 12,
    "top_p": 0.90,
    "repetition_penalty": 1.20,
    "max_new_tokens": 10240
  }
}

### 2. GenAI 스트리밍(Streaming / SSE) 요청
POST {{baseUrl}}/openapi/chat/v1/messages
Content-Type: application/json
Accept: text/event-stream
X-Lego-Client-Id: {{clientId}}
X-Lego-Client-Secret: {{clientSecret}}

{
  "modelIds": [
    "{{modelId}}"
  ],
  "contents": [
    "간단한 Python hello world 예제 코드를 작성해줘."
  ],
  "systemPrompt": "당신은 전문 소프트웨어 개발 어시스턴트입니다.",
  "isStream": true,
  "llmConfig": {
    "temperature": 0.30,
    "top_k": 12,
    "top_p": 0.90,
    "repetition_penalty": 1.20,
    "max_new_tokens": 10240
  }
}
```

---

> **참고**: `API_CLIENT_APP`, `abcxxxxxxxx`, `019a-xxxx-xxxxx` 값은 [.env](file:///mnt/c/03_sources/skc3779_srcs/p3-ai-code-chat-messages-wsl/.env)에 설정된 실제 키 및 모델 ID 값으로 대체하여 사용하시면 됩니다.