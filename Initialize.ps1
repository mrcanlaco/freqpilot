[CmdletBinding()]
param(
    [string]$UserDataPath = (Join-Path $PSScriptRoot 'runtime/user_data'),
    [string]$EnvFile = (Join-Path $PSScriptRoot '.env'),
    [ValidatePattern('^[a-z0-9][a-z0-9_-]{1,48}$')][string]$ProjectName = 'freqpilot'
)
$ErrorActionPreference = 'Stop'
$taskDataPath = [IO.Path]::GetFullPath($UserDataPath)
$taskEnvPath = [IO.Path]::GetFullPath($EnvFile)
if ($taskDataPath -match "[\r\n]" -or $taskEnvPath -match "[\r\n]") { throw 'Paths must not contain newlines.' }
if (Test-Path -LiteralPath $taskEnvPath) { throw 'Env file already exists. Keep the existing setup or choose a new -EnvFile.' }
if (Test-Path -LiteralPath $taskDataPath) { throw 'User data path already exists. Choose a new empty destination; initialization never overwrites data.' }
if ($taskEnvPath -eq $taskDataPath -or $taskEnvPath.StartsWith($taskDataPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Keep EnvFile outside the new user_data folder.' }
$taskTemplateRoot = Join-Path $PSScriptRoot 'templates'
$taskProvenance = Get-Content -LiteralPath (Join-Path $taskTemplateRoot 'PROVENANCE.json') -Raw | ConvertFrom-Json
foreach ($taskTemplate in $taskProvenance) {
    $taskSource = Join-Path $taskTemplateRoot ($taskTemplate.strategy + '.py')
    if ((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskTemplate.installed_sha256) { throw ('Template hash mismatch: ' + $taskTemplate.strategy) }
}
$taskConfig = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.example.json') -Raw | ConvertFrom-Json
foreach ($taskField in @('password', 'jwt_secret_key', 'ws_token')) {
    $taskConfig.api_server.$taskField = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
}
# All checks above happen before touching the new destination or the existing setup.
[IO.Directory]::CreateDirectory($taskDataPath) | Out-Null
foreach ($taskFolder in @('strategies', 'data/binance/futures', 'backtest_results', 'logs')) {
    [IO.Directory]::CreateDirectory((Join-Path $taskDataPath $taskFolder)) | Out-Null
}
$taskEncoding = [Text.UTF8Encoding]::new($false)
function Write-TaskNewFile([string]$taskPath, [string]$taskText) {
    $taskFile = [IO.File]::Open($taskPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $taskBytes = $taskEncoding.GetBytes($taskText); $taskFile.Write($taskBytes, 0, $taskBytes.Length) } finally { $taskFile.Dispose() }
}
Write-TaskNewFile (Join-Path $taskDataPath 'config.json') ($taskConfig | ConvertTo-Json -Depth 15)
foreach ($taskTemplate in $taskProvenance) {
    $taskName = $taskTemplate.strategy + '.py'
    [IO.File]::Copy((Join-Path $taskTemplateRoot $taskName), (Join-Path (Join-Path $taskDataPath 'strategies') $taskName), $false)
}
$taskAccess = @"
FreqPilot local access. Keep this file private; do not commit it.
UI: http://localhost:8090/studio
Backtest API: http://localhost:8091
Username: $($taskConfig.api_server.username)
Password: $($taskConfig.api_server.password)
Only paper/backtest. New bots start STOPPED. No Binance trading credentials are configured.
"@
Write-TaskNewFile (Join-Path $taskDataPath 'ACCESS.txt') $taskAccess
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($taskEnvPath)) | Out-Null
$taskPortablePath = $taskDataPath.Replace('\', '/').Replace("'", "\'")
$taskEnv = "FREQPILOT_USER_DATA='$taskPortablePath'`nFREQPILOT_PROJECT_NAME=$ProjectName`nFREQPILOT_IMAGE=$($ProjectName):2026.9-v0.1`n"
Write-TaskNewFile $taskEnvPath $taskEnv
Write-Host "Prepared $($taskProvenance.Count) strategy templates in $taskDataPath"
Write-Host "Local login is saved in $(Join-Path $taskDataPath 'ACCESS.txt'). No password was printed."
Write-Host 'No services were started and no data was downloaded.'
Write-Host ("Next: ./Start.ps1 -EnvFile '" + $taskEnvPath.Replace("'", "''") + "' -CheckOnly (or -Build to build/start).")
