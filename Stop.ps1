Push-Location $PSScriptRoot
try { docker compose stop } finally { Pop-Location }
