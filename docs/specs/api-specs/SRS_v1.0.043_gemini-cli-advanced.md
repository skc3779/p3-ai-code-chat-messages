# SRS v1.0.043 - Gemini CLI Advanced Features

**버전**: v1.0.043
**작성일**: 2026-02-13
**대상**: `gemini-ai-chat-code01.py` 및 관련 모듈

## 1. 소개

### 1.1 목적
본 문서는 Gemini CLI의 활용성을 극대화하기 위해 **프로필 관리**, **멀티모달 지원**, **표준 입출력 통합**의 3가지 핵심 기능을 정의합니다. 이는 단순 챗봇을 넘어 전문적인 개발 워크플로우에 통합될 수 있는 도구로 발전하기 위함입니다.

## 2. 핵심 기능 요구사항 (Core Functional Requirements)

### 2.1 프로필 관리 시스템 (Profile Management)

사용자가 작업 목적(코딩, 문서화, 디버깅 등)에 따라 모델 설정과 시스템 프롬프트를 세트로 묶어 관리하고 즉시 전환할 수 있어야 합니다.

#### FR-1: 프로필 구조
- 다음 설정을 포함하는 JSON 구조체로 정의:
  - `name`: 프로필 이름 (Unique ID)
  - `model_id`: 사용할 Gemini 모델 (예: gemini-1.5-pro)
  - `temperature`: 생성 창의성 (0.0 ~ 1.0)
  - `max_output_tokens`: 응답 최대 길이
  - `system_prompt_template`: 사용할 시스템 프롬프트 템플릿명

#### FR-2: 프로필 명령어
- **FR-2.1**: `/profile <name>` - 지정된 프로필로 설정을 즉시 변경 및 적용
- **FR-2.2**: `/profile_save <name>` - 현재 설정을 새로운 프로필로 저장
- **FR-2.3**: `/profile_list` - 저장된 프로필 목록 및 상세 설정 표시
- **FR-2.4**: `/profile_delete <name>` - 프로필 삭제

### 2.2 멀티모달 입력 지원 (Multimodal Input)

Gemini 모델의 강점인 멀티모달 기능을 활용하여 이미지 파일을 입력으로 처리할 수 있어야 합니다.

#### FR-3: 이미지 처리
- **FR-3.1**: `/image <path>` 명령어로 로컬 이미지 파일을 대화 컨텍스트에 추가
- **FR-3.2**: 지원 포맷: PNG, JPEG, WEBP
- **FR-3.3**: 이미지는 Base64로 인코딩되어 API 요청의 `inline_data`로 전송되어야 함
- **FR-3.4**: 여러 이미지를 순차적으로 추가 가능하며, `/clear_images`로 초기화 가능해야 함

#### FR-4: 멀티모달 활용 시나리오
- UI 스크린샷을 기반으로 HTML/CSS 코드 생성 요청
- 에러 로그 스크린샷 분석 요청
- 아키텍처 다이어그램 이미지 해석 요청

### 2.3 표준 입출력 모드 (Standard I/O Pipe Mode)

대화형 모드 외에 쉘 파이프라인의 일부로 동작할 수 있는 비대화형 모드를 지원해야 합니다.

#### FR-5: 파이프 모드 실행
- **FR-5.1**: 실행 인자 `--pipe` 또는 `-p` 지원
- **FR-5.2**: `stdin` (표준 입력)이 존재할 경우 자동으로 내용을 읽어 컨텍스트에 추가
- **FR-5.3**: 인자로 전달된 프롬프트와 stdin 내용을 결합하여 요청 전송

#### FR-6: 순수 출력 (Raw Output)
- **FR-6.1**: 파이프 모드에서는 불필요한 로그(로딩 바, 메뉴, 사용자 입력 표시 등)를 제거
- **FR-6.2**: 오직 AI의 응답 텍스트만 `stdout`으로 출력하여 파일 리다이렉션(`>`)이나 다음 파이프(`|`)로 전달 가능하게 함

## 3. 유스케이스 예시

### 3.1 프로필 전환
```bash
👤 You: /profile code-review
✅ 프로필 변경 완료: code-review
   - Model: gemini-1.5-pro
   - Temp: 0.2
   - System: Code Reviewer
```

### 3.2 이미지 분석
```bash
👤 You: /image ./screenshots/error_dialog.png
✅ 이미지 추가됨: error_dialog.png

👤 You: 이 에러가 발생하는 원인을 분석해줘
🤖 AI: 스크린샷의 에러 메시지는 NullReferenceException을 보여주고 있습니다...
```

### 3.3 파이프라인 연동 (Git Diff 리뷰)
```bash
$ git diff | python gemini-ai-chat-code01.py --pipe "이 변경사항을 리뷰하고 잠재적 버그를 찾아줘" > review_report.md
```

## 4. 제약 사항

- **C-1**: 이미지 처리는 `Pillow` 라이브러리를 사용하지 않고 표준 라이브러리만으로 구현하거나, 필수적인 경우에만 최소한의 의존성을 추가한다.
- **C-2**: 프로필 데이터는 `profiles.json` 파일에 영구 저장되어야 한다.
- **C-3**: 파이프 모드는 `argparse`를 사용하여 CLI 인자를 처리해야 한다.

## 5. 승인

- [x] 기존 기능 분석 완료
- [x] 타사 CLI 기능 비교 완료
- [x] 핵심 기능 3가지 제안 완료
