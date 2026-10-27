$script:FreqPilotOfficialImage = 'freqtradeorg/freqtrade@sha256:9d67afb8eb5f4e1210f4fb067efcbd5e005bd4f1c27f6f3888b8b9fc7f9b5199'

function Read-FreqPilotWorkspace {
    param([Parameter(Mandatory)][string]$RepoRoot, [Parameter(Mandatory)][string]$EnvFile, [switch]$IdentityOnly)
    $taskEnvPath = [IO.Path]::GetFullPath($EnvFile)
    if (!(Test-Path -LiteralPath $taskEnvPath -PathType Leaf)) { throw 'Workspace env file is missing. Run Initialize.ps1 for a new setup.' }
    $taskValues = @{}
    foreach ($taskLine in Get-Content -LiteralPath $taskEnvPath -Encoding utf8) {
        if ($taskLine -match '^\s*(FREQPILOT_[A-Z_]+)=(.*)$') {
            $taskKey = $Matches[1]; $taskValue = $Matches[2].Trim()
            if ($taskValues.ContainsKey($taskKey)) { throw ('Duplicate env entry: ' + $taskKey) }
            if ($taskValue.StartsWith("'") -and $taskValue.EndsWith("'")) { $taskValue = $taskValue.Substring(1, $taskValue.Length - 2).Replace("\'", "'") }
            elseif ($taskValue.StartsWith('"') -and $taskValue.EndsWith('"')) { $taskValue = $taskValue.Substring(1, $taskValue.Length - 2) }
            $taskValues[$taskKey] = $taskValue
        }
    }
    foreach ($taskKey in @('FREQPILOT_USER_DATA', 'FREQPILOT_PROJECT_NAME', 'FREQPILOT_IMAGE')) {
        $taskProcessValue = [Environment]::GetEnvironmentVariable($taskKey, 'Process')
        if ($taskProcessValue) { $taskValues[$taskKey] = $taskProcessValue }
    }
    if (!$taskValues.FREQPILOT_USER_DATA) { throw 'FREQPILOT_USER_DATA must point to the private user_data folder.' }
    $taskDataPath = if ([IO.Path]::IsPathRooted($taskValues.FREQPILOT_USER_DATA)) { [IO.Path]::GetFullPath($taskValues.FREQPILOT_USER_DATA) } else { [IO.Path]::GetFullPath((Join-Path $RepoRoot $taskValues.FREQPILOT_USER_DATA)) }
    $taskProject = if ($taskValues.FREQPILOT_PROJECT_NAME) { $taskValues.FREQPILOT_PROJECT_NAME } else { 'codex-freqtrade' }
    if ($taskProject -notmatch '^[a-z0-9][a-z0-9_-]{1,48}$') { throw 'Invalid FREQPILOT_PROJECT_NAME.' }
    if ($IdentityOnly) { return [pscustomobject]@{ RepoRoot=$RepoRoot; EnvFile=$taskEnvPath; UserData=$taskDataPath; Project=$taskProject; Config=$null } }
    $taskConfigPath = Join-Path $taskDataPath 'config.json'
    $taskConfig = Get-Content -LiteralPath $taskConfigPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($taskConfig.dry_run -ne $true -or $taskConfig.exchange.key -or $taskConfig.exchange.secret -or $taskConfig.exchange.password) { throw 'Only dry_run=true with no exchange trading credentials is supported.' }
    if ($taskConfig.trading_mode -ne 'futures' -or $taskConfig.margin_mode -ne 'isolated' -or $taskConfig.exchange.name -ne 'binance' -or $taskConfig.stake_currency -ne 'USDT') { throw 'This workspace requires Binance USDT-M Futures isolated.' }
    $taskPairs = @($taskConfig.exchange.pair_whitelist)
    if (!$taskPairs.Count -or @($taskPairs | Where-Object { $_ -notin @('BTC/USDT:USDT','ETH/USDT:USDT') }).Count) { throw 'The current research workspace supports BTC/ETH USDT-M only.' }
    if ($taskConfig.api_server.enabled -ne $true -or !$taskConfig.api_server.username) { throw 'Enable the authenticated local API before starting.' }
    foreach ($taskKey in @('password', 'jwt_secret_key', 'ws_token')) {
        if (!$taskConfig.api_server.$taskKey -or $taskConfig.api_server.$taskKey -eq '__GENERATE__') { throw ('Generate local API credentials first: ' + $taskKey) }
    }
    [pscustomobject]@{ RepoRoot=$RepoRoot; EnvFile=$taskEnvPath; UserData=$taskDataPath; Project=$taskProject; Config=$taskConfig }
}

function Assert-FreqPilotProject {
    param([Parameter(Mandatory)]$Workspace)
    $taskIds = @(& docker compose --project-directory $Workspace.RepoRoot --env-file $Workspace.EnvFile -f (Join-Path $Workspace.RepoRoot 'compose.yaml') ps --all --quiet)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect existing workspace containers.' }
    if (!$taskIds.Count) { return }
    $taskMountSets = @(& docker inspect --format '{{json .Mounts}}' @taskIds)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect existing workspace mounts.' }
    foreach ($taskMountSet in $taskMountSets) {
        $taskMounts = @($taskMountSet | ConvertFrom-Json | ForEach-Object { $_ })
        $taskDataMounts = @($taskMounts | Where-Object Destination -eq '/freqtrade/user_data')
        if ($taskDataMounts.Count -ne 1 -or [IO.Path]::GetFullPath($taskDataMounts[0].Source) -ne $Workspace.UserData) { throw 'This project name already belongs to different user_data. Choose another ProjectName; existing services were not changed.' }
    }
}

function Get-FreqPilotComposePlan {
    param([Parameter(Mandatory)]$Workspace)
    $taskRawPlan = & docker compose --project-directory $Workspace.RepoRoot --env-file $Workspace.EnvFile -f (Join-Path $Workspace.RepoRoot 'compose.yaml') config --format json
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose could not resolve the workspace.' }
    $taskPlan = ($taskRawPlan -join "`n") | ConvertFrom-Json
    if ($taskPlan.name -ne $Workspace.Project) { throw 'Resolved Compose project differs from the checked workspace.' }
    foreach ($taskServiceName in @('paper','backtest','research-paper')) {
        $taskService = $taskPlan.services.$taskServiceName
        $taskDataMount = @($taskService.volumes | Where-Object target -eq '/freqtrade/user_data')
        # Compose escapes literal dollar signs when serializing a reusable config plan.
        $taskResolvedSource = if ($taskDataMount.Count -eq 1) { $taskDataMount[0].source.Replace('$$', '$') } else { '' }
        if ($taskDataMount.Count -ne 1 -or [IO.Path]::GetFullPath($taskResolvedSource) -ne $Workspace.UserData) { throw 'Resolved data mount differs from the checked workspace.' }
        foreach ($taskPort in $taskService.ports) {
            if ($taskPort.host_ip -ne '127.0.0.1') { throw 'Publish APIs to loopback only.' }
        }
    }
    if (($taskPlan.services.paper.command -join ' ') -notmatch '--dry-run' -or ($taskPlan.services.'research-paper'.command -join ' ') -notmatch '--dry-run') { throw 'Paper service commands must force --dry-run.' }
    return $taskPlan
}

function Assert-FreqPilotPorts {
    param([Parameter(Mandatory)]$Workspace, [Parameter(Mandatory)]$Plan)
    foreach ($taskPort in @($Plan.services.paper.ports) + @($Plan.services.backtest.ports) + @($Plan.services.'research-paper'.ports)) {
        $taskPublished = [int]$taskPort.published
        $taskOwners = @(& docker ps --filter "publish=$taskPublished" --format '{{.Label "com.docker.compose.project"}}')
        if ($LASTEXITCODE -ne 0) { throw 'Docker is unavailable.' }
        if ($taskOwners.Count) {
            if (@($taskOwners | Where-Object { $_ -ne $Workspace.Project }).Count) { throw "Port $taskPublished belongs to another Docker project. Existing services were not changed." }
            continue
        }
        $taskListener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $taskPublished)
        try { $taskListener.Start() } catch { throw "Port $taskPublished is already in use. Existing services were not changed." } finally { $taskListener.Stop() }
    }
}

function Test-FreqPilotNativeConfig {
    param([Parameter(Mandatory)]$Workspace, [switch]$StartupOnly)
    $taskDataMount = 'type=bind,source=' + $Workspace.UserData + ',target=/freqtrade/user_data,readonly'
    $taskToolsMount = 'type=bind,source=' + (Join-Path $Workspace.RepoRoot 'tools') + ',target=/checks,readonly'
    [string[]]$taskCheckArgs = @()
    if ($StartupOnly) { $taskCheckArgs += '--startup-only' }
    & docker run --rm --network none --entrypoint python --mount $taskDataMount --mount $taskToolsMount $script:FreqPilotOfficialImage /checks/check_workspace.py @taskCheckArgs
    if ($LASTEXITCODE -ne 0) { throw 'Native configuration/strategy validation failed. No services were started.' }
}
