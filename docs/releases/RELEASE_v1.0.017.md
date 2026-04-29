# Release Notes: Claude Code Assistant v1.0.017

**버전**: v1.0.017  
**릴리즈 날짜**: 2026-01-25  
**타입**: Feature Release

---

## 🎯 릴리즈 개요

대화 히스토리 영속화 기능이 추가되었습니다. 세션 종료 후에도 이전 대화를 저장하고 불러올 수 있습니다.

---

## ✨ 새로운 기능

### 대화 히스토리 저장/로드 (P2-01)

| 명령어 | 설명 |
|--------|------|
| `/save_history [파일명]` | 현재 대화를 JSON 파일로 저장 |
| `/load_history <파일명>` | 저장된 대화 히스토리 로드 |
| `/list_history` | 저장된 히스토리 파일 목록 확인 |

**저장 위치**: `.chat_history/` 폴더  
**파일 형식**: `history_YYYYMMDD_HHMMSS.json`

---

## 🔧 변경 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/history_manager.py` | 히스토리 저장/로드 모듈 (신규) |
| `src/claude_assistant.py` | `save_history`, `load_history` 메서드 추가 |
| `src/genai_assistant.py` | 동일 메서드 추가 |
| `*-chat-code01.py` | CLI 명령어 핸들러 추가 |

---

## 📋 관련 문서

- [FSD_Conversation_History_v1.0.017.md](../requirements/FSD_Conversation_History_v1.0.017.md)
