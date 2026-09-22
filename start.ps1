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
    $env:LLM_PROVIDER = 'codex'
    $env:LLM_MODEL = 'gpt-5.5'
    $env:SAFETY_MODE = 'balanced'
    $env:AUTONOMOUS = 'true'
    $env:MAX_STEPS = '50'
    if (-not $env:PROFILE_DIR) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $env:PROFILE_DIR = Join-Path $PSScriptRoot "artifacts\start-profile-$stamp"
    }
    Write-Host 'Browser AI agent. Uses your Codex login and usage limits. No separate API key.'
    Write-Host 'Enter your task below. /stop or Ctrl+C stops the agent.'
    Write-Host 'Video prompts: VIDEO_PROMPTS.md; autonomous tasks: AUTONOMOUS_PROMPTS.md'
    Write-Host 'Autonomous mode: no questions during the task. Purchases and applications are blocked.'
    Write-Host "Browser profile: $env:PROFILE_DIR"
    & $python -m browser_agent
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
