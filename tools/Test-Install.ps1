[CmdletBinding()]
param([string]$ScratchRoot = (Join-Path $PSScriptRoot ('../work/install-tests-' + [guid]::NewGuid().ToString('N'))))
$ErrorActionPreference = 'Stop'
$taskRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskScratch = [IO.Path]::GetFullPath($ScratchRoot)
if (Test-Path -LiteralPath $taskScratch) { throw 'Choose a new scratch folder for installation tests.' }
[IO.Directory]::CreateDirectory($taskScratch) | Out-Null
. (Join-Path $PSScriptRoot 'Workspace.ps1')
$script:taskChecks = 0
function Assert-Task([bool]$Condition, [string]$Message) { if (!$Condition) { throw $Message }; $script:taskChecks++ }
function Assert-TaskThrows([scriptblock]$Action, [string]$Pattern) {
    $taskCaught = $false
    try { & $Action } catch { if ($_.Exception.Message -notmatch $Pattern) { throw }; $taskCaught = $true }
    Assert-Task $taskCaught ('Expected refusal: ' + $Pattern)
}
foreach ($taskKey in @('FREQPILOT_USER_DATA','FREQPILOT_PROJECT_NAME','FREQPILOT_IMAGE')) {
    if ([Environment]::GetEnvironmentVariable($taskKey, 'Process')) { throw 'Run installation tests without FREQPILOT_* environment overrides.' }
}
$taskEnv = Join-Path $taskScratch 'fresh.env'
$taskData = Join-Path $taskScratch "O'Neil `$ data"
$taskOutput = & (Join-Path $taskRepo 'Initialize.ps1') -EnvFile $taskEnv -UserDataPath $taskData -ProjectName freqpilot-installtest 6>&1 | Out-String
$taskWorkspace = Read-FreqPilotWorkspace -RepoRoot $taskRepo -EnvFile $taskEnv
$script:taskPlan = Get-FreqPilotComposePlan $taskWorkspace
Assert-Task ($taskWorkspace.UserData -eq $taskData) 'Quoted/dollar/space path did not round-trip.'
Assert-Task ($taskWorkspace.Config.dry_run -eq $true -and $taskWorkspace.Config.initial_state -eq 'stopped') 'New workspace must start paper-only and stopped.'
Assert-Task (@(Get-ChildItem -LiteralPath (Join-Path $taskData 'strategies') -Filter '*.py').Count -eq 8) 'Expected eight existing templates.'
$taskResearch = Get-Content -LiteralPath (Join-Path $taskData 'freqpilot/research/StarterFutures.json') -Raw | ConvertFrom-Json
Assert-Task ($taskResearch.idea -match 'EMA20/50' -and @($taskResearch.tags) -contains 'Mẫu') 'Fresh samples need a useful description and tags.'
Assert-Task ($taskResearch.is_favorite -eq $false -and !(Test-Path -LiteralPath (Join-Path $taskData 'freqpilot/runs'))) 'New workspace inherited favorites or performance reports.'
$taskSecrets = @('password','jwt_secret_key','ws_token') | ForEach-Object { $taskWorkspace.Config.api_server.$_ }
Assert-Task (@($taskSecrets | Sort-Object -Unique).Count -eq 3) 'Each local secret must be different.'
foreach ($taskSecret in $taskSecrets) { Assert-Task (!$taskOutput.Contains($taskSecret)) 'Initialization printed a secret.' }
$taskConfigHash = (Get-FileHash -LiteralPath (Join-Path $taskData 'config.json')).Hash
Assert-TaskThrows { & (Join-Path $taskRepo 'Initialize.ps1') -EnvFile $taskEnv -UserDataPath (Join-Path $taskScratch 'unused') } 'already exists'
Assert-Task (!(Test-Path -LiteralPath (Join-Path $taskScratch 'unused'))) 'Existing env refusal created user_data.'
Assert-TaskThrows { & (Join-Path $taskRepo 'Initialize.ps1') -EnvFile (Join-Path $taskScratch 'unused.env') -UserDataPath $taskData } 'already exists'
Assert-Task ((Get-FileHash -LiteralPath (Join-Path $taskData 'config.json')).Hash -eq $taskConfigHash) 'Existing config changed.'
Assert-Task (!(Test-Path -LiteralPath (Join-Path $taskScratch 'unused.env'))) 'Existing data refusal created an env file.'

# Corrupt a separate seed copy, never a template in the checkout.
$taskBadSeed = Join-Path $taskScratch 'bad-seed'
[IO.Directory]::CreateDirectory($taskBadSeed) | Out-Null
foreach ($taskFile in @('Initialize.ps1','config.example.json')) { Copy-Item -LiteralPath (Join-Path $taskRepo $taskFile) -Destination $taskBadSeed }
Copy-Item -LiteralPath (Join-Path $taskRepo 'templates') -Destination $taskBadSeed -Recurse
Add-Content -LiteralPath (Join-Path $taskBadSeed 'templates/StarterFutures.py') -Value '# changed in test'
Assert-TaskThrows { & (Join-Path $taskBadSeed 'Initialize.ps1') -EnvFile (Join-Path $taskScratch 'bad.env') -UserDataPath (Join-Path $taskScratch 'bad-data') } 'hash mismatch'
Assert-Task (!(Test-Path -LiteralPath (Join-Path $taskScratch 'bad-data'))) 'Hash refusal created user_data.'

# Mock every Docker call below. Start/Stop rejection tests cannot touch real containers.
$taskMock = [pscustomobject]@{ Calls=[Collections.Generic.List[string]]::new(); Mode='port-conflict'; Plan=$script:taskPlan; Data=$taskData; Scratch=$taskScratch }
$taskDockerMock = {
    $taskArguments = @($args); $taskCall = $taskArguments -join ' '
    $taskMock.Calls.Add($taskCall); $global:LASTEXITCODE = 0
    if ($taskCall -match ' config --format json$') { return ($taskMock.Plan | ConvertTo-Json -Depth 30) }
    if ($taskCall -match ' ps --all --quiet$') {
        if ($taskMock.Mode -in @('wrong-mount','stop-valid')) { return 'test-container' }
        return
    }
    if ($taskArguments[0] -eq 'inspect') {
        $taskMountedData = if ($taskMock.Mode -eq 'wrong-mount') { Join-Path $taskMock.Scratch 'different-user-data' } else { $taskMock.Data }
        return (ConvertTo-Json -InputObject @(@{ Destination='/freqtrade/user_data'; Source=$taskMountedData }) -Compress)
    }
    if ($taskArguments[0] -eq 'ps') { return 'another-project' }
    if ($taskArguments[0] -eq 'run' -and $taskMock.Mode -eq 'native-check') { return }
    if ($taskCall -match ' stop$' -and $taskMock.Mode -eq 'stop-valid') { return }
    throw ('Unexpected Docker action blocked by test: ' + $taskArguments[0])
}.GetNewClosure()
Set-Item -Path Function:docker -Value $taskDockerMock
Assert-TaskThrows { & (Join-Path $taskRepo 'Start.ps1') -EnvFile $taskEnv } 'belongs to another Docker project'
Assert-Task (@($taskMock.Calls | Where-Object { $_ -match ' (up|build|run)( |$)' }).Count -eq 0) 'Port conflict reached a mutating command.'
$taskMock.Mode = 'wrong-mount'; $taskMock.Calls.Clear()
Assert-TaskThrows { & (Join-Path $taskRepo 'Start.ps1') -EnvFile $taskEnv } 'different user_data'
Assert-TaskThrows { & (Join-Path $taskRepo 'Stop.ps1') -EnvFile $taskEnv } 'different user_data'
Assert-Task (@($taskMock.Calls | Where-Object { $_ -match ' (up|build|run|stop)( |$)' }).Count -eq 0) 'Project conflict reached a mutating command.'
$taskMock.Mode = 'native-check'; $taskMock.Calls.Clear()
Test-FreqPilotNativeConfig $taskWorkspace -StartupOnly
Assert-Task ($taskMock.Calls[0] -match '( |^)--startup-only( |$)') 'Native startup flag was split into characters.'

# Invalid config must not prevent stopping the correctly identified project.
$taskConfig = $taskWorkspace.Config
$taskConfig.dry_run = $false
$taskConfig | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $taskData 'config.json') -Encoding utf8
$taskMock.Calls.Clear()
Assert-TaskThrows { & (Join-Path $taskRepo 'Start.ps1') -EnvFile $taskEnv } 'dry_run=true'
Assert-Task ($taskMock.Calls.Count -eq 0) 'Invalid config reached Docker.'
$taskMock.Mode = 'stop-valid'
& (Join-Path $taskRepo 'Stop.ps1') -EnvFile $taskEnv
Assert-Task (@($taskMock.Calls | Where-Object { $_ -match ' stop$' }).Count -eq 1) 'Stop must remain available for its own project with a damaged config.'
$taskConfig.dry_run = $true
foreach ($taskField in @('key','secret')) {
    $taskConfig.exchange.$taskField = 'test-only-credential'
    $taskConfig | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $taskData 'config.json') -Encoding utf8
    Assert-TaskThrows { Read-FreqPilotWorkspace -RepoRoot $taskRepo -EnvFile $taskEnv | Out-Null } 'trading credentials'
    $taskConfig.exchange.$taskField = ''
}
$taskConfig.api_server.password = '__GENERATE__'
$taskConfig | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $taskData 'config.json') -Encoding utf8
Assert-TaskThrows { Read-FreqPilotWorkspace -RepoRoot $taskRepo -EnvFile $taskEnv | Out-Null } 'Generate local API credentials'
Write-Host "Installation checks passed: $script:taskChecks assertions. Docker mutations were mocked; no services started or stopped. Scratch data retained outside Git."
