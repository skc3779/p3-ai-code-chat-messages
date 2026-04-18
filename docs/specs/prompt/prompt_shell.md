
## Powershell 명령어  

```powershell

cd c:/03_sources/skc3779_srcs/p3-ai-code-chat-messages && python -m pytest tests/ 2>&1 | tail -15

cd c:/03_sources/skc3779_srcs/p3-ai-code-chat-messages && git stash && python -m pytest tests/test_api_logger.py 2>&1 | tail -5; git stash pop 2>&1 | tail -3


```
