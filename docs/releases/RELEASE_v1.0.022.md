# RELEASE v1.0.022

> **Release Date**: 2026-01-28  
> **Version**: v1.0.022

## 🛠️ Key Changes

### 1. Enhanced `/tree` Command
- **Feature**: The `/tree` command now automatically reloads `.gitignore` patterns before displaying the file structure.
- **Benefit**: Users no longer need to restart the application to apply changes made to ignore files.
- **Affected Files**:
  - `src/file_manager.py` (Added `reload_ignore_patterns` support)
  - `claude-ai-chat-code01.py`
  - `gen-ai-chat-code01.py`
