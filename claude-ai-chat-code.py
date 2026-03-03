#!/usr/bin/env python3
"""
Claude Code Assistant - AI 코딩 어시스턴트

모듈화된 버전: src/ 패키지에서 클래스들을 import합니다.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# src/ 패키지에서 클래스 import
from src import (
    FileManager,
    ContextBuilder,
    ClaudeCodeAssistant,
    TokenManager,
    FileWatcher,
    FilePatternMatcher,
    CLIInputHandler,
    DiffViewer,
)


def load_environment():
    """프로젝트 루트에 있는 .env 파일을 읽어 os.environ에 값을 채워 넣는다."""
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path, override=True)


def _supports_color() -> bool:
    """현재 터미널이 ANSI 컬러를 지원하는지 확인하고 Windows에서는 ANSI 모드를 활성화"""
    import sys
    # NO_COLOR 환경변수 확인 (표준 no-color.org 규약)
    if os.environ.get('NO_COLOR'):
        return False
    # stdout이 TTY인지 확인 (파이프 출력 시 색상 코드 제거)
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    # Windows: ANSI 가상 터미널 처리 활성화 시도
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return True


def print_banner():
    """ANSI Art 배너 출력 - >> GEN AI CODE CHAT <<"""
    use_color = _supports_color()

    # ANSI 컬러 정의
    C  = '\033[96m' if use_color else ''   # Bright Cyan
    M  = '\033[95m' if use_color else ''   # Bright Magenta
    G  = '\033[92m' if use_color else ''   # Bright Green
    Y  = '\033[93m' if use_color else ''   # Bright Yellow
    B  = '\033[94m' if use_color else ''   # Blue
    BD = '\033[1m'  if use_color else ''   # Bold
    R  = '\033[0m'  if use_color else ''   # Reset

    banner = f"""
{C}╔══════════════════════════════════════════════════════════════════════════════╗{R}
{C}║{R}                                                                              {C}║{R}
{C}║{R}        {M}{BD} ██████╗ ███████╗███╗   ██╗      █████╗ ██╗{R}                           {C}║{R}
{C}║{R}        {M}{BD}██╔════╝ ██╔════╝████╗  ██║     ██╔══██╗██║{R}                           {C}║{R}
{C}║{R}        {G}{BD}██║  ███╗█████╗  ██╔██╗ ██║     ███████║██║{R}                           {C}║{R}
{C}║{R}        {G}{BD}██║   ██║██╔══╝  ██║╚██╗██║     ██╔══██║██║{R}                           {C}║{R}
{C}║{R}        {Y}{BD}╚██████╔╝███████╗██║ ╚████║     ██║  ██║██║{R}                           {C}║{R}
{C}║{R}        {Y}{BD} ╚═════╝ ╚══════╝╚═╝  ╚═══╝     ╚═╝  ╚═╝╚═╝{R}                           {C}║{R}
{C}║{R}                                                                              {C}║{R}
{C}║{R}         {B}{BD}>> GEN AI CODE CHAT <<!{R}                                              {C}║{R}
{C}║{R}         {G}🤖  AI-Powered Code Assistant  ·  v1.0.051{R}                           {C}║{R}
{C}║{R}                                                                              {C}║{R}
{C}╚══════════════════════════════════════════════════════════════════════════════╝{R}
"""
    print(banner)


def print_menu():
    """메뉴 출력"""
    print("\n" + "=" * 80)
    print("🤖 Claude Code Assistant - AI 코딩 어시스턴트")
    print("=" * 80)
    print("명령어:")
    print("  /files [ext]          - 프로젝트 파일 목록 (예: /files .py .js)")
    print("  /tree                 - 프로젝트 구조 보기")
    print("  /read <pattern>       - 파일 읽기 (예: /read src/*.py)")
    print("  /context <pattern>    - 컨텍스트 포함하여 질문 (예: /context src/*.py)")
    print("  /auto_context         - 파일 단위 자동 반복 처리 (예: /auto_context [original/*.md])")
    print("  /save                 - AI 응답에서 파일 추출 및 저장")
    print("  /workspace [path]     - 작업 디렉토리 변경")
    print("  /stream               - 스트리밍 모드 활성화 (기본값)")
    print("  /nostream             - 논스트리밍 모드 활성화")
    print("  /history              - 대화 히스토리 보기")
    print("  /clear                - 대화 히스토리 초기화")
    print("  /save_history [name]  - 대화 히스토리 파일로 저장")
    print("  /load_history <name>  - 저장된 히스토리 로드")
    print("  /list_history         - 저장된 히스토리 목록")
    print("  /run [lang]           - 마지막 응답의 코드 실행 (python/js/bash)")
    print("  /diff                 - 마지막 응답의 코드 변경사항 Diff 표시")
    print("  /apply                - Diff 내용을 실제 파일에 적용")
    print("  /multiline            - 멀티라인 입력 모드 (종료: /end)")
    print("  /tokens               - 토큰 사용량 확인")
    print("  /shell <cmd>          - 쉘 명령어 실행 (안전 모드)")
    print("  /shell! <cmd>         - 쉘 명령어 실행 (위험 명령 허용)")
    print("  /llm_config <lang>    - 언어별 LLM 파라미터 설정 (예: /llm_config Java)")
    print("  /template <name>      - 시스템 프롬프트 템플릿 변경")
    print("  /template_list        - 사용 가능한 템플릿 목록")
    print("  /template_reset       - 기본 시스템 프롬프트로 복귀")
    print("  /watch <pattern>      - 파일 변경 감시 시작 (예: /watch *.py)")
    print("  /unwatch <pattern>    - 파일 변경 감시 중지")
    print("  /watch_list           - 감시 중인 패턴 목록")
    print("  /help                 - 도움말 보기")
    print("  /quit                 - 종료")
    print("=" * 80)
    print("\n💡 사용 예시:")
    print("  - '/context *.py 이 프로젝트에 README.md를 작성해줘'")
    print("  - '/context src/ 테스트 코드를 작성해줘'")
    print("  - '새로운 API 엔드포인트 /users를 추가해줘'")
    print("\n✨ AI 자동 기능:")
    print("  - 파일 시스템 조작 (읽기/쓰기/목록)")
    print("  - Git 버전 관리 (상태/diff/커밋)")
    print("  - 패키지 의존성 분석 (pip/npm)")
    print("=" * 80)


def main():
    # 환경변수 로드
    load_environment()

    # TokenManager 설정값 반영
    TokenManager.reload_from_env()

    # Claude API 설정값 (환경변수에서 로드)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    CLAUDE_MODEL_ID = os.getenv("CLAUDE_MODEL_ID", "claude-sonnet-4-5")
    CLAUDE_API_ENDPOINT = os.getenv("CLAUDE_API_ENDPOINT", "https://api.anthropic.com")

    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
        print("💡 .env 파일에 ANTHROPIC_API_KEY=your_api_key 를 추가하세요.")
        return

    # 작업 디렉토리 설정
    workspace = os.getcwd()

    # Claude 어시스턴트 초기화
    assistant = ClaudeCodeAssistant(
        api_key=ANTHROPIC_API_KEY,
        model_id=CLAUDE_MODEL_ID,
        endpoint_url=CLAUDE_API_ENDPOINT,
        workspace_dir=workspace
    )

    # 파일 감시자 초기화 (변경 시 자동 컨텍스트 갱신)
    def on_file_changed(filepath: str):
        """파일 변경 콜백: 컨텍스트 자동 갱신"""
        from pathlib import Path
        try:
            rel_path = Path(filepath).relative_to(workspace)
            print(f"\n🔄 파일 변경 감지: {rel_path}")
            # 변경된 파일을 컨텍스트에 추가
            context = assistant.context_builder.build_files_context([Path(filepath)])
            if context:
                history_entry = {"role": "user", "content": f"[File Updated: {rel_path}]\n{context}"}
                assistant.conversation_history.append(history_entry)
                print(f"✅ 컨텍스트 자동 갱신 완료")
        except Exception as e:
            print(f"⚠️  컨텍스트 갱신 실패: {e}")

    file_watcher = FileWatcher(workspace, callback=on_file_changed)

    streaming_mode = True
    last_response = ""
    
    # DiffViewer 초기화
    diff_viewer = DiffViewer()

    # CLI 입력 처리기 초기화 (Gemini CLI 스타일 TUI)
    input_handler = CLIInputHandler(
        workspace=workspace,
        model_name=CLAUDE_MODEL_ID,
        streaming_mode=True
    )

    print_banner()
    print(f"\n📂 현재 작업 디렉토리: {workspace}")
    print(f"🔄 현재 모드: {'스트리밍' if streaming_mode else '논스트리밍'}")


    while True:
        try:
            # 자동 완성이 적용된 입력 받기
            user_input = input_handler.get_input("> ")

            if not user_input:
                continue

            # 명령어 처리
            if user_input.startswith('/'):
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if command == '/quit':
                    print("\n👋 프로그램을 종료합니다.")
                    break

                elif command == '/help':
                    print_menu()

                elif command == '/stream':
                    streaming_mode = True
                    input_handler.update_streaming_mode(True)
                    print("✅ 스트리밍 모드로 변경되었습니다.")

                elif command == '/nostream':
                    streaming_mode = False
                    input_handler.update_streaming_mode(False)
                    print("✅ 논스트리밍 모드로 변경되었습니다.")

                elif command == '/history':
                    if assistant.conversation_history:
                        print("\n📜 대화 히스토리:")
                        for i, msg in enumerate(assistant.conversation_history, 1):
                            role = "👤" if msg.get('role') == 'user' else "🤖"
                            content = str(msg.get('content', ''))
                            if len(content) > 120:
                                preview = content[:120].replace('\n', ' ')
                            else:
                                preview = content
                            print(f"{role} [{i}]: {preview}{'...' if len(content) > 120 else ''}")
                    else:
                        print("📭 대화 히스토리가 비어있습니다.")

                elif command == '/clear':
                    assistant.conversation_history.clear()
                    print("✅ 대화 히스토리가 초기화되었습니다.")

                elif command == '/save_history':
                    filepath = args.strip() if args else None
                    saved_path = assistant.save_history(filepath)
                    print(f"✅ 히스토리 저장됨: {saved_path}")

                elif command == '/load_history':
                    if not args:
                        print("❌ 파일명을 지정하세요. 예: /load_history history_20260125.json")
                        continue
                    if assistant.load_history(args.strip()):
                        print(f"✅ 히스토리 로드됨: {args.strip()}")
                        print(f"   메시지 수: {len(assistant.conversation_history)}")
                    else:
                        print(f"❌ 히스토리 로드 실패: {args.strip()}")

                elif command == '/list_history':
                    files = assistant.list_history()
                    if files:
                        print("\n📋 저장된 히스토리 파일:")
                        for f in files:
                            print(f"   - {f}")
                    else:
                        print("📭 저장된 히스토리 파일이 없습니다.")

                elif command == '/tokens':
                    stats = TokenManager.get_token_stats(
                        assistant.conversation_history,
                        max_tokens=TokenManager.MAX_TOKENS_CLAUDE
                    )
                    print(f"\n📊 토큰 사용량:")
                    print(f"   현재:    {stats['current']:,} 토큰")
                    print(f"   한도:    {stats['max']:,} 토큰 (Claude)")
                    print(f"   사용률:  {stats['usage_percent']}%")
                    print(f"   메시지: {stats['message_count']}개")

                elif command == '/workspace':
                    if args:
                        new_workspace = Path(args).resolve()
                        if assistant.change_workspace(str(new_workspace)):
                            file_watcher.stop()
                            file_watcher = FileWatcher(str(new_workspace), callback=on_file_changed)
                            workspace = str(new_workspace)
                            input_handler.update_workspace(workspace)
                            print(f"✅ 작업 디렉토리 변경: {new_workspace}")
                        else:
                            print(f"❌ 유효하지 않은 디렉토리: {args}")
                    else:
                        print(f"📂 현재 작업 디렉토리: {assistant.file_manager.workspace_dir}")

                elif command == '/files':
                    extensions = args.split() if args else None
                    files = assistant.file_manager.list_files(extensions)

                    print(f"\n📁 파일 목록 (총 {len(files)}개):")
                    for f in files[:50]:
                        info = assistant.file_manager.get_file_info(f)
                        size_kb = info['size'] / 1024
                        print(f"  📄 {info['path']} ({size_kb:.1f}KB, {info['modified']})")

                    if len(files) > 50:
                        print(f"  ... 외 {len(files) - 50}개 파일")

                elif command == '/tree':
                    assistant.file_manager.reload_ignore_patterns()
                    tree = assistant.context_builder.build_file_tree()
                    print(f"\n{tree}")

                elif command == '/read':
                    if not args:
                        print("❌ 파일 패턴을 지정하세요. 예: /read src/*.py")
                        continue

                    pattern_matcher = FilePatternMatcher(assistant.file_manager.workspace_dir)
                    patterns = args.split()
                    all_files = assistant.file_manager.list_files()
                    matched_files = pattern_matcher.filter_files(all_files, patterns)

                    if matched_files:
                        context = assistant.context_builder.build_files_context(matched_files)
                        history_entry = {"role": "user", "content": f"[파일 컨텍스트 로드됨]\n{context}"}
                        assistant.conversation_history.append(history_entry)
                        print(context)
                    else:
                        print(f"❌ 패턴 '{args}'에 해당하는 파일이 없습니다.")

                elif command == '/context':
                    if not args:
                        print("❌ 형식: /context <파일패턴> [질문]")
                        print("💡 질문을 생략하면 멀티라인 입력 모드로 전환됩니다.")
                        print("예: /context src/*.py")
                        print("예: /context src/*.py 이 코드를 리팩토링해줘")
                        print("예: /context [src/*.py, docs/*.md] README.md 파일을 작성해줘")
                        continue

                    file_patterns = []
                    question = ""

                    # [pattern1, pattern2] 형식 확인
                    if args.startswith('['):
                        try:
                            end_idx = args.index(']')
                            patterns_str = args[1:end_idx]
                            file_patterns = [p.strip() for p in patterns_str.split(',') if p.strip()]
                            question = args[end_idx+1:].strip()
                        except ValueError:
                            print("❌ 닫는 대괄호 ']'가 없습니다.")
                            continue
                    else:
                        # 기존 단일 패턴 지원
                        parts = args.split(maxsplit=1)
                        file_patterns = [parts[0]]
                        question = parts[1] if len(parts) >= 2 else ""

                    # 질문이 없는 경우 멀티라인 입력
                    if not question:
                        question = input_handler.get_multiline()
                        if not question.strip():
                            print("❌ 질문을 입력하세요.")
                            continue

                    last_response = assistant.chat(
                        question,
                        streaming=streaming_mode,
                        include_context=True,
                        file_patterns=file_patterns
                    )

                elif command == '/auto_context':
                    if not args:
                        print("❌ 형식: /auto_context <파일패턴> [질문]")
                        print("💡 질문을 생략하면 멀티라인 입력 모드로 전환됩니다.")
                        print("예: /auto_context src/*.py")
                        print("예: /auto_context src/*.py 이 코드를 리팩토링해줘")
                        print("예: /auto_context [src/*.py, docs/*.md] README 작성해줘")
                        continue

                    file_patterns = []
                    question = ""

                    # [pattern1, pattern2] 형식 확인
                    if args.startswith('['):
                        try:
                            end_idx = args.index(']')
                            patterns_str = args[1:end_idx]
                            file_patterns = [p.strip() for p in patterns_str.split(',') if p.strip()]
                            question = args[end_idx+1:].strip()
                        except ValueError:
                            print("❌ 닫는 대괄호 ']'가 없습니다.")
                            continue
                    else:
                        # 단일 패턴 지원
                        parts = args.split(maxsplit=1)
                        file_patterns = [parts[0]]
                        question = parts[1] if len(parts) >= 2 else ""

                    # 질문이 없는 경우 멀티라인 입력
                    if not question:
                        question = input_handler.get_multiline()
                        if not question.strip():
                            print("❌ 질문을 입력하세요.")
                            continue

                    # 파일 매칭
                    pattern_matcher = FilePatternMatcher(assistant.file_manager.workspace_dir)
                    all_files = assistant.file_manager.list_files()
                    matched_files = pattern_matcher.filter_files(all_files, file_patterns)

                    if not matched_files:
                        print(f"❌ 패턴 {file_patterns}에 해당하는 파일이 없습니다.")
                        continue

                    # 매칭 파일 목록 표시
                    print(f"\n📂 매칭된 파일 {len(matched_files)}개:")
                    for i, f in enumerate(matched_files, 1):
                        rel = f.relative_to(assistant.file_manager.workspace_dir)
                        print(f"  {i}. {rel}")

                    # 사용자 확인
                    try:
                        confirm = input("\n▶ 자동 처리를 시작하시겠습니까? (Y/n): ").strip().lower()
                        if confirm == 'n':
                            print("⏭️  취소됨")
                            continue
                    except (EOFError, KeyboardInterrupt):
                        continue

                    # 자동 처리 실행
                    from src.context_processor import ContextProcessor
                    processor = ContextProcessor(
                        assistant=assistant,
                        file_manager=assistant.file_manager,
                        streaming=streaming_mode
                    )
                    processor.process_files(matched_files, question)

                elif command == '/save':
                    if not last_response:
                        print("❌ 저장할 응답이 없습니다.")
                        continue

                    saved_files = assistant.extract_and_save_files(last_response)
                    if saved_files:
                        print(f"\n✅ 총 {len(saved_files)}개 파일이 저장되었습니다.")
                    else:
                        print("\n⚠️  저장된 파일이 없습니다.")
                        print("💡 파일 형식: ```filename:path/to/file.ext")

                elif command == '/run':
                    if not last_response:
                        print("❌ 실행할 코드가 없습니다. 먼저 AI에게 코드 생성을 요청하세요.")
                        continue
                    
                    language = args.strip() if args else 'python'
                    code_blocks = assistant.code_executor.extract_code_from_response(last_response)
                    
                    if not code_blocks:
                        print("❌ 실행 가능한 코드 블록을 찾을 수 없습니다.")
                        continue
                    
                    print(f"\n🔍 {len(code_blocks)}개의 코드 블록을 발견했습니다.")
                    
                    for i, block in enumerate(code_blocks, 1):
                        block_lang = block.get('language', language)
                        filepath = block.get('filepath', '(인라인 코드)')
                        code = block.get('code', '')
                        
                        print(f"\n{'='*60}")
                        print(f"📌 [{i}] {filepath} ({block_lang})")
                        print(f"{'='*60}")
                        
                        preview_lines = code.split('\n')[:3]
                        for line in preview_lines:
                            print(f"   {line}")
                        if len(code.split('\n')) > 3:
                            print(f"   ... ({len(code.split(chr(10)))}줄)")
                        
                        confirm = input(f"\n▶️  이 코드를 실행하시겠습니까? (y/N): ").strip().lower()
                        if confirm != 'y':
                            print("⏭️  건너뛰기")
                            continue
                        
                        print(f"\n🚀 {block_lang} 코드 실행 중...")
                        result = assistant.code_executor.execute(code, block_lang)
                        
                        icon = result.get('icon', '📋')
                        
                        if result.get('success'):
                            print(f"\n{icon} ✅ 실행 성공!")
                            if result.get('stdout'):
                                print(f"\n📤 출력:")
                                print(result['stdout'])
                        else:
                            print(f"\n{icon} ❌ 실행 실패")
                            if result.get('stderr'):
                                print(f"\n🔴 오류:")
                                print(result['stderr'])
                            if result.get('error'):
                                print(f"\n⚠️  {result['error']}")

                elif command == '/multiline':
                    multiline_input = input_handler.get_multiline()

                    if multiline_input:
                        last_response = assistant.chat(multiline_input, streaming=streaming_mode)
                        if '```filename:' in last_response:
                            print("\n💡 응답에 파일이 포함되어 있습니다. /save 명령어로 저장할 수 있습니다.")
                    else:
                        print("⚠️ 입력이 비어있습니다.")

                elif command == '/shell' or command == '/shell!':
                    if not args:
                        print("❌ 실행할 명령어를 입력하세요.")
                        print("💡 예시: /shell pip list")
                        print(f"📝 허용 명령어: {assistant.terminal_executor.get_allowed_commands()}")
                        continue
                    
                    allow_unsafe = command == '/shell!'
                    
                    if allow_unsafe:
                        print("⚠️  위험 모드: 모든 명령어가 허용됩니다.")
                        confirm = input("▶️  정말 실행하시겠습니까? (y/N): ").strip().lower()
                        if confirm != 'y':
                            print("⏭️  취소됨")
                            continue
                    
                    print(f"\n💻 명령어 실행: {args}")
                    result = assistant.terminal_executor.execute(args, allow_unsafe=allow_unsafe)
                    
                    if result.get('success'):
                        print(f"\n✅ 실행 성공 (return code: {result.get('returncode', 0)})")
                        if result.get('stdout'):
                            print(f"\n📤 출력:")
                            print(result['stdout'])
                    else:
                        print(f"\n❌ 실행 실패")
                        if result.get('error'):
                            print(f"   {result['error']}")
                        if result.get('hint'):
                            print(f"💡 {result['hint']}")
                        if result.get('use_unsafe'):
                            print(f"🔓 {result['use_unsafe']}")
                        if result.get('stderr'):
                            print(f"\n🔴 오류 출력:")
                            print(result['stderr'])

                        if result.get('stderr'):
                            print(f"\n🔴 오류 출력:")
                            print(result['stderr'])

                elif command == '/template':
                    if not args:
                        print("❌ 템플릿 이름을 입력하세요. (예: /template code-review)")
                        continue
                    name = args.strip()
                    if assistant.set_system_prompt_from_template(name):
                        print(f"✅ 시스템 프롬프트가 '{name}' 템플릿으로 변경되었습니다.")
                    else:
                        print(f"❌ 템플릿을 찾을 수 없습니다: {name}")
                        print("💡 /template_list 로 목록을 확인하세요.")

                elif command == '/template_list':
                    templates = assistant.list_templates()
                    if templates:
                        print("\n📋 사용 가능한 프롬프트 템플릿:")
                        for t in templates:
                            print(f"   - {t['name']}: {t['description']}")
                    else:
                        print("📭 사용 가능한 템플릿이 없습니다.")
                        print(f"💡 {assistant.file_manager.workspace_dir / '.system-prompts'} 폴더에 YAML 파일을 추가하세요.")

                elif command == '/template_reset':
                    assistant.reset_system_prompt()
                    print("✅ 기본 시스템 프롬프트로 복귀했습니다.")

                elif command == '/watch':
                    if not args:
                        print("❌ 감시할 패턴을 지정하세요. 예: /watch *.py")
                        continue
                    pattern = args.strip()
                    if file_watcher.add_watch(pattern):
                        print(f"✅ 파일 감시 시작: {pattern}")
                        print(f"   현재 감시 패턴: {file_watcher.get_watched_patterns()}")
                    else:
                        print("❌ 파일 감시 추가 실패 (watchdog 설치 필요: pip install watchdog)")

                elif command == '/unwatch':
                    if not args:
                        print("❌ 제거할 패턴을 지정하세요. 예: /unwatch *.py")
                        continue
                    pattern = args.strip()
                    if file_watcher.remove_watch(pattern):
                        print(f"✅ 파일 감시 중지: {pattern}")
                        remaining = file_watcher.get_watched_patterns()
                        if remaining:
                            print(f"   남은 패턴: {remaining}")
                        else:
                            print("   모든 감시가 중지되었습니다.")
                    else:
                        print(f"❌ 해당 패턴을 찾을 수 없습니다: {pattern}")

                elif command == '/diff':
                    if not last_response:
                        print("❌ 비교할 응답이 없습니다. 먼저 AI에게 코드 수정을 요청하세요.")
                        continue
                    
                    suggestions = diff_viewer.extract_code_suggestions(last_response)
                    
                    if not suggestions:
                        print("❌ 응답에서 코드 제안을 찾을 수 없습니다.")
                        print("💡 코드는 ```filename:path/to/file.ext 형식이어야 합니다.")
                        continue
                    
                    print(f"\n🔍 {len(suggestions)}개의 파일 변경 제안을 발견했습니다:\n")
                    
                    for i, suggestion in enumerate(suggestions, 1):
                        filepath = assistant.file_manager.workspace_dir / suggestion['filepath']
                        new_content = suggestion['content']
                        
                        print(f"{'='*70}")
                        print(f"📄 [{i}] {suggestion['filepath']}")
                        print(f"{'='*70}")
                        
                        diff_result, file_exists = diff_viewer.generate_diff_for_file(
                            filepath, new_content, assistant.file_manager
                        )
                        print(diff_result)
                        
                        # 변경 통계 표시
                        if file_exists:
                            original = assistant.file_manager.read_file(filepath) or ""
                            stats = diff_viewer.get_diff_stats(original, new_content)
                            print(diff_viewer.format_stats_display(stats))
                        else:
                            print(f"📝 새 파일: {len(new_content.splitlines())}줄")
                        
                        print()
                    
                    if len(suggestions) == 1:
                        print("💡 /apply 명령어로 변경사항을 적용할 수 있습니다.")
                    else:
                        print("💡 여러 파일이 있습니다. 각 파일을 개별적으로 저장하려면 /save를 사용하세요.")

                elif command == '/apply':
                    success, message = diff_viewer.apply_diff(assistant.file_manager)
                    print(message)
                    if success:
                        print("💡 다른 변경사항이 있다면 /diff로 다시 확인하세요.")

                elif command == '/watch_list':
                    patterns = file_watcher.get_watched_patterns()
                    if patterns:
                        print("\n👁️  감시 중인 패턴:")
                        for p in patterns:
                            print(f"   - {p}")
                        print(f"   상태: {'🟢 실행 중' if file_watcher.is_running() else '🔴 중지됨'}")
                    else:
                        print("📭 감시 중인 패턴이 없습니다.")
                        print("💡 /watch <pattern> 으로 감시를 시작하세요.")

                else:
                    print(f"❌ 알 수 없는 명령어: {command}")
                    print("💡 /help를 입력하여 도움말을 확인하세요.")

                continue

            # 일반 채팅
            last_response = assistant.chat(user_input, streaming=streaming_mode)

            # 파일 저장 가능 여부 확인
            if '```filename:' in last_response:
                print("\n💡 응답에 파일이 포함되어 있습니다. /save 명령어로 저장할 수 있습니다.")

        except KeyboardInterrupt:
            print("\n\n👋 프로그램을 종료합니다.")
            break
        except Exception as e:
            print(f"\n❌ 오류 발생: {str(e)}")
            import traceback
            traceback.print_exc()
            continue


if __name__ == "__main__":
    main()