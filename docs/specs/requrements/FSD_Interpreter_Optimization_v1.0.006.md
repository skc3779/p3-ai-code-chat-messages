# FSD: Claude Code Assistant 인터프리터 최적화 기능 보강

**문서 버전**: v1.0.006  
**작성일자**: 2026-01-19  
**수정일자**: 2026-01-19  
**대상 파일**: `claude-ai-chat-code01.py`

---

## 1. 개요

### 1.1 목적
현재 `claude-ai-chat-code01.py`의 기능을 분석하고, **코드 인터프리터 최적화**를 위한 기능 보강 방안을 제시합니다.

### 1.2 현재 기능 분석

| 기능 영역 | 현재 지원 | 설명 |
|-----------|----------|------|
| **파일 읽기** | ✅ | `FileManager.read_file()` |
| **파일 쓰기** | ✅ | `FileManager.write_file()` |
| **디렉토리 탐색** | ✅ | `FileManager.list_files()`, `TreeBuilder` |
| **AI 채팅** | ✅ | Claude API 스트리밍 + Tool Use |
| **컨텍스트 빌드** | ✅ | `ContextBuilder` |
| **파일 추출/저장** | ✅ | `extract_and_save_files()` |
| **코드 실행** | ✅ | `CodeExecutor` (v1.0.003) |
| **터미널 명령** | ✅ | `TerminalExecutor` (v1.0.004) |
| **파일 도구** | ✅ **구현 완료** | `Filesystem Tools` (v1.0.006) |
| **Git 통합** | ❌ | 미지원 |
| **패키지 분석** | ❌ | 미지원 |

---

## 2. 기능 보강 권장 사항 및 현황

### 2.1 우선순위 평가 (업데이트됨)

| 순위 | 기능 | 상태 | 버전 |
|------|------|------|------|
| 1 | **코드 실행 환경** | ✅ 완료 | v1.0.003 |
| 2 | **터미널/Shell 통합** | ✅ 완료 | v1.0.004 |
| 3 | **Filesystem Tools (Tool Use)** | ✅ 완료 | **v1.0.006** |
| 4 | **Git 통합** | ⏳ 대기 | - |
| 5 | **패키지 의존성 분석** | ⏳ 대기 | - |

---

## 3. 구현 완료: 코드 실행 환경 (v1.0.003)
*(생략: 이전 문서 참조)*

---

## 4. 구현 완료: 터미널/Shell 통합 (v1.0.004)
*(생략: 이전 문서 참조)*

---

## 5. 구현 완료: Filesystem Tools (v1.0.006)

### 5.1 개요
Claude API의 **Tool Use (Function Calling)** 기능을 활용하여, AI가 직접 파일 시스템을 조작할 수 있도록 기능을 확장했습니다. 기존에는 사용자가 `/read`, `/save` 등의 명령어로 개입해야 했으나, 이제는 AI가 대화 문맥에 따라 필요한 파일 작업을 스스로 수행합니다.

### 5.2 구현된 도구 (Tools)

| 도구 이름 | 설명 | 입력 파라미터 |
|-----------|------|---------------|
| `read_file` | 파일 내용 읽기 | `path`: 상대 경로 |
| `write_file` | 파일 생성/수정 | `path`: 경로, `content`: 내용 |
| `list_files` | 디렉토리 파일 목록 | `path`: 디렉토리 경로 |
| `list_directory_tree` | 트리 구조 조회 | `path`: 루트 경로, `depth`: 깊이 |

### 5.3 기술적 구현
- **Protocol**: Claude API Tool Use
- **Streaming**: SSE 스트리밍 중 `content_block_start` (tool_use) 및 `content_block_delta` (input_json_delta) 이벤트를 수신하여 JSON을 조립하고 실행.
- **Recursion**: 도구 실행 결과(`tool_result`)를 API에 다시 전송하여 후속 응답(최종 답변)을 받아오는 재귀적 구조 구현.

### 5.4 사용 시나리오

**Q: "src 폴더에 있는 모든 파이썬 파일을 읽어서 분석해줘"**

1. **AI** (Tool Use 호출):
   ```json
   { "name": "list_files", "input": { "path": "src" } }
   ```
2. **System** (도구 실행):
   `src/main.py`, `src/utils.py` 목록 반환
3. **AI** (Tool Use 호출):
   ```json
   { "name": "read_file", "input": { "path": "src/main.py" } }
   ```
4. **AI** (Tool Use 호출):
   ```json
   { "name": "read_file", "input": { "path": "src/utils.py" } }
   ```
5. **System** (도구 실행):
   파일 내용 반환
6. **AI** (최종 응답):
   "코드를 분석했습니다. main.py는..."

---

## 6. 구현 로드맵 (업데이트)

### Phase 1 (v1.1.0) - 필수 기능 ✅ 완료
- CodeExecutor, TerminalExecutor, Filesystem Tools 모두 구현 완료됨.

### Phase 2 (v1.2.0) - 확장 기능
- Git 통합 (`GitManager` + Tool Use)
- 웹 검색 통합 (Tool Use)

### Phase 3 (v1.3.0) - 고도화
- MCP 서버 프로토콜 완전 준수 (옵션)
- 패키지 의존성 시각화

---

## 7. 현재 지원 명령어

| 명령어 | 설명 | 비고 |
|--------|------|------|
| (자동) | 파일 읽기/쓰기/탐색 | **Tool Use (New)** |
| `/run` | 코드 실행 | v1.0.003 |
| `/shell` | 쉘 명령 (안전) | v1.0.004 |
| `/files`, `/tree` | 수동 파일 조회 | 기존 유지 |

---

## 8. 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0.001 | 2026-01-19 | 최초 작성 |
| v1.0.003 | 2026-01-19 | CodeExecutor 구현 |
| v1.0.004 | 2026-01-19 | TerminalExecutor 구현 |
| v1.0.006 | 2026-01-19 | **Filesystem Tool Use 구현** (Priority 3) |
