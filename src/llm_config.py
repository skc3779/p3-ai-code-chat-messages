from typing import Dict, Optional

class LLMConfigProvider:
    """
    언어별 권장 파라미터를 제공하는 헬퍼 클래스.
    llm config 설정은 현재 Python, Java, Node.js, C#, SRS, 공통으로 
    구성되어 있습니다.
    """

    # 언어 → 파라미터 매핑 (표에 정의된 값)
    _LANGUAGE_PARAMS = {
        "python": {
            "temperature": 0.22,
            "top_k": 8,
            "top_p": 0.87,
            "repetition_penalty": 1.20,
            "max_new_tokens": 10240,
        },
        "java": {
            "temperature": 0.25,
            "top_k": 10,
            "top_p": 0.90,
            "repetition_penalty": 1.22,
            "max_new_tokens": 10240,
        },
        "node.js": {
            "temperature": 0.25,
            "top_k": 12,
            "top_p": 0.92,
            "repetition_penalty": 1.20,
            "max_new_tokens": 10240,
        },
        "c#": {
            "temperature": 0.30,
            "top_k": 15,
            "top_p": 0.92,
            "repetition_penalty": 1.25,
            "max_new_tokens": 10240,
        },
        "srs": {
            "temperature": 0.20,
            "top_k": 10,
            "top_p": 0.91,
            "repetition_penalty": 1.14,
            "max_new_tokens": 10240,
        },
        "baseline": {
            "temperature": 0.30,
            "top_k": 12,
            "top_p": 0.90,
            "repetition_penalty": 1.20,
            "max_new_tokens": 10240,
        },
    }

    def __init__(self, language: Optional[str] = None):
        """
        초기화 시 언어를 지정하면 이후 `get_config` 호출 시 자동 적용됩니다.
        언어가 지정되지 않으면 `baseline` 설정을 반환합니다.
        """
        self.language = (language or "baseline").lower()

    def set_language(self, language: str) -> None:
        """사용 중인 언어를 변경합니다."""
        self.language = language.lower()

    def get_language(self) -> str:
        return self.language

    def get_config(self) -> Dict:
        """
        현재 언어에 맞는 LLM 파라미터 딕셔너리를 반환합니다.
        지원되지 않는 언어이면 baseline 설정을 반환합니다.
        """
        # 언어 키는 표에 있는 형태와 일치하도록 정규화
        key = self.language
        if key not in self._LANGUAGE_PARAMS:
            # 'node.js' 와 같이 점이 포함된 경우를 대비해 변형을 시도
            alt_key = key.replace(".", "").replace("js", "js")
            key = alt_key if alt_key in self._LANGUAGE_PARAMS else "baseline"

        return self._LANGUAGE_PARAMS.get(key, self._LANGUAGE_PARAMS["baseline"])