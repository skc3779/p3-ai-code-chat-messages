# RELEASE v1.0.157 — `ai_cli` 배치 실행: `/auto_context` 명령 파라메터화 및 자동 종료

**릴리스 일자**: 2026-05-10
**FSD 문서**: [FSD_v1.0.157_ai-cli-batch-auto-context.md](../requirements/FSD_v1.0.157_ai-cli-batch-auto-context.md)

---

## 1. 변경 요약

| 기능 | 실행 방법 | 설명 |
|---|---|---|
| **배치 실행 디스패처** | `python -m ai_cli -t <claude\|gemini\|genai> -wp <ws> -c auto_context <pattern> -p <prompt file>` | 단일 명령으로 `/auto_context` 를 실행하고 처리 완료 시 exit code 와 함께 자동 종료 |
| **세 엔트리포인트 공통화** | `main_batch(workspace, command, command_args, prompt) -> int` | claude / gemini / genai 모두 동일 시그니처의 배치 진입점 노출 |

기존 REPL 모드 (`python claude-ai-chat-code.py` 등 직접 실행) 는 변경 없이 동작합니다.

---

## 2. 신규 파일

| 파일 | 역할 |
|---|---|
| `ai_cli.py` | `argparse` 기반 배치 디스패처. `-t / -wp / -c / -p` 파싱 후 엔트리포인트의 `main_batch()` 호출 |
| `tests/test_ai_cli_batch.py` | 디스패처 + `_parse_auto_context_args()` 단위 테스트 (18건) |

## 3. 수정 파일

| 파일 | 변경 내용 |
|---|---|
| `claude-ai-chat-code.py` | `_parse_auto_context_args()`, `main_batch()` 추가 (REPL `main()` 은 무수정) |
| `gemini-ai-chat-code.py` | 동일 |
| `gen-ai-chat-code.py` | 동일 |
| `README.md` | 배치 실행 사용법 섹션 추가 |

---

## 4. 옵션 명세

| 옵션 | 별칭 | 값 | 필수 |
|---|---|---|---|
| `-t`  | `--type`      | `claude` \| `gemini` \| `genai` | ✅ |
| `-wp` | `--workspace` | 작업 디렉토리 경로                | ✅ |
| `-c`  | `--command`   | `auto_context <pattern>`         | ✅ |
| `-p`  | `--prompt`    | 프롬프트 파일 경로 (UTF-8 / BOM)  | ✅ |

### 4.1 종료 코드

| 코드 | 의미 |
|---|---|
| 0   | 정상 처리 완료 |
| 1   | 입력 오류 (워크스페이스/프롬프트/매칭 0개) |
| 2   | 미지원 명령 또는 argparse 오류 (`auto_context` 외 또는 패턴 누락) |
| 3   | API/처리 중 예외 |
| 130 | KeyboardInterrupt |

---

## 5. 사용 예시

```bash
# Claude 로 src/*.py 자동 처리
python -m ai_cli -t claude -wp ./ -c auto_context "src/*.py" -p prompt.txt

# Gemini · 다중 패턴
python -m ai_cli -t gemini -wp /work \
    -c auto_context "[src/*.py, docs/*.md]" -p prompts/translate.txt

# GenAI · 절대 경로 워크스페이스
python -m ai_cli --type genai \
    --workspace "C:\proj" \
    --command auto_context "tests/*.py" \
    --prompt prompts/refactor.txt
```

> 와일드카드는 셸 글롭을 막기 위해 **반드시 따옴표** 로 감쌉니다.

---

## 6. 테스트 결과

```
tests/test_ai_cli_batch.py ...................... 18 passed
```

| 검증 항목 | 결과 |
|---|---|
| `parse_args()` 정상/오류 케이스 | ✅ |
| 미지원 명령 / 패턴 누락 → exit 2 | ✅ |
| 워크스페이스/프롬프트 누락·빈 파일 → exit 1 | ✅ |
| UTF-8 BOM 프롬프트 정상 로드 | ✅ |
| `main_batch()` 반환값 → exit code 그대로 전달 | ✅ |
| `KeyboardInterrupt` → exit 130 | ✅ |
| 일반 예외 → exit 3 | ✅ |
| 세 엔트리포인트 모두 `main_batch` 노출 | ✅ |
| 단일/대괄호/`-qc` 패턴 파싱 | ✅ |

---

## 7. 호환성

- 기존 REPL 진입 (`python claude-ai-chat-code.py`) 동작 변경 없음.
- `command_registry.py` 의 `/auto_context` 항목은 미수정 — REPL 명령어 시그니처 그대로.
- PyInstaller 빌드 환경에서도 `ai_cli.py` 는 표준 모듈 임포트로 작동 (NFR-05).

---

## 8. 후속 작업

- 배치 모드의 명령어 확장 (`read`, `context`, `agents` 등)
- `-c` 시퀀스 파이프라인 (`-c "auto_context ..." -c "save"`)
- `-o <file>` 결과 출력 파일 옵션
- `--no-stream`, `--quality-check` 단축 옵션
