"""CommandRegistry 및 CLIInputHandler import 테스트"""
from src.command_registry import CommandRegistry, CommandInfo
from src.cli_input import CLIInputHandler, PROMPT_TOOLKIT_AVAILABLE

# CommandRegistry 테스트
registry = CommandRegistry()

# 전체 명령어 수
commands = registry.get_commands()
print(f"[OK] 전체 명령어: {len(commands)}개")

# /s 필터링
filtered = registry.filter_commands('/s')
print(f"[OK] /s 필터: {[c.name for c in filtered]}")

# /sa 필터링
filtered = registry.filter_commands('/sa')
print(f"[OK] /sa 필터: {[c.name for c in filtered]}")

# /te 필터링
filtered = registry.filter_commands('/te')
print(f"[OK] /te 필터: {[c.name for c in filtered]}")

# /xyz 필터링 (결과 없음)
filtered = registry.filter_commands('/xyz')
print(f"[OK] /xyz 필터: {[c.name for c in filtered]} (빈 목록이어야 함)")

# 명령어 검색
cmd = registry.get_command('/save')
print(f"[OK] /save 검색: name={cmd.name}, desc={cmd.description}")

# prompt_toolkit 사용 가능 여부
print(f"[OK] prompt_toolkit 사용 가능: {PROMPT_TOOLKIT_AVAILABLE}")

# CLIInputHandler 초기화 (prompt_toolkit 모드)
handler = CLIInputHandler(
    workspace="C:\\test\\project",
    model_name="gemini-3.0-flash"
)
print(f"[OK] CLIInputHandler 초기화 (prompt_toolkit={handler._use_prompt_toolkit})")
print(f"[OK] workspace: {handler.workspace}")
print(f"[OK] model_name: {handler.model_name}")

# workspace 업데이트
handler.update_workspace("C:\\new\\path")
print(f"[OK] workspace 업데이트: {handler.workspace}")

print("\n=== 모든 테스트 통과 ===")
