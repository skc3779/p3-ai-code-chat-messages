#!/usr/bin/env python3
"""
Claude Code Assistant - AI 코딩 어시스턴트

모듈화된 버전: src/ 패키지에서 클래스들을 import합니다.
"""

import fnmatch
import os
from pathlib import Path

from dotenv import load_dotenv

# src/ 패키지에서 클래스 import
from src import (
    FileManager,
    ContextBuilder,
    ClaudeCodeAssistant,
)


def load_environment():
    """프로젝트 루트에 있는 .env 파일을 읽어 os.environ에 값을 채워 넣는다."""
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path, override=True)


def print_menu():
    """메뉴 출력"""
    print("\n" + "=" * 80)
    print("🤖 Claude Code Assistant - AI 코딩 어시스턴트")
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
    print("  /run [lang]         - 마지막 응답의 코드 실행 (python/js/bash)")
    print("  /shell <cmd>        - 쉘 명령어 실행 (안전 모드)")
    print("  /shell! <cmd>       - 쉘 명령어 실행 (위험 명령 허용)")
    print("  /help               - 도움말 보기")
    print("  /quit               - 종료")
    print("=" * 80)
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

    streaming_mode = True
    last_response = ""

    print_menu()
    print(f"\n📂 현재 작업 디렉토리: {workspace}")
    print(f"🔄 현재 모드: {'스트리밍' if streaming_mode else '논스트리밍'}")

    while True:
        try:
            user_input = input("\n👤 You: ").strip()

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
                    print("✅ 스트리밍 모드로 변경되었습니다.")

                elif command == '/nostream':
                    streaming_mode = False
                    print("✅ 논스트리밍 모드로 변경되었습니다.")

                elif command == '/history':
                    if assistant.conversation_history:
                        print("\n📜 대화 히스토리:")
                        for i, msg in enumerate(assistant.conversation_history, 1):
                            role = "👤" if msg.get('role') == 'user' else "🤖"
                            content = msg.get('content', '')
                            preview = content[:150].replace('\n', ' ')
                            print(f"{role} [{i}]: {preview}{'...' if len(content) > 150 else ''}")
                    else:
                        print("📭 대화 히스토리가 비어있습니다.")

                elif command == '/clear':
                    assistant.conversation_history.clear()
                    print("✅ 대화 히스토리가 초기화되었습니다.")

                elif command == '/workspace':
                    if args:
                        new_workspace = Path(args).resolve()
                        if new_workspace.exists() and new_workspace.is_dir():
                            assistant.file_manager = FileManager(str(new_workspace))
                            assistant.context_builder = ContextBuilder(assistant.file_manager)
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
                    tree = assistant.context_builder.build_file_tree()
                    print(f"\n{tree}")

                elif command == '/read':
                    if not args:
                        print("❌ 파일 패턴을 지정하세요. 예: /read src/*.py")
                        continue

                    patterns = args.split()
                    all_files = assistant.file_manager.list_files()
                    matched_files = []

                    for pattern in patterns:
                        matched = [f for f in all_files
                                   if fnmatch.fnmatch(str(f.relative_to(assistant.file_manager.workspace_dir)), pattern)]
                        matched_files.extend(matched)

                    if matched_files:
                        context = assistant.context_builder.build_files_context(matched_files)
                        print(context)
                    else:
                        print(f"❌ 패턴 '{args}'에 해당하는 파일이 없습니다.")

                elif command == '/context':
                    if not args:
                        print("❌ 형식: /context <파일패턴> <질문>")
                        print("예: /context src/*.py 이 코드를 리팩토링해줘")
                        continue

                    parts = args.split(maxsplit=1)
                    if len(parts) < 2:
                        print("❌ 질문을 입력하세요.")
                        continue

                    pattern = parts[0]
                    question = parts[1]

                    last_response = assistant.chat(
                        question,
                        streaming=streaming_mode,
                        include_context=True,
                        file_patterns=[pattern]
                    )

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