
## 테스트 v1.1.011

```ps1
python -m unittest tests.test_large_context_cache -v
python -m unittest tests.test_large_context_command -v
python -m unittest tests.test_large_context_processor -v
python -m unittest tests.test_large_context_provider_contract -v
```

## 테스트 v1.1.021

```ps1
python -m pytest tests/test_ai_cli_batch_auto_context.py tests/test_ai_cli_batch_context.py -v
python -m pytest tests/test_large_context_command.py tests/test_large_context_processor.py -v
python -m pytest tests/test_context_pattern.py -v
python -m pytest -v
```