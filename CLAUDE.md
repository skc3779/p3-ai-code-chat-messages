# CLAUDE.md (프로젝트 절대 가이드 및 기억 저장소)

## AI Team Role & Agent Assignment Rules
Whenever the `/team` or `/autopilot` skills are triggered, strictly adhere to this agent-team architecture:
1. **Claude Agent (Leader/Implementer)**:
   - Primary build-engineer. Focuses on writing solid logic inside target files.
   - Conducts final architectural integrity checks and merges changes.
2. **Codex Agent (Critic/Security Reviewer)**:
   - Acts as an aggressive code critic.
   - Analyzes Python syntax, edge-cases, performance bottlenecks, and potential bugs.
3. **Gemini Agent (Test & Document Author)**:
   - Generates mock data and comprehensive pytest test-cases.
   - Documents changes directly in code headers and requirement files.

## 🛠️ Verification & Test Command
- Run test: `pytest`
- Build / Lint check: `python -m py_compile claude-ai-chat-code.py gemini-ai-chat-code.py gen-ai-chat-code.py`