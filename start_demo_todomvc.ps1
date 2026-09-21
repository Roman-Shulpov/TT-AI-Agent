$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'First follow the Python installation instructions in README.md.'
    }
    if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
        throw 'Install Codex CLI: npm install -g @openai/codex. Then run: codex login'
    }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $env:LLM_PROVIDER = 'codex'
    $env:LLM_MODEL = 'gpt-5.5'
    $env:PROFILE_DIR = Join-Path $PSScriptRoot "artifacts\demo-profile-$stamp"
    $recordDir = Join-Path $PSScriptRoot "artifacts\demo-recording-$stamp"
    $task = 'Open https://demo.playwright.dev/todomvc/. Add three tasks: Read README, Run tests, Record demo. Mark Read README completed. Show only active tasks and report their names and count. Leave the browser on the final result.'

    Write-Host 'Demo run: TodoMVC presentation task.'
    Write-Host "Video folder: $recordDir"
    & $python -m browser_agent --task $task --record $recordDir
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
