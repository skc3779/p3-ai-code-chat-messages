## Codex MCP Command Collections

- [MCP](https://developers.openai.com/codex/mcp)
- [Oh My Codex](https://github.com/ohmycodex/omx)

### Codex MCP Commands

```ps1
codex mcp add context7 -- npx -y @upstash/context7-mcp
```

### 사용자 환경변수 등록 (sparkshell.bat - Windows)

1. sparkshell.bat 파일을 특정 폴더(예: C:\tools\)에 고정해 두고, 어떤 프로젝트 폴더에서 OMX를 실행하든 항상 해당 파일을 참조하게 만드는 방법입니다.

```ps1
# 1. PowerShell을 엽니다.
# 2. 아래 명령어의 경로를 실제 파일이 있는 "절대 경로(고정된 주소)"로 수정한 뒤 실행하세요.
[Environment]::SetEnvironmentVariable("OMX_EXPLORE_BIN", "$PWD\sparkshell.bat", "User")
```

2. 만약 sparkshell.bat이 특정 프로젝트에만 종속된 파일이라면, 전역 설정보다는 프로젝트 전용 명찰인 .env 파일을 사용하는 것이 AI 에이전트 생태계의 모범 사례입니다. OMX는 실행 시 자동으로 .env 파일의 환경 변수를 읽어 들입니다.

```ps1
# 프로젝트 폴더 내에 .env 파일을 생성하고 상대 경로(./)로 지정합니다.
Add-Content -Path .env -Value "OMX_EXPLORE_BIN=./sparkshell.bat"
```

