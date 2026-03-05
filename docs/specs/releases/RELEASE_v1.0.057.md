# RELEASE v1.0.057

## 릴리즈 정보
- **버전:** v1.0.057
- **배포일:** 2026-03-02

## 주요 변경 사항
- **메시지 컨텐츠 타입 유연성 강화:** OpenCode/AI SDK 등에서 일반 문자열이 아닌 멀티모달 컨텐츠 파트의 리스트 배열을 보내올 경우, Pydantic 모델의 `Input should be a valid string` 오류를 내뿜는 버그를 수정했습니다. 리스트 객체를 문자열로 안전하게 변환하여 파싱하도록 로직이 개선되었습니다.

## 관련 문서
- `BUG_v1.0.057_genai-content-string-validation.md`
