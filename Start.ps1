[CmdletBinding()]
param(
    [string]$EnvFile = (Join-Path $PSScriptRoot '.env'),
    [switch]$Build,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tools/Workspace.ps1')
$taskWorkspace = Read-FreqPilotWorkspace -RepoRoot $PSScriptRoot -EnvFile $EnvFile
$taskPlan = Get-FreqPilotComposePlan $taskWorkspace
Assert-FreqPilotProject $taskWorkspace
if (!$CheckOnly) { Assert-FreqPilotPorts $taskWorkspace $taskPlan }
if ($Build -and !$CheckOnly) {
    & pnpm --dir (Join-Path $PSScriptRoot 'ui') install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'UI dependency installation failed.' }
    & pnpm --dir (Join-Path $PSScriptRoot 'ui') exec vite build --outDir dist-next
    if ($LASTEXITCODE -ne 0) { throw 'UI build failed.' }
    $taskDist = Join-Path $PSScriptRoot 'ui/dist'
    $taskNext = Join-Path $PSScriptRoot 'ui/dist-next'
    [IO.Directory]::CreateDirectory($taskDist) | Out-Null
    Get-ChildItem -LiteralPath $taskNext -Force | Where-Object Name -ne 'index.html' | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $taskDist -Recurse -Force }
    Copy-Item -LiteralPath (Join-Path $taskNext 'index.html') -Destination (Join-Path $taskDist 'index.next.html') -Force
    Move-Item -LiteralPath (Join-Path $taskDist 'index.next.html') -Destination (Join-Path $taskDist 'index.html') -Force
}
if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'ui/dist/index.html'))) { throw 'Build the UI first with Start.ps1 -Build, or pnpm --dir ui install --frozen-lockfile and pnpm --dir ui build.' }
Test-FreqPilotNativeConfig $taskWorkspace -StartupOnly
if ($CheckOnly) {
    Write-Host 'Workspace, Compose and native strategies checked. No services started. Port availability is checked only before an actual start.'
    return
}
$taskComposeArgs = @('compose','--project-directory',$PSScriptRoot,'--env-file',$taskWorkspace.EnvFile,'-f',(Join-Path $PSScriptRoot 'compose.yaml'))
& docker @taskComposeArgs build backtest
if ($LASTEXITCODE -ne 0) { throw 'Backend image build failed. No services were started.' }
Assert-FreqPilotProject $taskWorkspace
Assert-FreqPilotPorts $taskWorkspace $taskPlan
& docker @taskComposeArgs up -d
if ($LASTEXITCODE -ne 0) { throw 'FreqPilot could not start. Inspect Docker Compose diagnostics.' }
Write-Host 'FreqPilot: http://localhost:8090/studio | Paper profiles: http://localhost:8090/paper | Backtest: http://localhost:8091/studio'
