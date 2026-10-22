[CmdletBinding()]
param([string]$EnvFile = (Join-Path $PSScriptRoot '.env'))
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tools/Workspace.ps1')
$taskWorkspace = Read-FreqPilotWorkspace -RepoRoot $PSScriptRoot -EnvFile $EnvFile -IdentityOnly
$null = Get-FreqPilotComposePlan $taskWorkspace
Assert-FreqPilotProject $taskWorkspace
& docker compose --project-directory $PSScriptRoot --env-file $taskWorkspace.EnvFile -f (Join-Path $PSScriptRoot 'compose.yaml') stop
if ($LASTEXITCODE -ne 0) { throw 'Could not stop this Compose project.' }
Write-Host 'Stopped this workspace. Data and databases were retained.'
