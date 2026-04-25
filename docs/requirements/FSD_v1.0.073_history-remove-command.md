# FSD v1.0.073 — `/history --remove` 과거 이력 삭제로 토큰 낭비 절감

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.073 |
| 작성일 | 2026-03-06 |
| 상태 | 초안 |
| 대상 파일 | `claude-ai-chat-code.py`, `gen-ai-chat-code.py`, `gemini-ai-chat-code.py`, `src/command_registry.py` |
| 연관 모듈 | `src/history_manager.py`, `src/token_manager.py` |

---

## 1. 개요

AI 어시스턴트는 매 요청마다 `conversation_history` 전체를 API에 전달한다.  
대화가 길어질수록 오래된 항목이 불필요하게 토큰을 소모하며, 플랫폼별 컨텍스트 윈도우 한도 초과의 원인이 된다.

현재 히스토리를 전부 초기화하는 `/clear` 명령은 있지만,  
**일부만 선택적으로 삭제**하는 수단이 없어 세밀한 토큰 절약이 불가능하다.

이 문서는 `/history --remove N` (단축: `/history -r N`) 명령을 추가하여  
오래된 항목부터 N개를 삭제하는 기능을 정의한다.

---

## 2. 현황 분석

### 2.1 conversation_history 구조

| 플랫폼 | 자료형 | 예시 |
|---|---|---|
| Claude | `List[Dict]` | `{"role": "user", "content": "..."}` |
| GenAI | `List[str]` | `"user: ..."` |
| Gemini | `List[Dict]` | `{"role": "user", "content": "..."}` |

항목은 **인덱스 0이 가장 오래된 것** (ASC 순서)으로 저장된다.

### 2.2 현재 관련 명령

| 명령 | 동작 |
|---|---|
| `/history` | 전체 히스토리 조회 |
| `/clear` | 전체 삭제 |
| `/save_history` | 파일로 저장 |

**문제점:** 오래된 항목만 선택 삭제하는 명령이 없다.

---

## 3. 요구사항

### 3.1 기능 요구사항

| ID | 요구사항 |
|---|---|
| FR-001 | `/history --remove N` 또는 `/history -r N` 명령을 인식한다. |
| FR-002 | `conversation_history`의 앞(인덱스 0)부터 N개를 삭제한다. |
| FR-003 | N이 현재 히스토리 항목 수보다 크면 오류 메시지를 출력하고 삭제하지 않는다. |
| FR-004 | N이 0 이하이거나 정수가 아닌 경우 사용법 안내 메시지를 출력한다. |
| FR-005 | 삭제 완료 후 삭제된 항목 수와 남은 항목 수를 출력한다. |
| FR-006 | Claude / GenAI / Gemini 세 엔트리 포인트 모두에 동일하게 적용한다. |
| FR-007 | `command_registry.py`의 `/history` 항목 usage 문자열을 업데이트한다. |
| FR-008 | `/history --delete <index>` 또는 `/history -d <index>` 명령을 인식한다. |
| FR-009 | 지정한 `index`에 해당하는 `conversation_history` 항목 1개를 삭제한다. (index는 1-based, `/history` 조회 시 표시되는 번호 기준) |
| FR-010 | 삭제 완료 후 삭제 성공 메시지를 출력하고, 갱신된 히스토리 목록을 즉시 출력한다. |

### 3.2 비기능 요구사항

- 삭제는 **비가역적**이므로 삭제 전 저장이 필요한 경우 사용자가 `/save_history`를 먼저 실행한다 (이 문서에서 자동 저장을 강제하지 않음).
- 기존 `/history` (인수 없음) 동작에 영향 없음.

---

## 4. 명령 사양

### 4.1 구문

```
/history --remove <N>
/history -r <N>
/history --delete <index>
/history -d <index>
```

- `N`: 삭제할 항목 수 (양의 정수)
- `index`: 삭제할 항목의 1-based 인덱스 번호 (`/history` 조회 시 출력되는 번호)

### 4.2 파싱 규칙

`/history` 명령 처리 시 `args`를 분석한다.

```
args 없음                          → 기존 /history 조회 동작
args == "--remove N" 또는 "-r N"  → 앞에서 N개 삭제 처리
args == "--delete I" 또는 "-d I"  → index I 항목 삭제 처리
그 외                              → 사용법 안내
```

### 4.3 응답 메시지

| 상황 | 출력 메시지 |
|---|---|
| 삭제 성공 | `✅ 히스토리 {N}개를 삭제했습니다. (남은 항목: {remaining}개)` |
| N > 현재 항목 수 | `❌ history 목록수({total})보다 숫자({N})가 더 많아 삭제가 불가능합니다.` |
| N ≤ 0 또는 숫자 아님 | `❌ 삭제할 개수는 1 이상의 정수여야 합니다. 예: /history --remove 5` |
| 히스토리 빈 경우 | `📭 대화 히스토리가 비어있습니다.` |
| index 삭제 성공 | `✅ 히스토리 {index}번 항목을 삭제했습니다. (남은 항목: {remaining}개)` + 갱신된 목록 출력 |
| index 범위 초과 또는 0 이하 | `❌ 유효하지 않은 인덱스입니다. (1 ~ {total} 범위)` |
| index가 숫자 아님 | `❌ 인덱스는 1 이상의 정수여야 합니다. 예: /history --delete 3` |

---

## 5. 구현 사양

### 5.1 `/history` 명령 처리 로직 (공통)

```python
elif command == '/history':
    if not args:
        # 기존 조회 동작
        if assistant.conversation_history:
            print("\n📜 대화 히스토리:")
            for i, msg in enumerate(assistant.conversation_history, 1):
                ...
        else:
            print("📭 대화 히스토리가 비어있습니다.")

    elif args.startswith('--remove') or args.startswith('-r'):
        # --remove N 또는 -r N 파싱
        parts = args.split()
        if len(parts) < 2:
            print("❌ 삭제할 개수는 1 이상의 정수여야 합니다. 예: /history --remove 5")
            continue
        try:
            n = int(parts[1])
        except ValueError:
            print("❌ 삭제할 개수는 1 이상의 정수여야 합니다. 예: /history --remove 5")
            continue
        if n <= 0:
            print("❌ 삭제할 개수는 1 이상의 정수여야 합니다. 예: /history --remove 5")
            continue
        total = len(assistant.conversation_history)
        if total == 0:
            print("📭 대화 히스토리가 비어있습니다.")
            continue
        if n > total:
            print(f"❌ history 목록수({total})보다 숫자({n})가 더 많아 삭제가 불가능합니다.")
            continue
        del assistant.conversation_history[:n]
        remaining = len(assistant.conversation_history)
        print(f"✅ 히스토리 {n}개를 삭제했습니다. (남은 항목: {remaining}개)")

    elif args.startswith('--delete') or args.startswith('-d'):
        # --delete <index> 또는 -d <index> 파싱
        parts = args.split()
        if len(parts) < 2:
            print("❌ 인덱스는 1 이상의 정수여야 합니다. 예: /history --delete 3")
            continue
        try:
            idx = int(parts[1])
        except ValueError:
            print("❌ 인덱스는 1 이상의 정수여야 합니다. 예: /history --delete 3")
            continue
        total = len(assistant.conversation_history)
        if total == 0:
            print("📭 대화 히스토리가 비어있습니다.")
            continue
        if idx < 1 or idx > total:
            print(f"❌ 유효하지 않은 인덱스입니다. (1 ~ {total} 범위)")
            continue
        del assistant.conversation_history[idx - 1]
        remaining = len(assistant.conversation_history)
        print(f"✅ 히스토리 {idx}번 항목을 삭제했습니다. (남은 항목: {remaining}개)")
        if assistant.conversation_history:
            print("\n📜 대화 히스토리:")
            for i, msg in enumerate(assistant.conversation_history, 1):
                ...
        else:
            print("📭 대화 히스토리가 비어있습니다.")

    else:
        print("❌ 알 수 없는 /history 옵션입니다. 예: /history --remove 5")
```

### 5.2 command_registry.py 수정

```python
# 변경 전
CommandInfo('/history', '대화 히스토리 보기', '/history'),

# 변경 후
CommandInfo('/history', '대화 히스토리 보기/삭제', '/history [--remove|-r <N>] [--delete|-d <index>]'),
```

---

## 6. 플랫폼별 유의사항

| 플랫폼 | conversation_history 타입 | 삭제 방식 |
|---|---|---|
| Claude | `List[Dict]` | `del assistant.conversation_history[:n]` |
| GenAI | `List[str]` | `del assistant.conversation_history[:n]` |
| Gemini | `List[Dict]` | `del assistant.conversation_history[:n]` |

세 플랫폼 모두 Python 리스트이므로 동일한 슬라이스 삭제 구문 사용.

---

## 7. 테스트 시나리오

| # | 입력 | 사전 조건 | 기대 결과 |
|---|---|---|---|
| T-01 | `/history --remove 3` | 히스토리 5개 | 앞 3개 삭제, `남은 항목: 2개` 출력 |
| T-02 | `/history -r 3` | 히스토리 5개 | T-01과 동일 |
| T-03 | `/history --remove 6` | 히스토리 5개 | `history 목록수(5)보다 숫자(6)가 더 많아 삭제가 불가능합니다.` |
| T-04 | `/history --remove 0` | 히스토리 5개 | 개수 오류 안내 메시지 |
| T-05 | `/history --remove abc` | 히스토리 5개 | 숫자 아님 오류 안내 메시지 |
| T-06 | `/history --remove 5` | 히스토리 5개 | 전체 삭제, `남은 항목: 0개` 출력 |
| T-07 | `/history --remove 1` | 히스토리 비어있음 | `대화 히스토리가 비어있습니다.` |
| T-08 | `/history` | 히스토리 2개 | 기존 조회 동작 (변경 없음) |
| T-09 | `/history --delete 2` | 히스토리 5개 | 2번 항목 삭제 후 갱신된 목록 출력, `남은 항목: 4개` |
| T-10 | `/history -d 2` | 히스토리 5개 | T-09와 동일 |
| T-11 | `/history --delete 6` | 히스토리 5개 | `유효하지 않은 인덱스입니다. (1 ~ 5 범위)` |
| T-12 | `/history --delete 0` | 히스토리 5개 | `유효하지 않은 인덱스입니다. (1 ~ 5 범위)` |
| T-13 | `/history --delete abc` | 히스토리 5개 | 숫자 아님 오류 안내 메시지 |
| T-14 | `/history --delete 1` | 히스토리 1개 | 1번 항목 삭제 후 `대화 히스토리가 비어있습니다.` 출력 |
| T-15 | `/history --delete 1` | 히스토리 비어있음 | `대화 히스토리가 비어있습니다.` |

---

## 8. 영향 범위

| 파일 | 변경 유형 |
|---|---|
| `claude-ai-chat-code.py` | `/history` 명령 처리 블록 수정 |
| `gen-ai-chat-code.py` | `/history` 명령 처리 블록 수정 |
| `gemini-ai-chat-code.py` | `/history` 명령 처리 블록 수정 |
| `src/command_registry.py` | `/history` usage 문자열 수정 |
| `tests/test_history_manager.py` | 신규 테스트 케이스 추가 (선택) |

`src/history_manager.py`는 파일 저장/로드만 담당하므로 **변경 없음**.

---

## 9. 이슈 및 제약

- 이 기능은 인메모리 `conversation_history`만 수정하며, 저장된 히스토리 파일에는 영향 없음.
- 삭제 후 API 호출 시 삭제된 메시지의 맥락은 복구 불가. 중요 맥락 보존이 필요하면 `/save_history` 선행 실행 권장.
- GenAI의 `List[str]` 구조는 홀수/짝수 인덱스로 user/assistant를 구분하는 경우가 있어,  
  N이 짝수가 아니면 role 균형이 깨질 수 있음 — 이 문서에서는 제한하지 않으나 주의 필요.
