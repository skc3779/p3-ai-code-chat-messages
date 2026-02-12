# RELEASE v1.0.029

## ✨ 주요 변경 사항

### 1. 코드 Diff 표시 기능 - P3-03

AI가 생성한 전체 코드를 단순히 출력하는 대신, **기존 코드와의 차이점(Diff)을 시각적으로 표시**합니다.

#### 📌 신규 명령어

| 명령어 | 설명 |
|--------|------|
| `/diff` | 마지막 AI 응답에서 코드 제안을 추출하여 원본 파일과 비교한 Diff 표시 |
| `/apply` | 마지막 Diff 내용을 실제 파일에 적용 (Patch) |

#### 🎨 Diff 출력 기능

- **컬러 표시**: 터미널 색상 코드를 사용하여 시각적 구분
  - 🟢 **초록색**: 추가된 라인 (`+`)
  - 🔴 **빨간색**: 삭제된 라인 (`-`)
  - 🟡 **노란색**: 섹션 헤더 (`@@`)
  - 🔵 **시안색**: 파일명 헤더

- **변경 통계**: 추가/삭제된 라인 수 및 총 변경사항 표시
- **Unified Diff 형식**: `difflib` 모듈을 사용한 표준 Diff 포맷

#### 🔄 워크플로우

```
1. AI에게 코드 수정 요청: "이 함수를 리팩토링해줘"
2. /diff 명령어로 변경사항 확인
3. 변경사항이 마음에 들면 /apply로 적용
   - 또는 /save로 파일 저장
```

### 2. 신규 모듈

- **`src/diff_viewer.py`**: DiffViewer 클래스
  - `generate_colored_diff()`: 색상 정보가 포함된 Diff 텍스트 생성
  - `extract_code_suggestions()`: AI 응답에서 코드 제안 추출
  - `get_diff_stats()`: 변경 통계 계산
  - `apply_diff()`: 변경사항 파일에 적용

### 3. 테스트 코드

- **`tests/test_diff_viewer.py`**: DiffViewer 단위 테스트
  - Diff 생성 테스트
  - 색상화 테스트
  - 코드 추출 테스트
  - 적용 로직 테스트

### 4. 통합

- **ClaudeCodeAssistant**: `/diff`, `/apply` 명령어 지원
- **GenAICodeAssistant**: `/diff`, `/apply` 명령어 지원

---

## 📄 관련 문서

- **FSD**: `docs/specs/drafts/FSD_Code_Diff_Display_v1.0.029.md`
- **SRS**: `docs/specs/requirements/SRS_Claude_Code_Assistant_Improvements_v1.0.016.md`

---

**업데이트 날짜**: 2026-02-06
**작성자**: Antigravity
