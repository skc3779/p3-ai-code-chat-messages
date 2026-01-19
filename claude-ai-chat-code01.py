
import fnmatch
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Callable

import requests
import sseclient
from dotenv import load_dotenv


class FileManager:
    """로컬 파일 시스템 관리"""

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.ignore_patterns = self._load_ignore_patterns()

    def _load_ignore_patterns(self) -> List[str]:
        """gitignore 스타일 패턴 로드"""
        patterns = [
            '*.pyc', '__pycache__', '.git', '.venv', 'venv',
            'node_modules', '.DS_Store', '*.log', '.env'
        ]

        gitignore_path = self.workspace_dir / '.gitignore'
        if gitignore_path.exists():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                patterns.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])

        return patterns

    def should_ignore(self, path: Path) -> bool:
        """파일/디렉토리를 무시해야 하는지 확인"""
        rel_path = path.relative_to(self.workspace_dir)
        path_str = str(rel_path)

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
        return False

    def list_files(self, extensions: Optional[List[str]] = None, max_depth: int = 5) -> List[Path]:
        """작업 공간의 파일 목록 반환"""
        files = []

        def scan_directory(directory: Path, current_depth: int = 0):
            if current_depth > max_depth:
                return

            try:
                for item in directory.iterdir():
                    if self.should_ignore(item):
                        continue

                    if item.is_file():
                        if extensions is None or item.suffix in extensions:
                            files.append(item)
                    elif item.is_dir():
                        scan_directory(item, current_depth + 1)
            except PermissionError:
                pass

        scan_directory(self.workspace_dir)
        return sorted(files)

    def read_file(self, filepath: Path) -> Optional[str]:
        """파일 내용 읽기"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(filepath, 'r', encoding='latin-1') as f:
                    return f.read()
            except Exception as e:
                print(f"⚠️  파일 읽기 실패 ({filepath}): {e}")
                return None
        except Exception as e:
            print(f"⚠️  파일 읽기 실패 ({filepath}): {e}")
            return None

    def write_file(self, filepath: Path, content: str) -> bool:
        """파일 쓰기"""
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"❌ 파일 쓰기 실패 ({filepath}): {e}")
            return False

    def get_file_info(self, filepath: Path) -> Dict:
        """파일 정보 반환"""
        try:
            stat = filepath.stat()
            return {
                'path': str(filepath.relative_to(self.workspace_dir)),
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'extension': filepath.suffix
            }
        except Exception:
            return {}

class TreeBuilder:
    """
    파일·디렉터리 트리를 문자열 형태로 만들어 반환합니다.

    Parameters
    ----------
    workspace_dir : Path
        트리를 시작할 루트 디렉터리.
    should_ignore : Callable[[Path], bool]
        파일·디렉터리를 무시할지 판단하는 함수.
        (예: .gitignore‑필터, .venv 등)
    max_depth : int, optional
        표시할 최대 깊이 (0이면 루트만, 1이면 바로 아래 레벨까지 …)
    """

    def __init__(
            self,
            workspace_dir: Path,
            should_ignore: Callable[[Path], bool],
            max_depth: int = 3,
    ) -> None:
        self.root = workspace_dir
        self.should_ignore = should_ignore
        self.max_depth = max_depth

    # ------------------------------------------------------------------ #
    def _add_children(
        self,
        dir_path: Path,
        prefix: str,
        depth: int,
        out: List[str],
    ) -> None:
        """
        ``dir_path`` 의 **직접적인 자식**들을 ``out`` 에 추가한다.
        ``depth`` 가 ``max_depth`` 와 같아지면 더 이상 하위 디렉터리를 탐색하지 않는다.
        """
        # 깊이 제한
        if depth >= self.max_depth:
            return

        # 자식들을 정렬 (디렉터리 → 파일 순)
        try:
            children = sorted(
                dir_path.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except PermissionError:          # 접근 권한이 없을 경우 무시
            return

        for idx, child in enumerate(children):
            # 무시 대상이면 건너뛰기
            if self.should_ignore(child):
                continue

            is_last = idx == len(children) - 1
            connector = "└── " if is_last else "├── "

            icon = "📁 " if child.is_dir() else "📄 "
            suffix = "/" if child.is_dir() else ""

            # 현재 라인 : 접두사 + 커넥터 + 아이콘 + 이름(+"/")
            out.append(f"{prefix}{connector}{icon}{child.name}{suffix}")

            # 디렉터리라면 재귀 호출 (다음 깊이)
            if child.is_dir():
                # 현재 라인에서 사용한 커넥터는 더 이상 필요 없으므로
                # 다음 라인에 사용할 prefix 를 만든다.
                next_prefix = prefix + ("    " if is_last else "│   ")
                self._add_children(child, next_prefix, depth + 1, out)

    # ------------------------------------------------------------------ #
    def build(self) -> str:
        """루트 디렉터리부터 시작해 전체 트리를 만든 뒤 문자열로 반환합니다."""
        lines: List[str] = [f"📁 프로젝트 구조 (작업 디렉터리: {self.root})"]

        # 루트 디렉터리 라인
        lines.append(f"📁 {self.root.name}/")

        # 루트 아래부터 재귀적으로 탐색
        self._add_children(self.root, "", 0, lines)

        return "\n".join(lines)

class ContextBuilder:
    """AI에게 전달할 컨텍스트 구성"""

    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager
        self.max_context_size = 100000  # 최대 컨텍스트 크기 (문자 수)

    def build_file_tree2(self, max_depth: int = 3) -> str:
        """파일 트리 구조 생성"""
        tree_lines = [f"📁 프로젝트 구조 (작업 디렉토리: {self.file_manager.workspace_dir})\n"]

        def add_tree_item(path: Path, prefix: str = "", depth: int = 0):
            if depth > max_depth:
                return

            if self.file_manager.should_ignore(path):
                return

            name = path.name
            if path.is_file():
                tree_lines.append(f"{prefix}📄 {name}")
            elif path.is_dir():
                tree_lines.append(f"{prefix}📁 {name}/")
                try:
                    items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
                    for i, item in enumerate(items):
                        is_last = i == len(items) - 1
                        new_prefix = prefix + ("    " if is_last else "│   ")
                        connector = "└── " if is_last else "├── "
                        tree_lines.append("")
                        tree_lines[-1] = prefix + connector
                        add_tree_item(item, new_prefix, depth + 1)
                except PermissionError:
                    pass

        add_tree_item(self.file_manager.workspace_dir)
        return "\n".join(tree_lines)

    def build_file_tree(self, max_depth: int = 3) -> str:
        """
        기존 구현을 `TreeBuilder` 로 대체합니다.
        """
        builder = TreeBuilder(
            workspace_dir=self.file_manager.workspace_dir,
            should_ignore=self.file_manager.should_ignore,
            max_depth=max_depth,
        )
        return builder.build()

    def build_files_context(self, filepaths: List[Path]) -> str:
        """선택된 파일들의 내용을 컨텍스트로 구성"""
        context_parts = []
        total_size = 0

        for filepath in filepaths:
            content = self.file_manager.read_file(filepath)
            if content is None:
                continue

            rel_path = filepath.relative_to(self.file_manager.workspace_dir)
            file_context = f"\n{'=' * 80}\n"
            file_context += f"📄 파일: {rel_path}\n"
            file_context += f"{'=' * 80}\n"
            file_context += f"```{filepath.suffix[1:] if filepath.suffix else ''}\n"
            file_context += content
            file_context += f"\n```\n"

            if total_size + len(file_context) > self.max_context_size:
                context_parts.append("\n⚠️  컨텍스트 크기 제한으로 일부 파일이 생략되었습니다.\n")
                break

            context_parts.append(file_context)
            total_size += len(file_context)

        return "\n".join(context_parts)

    def build_context(self, include_tree: bool = True, file_patterns: Optional[List[str]] = None) -> str:
        """전체 컨텍스트 구성"""
        context_parts = []

        # 파일 트리 추가
        if include_tree:
            context_parts.append(self.build_file_tree())
            context_parts.append("\n")

        # 파일 내용 추가
        if file_patterns:
            files = []
            all_files = self.file_manager.list_files()

            for pattern in file_patterns:
                matched = [f for f in all_files if
                           fnmatch.fnmatch(str(f.relative_to(self.file_manager.workspace_dir)), pattern)]
                files.extend(matched)

            if files:
                context_parts.append(self.build_files_context(files))

        return "\n".join(context_parts)


class ClaudeCodeAssistant:
    """Claude AI 코딩 어시스턴트"""

    def __init__(self, api_key: str, model_id: str = "claude-sonnet-4-5",
                 workspace_dir: str = ".", endpoint_url: str = "https://api.anthropic.com"):
        self.endpoint_url = endpoint_url
        self.headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        self.model_id = model_id
        self.conversation_history: List[Dict] = []

        self.file_manager = FileManager(workspace_dir)
        self.context_builder = ContextBuilder(self.file_manager)

        self.system_prompt = """당신은 전문 소프트웨어 개발 어시스턴트입니다.
사용자의 프로젝트 파일을 분석하고, 코드를 생성하거나 수정하며, 문서를 작성합니다.

[필수] 코드나 파일을 생성할 때는 반드시 아래 형식을 정확히 따르세요:

```filename:경로/파일명.확장자
코드 내용
```

예시:
```filename:src/main.py
print("Hello, World!")
```

```filename:README.md
# 프로젝트 제목
```

주의사항:
- 반드시 ```filename: 형식을 사용하세요 (```python, ```javascript 등 언어 식별자 사용 금지)
- 여러 파일은 각각 별도의 코드 블록으로 작성하세요
- 파일 경로는 프로젝트 루트 기준 상대 경로를 사용하세요"""



    def chat(self, user_message: str, streaming: bool = True,
             include_context: bool = False, file_patterns: Optional[List[str]] = None) -> str:
        """AI와 채팅"""

        # 컨텍스트 구성
        if include_context:
            context = self.context_builder.build_context(
                include_tree=True,
                file_patterns=file_patterns
            )

            if context:
                full_message = f"{context}\n\n{'=' * 80}\n\n{user_message}"
            else:
                full_message = user_message
        else:
            full_message = user_message

        # API 호출 - Claude API 형식으로 메시지 구성
        messages = self.conversation_history.copy()
        messages.append({"role": "user", "content": full_message})

        body = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": 8192,
            "system": self.system_prompt,
            "stream": streaming
        }

        api_url = f"{self.endpoint_url}/v1/messages"

        try:
            if streaming:
                return self._chat_streaming(api_url, body, user_message, full_message)
            else:
                return self._chat_non_streaming(api_url, body, user_message, full_message)
        except Exception as e:
            print(f"\n❌ API 호출 오류: {str(e)}")
            return ""

    def _chat_streaming(self, api_url: str, body: Dict,
                        original_message: str, full_message: str) -> str:
        """스트리밍 모드 채팅"""
        response = requests.post(api_url, headers=self.headers, json=body, stream=True)

        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            return ""

        client = sseclient.SSEClient(response)
        result_message = ""

        print("\n🤖 AI: ", end="", flush=True)

        for event in client.events():
            if event.data:
                try:
                    data = json.loads(event.data)
                    event_type = data.get('type')

                    if event_type == 'content_block_delta':
                        content = data.get('delta', {}).get('text', '')
                        if content:
                            print(content, end="", flush=True)
                            result_message += content
                    elif event_type == 'message_stop':
                        break
                except json.JSONDecodeError:
                    continue

        print("\n")

        # 히스토리에 추가 (Claude API 역할 기반 형식)
        self.conversation_history.append({"role": "user", "content": original_message})
        if result_message:
            self.conversation_history.append({"role": "assistant", "content": result_message})

        return result_message

    def _chat_non_streaming(self, api_url: str, body: Dict,
                            original_message: str, full_message: str) -> str:
        """논스트리밍 모드 채팅"""
        response = requests.post(api_url, headers=self.headers, json=body)

        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            return ""

        result = response.json()
        # Claude API 응답 구조: content[0].text
        content_blocks = result.get('content', [])
        content = content_blocks[0].get('text', '') if content_blocks else ''

        print(f"\n🤖 AI: {content}\n")

        # 히스토리에 추가 (Claude API 역할 기반 형식)
        self.conversation_history.append({"role": "user", "content": original_message})
        if content:
            self.conversation_history.append({"role": "assistant", "content": content})

        return content

    def extract_and_save_files(self, response: str) -> List[str]:
        """AI 응답에서 파일을 추출하여 저장"""
        import re

        # ```filename:path/to/file.ext 형식 찾기
        pattern = r'```filename:(.+?)\n(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)

        saved_files = []

        for filepath_str, content in matches:
            filepath_str = filepath_str.strip()
            filepath = self.file_manager.workspace_dir / filepath_str

            # 파일 저장 전 확인
            if filepath.exists():
                print(f"\n⚠️  파일이 이미 존재합니다: {filepath_str}")
                confirm = input("덮어쓰시겠습니까? (y/N): ").strip().lower()
                if confirm != 'y':
                    print(f"⏭️  건너뛰기: {filepath_str}")
                    continue

            if self.file_manager.write_file(filepath, content.strip()):
                saved_files.append(filepath_str)
                print(f"✅ 파일 저장됨: {filepath_str}")

        return saved_files

def load_environment():
    """
    프로젝트 루트(.gitignore와 같은 위치)에 있는 .env 파일을 읽어
    os.environ 에 값을 채워 넣는다.
    """
    # 현재 파일이 위치한 디렉터리(예: src/ 혹은 프로젝트 루트) 기준으로 .env 경로 지정
    env_path = Path(__file__).resolve().parent / ".env"   # 필요에 따라 조정
    load_dotenv(dotenv_path=env_path, override=True)   # override=True → 기존 env 변수 덮어쓰기

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
    print("  /help               - 도움말 보기")
    print("  /quit               - 종료")
    print("=" * 80)
    print("\n💡 사용 예시:")
    print("  - '/context *.py 이 프로젝트에 README.md를 작성해줘'")
    print("  - '/context src/ 테스트 코드를 작성해줘'")
    print("  - '새로운 API 엔드포인트 /users를 추가해줘'")
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
                    for f in files[:50]:  # 최대 50개만 표시
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
                                   if
                                   fnmatch.fnmatch(str(f.relative_to(assistant.file_manager.workspace_dir)), pattern)]
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

                    # 패턴과 질문 분리
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