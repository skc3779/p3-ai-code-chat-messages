# FSD: 대화 히스토리 저장/로드 기능

**문서 버전**: v1.0.017  
**작성일자**: 2026-01-25  
**참조 SRS**: SRS_Claude_Code_Assistant_Improvements_v1.0.016.md (P2-01)

---

## 1. 개요

### 1.1 현재 문제
세션 종료 시 대화 히스토리(conversation_history)가 메모리에서 삭제되어 이전 대화 맥락이 완전히 손실됨.

### 1.2 개선 목표
JSON 파일을 통해 대화 히스토리를 영속화하여, 세션 간 연속성을 확보.

---

## 2. 기능 요구사항

| 기능 | 설명 |
|------|------|
| **히스토리 저장** | `/save_history` 명령어 또는 종료 시 자동 저장 |
| **히스토리 로드** | `/load_history` 명령어 또는 시작 시 자동 로드 |
| **저장 위치** | 작업 디렉토리 내 `.chat_history/` 폴더 |
| **파일 형식** | JSON (`history_YYYYMMDD_HHMMSS.json`) |

---

## 3. 구현 설계

### 3.1 신규 메서드 (`ClaudeCodeAssistant` / `GenAICodeAssistant`)

```python
def save_history(self, filepath: Optional[str] = None) -> bool:
    """대화 히스토리를 JSON 파일로 저장"""
    
def load_history(self, filepath: str) -> bool:
    """JSON 파일에서 대화 히스토리 로드"""
```

### 3.2 저장 데이터 구조

#### 3.2.1 ClaudeCodeAssistant (Dict 기반)

```json
{
  "version": "1.0",
  "type": "claude",
  "created_at": "2026-01-25T18:00:00",
  "model_id": "claude-sonnet-4-5",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

#### 3.2.2 GenAICodeAssistant (String 리스트 기반)

```json
{
  "version": "1.0",
  "type": "genai",
  "created_at": "2026-01-25T18:00:00",
  "model_id": "your-model-id",
  "messages": [
    "사용자 메시지 1",
    "AI 응답 1",
    "사용자 메시지 2",
    "AI 응답 2"
  ]
}
```

> **참고**: `type` 필드를 통해 로드 시 적절한 어시스턴트 형식으로 복원됨.

### 3.3 CLI 명령어 추가

| 명령어 | 설명 |
|--------|------|
| `/save_history [파일명]` | 현재 히스토리 저장 |
| `/load_history <파일명>` | 저장된 히스토리 로드 |
| `/list_history` | 저장된 히스토리 파일 목록 |

---

## 4. 검증 방안

- 단위 테스트: `save_history`, `load_history` 함수 동작 검증
- 통합 테스트: CLI 명령어 실행 후 히스토리 복원 확인
