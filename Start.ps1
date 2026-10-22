$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    if (!(Test-Path -LiteralPath '.env')) { throw 'Create .env from .env.example and point to your paper user_data first.' }
    $taskDataPath = $env:FREQPILOT_USER_DATA
    if (!$taskDataPath) {
        $taskEnvLine = Get-Content -LiteralPath '.env' | Where-Object { $_ -match '^FREQPILOT_USER_DATA=' } | Select-Object -First 1
        $taskDataPath = ($taskEnvLine -replace '^FREQPILOT_USER_DATA=', '').Trim().Trim('"').Trim("'")
    }
    if (!$taskDataPath) { throw 'FREQPILOT_USER_DATA must be set.' }
    $taskConfig = Get-Content -Raw -LiteralPath (Join-Path $taskDataPath 'config.json') | ConvertFrom-Json
    if ($taskConfig.dry_run -ne $true -or $taskConfig.exchange.key -or $taskConfig.exchange.secret) { throw 'This setup requires dry_run=true and no exchange trading keys.' }
    if (!(Test-Path -LiteralPath 'ui/dist/index.html')) { throw 'Build the UI first: pnpm --dir ui install --frozen-lockfile; pnpm --dir ui build' }
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw 'FreqPilot could not start. Inspect Docker Compose diagnostics.' }
    Write-Host 'FreqPilot: http://localhost:8090/studio | Backtest: http://localhost:8091/studio'
} finally { Pop-Location }
