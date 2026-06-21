# task_fsd.md (파일 생성 후 아래 내용 입력)

## 🎯 목표 (Objective)
CLI 명령어 `/context` 사용 시 발생하는 '대규모 파일 토큰 오버플로우' 문제를 해결하기 위한 아키텍처를 설계하고, `docs/requirements/FSD_v1.1.011_context-large-file-handling.md` 문서를 작성해 주세요.

## 📂 참조해야 할 파일 (Context Files)
아래 파일들을 먼저 읽고 현재 구현 상태와 기존 요구사항을 파악하세요.
1. 파이썬 스크립트: `claude-ai-chat-code.py`, `gemini-ai-chat-code.py`, `gen-ai-chat-code.py`
2. 기존 FSD 문서: `docs/requirements/FSD_v1.0.068_context-multi-pattern-test.md`, `docs/requirements/FSD_v1.0.123_auto-context-quality-check-and-context-no-tree.md`

## 🚨 해결해야 할 문제점 (Problem Statement)
현재 `/context -nt [src/**/*.java, docs/*.md] 상세한 프로젝트 분석 가이드 파일 만들어줘.` 처럼 패턴에 맞는 파일이 수백 개인 경우, 파일 내용을 LLM에 한 번에 모두 전달하여 **토큰 오버플로우(Token Overflow)**가 발생합니다. 이로 인해 분석 및 GUIDE.md 파일 작성이 불가능한 상태입니다.  
`/context [옵션...] <파일패턴> [질문]` 중 옵션에 `--no-tree` 추가하면 트리 구조를 표시하지 않고 파일 내용을 LLM에 전달하게 된다. 이로 인해 장점은 토큰 용량을 조금 줄일 수 있지만, 전체 파일 구조를 LLM에 전달할 수 없다는 단점이 있다.

```
/context [src/**/*.java, docs/*.md] 상세한 프로젝트 분석 가이드 파일 만들어줘.
/context -nt [src/**/*.java, docs/*.md] 상세한 프로젝트 분석 가이드 파일 만들어줘.
```


## 📋 작업 지시 (Instructions)
1. **분석 및 해결책 모색**: 위 참조 파일들을 분석하여 CLI가 이 문제를 어떻게 회피하고 처리해야 할지(예: Chunking, Map-Reduce, 요약 후 전달, 트리 구조만 먼저 전달 등) 최적의 설계 방안을 마련하세요.
2. **역질문 필수 (Ask First)**: FSD 문서를 작성하기 전에, 제가 생각하는 방향성이나 시스템 제약사항에 대해 반드시 2~3가지 핵심 질문을 먼저 던져주세요. 
3. **FSD 작성**: 제 답변이 완료되면, 논의된 해결책을 바탕으로 `docs/requirements/FSD_v1.1.011_context-large-file-handling.md` 문서를 작성해 주세요.

