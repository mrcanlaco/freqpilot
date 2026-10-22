[CmdletBinding()]
param(
    [switch]$InstallDependencies,
    [string]$ScratchRoot = (Join-Path $PSScriptRoot ('work/check-' + [guid]::NewGuid().ToString('N')))
)
$ErrorActionPreference = 'Stop'
$taskScratch = [IO.Path]::GetFullPath($ScratchRoot)
if (Test-Path -LiteralPath $taskScratch) { throw 'Choose a new scratch folder for this check.' }
[IO.Directory]::CreateDirectory($taskScratch) | Out-Null
$taskNode = & node --version
if ($LASTEXITCODE -ne 0 -or $taskNode -notmatch '^v24\.') { throw 'Use Node.js 24 for the pinned UI toolchain.' }
if ($InstallDependencies) {
    & pnpm --dir (Join-Path $PSScriptRoot 'ui') install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'Frozen UI dependency installation failed.' }
}
& pnpm --dir (Join-Path $PSScriptRoot 'ui') typecheck
if ($LASTEXITCODE -ne 0) { throw 'UI typecheck failed.' }
& pnpm --dir (Join-Path $PSScriptRoot 'ui') exec vitest run --maxWorkers=4
if ($LASTEXITCODE -ne 0) { throw 'UI tests failed.' }
# Build into the ignored staging folder, never replace the UI served by a running bot.
& pnpm --dir (Join-Path $PSScriptRoot 'ui') exec vite build --outDir dist-next
if ($LASTEXITCODE -ne 0) { throw 'UI production build failed.' }
$taskImage = 'freqpilot-check:2026.9-v0.1'
& docker build --tag $taskImage (Join-Path $PSScriptRoot 'backend')
if ($LASTEXITCODE -ne 0) { throw 'Pinned backend image build failed.' }
$taskTestsMount = 'type=bind,source=' + (Join-Path $PSScriptRoot 'backend') + ',target=/checks,readonly'
& docker run --rm --network none --entrypoint python --mount $taskTestsMount $taskImage -m unittest discover -s /checks -p 'test_*.py'
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
& (Join-Path $PSScriptRoot 'tools/Test-Install.ps1') -ScratchRoot (Join-Path $taskScratch 'installer-tests')
if (!$?) { throw 'Installation guard tests failed.' }
$taskEnv = Join-Path $taskScratch 'clean.env'
& (Join-Path $PSScriptRoot 'Initialize.ps1') -EnvFile $taskEnv -UserDataPath (Join-Path $taskScratch 'clean-user-data') -ProjectName freqpilot-check
if (!$?) { throw 'Clean initialization failed.' }
. (Join-Path $PSScriptRoot 'tools/Workspace.ps1')
$taskWorkspace = Read-FreqPilotWorkspace -RepoRoot $PSScriptRoot -EnvFile $taskEnv
$null = Get-FreqPilotComposePlan $taskWorkspace
Test-FreqPilotNativeConfig $taskWorkspace
Write-Host 'FreqPilot checks passed: UI, pinned backend, installation guards and fresh native strategy configuration. No trading service was started.'
