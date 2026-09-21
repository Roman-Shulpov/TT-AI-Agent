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
    Write-Host 'Browser AI agent. Uses your Codex login and usage limits. No separate API key.'
    Write-Host 'Enter your task below. /stop or Ctrl+C stops the agent.'
    & $python -m browser_agent
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
