# RELEASE v1.0.023

> **Release Date**: 2026-01-28  
> **Version**: v1.0.023

## 🛠️ Key Changes

### 1. Improved `.gitignore` Pattern Matching
- **Feature**: Directory ignore patterns are now normalized to handle trailing slashes consistently.
- **Details**: `folder/` and `folder` are now treated identically, ensuring that directory exclusions work reliably regardless of the trailing slash convention used in `.gitignore`.
- **Affected File**: `src/ignorer.py`
