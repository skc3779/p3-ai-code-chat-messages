"""
Tool Definitions - Claude API 도구 정의
"""

FILESYSTEM_TOOLS = [
    {
        "name": "read_file",
        "description": "파일 시스템에서 파일의 내용을 읽습니다. 파일이 텍스트 형식이 아닌 경우 읽지 못할 수 있습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "읽을 파일의 상대 경로 (예: src/main.py)"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "파일 시스템에 파일을 생성하거나 덮어씁니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "저장할 파일의 상대 경로"
                },
                "content": {
                    "type": "string",
                    "description": "파일에 작성할 내용"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_files",
        "description": "지정된 디렉토리의 파일 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "목록을 조회할 디렉토리 경로 (기본값: .)",
                    "default": "."
                }
            }
        }
    },
    {
        "name": "list_directory_tree",
        "description": "프로젝트의 디렉토리 트리 구조를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "루트 디렉토리 경로 (기본값: .)",
                    "default": "."
                },
                "depth": {
                    "type": "integer",
                    "description": "트리 깊이 (기본값: 3)",
                    "default": 3
                }
            }
        }
    },
    {
        "name": "git_status",
        "description": "Git 저장소의 현재 상태(변경된 파일 등)를 확인합니다.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "git_diff",
        "description": "파일의 변경 사항(diff)을 확인합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cached": {
                    "type": "boolean",
                    "description": "스테이징된(staged) 변경 사항을 볼지 여부 (기본값: false)",
                    "default": False
                }
            }
        }
    },
    {
        "name": "git_log",
        "description": "최근 커밋 로그를 확인합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_count": {
                    "type": "integer",
                    "description": "확인할 최근 커밋 수 (기본값: 5)",
                    "default": 5
                }
            }
        }
    },
    {
        "name": "git_add",
        "description": "파일을 스테이징(staging) 영역에 추가합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "추가할 파일 경로 목록"
                }
            },
            "required": ["files"]
        }
    },
    {
        "name": "git_commit",
        "description": "변경 사항을 커밋합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "커밋 메시지"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "list_packages",
        "description": "설치된 패키지(라이브러리) 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "언어 (python 또는 node/npm)",
                    "enum": ["python", "node", "npm"]
                }
            },
            "required": ["language"]
        }
    }
]
