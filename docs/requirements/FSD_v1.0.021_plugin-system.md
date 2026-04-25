# FSD: 플러그인 아키텍처 (P3-02)

> **문서 버전**: v1.0.021  
> **작성일**: 2026-01-25  
> **상태**: Draft  
> **관련 SRS**: SRS_Claude_Code_Assistant_Improvements_v1.0.016.md

---

## 1. 개요

### 1.1 목적
핵심 코드를 수정하지 않고도 외부 기능을 쉽게 추가하고 확장할 수 있는 플러그인 아키텍처를 도입합니다.

### 1.2 현재 문제
* 새로운 기능(새 명령어, 새 도구 등)을 추가하려면 핵심 클래스(`ClaudeCodeAssistant` 또는 `GenAICodeAssistant`)를 직접 수정해야 함.
* 코드가 비대해지고 유지보수가 어려워짐.

---

## 2. 기능 요구사항

### 2.1 플러그인 로딩
* `plugins/` 디렉토리 내의 Python 모듈을 동적으로 로드.
* 플러그인은 커스텀 명령어(`/command`)와 커스텀 도구(Tool)를 등록할 수 있음.

### 2.2 플러그인 인터페이스
* `Plugin` 기본 클래스 정의 (setup, teardown 메서드 등).
* 이벤트 훅 제공 (메시지 수신 전/후, 응답 생성 후 등).

---

## 3. 기술 설계

### 3.1 구조
```python
class PluginBase:
    def register_commands(self, command_registry): pass
    def register_tools(self, tool_registry): pass

# 동적 로딩
import importlib 
# plugins 폴더 스캔 후 load_module 실행
```

### 3.1 구조
```python
# src/plugin_base.py
class PluginBase:
    def on_init(self, assistant: object): 
        """플러그인 초기화 시 호출 (assistant는 ClaudeCodeAssistant 또는 GenAICodeAssistant)"""
        pass
        
    def register_commands(self) -> Dict[str, Callable]: 
        """커스텀 명령어 등록"""
        return {}

    def register_tools(self) -> List[Dict]: 
        """커스텀 도구 정의 (JSON 스키마) 등록"""
        return []
```

### 3.2 통합 설계
* **공통 모듈**: `src/plugin_manager.py`
    * 플러그인 로드, 유효성 검사, 라이프사이클 관리.
* **적용 대상**:
    * `claude-ai-chat-code01.py`: `ClaudeCodeAssistant`에 플러그인 매니저 연동.
    * `gen-ai-chat-code01.py`: `GenAICodeAssistant`에 플러그인 매니저 연동.
    * 두 실행 파일의 `main()` 함수에서 플러그인을 로드하고 초기화해야 함.

---

## 4. 검증 계획
* 단일 플러그인(예: `hello_world`)을 작성하여 `ClaudeCodeAssistant`와 `GenAICodeAssistant` 양쪽에서 모두 `/hello` 명령어가 동작하는지 확인.
