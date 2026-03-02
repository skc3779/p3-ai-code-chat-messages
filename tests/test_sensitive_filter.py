"""
SensitiveWordFilter 단위 테스트

FSD v1.0.058 테스트 케이스:
- TC-058-001: 민감 단어 감지
- TC-058-002: 소문자 치환/복원
- TC-058-003: 대문자 치환/복원
- TC-058-004: Title Case 치환/복원
- TC-058-005: 혼합 대소문자 (문장 내)
- TC-058-006: contents 배열 치환
- TC-058-007: 민감 단어가 없는 경우 (변경 없음)
- TC-058-008: 복원의 정확성 (mask → unmask 왕복)
- TC-058-009: 여러 민감 단어가 동시에 포함된 경우
- TC-058-010: 단어 내부 부분 매칭 처리
"""

import unittest
from src.sensitive_filter import SensitiveWordFilter


class TestSensitiveWordFilter(unittest.TestCase):
    """SensitiveWordFilter 단위 테스트"""

    def setUp(self):
        self.filter = SensitiveWordFilter()

    # ── TC-058-001: 민감 단어 감지 ──

    def test_has_sensitive_words_true(self):
        """민감 단어가 있으면 True 반환"""
        self.assertTrue(self.filter.has_sensitive_words("Enter your password here"))
        self.assertTrue(self.filter.has_sensitive_words("API_KEY=abc123"))
        self.assertTrue(self.filter.has_sensitive_words("my secret value"))
        self.assertTrue(self.filter.has_sensitive_words("Bearer token xyz"))
        self.assertTrue(self.filter.has_sensitive_words("user credential info"))

    def test_has_sensitive_words_false(self):
        """민감 단어가 없으면 False 반환"""
        self.assertFalse(self.filter.has_sensitive_words("Hello world"))
        self.assertFalse(self.filter.has_sensitive_words("This is a normal message"))
        self.assertFalse(self.filter.has_sensitive_words(""))

    def test_get_detected_words(self):
        """감지된 민감 단어 목록을 반환"""
        text = "Set password and secret for your api_key"
        detected = self.filter.get_detected_words(text)
        self.assertIn("password", detected)
        self.assertIn("secret", detected)
        self.assertIn("api_key", detected)

    # ── TC-058-002: 소문자 치환/복원 ──

    def test_mask_lowercase_password(self):
        """소문자 password -> p1assw1ord"""
        result = self.filter.mask("Enter your password here")
        self.assertIn("p1assw1ord", result)
        self.assertNotIn("password", result)

    def test_mask_lowercase_secret(self):
        """소문자 secret -> s1ecr1et"""
        result = self.filter.mask("my secret value")
        self.assertIn("s1ecr1et", result)
        self.assertNotIn("secret", result)

    def test_mask_lowercase_api_key(self):
        """소문자 api_key -> a1pi_k1ey"""
        result = self.filter.mask("your api_key is")
        self.assertIn("a1pi_k1ey", result)
        self.assertNotIn("api_key", result)

    def test_mask_lowercase_apikey(self):
        """소문자 apikey -> a1pike1y"""
        result = self.filter.mask("the apikey value")
        self.assertIn("a1pike1y", result)
        self.assertNotIn("apikey", result)

    def test_mask_lowercase_token(self):
        """소문자 token -> t1oken"""
        result = self.filter.mask("bearer token xyz")
        self.assertIn("t1oken", result)
        self.assertNotIn("token", result)

    def test_mask_lowercase_credential(self):
        """소문자 credential -> c1red1ent1al"""
        result = self.filter.mask("user credential info")
        self.assertIn("c1red1ent1al", result)
        self.assertNotIn("credential", result)

    # ── TC-058-003: 대문자 치환/복원 ──

    def test_mask_uppercase_password(self):
        """대문자 PASSWORD -> P1ASSW1ORD"""
        result = self.filter.mask("Enter your PASSWORD here")
        self.assertIn("P1ASSW1ORD", result)
        self.assertNotIn("PASSWORD", result)

    def test_mask_uppercase_secret(self):
        """대문자 SECRET -> S1ECR1ET"""
        result = self.filter.mask("MY SECRET VALUE")
        self.assertIn("S1ECR1ET", result)
        self.assertNotIn("SECRET", result)

    def test_mask_uppercase_credential(self):
        """대문자 CREDENTIAL -> C1RED1ENT1AL"""
        result = self.filter.mask("USER CREDENTIAL INFO")
        self.assertIn("C1RED1ENT1AL", result)
        self.assertNotIn("CREDENTIAL", result)

    def test_mask_uppercase_token(self):
        """대문자 TOKEN -> T1OKEN"""
        result = self.filter.mask("BEARER TOKEN XYZ")
        self.assertIn("T1OKEN", result)
        self.assertNotIn("TOKEN", result)

    # ── TC-058-004: Title Case 치환/복원 ──

    def test_mask_titlecase_password(self):
        """Title Case Password -> P1assw1ord"""
        result = self.filter.mask("Enter your Password here")
        self.assertIn("P1assw1ord", result)
        self.assertNotIn("Password", result)

    def test_mask_titlecase_secret(self):
        """Title Case Secret -> S1ecr1et"""
        result = self.filter.mask("My Secret value")
        self.assertIn("S1ecr1et", result)
        self.assertNotIn("Secret", result)

    def test_mask_titlecase_credential(self):
        """Title Case Credential -> C1red1ent1al"""
        result = self.filter.mask("User Credential Info")
        self.assertIn("C1red1ent1al", result)
        self.assertNotIn("Credential", result)

    # ── TC-058-005: 혼합 대소문자 문장 ──

    def test_mask_mixed_case_sentence(self):
        """여러 대소문자 조합이 혼합된 문장"""
        text = "Set password, SECRET, and Token for api_key"
        result = self.filter.mask(text)
        self.assertIn("p1assw1ord", result)
        self.assertIn("S1ECR1ET", result)
        self.assertIn("T1oken", result)
        self.assertIn("a1pi_k1ey", result)

    # ── TC-058-006: contents 배열 치환 ──

    def test_mask_contents_list(self):
        """문자열 리스트 각 항목의 민감 단어 치환"""
        contents = [
            "[User Context]\nmy password is abc",
            "[Assistant Context]\nSet your SECRET in config",
            "normal text without sensitive words",
        ]
        result = self.filter.mask_contents(contents)
        self.assertIn("p1assw1ord", result[0])
        self.assertIn("S1ECR1ET", result[1])
        self.assertEqual("normal text without sensitive words", result[2])

    def test_mask_contents_empty_list(self):
        """빈 리스트"""
        self.assertEqual([], self.filter.mask_contents([]))

    # ── TC-058-007: 민감 단어 없는 경우 ──

    def test_mask_no_sensitive_words(self):
        """민감 단어가 없으면 원본 그대로 반환"""
        text = "Hello, this is a normal message about coding."
        self.assertEqual(text, self.filter.mask(text))

    def test_unmask_no_masked_words(self):
        """치환된 단어가 없으면 원본 그대로 반환"""
        text = "Hello, this is a normal response."
        self.assertEqual(text, self.filter.unmask(text))

    # ── TC-058-008: 왕복 (mask → unmask) 정확성 ──

    def test_roundtrip_lowercase(self):
        """소문자 민감 단어 왕복 확인"""
        original = "Set password and secret for token"
        masked = self.filter.mask(original)
        restored = self.filter.unmask(masked)
        self.assertEqual(original, restored)

    def test_roundtrip_uppercase(self):
        """대문자 민감 단어 왕복 확인"""
        original = "SET PASSWORD AND SECRET FOR TOKEN"
        masked = self.filter.mask(original)
        restored = self.filter.unmask(masked)
        self.assertEqual(original, restored)

    def test_roundtrip_titlecase(self):
        """Title Case 민감 단어 왕복 확인"""
        original = "Enter Password and Secret for Token"
        masked = self.filter.mask(original)
        restored = self.filter.unmask(masked)
        self.assertEqual(original, restored)

    def test_roundtrip_mixed(self):
        """혼합 대소문자 왕복 확인"""
        original = "password PASSWORD Password secret SECRET Secret token TOKEN Token credential CREDENTIAL Credential api_key apikey"
        masked = self.filter.mask(original)
        restored = self.filter.unmask(masked)
        self.assertEqual(original, restored)

    def test_roundtrip_multiline(self):
        """멀티라인 텍스트 왕복 확인"""
        original = """DB_PASSWORD=mypass123
API_SECRET=abc
CLIENT_TOKEN=xyz
USER_CREDENTIAL=admin"""
        masked = self.filter.mask(original)
        # 치환이 제대로 적용되었는지 확인
        self.assertNotIn("PASSWORD", masked)
        self.assertNotIn("SECRET", masked)
        self.assertNotIn("TOKEN", masked)
        self.assertNotIn("CREDENTIAL", masked)
        # 복원 확인
        restored = self.filter.unmask(masked)
        self.assertEqual(original, restored)

    # ── TC-058-009: 여러 민감 단어 동시 포함 ──

    def test_multiple_same_word(self):
        """같은 민감 단어가 여러 번 등장"""
        text = "password1 and password2 and PASSWORD3"
        result = self.filter.mask(text)
        self.assertEqual(result.count("p1assw1ord"), 2)
        self.assertEqual(result.count("P1ASSW1ORD"), 1)

    def test_all_sensitive_words_at_once(self):
        """모든 민감 단어가 한 문장에 등장"""
        text = "password secret api_key apikey token credential"
        result = self.filter.mask(text)
        self.assertIn("p1assw1ord", result)
        self.assertIn("s1ecr1et", result)
        self.assertIn("a1pi_k1ey", result)
        self.assertIn("a1pike1y", result)
        self.assertIn("t1oken", result)
        self.assertIn("c1red1ent1al", result)

    # ── TC-058-010: 코드 컨텍스트 내 민감 단어 ──

    def test_mask_code_context(self):
        """실제 코드 블록 내 민감 단어 치환"""
        code = """def get_config():
    password = os.getenv("DB_PASSWORD")
    api_key = os.getenv("API_KEY")
    secret = os.getenv("CLIENT_SECRET")
    return {"password": password, "api_key": api_key}"""
        result = self.filter.mask(code)
        self.assertNotIn("password", result.lower())
        self.assertNotIn("secret", result.lower())
        self.assertNotIn("api_key", result.lower())

    def test_mask_system_prompt(self):
        """시스템 프롬프트 치환"""
        prompt = "You are an assistant. Never expose user password or secret."
        result = self.filter.mask_system_prompt(prompt)
        self.assertNotIn("password", result)
        self.assertNotIn("secret", result)

    def test_mask_system_prompt_empty(self):
        """빈 시스템 프롬프트는 그대로"""
        self.assertEqual("", self.filter.mask_system_prompt(""))
        self.assertIsNone(self.filter.mask_system_prompt(None))

    # ── TC-058-011: 엣지 케이스 ──

    def test_empty_string(self):
        """빈 문자열 처리"""
        self.assertEqual("", self.filter.mask(""))
        self.assertEqual("", self.filter.unmask(""))

    def test_apply_case_helper(self):
        """_apply_case 헬퍼 메서드 직접 테스트"""
        # 모두 대문자
        self.assertEqual("P1ASSW1ORD", SensitiveWordFilter._apply_case("PASSWORD", "p1assw1ord"))
        # Title Case
        self.assertEqual("P1assw1ord", SensitiveWordFilter._apply_case("Password", "p1assw1ord"))
        # 소문자
        self.assertEqual("p1assw1ord", SensitiveWordFilter._apply_case("password", "p1assw1ord"))

    def test_unmask_response_with_code(self):
        """AI 응답 내 코드에서 치환어 복원"""
        response = """Here's your config:
```python
db_p1assw1ord = "secret_value"
a1pi_k1ey = "key_value"
```"""
        result = self.filter.unmask(response)
        self.assertIn("db_password", result)
        self.assertIn("api_key", result)


if __name__ == "__main__":
    unittest.main()
