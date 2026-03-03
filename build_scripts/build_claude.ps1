# Claude Assistant 실행 파일 빌드 스크립트
# 요구사항 FSD v1.0.065 반영

$APP_NAME = "ClaudeAssistant"
$ICON_FILE = "NONE" # 추후 아이콘 반영 시 변경

# --noconsole 제외 (CLI 챗봇 특성 고려)
Write-Host "Building $APP_NAME..."

# 스크립트 위치의 상위 폴더(프로젝트 루트)로 이동하여 실행
Set-Location -Path "$PSScriptRoot\.."

pyinstaller --noconfirm `
    --onefile `
    --name=$APP_NAME `
    --distpath="build_output/dist" `
    --workpath="build_output/build" `
    --specpath="build_output/spec" `
    --clean `
    claude-ai-chat-code.py

Write-Host "Build finished! Output located in build_output/dist/$APP_NAME.exe"
