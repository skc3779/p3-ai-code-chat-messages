# RELEASE v1.0.025

> **Release Date**: 2026-02-02  
> **Version**: v1.0.025

## 🐛 Bug Fix: `/read` Command Pattern Matching

### Issue
`/read <pattern>` command failed for various path formats due to incorrect pattern normalization.

### Root Cause
- `lstrip('./').lstrip('.\\')` incorrectly removed `.` from folder names like `.system-prompts`
- No support for absolute paths
- Inconsistent path separator handling (`/` vs `\`)

### Solution
Created `FilePatternMatcher` class (`src/file_pattern_matcher.py`) with:
- `normalize_pattern()`: Proper prefix removal using `startswith()`, path separator unification
- `match()`: Multi-strategy matching (relative path, filename, partial path)
- `filter_files()`: Batch file filtering

### Affected Files
- **[NEW]** `src/file_pattern_matcher.py`
- `src/__init__.py`
- `claude-ai-chat-code01.py`
- `gen-ai-chat-code01.py`

### Test Commands
```bash
/read code-review.yaml
/read .system-prompts/code-review.yaml
/read ./.system-prompts/*.yaml
```
