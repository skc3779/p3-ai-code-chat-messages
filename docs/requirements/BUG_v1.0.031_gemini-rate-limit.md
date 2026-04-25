# BUG: Gemini API Rate Limit 오류 (429)

> **문서 버전**: v1.0.031  
> **작성일**: 2026-02-06  
> **상태**: Analyzed  
> **관련 FSD**: FSD_Gemini_API_Integration_v1.0.030.md

---

## 1. 오류 현상

### 1.1 증상
Gemini Code Assistant 실행 시 **HTTP 429 (Too Many Requests)** 오류가 발생합니다.

```
⚠️ API 오류 (429). 1.0초 후 재시도... (1/3)
⚠️ API 오류 (429). 1.9초 후 재시도... (2/3)
⚠️ API 오류 (429). 2.6초 후 재시도... (3/3)
❌ API Error: 429 - {...}
```

### 1.2 오류 메시지
```json
{
  "error": {
    "code": 429,
    "message": "You exceeded your current quota...",
    "status": "RESOURCE_EXHAUSTED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [
          {
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_input_token_count",
            "quotaId": "GenerateContentInputTokensPerModelPerDay-FreeTier"
          },
          {
            "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
            "quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
          }
        ]
      }
    ]
  }
}
```

---

## 2. 원인 분석

### 2.1 근본 원인
**Gemini API Free Tier 할당량 초과**

| 할당량 유형 | 제한 |
|------------|------|
| 분당 요청 수 (RPM) | 15 requests/minute |
| 일일 요청 수 (RPD) | 1,500 requests/day |
| 분당 토큰 수 (TPM) | 32,000 tokens/minute |
| 일일 토큰 수 (TPD) | 1,500,000 tokens/day |

### 2.2 트리거 조건
1. Free Tier API 키 사용 중
2. 분당 15회 이상 요청
3. 일일 할당량 소진
4. 첫 번째 요청이지만 다른 프로젝트에서 이미 할당량 소진

### 2.3 버그 여부
**이것은 버그가 아닙니다.** Gemini API의 정상적인 Rate Limiting 동작입니다.

그러나 현재 구현에서 개선이 필요한 부분:
1. 429 오류 시 `retryDelay` 값을 파싱하여 대기 시간에 반영하지 않음
2. 사용자에게 할당량 상태를 명확히 안내하지 않음

---

## 3. 해결 방법

### 3.1 즉시 해결 (사용자 조치)

**옵션 1: 대기**
```
응답의 retryDelay 값(예: 16초) 이상 대기 후 재시도
```

**옵션 2: 다른 모델 사용**
```env
# .env 파일에서 모델 변경
GEMINI_MODEL_ID=gemini-2.0-flash-exp
```

**옵션 3: 유료 플랜 업그레이드**
- [Google AI Studio](https://aistudio.google.com/)에서 Billing 설정
- Pay-as-you-go 플랜으로 전환

### 3.2 코드 개선 (개발자 조치)

**개선 1: retryDelay 파싱 및 적용**
```python
# src/gemini_assistant.py 수정
def _parse_retry_delay(self, response_text: str) -> float:
    """429 응답에서 권장 대기 시간 추출"""
    try:
        import re
        match = re.search(r'retryDelay.*?(\d+(?:\.\d+)?)', response_text)
        if match:
            return float(match.group(1))
    except:
        pass
    return 30.0  # 기본 30초 대기
```

**개선 2: 429 오류 시 명확한 안내**
```python
if response.status_code == 429:
    print("\n⚠️ Gemini API 할당량 초과")
    print("💡 해결 방법:")
    print("   1. 잠시 대기 후 재시도 (권장: 30초 이상)")
    print("   2. 다른 모델로 변경: gemini-2.0-flash-exp")
    print("   3. Google AI Studio에서 할당량 확인")
```

**개선 3: 할당량 관리 기능 추가**
```python
# 새 명령어: /quota
def show_quota_info(self):
    """할당량 정보 표시"""
    print("\n📊 Gemini API Free Tier 할당량:")
    print("  - 분당 요청: 15 RPM")
    print("  - 일일 요청: 1,500 RPD")
    print("  - 분당 토큰: 32,000 TPM")
    print("  - 일일 토큰: 1,500,000 TPD")
```

---

## 4. 예방 조치

### 4.1 Rate Limiting 설계
```python
import time
from datetime import datetime, timedelta

class RateLimiter:
    """API 호출 속도 제한"""
    
    def __init__(self, max_requests_per_minute=10):  # 15 RPM 중 10만 사용
        self.max_rpm = max_requests_per_minute
        self.request_times = []
    
    def wait_if_needed(self):
        """필요시 대기"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # 1분 이내 요청 필터링
        self.request_times = [t for t in self.request_times if t > minute_ago]
        
        if len(self.request_times) >= self.max_rpm:
            wait_time = (self.request_times[0] - minute_ago).total_seconds()
            print(f"⏳ Rate limit 방지를 위해 {wait_time:.1f}초 대기...")
            time.sleep(wait_time + 0.5)
        
        self.request_times.append(now)
```

### 4.2 모델별 할당량 확인 링크
- [Gemini API 할당량 문서](https://ai.google.dev/gemini-api/docs/rate-limits)
- [사용량 모니터링](https://ai.dev/rate-limit)

---

## 5. 버전별 조치 계획

| 버전 | 조치 사항 | 상태 |
|------|----------|------|
| v1.0.031 | 오류 원인 문서화 | 완료 |
| v1.0.032 | 429 오류 시 retryDelay 파싱 | 미구현 |
| v1.0.033 | RateLimiter 클래스 추가 | 미구현 |
| v1.0.034 | /quota 명령어 추가 | 미구현 |

---

## 6. 참고 자료

- [Gemini API Rate Limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Google Cloud 할당량 관리](https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com/quotas)
- [Free Tier vs Paid Tier 비교](https://ai.google.dev/pricing)

---

## 7. 버전 히스토리

| 버전 | 날짜 | 작성자 | 변경 내용 |
|------|------|--------|----------|
| v1.0.031 | 2026-02-06 | AI Assistant | 429 오류 분석 및 해결 방법 문서화 |
