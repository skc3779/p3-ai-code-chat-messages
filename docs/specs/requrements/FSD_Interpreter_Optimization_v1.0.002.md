# FSD: Claude Code Assistant 인터프리터 최적화 기능 보강

**문서 버전**: v1.0.002  
**작성일자**: 2026-01-19  
**대상 파일**: `claude-ai-chat-code01.py`

---

## 1. 개요

### 1.1 목적
현재 `claude-ai-chat-code01.py`의 기능을 분석하고, **코드 인터프리터 최적화**를 위한 기능 보강 방안을 제시합니다.

### 1.2 현재 기능 분석

| 기능 영역 | 현재 지원 | 설명 |
|-----------|----------|------|
| **파일 읽기** | ✅ | `FileManager.read_file()` |
| **파일 쓰기** | ✅ | `FileManager.write_file()` |
| **디렉토리 탐색** | ✅ | `FileManager.list_files()`, `TreeBuilder` |
| **AI 채팅** | ✅ | Claude API 스트리밍 |
| **컨텍스트 빌드** | ✅ | `ContextBuilder` |
| **파일 추출/저장** | ✅ | `extract_and_save_files()` |
| **코드 실행** | ❌ | 미지원 |
| **터미널 명령** | ❌ | 미지원 |
| **Git 통합** | ❌ | 미지원 |
| **패키지 분석** | ❌ | 미지원 |
| **MCP 통합** | ❌ | 미지원 |

---

## 2. 기능 보강 권장 사항

### 2.1 우선순위 평가

| 순위 | 기능 | 효과 | 구현 난이도 | 권장도 |
|------|------|------|-------------|--------|
| 1 | **코드 실행 환경** | ⭐⭐⭐⭐⭐ | 중 | 🔴 필수 |
| 2 | **터미널/Shell 통합** | ⭐⭐⭐⭐⭐ | 중 | 🔴 필수 |
| 3 | **Filesystem MCP** | ⭐⭐⭐⭐ | 상 | 🟡 권장 |
| 4 | **Git 통합** | ⭐⭐⭐⭐ | 중 | 🟡 권장 |
| 5 | **패키지 의존성 분석** | ⭐⭐⭐ | 하 | 🟢 선택 |
| 6 | **웹 검색/URL Fetch** | ⭐⭐⭐ | 중 | 🟢 선택 |
| 7 | **데이터베이스 연결** | ⭐⭐ | 중 | 🟢 선택 |

---

## 3. 상세 기능 설계

### 3.1 🔴 코드 실행 환경 (필수)

**목적**: AI가 생성한 코드를 즉시 실행하여 결과를 확인

#### 3.1.1 기능 설명

```
┌─────────────────────────────────────────────────────────────┐
│  사용자 요청: "Python으로 피보나치 함수 작성하고 실행해줘"    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Claude AI: 코드 생성                                        │
│  ```filename:fibonacci.py                                   │
│  def fib(n): ...                                            │
│  ```                                                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  CodeExecutor: 샌드박스 환경에서 실행                        │
│  - stdout/stderr 캡처                                       │
│  - 타임아웃 처리                                            │
│  - 에러 핸들링                                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  결과 반환: "실행 결과: 1, 1, 2, 3, 5, 8, 13..."            │
└─────────────────────────────────────────────────────────────┘
```

#### 3.1.2 구현 설계

```python
class CodeExecutor:
    """코드 실행 환경"""
    
    SUPPORTED_LANGUAGES = {
        'python': {'cmd': 'python', 'ext': '.py'},
        'javascript': {'cmd': 'node', 'ext': '.js'},
        'bash': {'cmd': 'bash', 'ext': '.sh'},
    }
    
    def __init__(self, workspace_dir: Path, timeout: int = 30):
        self.workspace_dir = workspace_dir
        self.timeout = timeout
    
    def execute(self, code: str, language: str = 'python') -> Dict:
        """코드 실행 및 결과 반환"""
        import subprocess
        import tempfile
        
        if language not in self.SUPPORTED_LANGUAGES:
            return {'success': False, 'error': f'Unsupported language: {language}'}
        
        lang_config = self.SUPPORTED_LANGUAGES[language]
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix=lang_config['ext'], delete=False
        ) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                [lang_config['cmd'], temp_file],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.workspace_dir)
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': f'Timeout after {self.timeout}s'}
        finally:
            os.unlink(temp_file)
```

#### 3.1.3 명령어 추가

```
/run [language]    - 마지막 응답의 코드 실행 (기본: python)
/exec <code>       - 인라인 코드 실행
```

---

### 3.2 🔴 터미널/Shell 통합 (필수)

**목적**: 시스템 명령어 실행 (pip install, npm, git 등)

#### 3.2.1 구현 설계

```python
class TerminalExecutor:
    """터미널 명령어 실행"""
    
    ALLOWED_COMMANDS = [
        'pip', 'python', 'node', 'npm', 'git', 'ls', 'dir', 'cat', 
        'type', 'echo', 'pwd', 'cd', 'mkdir', 'touch', 'rm', 'cp', 'mv'
    ]
    
    def __init__(self, workspace_dir: Path, timeout: int = 60):
        self.workspace_dir = workspace_dir
        self.timeout = timeout
    
    def execute(self, command: str, allow_unsafe: bool = False) -> Dict:
        """명령어 실행"""
        import subprocess
        import shlex
        
        # 명령어 파싱 및 검증
        parts = shlex.split(command)
        base_cmd = parts[0] if parts else ''
        
        if not allow_unsafe and base_cmd not in self.ALLOWED_COMMANDS:
            return {
                'success': False, 
                'error': f'Command not allowed: {base_cmd}',
                'hint': f'Allowed: {", ".join(self.ALLOWED_COMMANDS)}'
            }
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.workspace_dir)
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': f'Timeout after {self.timeout}s'}
```

#### 3.2.2 명령어 추가

```
/shell <command>   - 쉘 명령어 실행 (안전 모드)
/shell! <command>  - 쉘 명령어 실행 (위험 명령 허용)
```

---

### 3.3 🟡 Filesystem MCP 통합 (권장)

**목적**: Model Context Protocol을 통한 표준화된 파일 시스템 접근

#### 3.3.1 MCP란?

**Model Context Protocol (MCP)**는 Anthropic이 제안한 표준 프로토콜로, AI 모델이 외부 도구와 상호작용하기 위한 규격입니다.

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude AI Model                         │
└─────────────────────────────────────────────────────────────┘
                              ↓ MCP Protocol
┌─────────────────────────────────────────────────────────────┐
│                     MCP Server                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Filesystem │  │    Git      │  │    Database         │ │
│  │    Tools    │  │   Tools     │  │      Tools          │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

#### 3.3.2 Filesystem MCP 이점

| 현재 방식 | MCP 통합 방식 |
|-----------|---------------|
| 수동으로 파일 읽어서 컨텍스트에 포함 | AI가 필요할 때 직접 파일 요청 |
| 모든 파일을 미리 로드 (비효율적) | 필요한 파일만 on-demand 로드 |
| 파일 수정 후 수동 저장 | AI가 직접 파일 생성/수정 |
| 커스텀 구현 필요 | 표준 프로토콜로 확장 용이 |

#### 3.3.3 MCP 도구 정의

```python
MCP_FILESYSTEM_TOOLS = [
    {
        "name": "read_file",
        "description": "파일 내용을 읽습니다",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "파일 경로"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "파일에 내용을 씁니다",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "파일 경로"},
                "content": {"type": "string", "description": "파일 내용"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_directory",
        "description": "디렉토리 내용을 나열합니다",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "디렉토리 경로"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "create_directory",
        "description": "디렉토리를 생성합니다",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "디렉토리 경로"}
            },
            "required": ["path"]
        }
    }
]
```

#### 3.3.4 Claude Tool Use 연동

```python
def chat_with_tools(self, user_message: str) -> str:
    """도구 사용이 가능한 채팅"""
    
    body = {
        "model": self.model_id,
        "messages": self.conversation_history + [
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 8192,
        "system": self.system_prompt,
        "tools": MCP_FILESYSTEM_TOOLS  # 도구 정의 추가
    }
    
    response = requests.post(
        f"{self.endpoint_url}/v1/messages",
        headers=self.headers,
        json=body
    )
    
    result = response.json()
    
    # 도구 호출 처리
    for content_block in result.get('content', []):
        if content_block.get('type') == 'tool_use':
            tool_name = content_block['name']
            tool_input = content_block['input']
            tool_result = self._execute_tool(tool_name, tool_input)
            # 도구 결과로 후속 대화 진행
```

---

### 3.4 🟡 Git 통합 (권장)

**목적**: 버전 관리 작업 지원

#### 3.4.1 구현 설계

```python
class GitManager:
    """Git 저장소 관리"""
    
    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
    
    def status(self) -> str:
        """git status 실행"""
        return self._run_git('status', '--short')
    
    def diff(self, file: Optional[str] = None) -> str:
        """git diff 실행"""
        cmd = ['diff']
        if file:
            cmd.append(file)
        return self._run_git(*cmd)
    
    def log(self, count: int = 10) -> str:
        """git log 실행"""
        return self._run_git('log', f'-{count}', '--oneline')
    
    def add(self, files: List[str]) -> str:
        """git add 실행"""
        return self._run_git('add', *files)
    
    def commit(self, message: str) -> str:
        """git commit 실행"""
        return self._run_git('commit', '-m', message)
    
    def _run_git(self, *args) -> str:
        import subprocess
        result = subprocess.run(
            ['git'] + list(args),
            capture_output=True,
            text=True,
            cwd=str(self.workspace_dir)
        )
        return result.stdout + result.stderr
```

#### 3.4.2 명령어 추가

```
/git status        - 변경된 파일 상태
/git diff [file]   - 변경 내용 확인
/git log [n]       - 최근 커밋 이력
/git add <files>   - 스테이징
/git commit <msg>  - 커밋
```

---

### 3.5 🟢 패키지 의존성 분석 (선택)

```python
class DependencyAnalyzer:
    """프로젝트 의존성 분석"""
    
    def analyze(self) -> Dict:
        """프로젝트 의존성 분석"""
        result = {}
        
        # Python (requirements.txt, setup.py, pyproject.toml)
        req_file = self.workspace_dir / 'requirements.txt'
        if req_file.exists():
            result['python'] = self._parse_requirements(req_file)
        
        # Node.js (package.json)
        pkg_file = self.workspace_dir / 'package.json'
        if pkg_file.exists():
            result['nodejs'] = self._parse_package_json(pkg_file)
        
        return result
```

---

## 4. 구현 로드맵

### Phase 1 (v1.1.0) - 필수 기능

| 기능 | 예상 공수 | 우선순위 |
|------|----------|----------|
| `CodeExecutor` 클래스 구현 | 1일 | 🔴 High |
| `TerminalExecutor` 클래스 구현 | 1일 | 🔴 High |
| `/run`, `/shell` 명령어 추가 | 0.5일 | 🔴 High |

### Phase 2 (v1.2.0) - 권장 기능

| 기능 | 예상 공수 | 우선순위 |
|------|----------|----------|
| Claude Tool Use 연동 | 2일 | 🟡 Medium |
| `GitManager` 클래스 구현 | 1일 | 🟡 Medium |
| `/git` 명령어 추가 | 0.5일 | 🟡 Medium |

### Phase 3 (v1.3.0) - 선택 기능

| 기능 | 예상 공수 | 우선순위 |
|------|----------|----------|
| MCP 서버 구현 | 3일 | 🟢 Low |
| 의존성 분석 | 0.5일 | 🟢 Low |
| 웹 검색 통합 | 1일 | 🟢 Low |

---

## 5. 결론 및 권장 사항

### 5.1 Filesystem MCP에 대한 의견

**MCP 통합은 장기적으로 권장되지만, 단기적으로는 필수가 아닙니다.**

| 관점 | 의견 |
|------|------|
| **장점** | 표준 프로토콜, 확장성, Claude Tool Use와 자연스러운 연동 |
| **단점** | 구현 복잡도 증가, 현재 버전에서는 과도한 기능일 수 있음 |
| **권장** | Phase 2에서 Claude Tool Use 연동 먼저 구현 후, Phase 3에서 MCP로 확장 |

### 5.2 즉시 구현 권장 기능

1. **`CodeExecutor`**: AI가 생성한 코드 즉시 실행 → 코드 인터프리터의 핵심 기능
2. **`TerminalExecutor`**: pip install, npm 등 시스템 명령 실행 → 개발 환경 자동화
3. **`/run`, `/shell` 명령어**: 사용자 인터페이스 확장

### 5.3 요약

```
현재 상태: 파일 읽기/쓰기 + AI 채팅
    ↓
Phase 1: + 코드 실행 + 터미널 통합 (필수)
    ↓  
Phase 2: + Git 통합 + Tool Use (권장)
    ↓
Phase 3: + MCP 통합 + 확장 기능 (선택)
```

---

## 6. 참고 자료

- [Claude Tool Use 문서](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Filesystem Server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
