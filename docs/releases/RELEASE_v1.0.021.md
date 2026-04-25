# RELEASE v1.0.021

> **Release Date**: 2026-01-28  
> **Version**: v1.0.021

## 🛠️ Key Changes

### 1. Prompt Template System (v1.0.020)
- **Feature**: Introduced a flexible prompt template system using YAML files in `.system-prompts/`.
- **New Commands**:
  - `/template <name>`: Switch to a specific system prompt context (e.g., code-review).
  - `/template_list`: View all available templates.
  - `/template_reset`: Restore the default system prompt.
- **File**: `FSD_Prompt_Templates_v1.0.020.md`

### 2. File Watcher Deadlock Fix (v1.0.021)
- **Fix**: Resolved a critical deadlock issue causing the application to hang when using the `/watch` command.
- **Details**: Replaced standard `Lock` with `RLock` in `src/file_watcher.py` to allow reentrant lock acquisition.
- **File**: `BUG_File_Watcher_Deadlock_v1.0.021.md`
