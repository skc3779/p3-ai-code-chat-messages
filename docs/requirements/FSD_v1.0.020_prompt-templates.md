# FSD: 프롬프트 템플릿 시스템 (P3-01)

> **문서 버전**: v1.0.020  
> **작성일**: 2026-01-25  
> **상태**: ✅ Implemented  
> **관련 SRS**: SRS_Claude_Code_Assistant_Improvements_v1.0.016.md

---

## 1. 개요

### 1.1 목적
하드코딩된 시스템 프롬프트 대신, 상황별(코드 리뷰, 버그 수정, 문서 작성 등)로 최적화된 프롬프트 템플릿을 선택하여 사용할 수 있도록 기능을 개선합니다.

### 1.2 현재 문제
* 시스템 프롬프트가 소스 코드에 고정되어 있음.
* 목적에 따라 프롬프트를 변경하려면 코드를 수정해야 함.

---

## 2. 기능 요구사항

### 2.1 템플릿 관리
* `.system-prompts/` 디렉토리에 YAML 형식으로 템플릿 파일 저장.
* 각 템플릿은 이름, 설명, 시스템 프롬프트 내용을 포함.

### 2.2 사용자 명령어
```bash
/template <name>      # 특정 템플릿 적용 (예: /template code-review)
/template_list        # 사용 가능한 템플릿 목록 표시
/template_reset       # 기본 프롬프트로 복귀
```

---

## 3. 기술 설계

### 3.1 템플릿 파일 구조 (예시)
```yaml
# .system-prompts/code-review.yaml
name: code-review
description: 시니어 개발자 관점의 코드 리뷰
system_prompt: |
  당신은 엄격한 시니어 개발자입니다.
  다음 기준으로 코드를 리뷰하세요:
  1. 버그 가능성
  2. 성능 이슈
  3. 가독성 및 명명 규칙
```

### 3.2 구현 설계
* **공통 모듈**: `src/template_manager.py` (신규)
    * `TemplateManager` 클래스: YAML 파일 로딩, 파싱, 캐싱 담당.
* **통합 포인트**:
    * `ClaudeCodeAssistant`: `__init__`에서 `TemplateManager` 초기화, 시스템 프롬프트 설정 메서드 추가.
    * `GenAICodeAssistant`: `__init__`에서 `TemplateManager` 초기화, LLM 요청 시 시스템 프롬프트 주입 로직 수정.
    * 두 어시스턴트 모두 `/template` 명령어를 통해 런타임에 프롬프트 교체 가능.

### 3.3 템플릿 파일 예시
```yaml
# .system-prompts/code-review.yaml
name: code-review
description: 코드 리뷰 모드
# Claude용 프롬프트
claude_system_prompt: |
  ...
# GenAI용 프롬프트 (옵션, 없으면 공용 사용)
genai_system_prompt: |
  ...
```
