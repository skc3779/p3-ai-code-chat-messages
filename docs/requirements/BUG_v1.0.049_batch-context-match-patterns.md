# BUG v1.0.049 - `/auto_context` FilePatternMatcher.match_patterns 오류

## 문서 정보
- **버전**: v1.0.049
- **작성일**: 2026-02-26
- **상태**: Fixed
- **관련 FSD**: FSD v1.0.049 (Context File Pattern 자동 처리)
- **대상 파일**: `gemini-ai-chat-code01.py`

---

## 1. 증상

`gemini-ai-chat-code01.py`에서 `/auto_context` 명령어 실행 시 오류 발생:

```
> /auto_context [original/*.md]
📝 멀티라인 모드 (종료: /end)
... original 폴더에 있는 md 파일을 1개씩 한글로 번역해서 hangle 폴더에 동일한 파일명으로 저장해줘
... /end

❌ 오류 발생: 'FilePatternMatcher' object has no attribute 'match_patterns'
```

---

## 2. 원인

`gemini-ai-chat-code01.py`의 `/auto_context` 핸들러에서 존재하지 않는 메서드 `match_patterns()`를 호출.

`FilePatternMatcher` 클래스의 실제 API:

| 메서드 | 시그니처 |
|--------|----------|
| `normalize_pattern` | `(self, pattern: str) -> str` |
| `match` | `(self, filepath: Path, pattern: str) -> bool` |
| `filter_files` | `(self, files: List[Path], patterns: List[str]) -> List[Path]` |

→ `match_patterns`는 존재하지 않음. 올바른 메서드는 `filter_files(files, patterns)`.

### 버그 코드 (L248-249)

```python
# ❌ 잘못된 코드
matcher = FilePatternMatcher(assistant.file_manager.workspace_dir)
matched_files = matcher.match_patterns(file_patterns)
```

### 수정 코드

```python
# ✅ 수정된 코드
matcher = FilePatternMatcher(assistant.file_manager.workspace_dir)
all_files = assistant.file_manager.list_files()
matched_files = matcher.filter_files(all_files, file_patterns)
```

---

## 3. 영향 범위

| 파일 | 영향 |
|------|------|
| `gemini-ai-chat-code01.py` | ✅ **버그 있음** → 수정 완료 |
| `gen-ai-chat-code01.py` | ❌ 영향 없음 (처음부터 `filter_files` 사용) |
| `claude-ai-chat-code01.py` | ❌ 영향 없음 (처음부터 `filter_files` 사용) |

---

## 4. 근본 원인

FSD v1.0.049 구현 시, `gemini-ai-chat-code01.py`의 기존 `/read` 핸들러(L174)가 `matcher.match_patterns(patterns)` 형태를 사용하고 있어 이를 참조하여 동일하게 작성. 그러나 해당 호출도 실제로는 동작하지 않는 코드(기존 버그)였음.

---

## 5. 수정 내역

- **파일**: `gemini-ai-chat-code01.py` L248-249
- **변경**: `match_patterns()` → `list_files()` + `filter_files()` 패턴으로 대체
