# FSD v1.1.011 — `/context --large` 대규모 파일 컨텍스트 처리

## 문서 정보

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.1.011 |
| 작성일 | 2026-06-20 |
| 상태 | 구현 완료 |
| 대상 명령 | `/context` |
| 선행 문서 | `FSD_v1.0.068_context-multi-pattern-test.md`, `FSD_v1.0.123_auto-context-quality-check-and-context-no-tree.md` |
| 사용자 결정 | `--large` 명시 옵션, 다중 LLM 호출 허용, 디스크 캐시 및 실패 재개 |

---

## 1. 목적

수백 개 파일 또는 단일 대형 파일을 `/context`로 분석할 때 모든 원문을 한 요청에 넣지 않고, 파일을 안전한 크기로 분할해 여러 번 분석한 뒤 결과를 계층적으로 통합한다.

기존 `/context` 동작은 변경하지 않는다. 사용자가 `--large` or `-l`를 명시한 경우에만 **Map → 계층형 Reduce** 파이프라인을 실행한다.

```text
/context --large [src/**/*.java, docs/*.md] 상세한 프로젝트 분석 가이드 파일 만들어줘.
/context --large -nt [src/**/*.java, docs/*.md] 상세한 프로젝트 분석 가이드 파일 만들어줘.
```

성공 조건은 다음과 같다.

1. 매칭 파일 전체가 Map 대상 또는 명시적인 읽기 실패 대상으로 기록된다.
2. 어떤 단일 LLM 요청도 계산된 입력 예산을 초과하지 않는다.
3. 중단 후 같은 명령을 다시 실행하면 완료된 유효 청크를 재호출하지 않고 이어서 처리한다.
4. 최종 응답은 파일 경로와 근거를 유지하며 사용자의 원래 질문에 답한다.
5. `--large`가 없는 기존 `/context` 및 `-nt` 동작에는 회귀가 없다.

---

## 2. 현행 구현 분석

### 2.1 현재 호출 경로

세 엔트리 포인트는 동일한 형태로 `/context`를 처리한다.

```text
명령 파싱
  → assistant.chat(include_context=True, file_patterns=..., include_tree=...)
  → ContextBuilder.build_context()
  → 프로젝트 트리 + 매칭 파일 원문을 단일 user 메시지로 구성
  → LLM 1회 호출
```

근거:

- `claude-ai-chat-code.py:407-457`
- `gemini-ai-chat-code.py:246-294`
- `gen-ai-chat-code.py:415-469`
- `src/claude_assistant.py:175-214`
- `src/gemini_assistant.py:176-206`
- `src/genai_assistant.py:276-306`

### 2.2 토큰 오버플로우 및 정보 손실 원인

`src/context_builder.py:61-91`은 파일 원문 길이를 `max_tokens × 3.5자`로 제한하지만 다음 항목을 같은 예산에 포함하지 않는다.

- 프로젝트 트리
- 시스템 프롬프트
- 사용자 질문
- 기존 대화 히스토리
- 파일 구분자 및 코드 펜스
- 모델 출력 예약 토큰

또한 첫 번째 초과 파일을 만나면 이후 파일 처리를 `break`한다. 따라서 API가 요청을 거부하지 않더라도 뒤쪽 파일이 전부 누락될 수 있다. 현재 테스트도 경고 문자열만 확인하며 전체 파일 처리 여부는 검증하지 않는다(`tests/test_context_builder.py:109-124`).

### 2.3 패턴 매칭 경로 불일치

`ContextBuilder.build_context()`는 직접 `fnmatch.fnmatch()`를 사용한다(`src/context_builder.py:101-108`). 반면 `/auto_context` 등은 중복 제거, 경로 정규화, `**` 처리를 제공하는 `FilePatternMatcher`를 사용한다(`src/file_pattern_matcher.py:15-161`).

대규모 모드는 대상 파일 누락과 중복 처리가 캐시 정확성에 직접 영향을 주므로 `FilePatternMatcher.filter_files()`를 단일 매칭 경로로 사용해야 한다.

### 2.4 `-nt`의 한계

`-nt`는 트리를 제거해 일부 토큰을 절감하지만 파일 원문 총량은 줄이지 않는다. 또한 프로젝트 구조 정보가 없어 최종 통합 시 모듈 경계와 파일 관계를 판단하기 어렵다. 따라서 `--large` 기본 모드는 트리를 매 Map 요청마다 반복하지 않고, **최종 Reduce에 한 번만 압축된 트리와 파일 인벤토리를 전달**한다.

---

## 3. 범위

### 3.1 포함

- `/context --large` 옵션 파싱 및 세 엔트리 포인트의 동일한 라우팅
- `FilePatternMatcher` 기반 파일 선택과 중복 제거
- 파일 경계 우선 청킹 및 단일 대형 파일의 줄 단위 분할
- 순차 Map 호출과 계층형 Reduce 호출
- 프로젝트 트리·파일 인벤토리의 효율적 전달
- 디스크 캐시, 원자적 체크포인트, 자동 재개
- 파일 변경 감지 및 영향받은 청크만 무효화
- 진행률, 예상/실제 호출 수, 재사용 수, 실패 요약
- 단위·통합·중단/재개 테스트

### 3.2 제외

- `--large` 자동 감지 또는 기존 `/context`의 자동 전환
- 병렬 LLM 호출
- 벡터 데이터베이스, 임베딩 검색, RAG 서버
- 새로운 외부 Python 패키지
- `/read`, `/auto_context`, `/agents`의 대규모 모드 적용
- 캐시를 다른 워크스페이스 또는 사용자와 공유하는 기능
- 정확한 provider tokenizer 도입

---

## 4. 사용자 인터페이스

### 4.1 명령 형식

```text
/context [옵션...] <파일패턴> [질문]

옵션:
  --large           대규모 컨텍스트를 여러 LLM 호출로 분할 처리한다.
  -nt, --no-tree    프로젝트 트리를 최종 통합 입력에서 제외한다.
```

`--large`는 선두 옵션 영역에서 `-nt`와 순서에 관계없이 함께 사용할 수 있다.

```text
/context --large src/*.py 질문
/context -nt --large [src/**/*.java, docs/*.md] 질문
/context --large --no-tree [src/**/*.java, docs/*.md] 질문
```

알 수 없는 옵션은 기존 계약대로 오류 처리한다.

### 4.2 기존 동작 호환성

| 입력 | 동작 |
|---|---|
| `/context <pattern> 질문` | 기존 단일 호출 유지 |
| `/context -nt <pattern> 질문` | 기존 단일 호출, 트리 제외 |
| `/context --large <pattern> 질문` | 대규모 파이프라인, 최종 Reduce에 트리 포함 |
| `/context --large -nt <pattern> 질문` | 대규모 파이프라인, 트리 제외; 파일 인벤토리는 유지 |

파일 인벤토리에는 상대 경로, 바이트 크기, 청크 번호만 포함한다. `-nt`는 시각적 프로젝트 트리를 제거하지만 완전성 검증에 필요한 인벤토리까지 제거하지 않는다.

### 4.3 실행 전 출력

LLM 호출 전에 다음 정보를 표시한다.

```text
📦 대규모 컨텍스트 모드
   매칭 파일: 284개
   총 크기: 18.4 MB
   Map 청크: 37개
   예상 LLM 호출: 최소 38회 (Map 37 + Reduce 1, 계층 Reduce 시 증가)
   캐시 작업 ID: 8f41c2d19a7e
```

비대화형 확인 프롬프트는 추가하지 않는다. 사용자가 `--large`를 명시한 것이 다중 호출과 비용에 대한 실행 의사로 간주된다.

---

## 5. 아키텍처

### 5.1 구성 요소

| 구성 요소 | 책임 |
|---|---|
| `LargeContextProcessor` | 인벤토리 생성, 청킹, Map/Reduce 실행, 진행률과 최종 결과 관리 |
| `LargeContextCache` | manifest·청크 요약·Reduce 결과의 원자적 저장, 검증, 재개 |
| `ContextChunker` | 토큰 예산에 맞춘 파일 경계/줄 경계 분할 |
| `LargeContextPrompts` | Map/Reduce 프롬프트의 단일 정의 |
| 기존 `FilePatternMatcher` | 패턴 정규화, `**` 처리, 중복 없는 파일 선택 |
| 기존 assistant | 실제 provider 호출; 대규모 처리 중 컨텍스트 자동 첨부 비활성화 |

권장 신규 파일:

```text
src/large_context_processor.py
src/large_context_cache.py
src/context_chunker.py
src/large_context_prompts.py
tests/test_context_chunker.py
tests/test_large_context_cache.py
tests/test_large_context_processor.py
tests/test_large_context_command.py
```

### 5.2 전체 흐름

```text
/context --large ...
  │
  ├─ 옵션·패턴·질문 파싱
  ├─ FilePatternMatcher로 파일 목록 확정 및 정렬
  ├─ 파일 SHA-256, 크기, 상대 경로 인벤토리 생성
  ├─ 안정적 파일 경계 청킹
  ├─ job_id 계산 및 cache manifest 로드/생성
  │
  ├─ Map [순차]
  │    ├─ 유효 캐시 있음 → 재사용
  │    └─ 없음 → 격리된 LLM 호출 → 즉시 원자적 저장
  │
  ├─ Reduce
  │    ├─ 전체 요약이 예산 이내 → 최종 Reduce 1회
  │    └─ 예산 초과 → 요약 그룹별 중간 Reduce → 반복
  │
  ├─ 최종 응답 캐시 저장
  ├─ 메인 대화 히스토리에 원 질문/최종 답변만 반영
  └─ 결과와 처리 통계 출력
```

### 5.3 다중 호출의 히스토리 격리

Map 및 중간 Reduce 결과를 기존 `assistant.conversation_history`에 누적하면 청크가 진행될수록 요청 크기가 다시 증가한다. 따라서 각 내부 호출은 빈 임시 히스토리에서 실행하고 호출 종료 후 원래 히스토리를 `try/finally`로 복원한다.

규칙:

1. 내부 호출은 `include_context=False`로 실행한다.
2. 내부 호출 직전 메인 히스토리를 보존하고 빈 리스트로 교체한다.
3. 성공·예외·사용자 중단과 관계없이 원래 히스토리를 복원한다.
4. Map 및 중간 Reduce 메시지는 메인 히스토리에 남기지 않는다.
5. 전체 성공 시에만 원래 질문과 최종 답변 한 쌍을 메인 히스토리에 추가한다.
6. v1.1.011은 현재 단일 스레드 REPL을 전제로 순차 실행한다.

이 정책은 대규모 처리의 입력 크기를 청크 예산으로 고정하고 일반 대화를 중간 요약으로 오염시키지 않는다.

---

## 6. 토큰 예산과 청킹

### 6.1 예산 계산

provider별 `ContextBuilder.max_tokens`를 안전한 총 요청 예산으로 재사용한다. 이 값은 모델의 원래 컨텍스트 윈도우가 아니라, `.env.example:9-12`와 `src/token_manager.py:23-26`에서 정의한 **플랫폼별 컨텍스트 윈도우의 75% 안전 상한**이다.

| 플랫폼 | 환경변수 | 기본 안전 상한 | 원래 컨텍스트 윈도우 대비 |
|---|---|---:|---:|
| Claude | `MAX_TOKENS_CLAUDE` | 150,000 | 200,000의 75% |
| GenAI | `MAX_TOKENS_GENAI` | 96,000 | 128,000의 75% |
| Gemini | `MAX_TOKENS_GEMINI` | 786,000 | 약 1,000,000의 75% 수준 |

세 엔트리 포인트는 `.env` 로드 후 `TokenManager.reload_from_env()`를 호출하고, 각 assistant는 해당 플랫폼의 `MAX_TOKENS_*` 값으로 `ContextBuilder`를 생성한다. 따라서 대규모 처리기는 현재 assistant의 `context_builder.max_tokens`를 읽어야 하며 Claude 기본값 또는 `TokenManager.DEFAULT_MAX_TOKENS`를 별도로 사용하면 안 된다.

`request_budget_tokens`에는 **75%를 다시 곱하지 않는다.** 이미 75% 안전 상한이 적용된 값이기 때문이다. 아래 `output_reserve_tokens`, `prompt_reserve_tokens`, `safety_reserve_tokens`는 이 안전 상한 내부에서 출력·프롬프트·문자 기반 토큰 추정 오차를 확보하기 위한 추가 예약이다. 정확한 tokenizer 의존성은 추가하지 않고 기존 `TokenManager.CHARS_PER_TOKEN = 3.5` 추정식을 사용한다.

```text
request_budget_tokens = assistant.context_builder.max_tokens
output_reserve_tokens = min(8192, floor(request_budget_tokens × 0.10))
prompt_reserve_tokens = 4096
safety_reserve_tokens = floor(request_budget_tokens × 0.10)
usable_input_tokens = request_budget_tokens
                      - output_reserve_tokens
                      - prompt_reserve_tokens
                      - safety_reserve_tokens

map_payload_tokens = min(32768, usable_input_tokens)
map_payload_chars  = floor(map_payload_tokens × 3.5)
reduce_payload_chars = floor(usable_input_tokens × 3.5)
```

모든 값은 0보다 커야 한다. `usable_input_tokens < 8192`이면 호출하지 않고 설정 오류를 출력한다.

기본 환경값을 적용한 계산 예시는 다음과 같다.

| 플랫폼 | `request_budget_tokens` | 출력 예약 | 프롬프트 예약 | 안전 예약 | `usable_input_tokens` | Map payload 상한 |
|---|---:|---:|---:|---:|---:|---:|
| Claude | 150,000 | 8,192 | 4,096 | 15,000 | 122,712 | 32,768 |
| GenAI | 96,000 | 8,192 | 4,096 | 9,600 | 74,112 | 32,768 |
| Gemini | 786,000 | 8,192 | 4,096 | 78,600 | 695,112 | 32,768 |

`.env`에서 `MAX_TOKENS_*`를 변경하면 위 고정 예시가 아니라 런타임 값을 같은 식에 대입한다. 환경변수가 없거나 정수가 아니면 `TokenManager.reload_from_env()`의 플랫폼별 기본값을 사용한다. 0 이하 또는 예약량보다 작은 값은 대규모 처리기에서 설정 오류로 거부한다.

### 6.2 파일 경계 우선 청킹

1. 매칭 파일을 정규화된 상대 경로 오름차순으로 정렬한다.
2. 파일 구분자, 상대 경로, 줄 번호 메타데이터까지 payload 크기에 포함한다.
3. 다음 파일을 더하면 예산을 초과할 경우 현재 청크를 확정한다.
4. 동일 파일은 여러 패턴에 매칭되어도 한 번만 포함한다.
5. 읽기 실패 파일은 건너뛰되 manifest에 `read_error`와 오류 유형을 기록한다.

### 6.3 단일 대형 파일 분할

파일 하나가 `map_payload_chars`보다 크면 줄 경계로 분할한다.

- 각 조각은 `path`, `part_index`, `part_count`, `start_line`, `end_line`을 가진다.
- 경계 문맥 보존을 위해 이전 조각의 마지막 20줄을 다음 조각에 겹쳐 넣는다.
- 겹친 줄은 메타데이터에 `overlap_lines`로 표시한다.
- 한 줄 자체가 예산보다 길면 해당 줄을 문자 경계로 분할하되 `line_fragment`를 표시한다.
- 바이너리 또는 `FileManager.read_file()`이 읽을 수 없는 파일은 원문을 강제 변환하지 않는다.

### 6.4 완전성 불변조건

처리 종료 시 다음 식을 검증한다.

```text
matched_files
= completely_mapped_files
 + split_and_completely_mapped_files
 + explicitly_failed_files
```

어떤 파일도 위 세 집합 중 정확히 하나에 속하지 않으면 최종 Reduce를 실행하지 않고 작업을 `incomplete`로 저장한다.

---

## 7. Map–Reduce 프롬프트 계약

### 7.1 Map 단계

각 Map 호출은 다음을 입력으로 받는다.

- 사용자의 원래 질문
- 현재 청크 파일/조각 인벤토리
- 해당 청크 원문
- 출력 스키마

Map 결과는 자유로운 최종 답변이 아니라 다음 항목을 포함한 구조화 Markdown이어야 한다.

```text
## Scope
## Key facts
## Symbols and responsibilities
## Dependencies and relationships
## Risks / unknowns
## Evidence
- relative/path.ext:L10-L24 — 근거 요약
```

요구사항:

- 청크 밖의 파일을 읽었다고 주장하지 않는다.
- 모든 핵심 사실에 상대 경로와 가능한 줄 범위를 붙인다.
- 사용자의 최종 산출물 요청과 관련 없는 세부사항은 축약한다.
- 결론을 내릴 근거가 없으면 `Unknown`으로 기록한다.
- 파일 생성·수정 도구를 호출하지 않는다.

### 7.2 계층형 Reduce

모든 Map 요약과 트리/인벤토리가 `reduce_payload_chars` 이내이면 최종 Reduce를 한 번 실행한다. 초과하면 요약을 예산 단위 그룹으로 묶어 중간 Reduce를 실행하고, 결과가 한 요청에 들어갈 때까지 반복한다.

중간 Reduce는 다음을 보존해야 한다.

- 파일 경로 및 줄 근거
- 상충하는 관찰
- 미분석/읽기 실패 파일 목록
- 사용자 질문과 관련된 모듈 관계
- 하위 요약 ID 목록

중간 Reduce 결과의 캐시 키에는 입력 요약 fingerprint 목록과 Reduce 레벨을 포함한다.

### 7.3 최종 Reduce

최종 Reduce 입력:

1. 사용자의 원래 질문
2. Map 또는 직전 Reduce 요약 전체
3. 매칭 파일 인벤토리와 완전성 통계
4. `-nt`가 없을 때 압축 프로젝트 트리 1회
5. 읽기 실패·불확실성 목록

최종 결과는 사용자의 요청 언어와 산출물 형식을 따른다. `GUIDE.md` 같은 파일 작성을 요구한 경우 기존 assistant의 파일 응답 형식을 유지하되, 중간 Map 단계에서는 파일을 생성하지 않고 최종 Reduce만 산출물을 생성할 수 있다.

---

## 8. 디스크 캐시와 재개

### 8.1 저장 위치

워크스페이스 내부의 다음 경로를 사용한다.

```text
.large_context_cache/
└── <job_id>/
    ├── manifest.json
    ├── maps/
    │   ├── <chunk_fingerprint>.md
    │   └── <chunk_fingerprint>.json
    ├── reduces/
    │   ├── L01-<group_fingerprint>.md
    │   └── L01-<group_fingerprint>.json
    └── final.md
```

`.large_context_cache/`는 `.gitignore`에 추가한다. 캐시에는 소스 원문 전체를 복제하지 않고 요약, 인벤토리, 해시, 상태만 저장한다. 지원 OS에서는 디렉터리 `0700`, 파일 `0600` 권한을 적용한다.

### 8.2 작업 ID

`job_id`는 다음 정규화 값의 SHA-256 앞 12자리다.

```text
workspace 절대경로
provider 종류와 model_id
정렬된 파일 패턴
원래 질문
include_tree 값
청킹/프롬프트 스키마 버전
```

파일 내용 해시는 `job_id`에 넣지 않고 manifest와 청크 fingerprint에 넣는다. 따라서 같은 명령에서 일부 파일이 바뀌어도 작업 디렉터리를 재사용하면서 영향받은 청크만 다시 처리할 수 있다.

### 8.3 Manifest 최소 스키마

```json
{
  "schema_version": 1,
  "job_id": "8f41c2d19a7e",
  "status": "mapping",
  "provider": "claude",
  "model_id": "...",
  "question_sha256": "...",
  "patterns": ["src/**/*.java", "docs/*.md"],
  "include_tree": true,
  "budget": {},
  "files": [],
  "chunks": [],
  "reduce_levels": [],
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "last_error": null
}
```

상태 전이는 다음으로 제한한다.

```text
planned → mapping → reducing → complete
                    ↘ incomplete
각 실행 단계 → interrupted | failed
interrupted | failed | incomplete → mapping 또는 reducing (재개)
```

### 8.4 청크 fingerprint 및 선택적 무효화

Map 청크 fingerprint는 다음 값으로 계산한다.

```text
정렬된 (상대경로, 파일 SHA-256, 시작 줄, 종료 줄) 목록
사용자 질문 SHA-256
provider/model_id
Map 프롬프트 버전
map_payload_tokens
```

재실행 시 fingerprint가 같고 메타데이터 상태가 `complete`이며 요약 파일 해시가 일치할 때만 재사용한다. 파일 변경으로 fingerprint가 달라진 청크와 그 결과를 입력으로 사용한 Reduce 그룹만 무효화한다.

### 8.5 원자적 저장과 손상 복구

- JSON/Markdown은 같은 디렉터리의 임시 파일에 쓴 뒤 `os.replace()`로 교체한다.
- Map 성공 직후 해당 요약과 manifest를 저장한다.
- Reduce 그룹 성공 직후에도 동일하게 체크포인트한다.
- JSON 파싱 실패, 요약 파일 누락, 저장된 SHA-256 불일치는 해당 항목만 `corrupt`로 간주해 재호출한다.
- `KeyboardInterrupt`는 현재 완료된 체크포인트를 보존하고 manifest를 `interrupted`로 갱신한 뒤 상위 REPL로 전달한다.
- API 오류는 현재 청크를 `failed`로 기록하고 전체 작업을 중단한다. 같은 명령 재실행 시 실패 청크부터 자동 재개한다.

### 8.6 완료 결과 재사용

동일 작업이 이미 `complete`이고 모든 입력 파일 fingerprint가 유효하면 LLM을 호출하지 않고 `final.md`를 반환한다. 출력에 `♻️ 완료 캐시 재사용`과 작업 ID를 표시한다.

---

## 9. 오류 처리와 사용자 피드백

| 상황 | 동작 |
|---|---|
| 패턴 매칭 0개 | 호출 없이 오류 출력 |
| 질문 없음 | 기존 멀티라인 입력 사용; 빈 질문이면 중단 |
| 예산 설정이 너무 작음 | 호출 없이 필요한 최소값과 현재값 출력 |
| 파일 읽기 실패 | manifest에 기록하고 나머지 Map 진행 |
| 모든 파일 읽기 실패 | Reduce 없이 `failed` |
| Map API 오류 | 성공 청크 저장 후 작업 중단, 재실행 안내 |
| 캐시 일부 손상 | 손상 항목만 재처리 |
| Reduce API 오류 | Map 결과 보존, 해당 Reduce부터 재개 |
| 파일이 실행 중 변경됨 | 최종 Reduce 전 해시 재검증; 변경 감지 시 영향 청크 재Map |
| Ctrl+C | 체크포인트 보존, `interrupted` 저장, 정상 REPL 복귀 |

진행 출력 예:

```text
[Map 12/37] src/service/A.java ... ✅ 저장
[Map 13/37] docs/guide.md ... ♻️ 캐시 재사용
[Reduce L1 2/5] chunks 9-16 ... ✅ 저장
```

완료 요약:

```text
✅ 대규모 컨텍스트 처리 완료
   파일: 284개 (완료 283, 읽기 실패 1)
   LLM 호출: 41회 (Map 34, Reduce 7)
   캐시 재사용: Map 3, Reduce 1
   작업 ID: 8f41c2d19a7e
```

---

## 10. 기능 요구사항

### 10.1 명령 및 호환성

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-011-001 | `/context`는 선두 옵션 `--large`를 인식한다. | 필수 |
| FR-011-002 | `--large`와 `-nt`/`--no-tree`는 순서와 관계없이 조합할 수 있다. | 필수 |
| FR-011-003 | `--large`가 없으면 v1.0.123 동작과 호출 횟수를 유지한다. | 필수 |
| FR-011-004 | 세 엔트리 포인트는 동일한 파서와 `LargeContextProcessor`를 사용한다. | 필수 |
| FR-011-005 | `--large` 명시 시 별도 확인 없이 다중 호출을 시작한다. | 필수 |

### 10.2 파일 선택과 청킹

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-011-010 | 파일 선택은 `FilePatternMatcher.filter_files()`를 사용한다. | 필수 |
| FR-011-011 | 중복 매칭 파일은 한 번만 처리한다. | 필수 |
| FR-011-012 | 일반 파일은 파일 경계를 보존해 청킹한다. | 필수 |
| FR-011-013 | 단일 초대형 파일은 줄 경계와 20줄 overlap으로 분할한다. | 필수 |
| FR-011-014 | 각 파일은 완료, 분할 완료, 명시적 실패 중 하나로 기록된다. | 필수 |
| FR-011-015 | 최종 Reduce 직전에 파일 해시를 다시 검증한다. | 필수 |
| FR-011-016 | 요청 예산은 현재 assistant에 주입된 플랫폼별 `ContextBuilder.max_tokens`를 사용한다. | 필수 |
| FR-011-017 | `MAX_TOKENS_*`는 이미 75% 안전 상한이므로 요청 예산에 75%를 다시 곱하지 않는다. | 필수 |
| FR-011-018 | `.env`의 유효한 플랫폼별 override는 청킹과 Reduce 예산에 즉시 반영한다. | 필수 |

### 10.3 LLM 파이프라인

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-011-020 | Map 호출은 순차 실행하고 각 호출의 히스토리를 격리한다. | 필수 |
| FR-011-021 | Map 결과는 파일 경로와 가능한 줄 범위 근거를 포함한다. | 필수 |
| FR-011-022 | 요약 총량이 Reduce 예산을 넘으면 계층형 Reduce를 반복한다. | 필수 |
| FR-011-023 | 트리는 Map마다 반복하지 않고 최종 Reduce에 최대 한 번 포함한다. | 필수 |
| FR-011-024 | `-nt`는 최종 Reduce의 트리만 제거하고 파일 인벤토리는 유지한다. | 필수 |
| FR-011-025 | 중간 단계는 파일을 생성·수정하지 않으며 최종 Reduce만 사용자 산출물을 생성한다. | 필수 |
| FR-011-026 | 성공 시 메인 히스토리에는 원 질문과 최종 답변만 추가한다. | 필수 |

### 10.4 캐시와 재개

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-011-030 | 각 Map 및 Reduce 성공 결과를 즉시 디스크에 체크포인트한다. | 필수 |
| FR-011-031 | 같은 명령 재실행 시 유효한 완료 항목을 자동 재사용한다. | 필수 |
| FR-011-032 | 파일 변경 시 영향받은 Map과 종속 Reduce만 무효화한다. | 필수 |
| FR-011-033 | 캐시 파일은 임시 파일과 `os.replace()`로 원자적으로 저장한다. | 필수 |
| FR-011-034 | 캐시 손상은 전체 삭제 없이 손상 항목 단위로 복구한다. | 필수 |
| FR-011-035 | 완료 작업의 유효한 `final.md`는 LLM 호출 없이 재사용한다. | 필수 |
| FR-011-036 | `.large_context_cache/`를 Git 추적 대상에서 제외한다. | 필수 |

---

## 11. 비기능 요구사항

| ID | 요구사항 |
|---|---|
| NFR-011-001 | Python 표준 라이브러리만 사용하며 새 패키지를 추가하지 않는다. |
| NFR-011-002 | 모든 내부 호출의 입력 추정치는 계산된 request budget 이하이어야 한다. |
| NFR-011-003 | 캐시 저장 실패가 소스 파일 또는 기존 캐시 완료 파일을 손상시키면 안 된다. |
| NFR-011-004 | 캐시에는 소스 원문 전체를 별도로 복제하지 않는다. |
| NFR-011-005 | 상대 경로를 사용하고 워크스페이스 밖 파일을 캐시에 기록하지 않는다. |
| NFR-011-006 | 현재 동기식 REPL과 assistant의 가변 상태를 고려해 v1.1.011은 병렬 호출하지 않는다. |
| NFR-011-007 | Map/Reduce 프롬프트 스키마 버전을 manifest와 fingerprint에 포함한다. |
| NFR-011-008 | 로그와 manifest에 API 키, 인증 헤더, 시스템 프롬프트 원문을 저장하지 않는다. |
| NFR-011-009 | Windows와 Linux/WSL에서 경로를 POSIX 상대 경로로 정규화한다. |
| NFR-011-010 | 예산 계산은 Claude 고정값으로 fallback하지 않고 실행 중인 provider의 `MAX_TOKENS_*` 안전 상한을 보존한다. |

---

## 12. 변경 대상

| 파일 | 변경 유형 | 내용 |
|---|---|---|
| `src/large_context_processor.py` | 신규 | Map/Reduce 오케스트레이션, 히스토리 격리, 완전성 검증 |
| `src/large_context_cache.py` | 신규 | manifest, fingerprint, 원자적 저장, 재개 |
| `src/context_chunker.py` | 신규 | 예산 계산, 파일/줄 경계 청킹 |
| `src/large_context_prompts.py` | 신규 | 버전이 지정된 Map/Reduce 프롬프트 |
| `src/cli_input.py` | 수정 | 하나의 호출에서 `--large`와 `-nt` 복수 옵션 파싱 지원 확인/보강 |
| `claude-ai-chat-code.py` | 수정 | `/context --large` 라우팅 |
| `gemini-ai-chat-code.py` | 수정 | 동일 |
| `gen-ai-chat-code.py` | 수정 | 동일 |
| `src/__init__.py` | 수정 | 신규 공개 클래스 export |
| `.gitignore` | 수정 | `.large_context_cache/` 추가 |
| `tests/test_context_chunker.py` | 신규 | 청킹 및 예산 테스트 |
| `tests/test_large_context_cache.py` | 신규 | 캐시·손상·재개 테스트 |
| `tests/test_large_context_processor.py` | 신규 | Map/Reduce·격리·완전성 테스트 |
| `tests/test_large_context_command.py` | 신규 | 옵션 및 3개 엔트리 포인트 계약 테스트 |

기존 `ContextBuilder`의 일반 모드 동작 변경은 본 FSD의 필수 범위가 아니다. 대규모 모드는 별도 processor에서 `FilePatternMatcher`를 사용한다.

---

## 13. 테스트 시나리오

### 13.1 옵션 및 호환성

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| T-011-001 | `--large src/*.py 질문` 파싱 | `large=True`, 패턴과 질문 보존 |
| T-011-002 | `-nt --large [...] 질문` | `large=True`, `no_tree=True` |
| T-011-003 | `--large --no-tree [...] 질문` | T-011-002와 동일 |
| T-011-004 | `--large` 없음 | 기존 `assistant.chat(include_context=True)` 호출 |
| T-011-005 | 알 수 없는 옵션 | LLM 호출 없이 오류 |
| T-011-006 | 세 엔트리 포인트의 옵션·라우팅 계약 | 동일 결과 |

### 13.2 청킹

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| T-011-010 | 여러 소형 파일이 예산 이내 | 한 Map 청크, 파일 경계 유지 |
| T-011-011 | 다음 파일 추가 시 예산 초과 | 다음 청크로 이동, 누락 없음 |
| T-011-012 | 단일 파일이 예산 초과 | 줄 경계 분할, 20줄 overlap |
| T-011-013 | 예산보다 긴 단일 라인 | 문자 분할 및 `line_fragment` 표시 |
| T-011-014 | 다중 패턴 중복 매칭 | 파일 한 번만 포함 |
| T-011-015 | `src/**/*.java` | 중첩 디렉터리 파일 포함 |
| T-011-016 | 파일 읽기 실패 | manifest에 실패 기록, 나머지 진행 |
| T-011-017 | 모든 청크 payload 추정치 검사 | 각 청크가 예산 이하 |

### 13.3 Map–Reduce

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| T-011-020 | Map 3개, 요약이 Reduce 예산 이내 | Map 3회 + 최종 Reduce 1회 |
| T-011-021 | 요약이 Reduce 예산 초과 | 중간 Reduce 후 최종 Reduce |
| T-011-022 | Map 호출 전후 assistant history | 원본과 동일 |
| T-011-023 | 처리 성공 | 메인 history에 질문/최종 답변만 추가 |
| T-011-024 | `--large` 기본 | 트리가 최종 Reduce에 한 번만 포함 |
| T-011-025 | `--large -nt` | 트리 0회, 인벤토리는 포함 |
| T-011-026 | 파일 하나가 어떤 상태에도 속하지 않음 | 최종 Reduce 금지, `incomplete` |
| T-011-027 | Reduce 직전 파일 변경 | 해당 청크 재Map 후 Reduce |

### 13.4 캐시와 재개

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| T-011-030 | Map 5개 중 3번째 후 API 오류 | 1~2번 저장, 작업 `failed` |
| T-011-031 | T-011-030과 같은 명령 재실행 | 1~2번 재사용, 3번부터 호출 |
| T-011-032 | 한 파일 내용 변경 | 해당 fingerprint 청크와 종속 Reduce만 재호출 |
| T-011-033 | Map Markdown 해시 불일치 | 해당 Map만 `corrupt` 처리 후 재호출 |
| T-011-034 | manifest JSON 손상 | 안전한 오류 출력, 원본 소스 무변경 |
| T-011-035 | Reduce 중 오류 후 재실행 | Map 전체 재사용, 미완료 Reduce부터 시작 |
| T-011-036 | 완료 작업 재실행 | LLM 0회, `final.md` 반환 |
| T-011-037 | 저장 중 예외 | 기존 완료 체크포인트 내용 유지 |
| T-011-038 | Ctrl+C | `interrupted` 저장, 다음 실행에서 재개 |

### 13.5 플랫폼별 75% 안전 상한

> **배경**: `.env`의 `MAX_TOKENS_*` 값은 플랫폼 컨텍스트 윈도우의 **75% 안전 상한이 이미 적용된 값**이다.
> 코드 어느 경로에서도 이 값에 75%를 재적용해서는 안 된다.
>
> **발견된 버그 (2026-06-21 수정)**: `TokenManager.auto_trim_history()`가 `token_threshold = int(max_tokens * 0.75)`로
> 계산해 이중 75%를 적용하고 있었다. 실효 트리밍 임계가 56.25% (75%×75%)로 떨어져
> 히스토리가 지나치게 일찍 잘렸다. `token_threshold = max_tokens`로 수정해 단일 75% 상한을 보장한다.

#### T-011-040 ~ T-011-044: LargeContextProcessor 예산 (이중 75% 없음)

`LargeContextProcessor`는 `assistant.context_builder.max_tokens`를 그대로 request budget으로 사용하며
추가 75% 곱셈을 하지 않는다 (FR-011-017). 아래 수치는 기본 `.env` 값 기준이다.

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| T-011-040 | 기본 Claude assistant | request budget 150,000, usable input 122,712 |
| T-011-041 | 기본 GenAI assistant | request budget 96,000, usable input 74,112 |
| T-011-042 | 기본 Gemini assistant | request budget 786,000, usable input 695,112 |
| T-011-043 | `MAX_TOKENS_GENAI=64000` override 후 reload | request budget 64,000; 75% 재적용 없음 |
| T-011-044 | `MAX_TOKENS_CLAUDE=0` 또는 예약량 미만 | LLM 호출 없이 설정 오류 |

#### T-011-045 ~ T-011-049: auto_trim_history 이중 75% 방지 (2026-06-21 추가)

`auto_trim_history()`의 트리밍 임계는 `max_tokens` 그 자체여야 한다. 구버그 기준 임계(0.75×max)와
실제 한도(max) 사이 구간에서 트리밍이 발생하면 안 된다. 검증 코드: `tests/test_tokens_command.py`.

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| T-011-045 | Claude: 히스토리 ≈ 112,501 토큰 (구버그 임계 직상) | **트리밍 없음** — 이중 75% 회귀 방지 |
| T-011-046 | GenAI: 히스토리 ≈ 72,001 토큰 (구버그 임계 직상) | **트리밍 없음** |
| T-011-047 | Gemini: 히스토리 ≈ 589,501 토큰 (구버그 임계 직상) | **트리밍 없음** |
| T-011-048 | 히스토리가 max_tokens 초과 (3개 메시지, MIN_KEEP=2 보장) | 트리밍 발동, 결과 ≤ max_tokens |
| T-011-049 | verbose=True 트리밍 출력 | 출력에 `"한도 초과"` 포함, `"75%"` 미포함 |

**구버그 vs 수정 비교:**

| 플랫폼 | 실제 윈도우 | `.env` 값 (75%) | 구버그 임계 (56.25%) | **수정 후 임계 (75%)** |
|---|---:|---:|---:|---:|
| Claude | 200,000 | 150,000 | 112,500 | **150,000** |
| GenAI | 128,000 | 96,000 | 72,000 | **96,000** |
| Gemini | ~1,048,576 | 786,000 | 589,500 | **786,000** |

### 13.6 회귀

다음 기존 테스트를 반드시 함께 실행한다.

```text
tests/test_context_builder.py
tests/test_context_pattern.py
tests/test_command_parser_options.py
tests/test_assistants_include_tree.py
```

---

## 14. 수용 기준

> **검증일**: 2026-06-21  
> **검증 환경**: Python 3.12.10, pytest 9.1.1, Linux (WSL2)  
> **결과**: 신규 테스트 35개 통과, 회귀 테스트 58개 통과

- [x] 세 CLI에서 `/context --large`가 동일하게 동작한다. _(test_large_context_command: test_all_three_entry_points_use_shared_parser_and_processor)_
- [x] 100개 이상의 테스트 파일을 처리할 때 모든 파일이 완료 또는 명시적 실패로 manifest에 기록된다. _(`_validate_completeness` 불변조건 + test_large_context_processor)_
- [x] 테스트에서 생성된 모든 Map/Reduce 요청의 추정 입력 크기가 예산 이하이다. _(test_rendered_request_overflow_rejected_before_call, `_build_chunk` payload 검증)_
- [x] 기본 환경에서 Claude 150,000, GenAI 96,000, Gemini 786,000이 각각의 request budget으로 선택된다. _(test_context_chunker: test_all_provider_default_safe_caps_are_used_as_request_budgets)_
- [x] request budget에 75%를 다시 곱하지 않으며 출력·프롬프트·추정 오차 예약만 차감한다. _(test_context_chunker: test_uses_safe_cap_without_second_75_percent)_
- [x] `.env`의 플랫폼별 `MAX_TOKENS_*` override가 해당 provider 실행에 반영된다. _(test_large_context_processor: test_budget_change_invalidates_cache_identity)_
- [x] Map 10개 중 5개 완료 후 강제 실패한 작업을 재실행하면 완료된 5개에 대한 LLM 호출이 0회이다. _(test_failed_map_resumes_without_recalling_completed_map)_
- [x] 한 파일 변경 시 변경 파일이 속한 청크와 종속 Reduce만 다시 호출된다. _(test_file_change_is_automatically_remapped_once)_
- [x] 완료된 동일 작업 재실행 시 LLM 호출이 0회이다. _(test_valid_final_cache_avoids_all_llm_calls)_
- [x] 내부 호출의 성공·예외·Ctrl+C 이후에도 기존 assistant history가 복원된다. _(test_history_isolated_tools_disabled_and_final_pair_committed, test_keyboard_interrupt_persists_interrupted_manifest)_
- [x] 기본 대규모 모드에서는 트리가 최종 Reduce에만 한 번 포함된다. _(`process()` 내 `build_file_tree()` 1회 호출 후 `_reduce()`에만 전달)_
- [x] `--large -nt`에서는 트리가 포함되지 않지만 전체 파일 인벤토리는 전달된다. _(`include_tree=False`일 때 `tree=""`, inventory는 항상 렌더링)_
- [x] `--large` 없는 기존 `/context` 테스트가 모두 통과한다. _(회귀 테스트 58개 통과: test_context_builder, test_context_pattern, test_command_parser_options, test_assistants_include_tree)_
- [x] 캐시 및 구현에 외부 패키지가 추가되지 않는다. _(신규 4개 파일 모두 Python 표준 라이브러리만 사용)_

---

## 15. 구현 순서

> **검증일**: 2026-06-21

1. ✅ 옵션 파서 회귀 테스트와 `--large` 조합 테스트를 먼저 추가한다.
   - `tests/test_large_context_command.py`: `test_large_and_no_tree_are_order_independent`, `test_short_large_alias`, `test_normal_context_remains_single_call_mode` 등 5개 테스트
   - `tests/test_command_parser_options.py` 기존 회귀 포함해 11개 통과
2. ✅ `ContextChunker`와 완전성 불변조건 단위 테스트를 작성·구현한다.
   - `src/context_chunker.py`: `ContextBudget`, `ContextChunker`, `FileRecord`, `ChunkPart`, `ContextChunk`
   - `tests/test_context_chunker.py`: 5개 테스트 통과
3. ✅ `LargeContextCache`의 manifest, fingerprint, 원자적 저장, 손상 복구 테스트를 작성·구현한다.
   - `src/large_context_cache.py`: `os.replace()` 원자적 저장, SHA-256 무결성 검증
   - `tests/test_large_context_cache.py`: 3개 테스트 통과
4. ✅ mock assistant로 `LargeContextProcessor`의 Map, 계층 Reduce, 히스토리 격리, 재개를 구현한다.
   - `src/large_context_processor.py`: `_invoke()` try/finally 격리, `_reduce()` 계층 반복, `_validate_completeness()`
   - `tests/test_large_context_processor.py`: 18개 테스트 통과
5. ✅ 세 엔트리 포인트를 동일한 processor에 연결한다.
   - `claude-ai-chat-code.py`, `gemini-ai-chat-code.py`, `gen-ai-chat-code.py` 모두 `LargeContextProcessor` 임포트 및 라우팅
   - `tests/test_large_context_provider_contract.py`: 4개 provider 계약 테스트 통과
6. ✅ `.gitignore`와 공개 export를 갱신한다.
   - `.gitignore`: `.large_context_cache/` 추가 완료
   - `src/__init__.py`: `LargeContextProcessor`, `LargeContextError`, `LargeContextCache`, `ContextChunker`, `ContextBudget`, `build_map_prompt`, `build_reduce_prompt` export 추가 완료
7. ✅ 신규 테스트 후 기존 `/context`, 옵션 파서, assistant tree 테스트를 실행한다.
   - 신규 35개 + 회귀 58개 = **전체 93개 테스트 통과**
8. ✅ 임시 워크스페이스에서 강제 실패·재개와 파일 변경 무효화를 통합 검증한다.
   - `test_failed_map_resumes_without_recalling_completed_map`: Map 실패 재개
   - `test_reduce_failure_resume_reuses_all_maps`: Reduce 실패 재개
   - `test_file_change_is_automatically_remapped_once`: 파일 변경 감지 및 재Map
   - `test_keyboard_interrupt_persists_interrupted_manifest`: Ctrl+C 체크포인트 보존

---

## 16. 위험과 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| Map 요약에서 중요한 세부사항 소실 | 최종 문서 부정확 | 근거 경로/줄 계약, 질문 중심 요약, 계층 Reduce에서 근거 보존 |
| 호출 수와 비용 증가 | 실행 시간·비용 증가 | 실행 전 최소 호출 수 표시, 캐시 재사용, 순차 체크포인트 |
| 대화 히스토리 누적 | 다시 토큰 초과 | 내부 호출 완전 격리, 최종 결과만 history 반영 |
| 실행 중 파일 변경 | 혼합된 시점의 분석 | Reduce 전 SHA-256 재검증 및 영향 청크 재처리 |
| 캐시에 민감 정보 파생 요약 저장 | 로컬 노출 | Git 제외, 원문 미복제, 제한 권한, 인증 정보 저장 금지 |
| 캐시 스키마/프롬프트 변경 | 오래된 결과 오사용 | schema/prompt version을 fingerprint에 포함 |
| assistant 상태 swap 예외 | 일반 채팅 상태 손상 | `try/finally`, 단위 테스트, v1.1.011 순차 실행 제한 |

---

## 17. 후속 개선 후보

- provider별 정확한 tokenizer를 사용할 수 있을 때 추정기 교체
- 읽기 전용 Map 호출의 제한적 병렬화
- 캐시 목록·삭제 명령과 보존 기간 정책
- 사용자가 청크 크기와 출력 예약 토큰을 조정하는 고급 옵션
- 대규모 분석 결과의 검색 가능한 장기 인덱스

본 항목은 v1.1.011 구현 범위가 아니다.

---

## 18. 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v1.1.011 | 2026-06-20 | `/context --large`, 순차 Map–Reduce, 디스크 캐시·자동 재개 설계 최초 작성 |
| v1.1.011 | 2026-06-21 | 구현 완료 검증: 신규 35개 + 회귀 58개 테스트 전체 통과. `src/__init__.py` 신규 클래스 export 추가. 14절 수용 기준 전항목 충족, 15절 구현 순서 8단계 완료 |
| v1.1.011 | 2026-06-21 | `auto_trim_history` 이중 75% 버그 수정: `token_threshold = int(max_tokens × 0.75)` → `token_threshold = max_tokens`. 실효 임계 56.25% → 75%로 정정. `set_max_messages(0)` 허용 버그 동시 수정 (`< 0` → `< 1`). 13.5절 T-011-045~049 및 `tests/test_tokens_command.py` T-A01~A05 추가 (총 105개 테스트 통과) |
