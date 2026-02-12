#!/usr/bin/env python3
"""
Gemini Code Assistant - AI 코딩 어시스턴트

모듈화된 버전: src/ 패키지에서 클래스들을 import합니다.
Google Gemini API를 REST API로 직접 호출합니다.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# src/ 패키지에서 클래스 import
from src import (
    FileManager,
    ContextBuilder,
    TokenManager,
    FileWatcher,
    FilePatternMatcher,
    CLIInputHandler,
    DiffViewer,
)
from src.gemini_assistant import GeminiCodeAssistant


def load_environment():
    """프로젝트 루트에 있는 .env 파일을 읽어 os.environ에 값을 채워 넣는다."""
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path, override=True)


def print_menu():
    """메뉴 출력"""
    print("\n" + "=" * 80)
    print("🤖 Gemini Code Assistant - AI 코딩 어시스턴트")
    print("=" * 80)
    print("명령어:")
    print("  /files [ext]        - 프로젝트 파일 목록 (예: /files .py .js)")
    print("  /tree               - 프로젝트 구조 보기")
    print("  /read <pattern>     - 파일 읽기 (예: /read src/*.py)")
    print("  /context <pattern>  - 컨텍스트 포함하여 질문 (예: /context src/*.py)")
    print("  /save               - AI 응답에서 파일 추출 및 저장")
    print("  /workspace [path]   - 작업 디렉토리 변경")
    print("  /stream             - 스트리밍 모드 활성화 (기본값)")
    print("  /nostream           - 논스트리밍 모드 활성화")
    print("  /history            - 대화 히스토리 보기")
    print("  /clear              - 대화 히스토리 초기화")
    print("  /save_history [name]- 대화 히스토리 파일로 저장")
    print("  /load_history <name>- 저장된 히스토리 로드")
    print("  /list_history       - 저장된 히스토리 목록")
    print("  /run [lang]         - 마지막 응답의 코드 실행 (python/js/bash)")
    print("  /diff               - 마지막 응답의 코드 변경사항 Diff 표시")
    print("  /apply              - Diff 내용을 실제 파일에 적용")
    print("  /multiline          - 멀티라인 입력 모드 (종료: /end)")
    print("  /tokens             - 토큰 사용량 확인")
    print("  /shell <cmd>        - 쉘 명령어 실행 (안전 모드)")
    print("  /shell! <cmd>       - 쉘 명령어 실행 (위험 명령 허용)")
    print("  /template <name>    - 시스템 프롬프트 템플릿 변경")
    print("  /template_list      - 사용 가능한 템플릿 목록")
    print("  /template_reset     - 기본 시스템 프롬프트로 복귀")
    print("  /watch <pattern>    - 파일 변경 감시 시작 (예: /watch *.py)")
    print("  /unwatch <pattern>  - 파일 변경 감시 중지")
    print("  /watch_list         - 감시 중인 패턴 목록")
    print("  /help               - 도움말 보기")
    print("  /quit               - 종료")
    print("=" * 80)
    print("=" * 80)
    print("\n💡 사용 예시:")
    print("  - '/context *.py 이 프로젝트에 README.md를 작성해줘'")
    print("  - '/context src/ 테스트 코드를 작성해줘'")
    print("  - '새로운 API 엔드포인트 /users를 추가해줘'")
    print("=" * 80)


def main():
    # 환경변수 로드
    load_environment()

    # Gemini API 설정값 (환경변수에서 로드)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL_ID = os.getenv("GEMINI_MODEL_ID", "gemini-3.0-flash")
    GEMINI_API_ENDPOINT = os.getenv("GEMINI_API_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta")

    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("💡 .env 파일에 GEMINI_API_KEY=your_api_key 를 추가하세요.")
        return

    # 작업 디렉토리 설정
    workspace = os.getcwd()

    # Gemini 어시스턴트 초기화
    assistant = GeminiCodeAssistant(
        api_key=GEMINI_API_KEY,
        model_id=GEMINI_MODEL_ID,
        endpoint_url=GEMINI_API_ENDPOINT,
        workspace_dir=workspace
    )

    # DiffViewer 초기화
    diff_viewer = DiffViewer()

    # CLI 입력 핸들러 초기화
    cli_handler = CLIInputHandler()

    # FileWatcher 초기화
    file_watcher = FileWatcher(workspace)

    # 메뉴 출력
    print_menu()
    print(f"\n📂 작업 디렉토리: {workspace}")
    print(f"🤖 모델: {GEMINI_MODEL_ID}")

    streaming = True
    last_response = ""

    while True:
        try:
            user_input = cli_handler.get_input("👤 You: ")

            if not user_input:
                continue

            # 멀티라인 모드 처리
            if user_input.lower() == '/multiline':
                print("📝 멀티라인 입력 모드 (/end로 종료):")
                lines = []
                while True:
                    line = input("... ")
                    if line.lower() == '/end':
                        break
                    lines.append(line)
                user_input = '\n'.join(lines)
                if not user_input:
                    continue

            # 명령어 처리
            if user_input.startswith('/'):
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if command == '/quit':
                    file_watcher.stop()
                    print("👋 종료합니다.")
                    break

                elif command == '/help':
                    print_menu()

                elif command == '/files':
                    extensions = args.split() if args else None
                    files = assistant.file_manager.list_files(extensions=extensions)
                    print(f"\n📁 파일 목록 ({len(files)}개):")
                    for f in files[:50]:
                        print(f"  - {f.relative_to(assistant.file_manager.workspace_dir)}")
                    if len(files) > 50:
                        print(f"  ... 외 {len(files) - 50}개")

                elif command == '/tree':
                    tree = assistant.context_builder.build_file_tree()
                    print(f"\n🌳 프로젝트 구조:\n{tree}")

                elif command == '/read':
                    if not args:
                        print("❌ 사용법: /read <파일패턴>")
                        continue
                    patterns = args.split()
                    matcher = FilePatternMatcher(assistant.file_manager.workspace_dir)
                    matched_files = matcher.match_patterns(patterns)
                    if matched_files:
                        for filepath in matched_files[:5]:
                            content = assistant.file_manager.read_file(filepath)
                            if content:
                                rel_path = filepath.relative_to(assistant.file_manager.workspace_dir)
                                print(f"\n📄 {rel_path}:\n{'-' * 40}\n{content[:2000]}")
                                if len(content) > 2000:
                                    print(f"\n... (생략, 총 {len(content)}자)")
                    else:
                        print("❌ 일치하는 파일이 없습니다.")

                elif command == '/context':
                    if not args:
                        print("❌ 사용법: /context <파일패턴> [질문]")
                        print("💡 질문을 생략하면 멀티라인 입력 모드로 전환됩니다.")
                        continue
                    
                    context_parts = args.split(maxsplit=1)
                    patterns = context_parts[0].split(',')
                    
                    # 질문이 포함된 경우 (한 줄 입력)
                    if len(context_parts) >= 2:
                        question = context_parts[1]
                    else:
                        # 질문이 없는 경우 (멀티라인 입력)
                        question = cli_handler.get_multiline_legacy()
                        if not question.strip():
                            print("❌ 질문을 입력하세요.")
                            continue
                    
                    last_response = assistant.chat(
                        question, streaming=streaming,
                        include_context=True, file_patterns=patterns
                    )

                elif command == '/save':
                    if last_response:
                        saved = assistant.extract_and_save_files(last_response)
                        if saved:
                            print(f"✅ {len(saved)}개 파일 저장됨:")
                            for f in saved:
                                print(f"  - {f}")
                        else:
                            print("💡 저장할 파일 블록이 없습니다.")
                    else:
                        print("💡 저장할 응답이 없습니다.")

                elif command == '/workspace':
                    if args:
                        new_workspace = Path(args).resolve()
                        if new_workspace.exists() and new_workspace.is_dir():
                            assistant.file_manager = FileManager(str(new_workspace))
                            assistant.context_builder = ContextBuilder(assistant.file_manager)
                            file_watcher.stop()
                            file_watcher = FileWatcher(str(new_workspace))
                            print(f"✅ 작업 디렉토리 변경: {new_workspace}")
                        else:
                            print(f"❌ 유효하지 않은 디렉토리: {args}")
                    else:
                        print(f"📂 현재 작업 디렉토리: {assistant.file_manager.workspace_dir}")

                elif command == '/stream':
                    streaming = True
                    print("✅ 스트리밍 모드 활성화")

                elif command == '/nostream':
                    streaming = False
                    print("✅ 논스트리밍 모드 활성화")

                elif command == '/history':
                    print("\n📜 대화 히스토리:")
                    for i, msg in enumerate(assistant.conversation_history):
                        role = "🧑" if msg["role"] == "user" else "🤖"
                        content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
                        print(f"  {i + 1}. {role} {content}")

                elif command == '/clear':
                    assistant.conversation_history = []
                    print("✅ 대화 히스토리 초기화")

                elif command == '/save_history':
                    filepath = assistant.save_history(args if args else None)
                    print(f"✅ 히스토리 저장됨: {filepath}")

                elif command == '/load_history':
                    if not args:
                        print("❌ 사용법: /load_history <파일명>")
                        continue
                    if assistant.load_history(args):
                        print(f"✅ 히스토리 로드됨: {args}")
                    else:
                        print(f"❌ 히스토리 로드 실패: {args}")

                elif command == '/list_history':
                    files = assistant.list_history()
                    print(f"\n📂 저장된 히스토리 ({len(files)}개):")
                    for f in files:
                        print(f"  - {f}")

                elif command == '/run':
                    if last_response:
                        lang = args if args else 'python'
                        # 코드 블록 추출
                        import re
                        code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', last_response, re.DOTALL)
                        if code_blocks:
                            code = code_blocks[-1]
                            print(f"\n⚡ 코드 실행 ({lang}):")
                            result = assistant.code_executor.execute(code, language=lang)
                            if result['success']:
                                print(f"✅ 성공:\n{result['stdout']}")
                            else:
                                print(f"❌ 오류:\n{result['stderr']}")
                        else:
                            print("💡 실행할 코드 블록이 없습니다.")
                    else:
                        print("💡 실행할 응답이 없습니다.")

                elif command == '/diff':
                    if last_response:
                        suggestions = diff_viewer.extract_code_suggestions(last_response)
                        if suggestions:
                            for suggestion in suggestions:
                                filepath = suggestion['filepath']
                                new_content = suggestion['content']
                                diff_output = diff_viewer.generate_diff_for_file(
                                    filepath, new_content, assistant.file_manager
                                )
                                print(diff_output)
                                print()
                        else:
                            print("💡 표시할 코드 제안이 없습니다.")
                    else:
                        print("💡 Diff를 생성할 응답이 없습니다.")

                elif command == '/apply':
                    success, message = diff_viewer.apply_diff(assistant.file_manager)
                    print(message)
                    if success:
                        print("💡 다른 변경사항이 있다면 /diff로 다시 확인하세요.")

                elif command == '/tokens':
                    stats = TokenManager.get_token_stats(
                        assistant.conversation_history,
                        TokenManager.MAX_TOKENS_GEMINI
                    )
                    print(f"\n📊 토큰 사용량:")
                    print(f"  - 현재: {stats['current']:,} / {stats['max']:,} ({stats['usage_percent']}%)")
                    print(f"  - 메시지 수: {stats['message_count']}")
                    print(f"  - 남은 토큰: {stats['remaining']:,}")

                elif command == '/shell':
                    if not args:
                        print("❌ 사용법: /shell <명령어>")
                        continue
                    result = assistant.terminal_executor.execute(args, allow_dangerous=False)
                    print(f"\n{result}")

                elif command == '/shell!':
                    if not args:
                        print("❌ 사용법: /shell! <명령어>")
                        continue
                    confirm = input(f"⚠️ '{args}' 실행하시겠습니까? (y/n): ")
                    if confirm.lower() == 'y':
                        result = assistant.terminal_executor.execute(args, allow_dangerous=True)
                        print(f"\n{result}")

                elif command == '/template':
                    if not args:
                        print("❌ 사용법: /template <템플릿명>")
                        continue
                    if assistant.set_system_prompt_from_template(args):
                        print(f"✅ 템플릿 적용됨: {args}")
                    else:
                        print(f"❌ 템플릿을 찾을 수 없습니다: {args}")

                elif command == '/template_list':
                    templates = assistant.list_templates()
                    print(f"\n📋 사용 가능한 템플릿 ({len(templates)}개):")
                    for t in templates:
                        print(f"  - {t['name']}: {t['description']}")

                elif command == '/template_reset':
                    assistant.reset_system_prompt()
                    print("✅ 기본 시스템 프롬프트로 복귀")

                elif command == '/watch':
                    if not args:
                        print("❌ 사용법: /watch <패턴>")
                        continue
                    if file_watcher.add_watch(args):
                        print(f"✅ 파일 감시 시작: {args}")
                    else:
                        print("❌ 파일 감시 시작 실패 (watchdog 설치 필요)")

                elif command == '/unwatch':
                    if not args:
                        print("❌ 사용법: /unwatch <패턴>")
                        continue
                    if file_watcher.remove_watch(args):
                        print(f"✅ 파일 감시 중지: {args}")
                    else:
                        print(f"❌ 감시 중인 패턴이 아닙니다: {args}")

                elif command == '/watch_list':
                    patterns = file_watcher.get_watched_patterns()
                    if patterns:
                        print(f"\n👁️ 감시 중인 패턴 ({len(patterns)}개):")
                        for p in patterns:
                            print(f"  - {p}")
                    else:
                        print("💡 감시 중인 패턴이 없습니다.")

                else:
                    print(f"❌ 알 수 없는 명령어: {command}")
                    print("💡 /help로 사용 가능한 명령어를 확인하세요.")

            else:
                # 일반 채팅
                last_response = assistant.chat(user_input, streaming=streaming)

        except KeyboardInterrupt:
            file_watcher.stop()
            print("\n👋 종료합니다.")
            break
        except Exception as e:
            print(f"\n❌ 오류 발생: {str(e)}")


if __name__ == "__main__":
    main()
