# RELEASE v1.0.024

> **Release Date**: 2026-01-28  
> **Version**: v1.0.024

## 🛠️ Key Changes

### 1. Fix: Ignore Pattern Application
- **Fix**: The application now correctly ignores files and directories specified with trailing slashes (e.g., `target/`) in `.gitignore`.
- **Details**: Updated `FileManager` to utilize the improved `Ignorer` class for consistent pattern matching, ensuring directories like `target/` are properly excluded from file listings and context.
- **Affected Files**: 
  - `src/file_manager.py`
