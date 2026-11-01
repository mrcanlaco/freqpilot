[CmdletBinding()]
param(
    [string]$SshHost = 'storage-msi-vpn',
    [string]$WslDistro = 'DaoVangServer',
    [string]$RemoteRoot = '/opt/freqpilot',
    [string]$LocalUserData = '',
    [switch]$BuildUi,
    [switch]$SkipDataSync,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'

function Invoke-SshStdin {
    param(
        [Parameter(Mandatory)][string]$RemoteCommand,
        [Parameter(Mandatory)][byte[]]$InputBytes
    )
    $psi = [Diagnostics.ProcessStartInfo]::new('ssh')
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.Arguments = "$SshHost `"$RemoteCommand`""
    $proc = [Diagnostics.Process]::Start($psi)
    $outTask = $proc.StandardOutput.ReadToEndAsync()
    $errTask = $proc.StandardError.ReadToEndAsync()
    $proc.StandardInput.BaseStream.Write($InputBytes, 0, $InputBytes.Length)
    $proc.StandardInput.Close()
    $proc.WaitForExit()
    $stdout = $outTask.GetAwaiter().GetResult()
    $stderr = $errTask.GetAwaiter().GetResult()
    if ($proc.ExitCode -ne 0) {
        throw "Remote MSI step failed (exit $($proc.ExitCode)):`n$stderr`n$stdout"
    }
    return $stdout
}

function Invoke-MsiBash {
    param(
        [Parameter(Mandatory)][string]$Script,
        [byte[]]$StdinPayload = $null
    )
    $lfScript = $Script.Replace("`r`n", "`n")
    if ($null -eq $StdinPayload) {
        return Invoke-SshStdin -RemoteCommand "wsl -d $WslDistro -- bash -s" -InputBytes ([Text.Encoding]::UTF8.GetBytes($lfScript))
    }
    $remoteTmp = "/tmp/fp_deploy_$([Guid]::NewGuid().ToString('N')).sh"
    $wrapped = "trap 'rm -f $remoteTmp' EXIT`n" + $lfScript
    [void](Invoke-SshStdin -RemoteCommand "wsl -d $WslDistro -- tee $remoteTmp" -InputBytes ([Text.Encoding]::UTF8.GetBytes($wrapped)))
    return Invoke-SshStdin -RemoteCommand "wsl -d $WslDistro -- bash $remoteTmp" -InputBytes $StdinPayload
}

# Resolve local user_data from .env if not explicitly provided
if (!$LocalUserData) {
    $envPath = Join-Path $PSScriptRoot '.env'
    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath -Encoding utf8) {
            if ($line -match '^\s*FREQPILOT_USER_DATA=(.*)$') {
                $val = $Matches[1].Trim().Trim("'`"")
                $LocalUserData = if ([IO.Path]::IsPathRooted($val)) { [IO.Path]::GetFullPath($val) } else { [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $val)) }
            }
        }
    }
}

# 1. Ensure ui/dist is fresh
$distIndex = Join-Path $PSScriptRoot 'ui/dist/index.html'
$needUiBuild = $BuildUi -or !(Test-Path -LiteralPath $distIndex)
if (!$needUiBuild) {
    $distTime = (Get-Item -LiteralPath $distIndex).LastWriteTimeUtc
    $newerSrc = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'ui/src') -Recurse -File |
        Where-Object { $_.Name -notin @('auto-imports.d.ts', 'components.d.ts') -and $_.LastWriteTimeUtc -gt $distTime } |
        Select-Object -First 1
    if ($newerSrc) {
        Write-Host "[1/5] Detected newer UI source ($($newerSrc.Name)); rebuilding ui/dist..."
        $needUiBuild = $true
    }
}
if ($needUiBuild) {
    if ($DryRun) {
        Write-Host "[1/5] [DryRun] Would build ui/dist with vite."
    } else {
        Write-Host "[1/5] Building UI bundle (ui/dist)..."
        & pnpm --dir (Join-Path $PSScriptRoot 'ui') exec vite build --outDir dist-next
        if ($LASTEXITCODE -ne 0) { throw 'UI build failed.' }
        $taskDist = Join-Path $PSScriptRoot 'ui/dist'
        $taskNext = Join-Path $PSScriptRoot 'ui/dist-next'
        [IO.Directory]::CreateDirectory($taskDist) | Out-Null
        Get-ChildItem -LiteralPath $taskNext -Force | Where-Object Name -ne 'index.html' | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $taskDist -Recurse -Force
        }
        Copy-Item -LiteralPath (Join-Path $taskNext 'index.html') -Destination (Join-Path $taskDist 'index.next.html') -Force
        Move-Item -LiteralPath (Join-Path $taskDist 'index.next.html') -Destination (Join-Path $taskDist 'index.html') -Force
    }
} else {
    Write-Host "[1/5] ui/dist is up to date."
}

# 2. Check local git status vs origin/main
$unpushed = @(& git -C $PSScriptRoot log origin/main..HEAD --oneline 2>$null)
if ($unpushed.Count -gt 0) {
    Write-Warning "You have $($unpushed.Count) local commit(s) not pushed to origin/main yet. Run 'git push origin main' first so MSI pulls them."
}

# 3. Git pull on MSI + sync site/
Write-Host "[2/5] Pulling latest Git commit on MSI ($RemoteRoot/repo) & updating landing site..."
if (!$DryRun) {
    $gitOut = Invoke-MsiBash -Script @"
set -euo pipefail
cd "$RemoteRoot/repo"
git fetch origin main
git merge --ff-only origin/main
cp -f site/index.html site/compare.html site/demo.html "$RemoteRoot/site/"
git log -n 1 --oneline
"@
    Write-Host "      MSI repo at: $($gitOut.Trim())"
}

# 4. Ship gitignored ui/dist atomically
Write-Host "[3/5] Shipping compiled ui/dist to MSI..."
if (!$DryRun) {
    $tmpTar = [IO.Path]::GetTempFileName() + '.tar.gz'
    try {
        & tar -czf $tmpTar -C (Join-Path $PSScriptRoot 'ui/dist') .
        if ($LASTEXITCODE -ne 0) { throw 'Failed to archive ui/dist.' }
        $payload = [IO.File]::ReadAllBytes($tmpTar)
        [void](Invoke-MsiBash -StdinPayload $payload -Script @"
set -euo pipefail
rm -rf "$RemoteRoot/repo/ui/dist-next"
mkdir -p "$RemoteRoot/repo/ui/dist-next" "$RemoteRoot/repo/ui/dist"
tar -xzf - -C "$RemoteRoot/repo/ui/dist-next"
cp -rf "$RemoteRoot/repo/ui/dist-next"/* "$RemoteRoot/repo/ui/dist"/
rm -rf "$RemoteRoot/repo/ui/dist-next"
"@)
    } finally {
        Remove-Item -LiteralPath $tmpTar -Force -ErrorAction SilentlyContinue
    }
}

# 5. Add-only, SHA-256-verified sync of new research assets into isolated studio_user_data
if (!$SkipDataSync -and $LocalUserData -and (Test-Path -LiteralPath $LocalUserData)) {
    Write-Host "[4/5] Checking add-only research assets against MSI ($RemoteRoot/studio_user_data)..."
    $remoteInventoryRaw = Invoke-MsiBash -Script @"
set -euo pipefail
UD="$RemoteRoot/studio_user_data"
mkdir -p "`$UD"
cd "`$UD"
for rel in data/binance/futures/*.feather strategies/*.py freqpilot/research/*.json freqpilot/notes/* freqpilot/presets/* freqpilot/runs/* freqpilot/sensitivity/* freqpilot/walk_forward/*; do
    if [ -e "`$rel" ]; then echo "`$rel"; fi
done
"@
    $remoteSet = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($line in ($remoteInventoryRaw -split "`n")) {
        $trimmed = $line.Trim()
        if ($trimmed) { [void]$remoteSet.Add($trimmed) }
    }

    $toCopy = [Collections.Generic.List[string]]::new()
    $verifiedRuns = [Collections.Generic.Dictionary[string, string]]::new()

    $filePatterns = @(
        @{ Dir = 'data/binance/futures'; Filter = '*.feather' },
        @{ Dir = 'strategies'; Filter = '*.py' },
        @{ Dir = 'freqpilot/research'; Filter = '*.json' },
        @{ Dir = 'freqpilot/notes'; Filter = '*' }
    )
    foreach ($pat in $filePatterns) {
        $fullDir = Join-Path $LocalUserData $pat.Dir
        if (Test-Path -LiteralPath $fullDir) {
            foreach ($f in Get-ChildItem -LiteralPath $fullDir -Filter $pat.Filter -File) {
                $rel = "$($pat.Dir)/$($f.Name)"
                if (!$remoteSet.Contains($rel)) { $toCopy.Add($rel) }
            }
        }
    }

    $dirGroups = @('freqpilot/presets', 'freqpilot/runs', 'freqpilot/sensitivity', 'freqpilot/walk_forward')
    foreach ($grp in $dirGroups) {
        $fullGrp = Join-Path $LocalUserData $grp
        if (Test-Path -LiteralPath $fullGrp) {
            foreach ($item in Get-ChildItem -LiteralPath $fullGrp) {
                $rel = "$grp/$($item.Name)"
                if ($remoteSet.Contains($rel)) { continue }
                if ($grp -eq 'freqpilot/runs' -and $item.PSIsContainer) {
                    $recFile = Join-Path $item.FullName 'record.json'
                    $zipFile = Join-Path $item.FullName 'artifact.zip'
                    if (Test-Path -LiteralPath $recFile) {
                        $rec = Get-Content -LiteralPath $recFile -Raw -Encoding utf8 | ConvertFrom-Json
                        if ($rec.status -in @('pending', 'running')) { continue }
                        if ($rec.artifact_sha256 -and (Test-Path -LiteralPath $zipFile)) {
                            $actualHash = (Get-FileHash -LiteralPath $zipFile -Algorithm SHA256).Hash.ToLowerInvariant()
                            if ($actualHash -ne $rec.artifact_sha256.ToLowerInvariant()) {
                                throw "SHA-256 mismatch on local run $($item.Name): expected $($rec.artifact_sha256), got $actualHash"
                            }
                            $verifiedRuns[$rel] = $actualHash
                        }
                    }
                }
                $toCopy.Add($rel)
            }
        }
    }

    if ($toCopy.Count -eq 0) {
        Write-Host "      No new strategies, data files, or runs to add (0 items)."
    } elseif ($DryRun) {
        Write-Host "      [DryRun] Would add $($toCopy.Count) new item(s) (add-only, 0 overwrites):"
        $toCopy | Select-Object -First 20 | ForEach-Object { Write-Host "        + $_" }
    } else {
        Write-Host "      Transferring $($toCopy.Count) new item(s) (add-only, verifying $($verifiedRuns.Count) SHA-256 bundle(s))..."
        $tmpList = [IO.Path]::GetTempFileName()
        $tmpDataTar = [IO.Path]::GetTempFileName() + '.tar.gz'
        try {
            [IO.File]::WriteAllLines($tmpList, $toCopy, [Text.UTF8Encoding]::new($false))
            & tar -czf $tmpDataTar -C $LocalUserData -T $tmpList
            if ($LASTEXITCODE -ne 0) { throw 'Failed to create add-only user_data archive.' }
            $hashChecks = ($verifiedRuns.GetEnumerator() | ForEach-Object {
                "echo '$($_.Value)  `$STAGE/$($_.Key)/artifact.zip' | sha256sum -c - >/dev/null"
            }) -join "`n"
            $payload = [IO.File]::ReadAllBytes($tmpDataTar)
            [void](Invoke-MsiBash -StdinPayload $payload -Script @"
set -euo pipefail
UD="$RemoteRoot/studio_user_data"
STAGE="`$UD/.sync_staging_`$`$"
rm -rf "`$STAGE"
mkdir -p "`$STAGE"
tar -xzf - -C "`$STAGE"
$hashChecks
cd "`$STAGE"
find . -mindepth 1 | while read -r p; do
    rel="`$(echo "`$p" | sed 's|^\./||')"
    if [ -d "`$STAGE/`$rel" ]; then
        mkdir -p "`$UD/`$rel"
    elif [ -f "`$STAGE/`$rel" ] && [ ! -e "`$UD/`$rel" ]; then
        mkdir -p "`$(dirname "`$UD/`$rel")"
        mv -n "`$STAGE/`$rel" "`$UD/`$rel"
    fi
done
rm -rf "`$STAGE"
chown -R 1000:1000 "`$UD"
"@)
            Write-Host "      Added $($toCopy.Count) new item(s) and verified SHA-256 hashes on MSI."
        } finally {
            Remove-Item -LiteralPath $tmpList, $tmpDataTar -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host "[4/5] Skipped user_data sync."
}

# 6. Rebuild & restart isolated Studio services (:8091 & :8095), leaving :8090 live paper bot untouched
Write-Host "[5/5] Rebuilding & restarting isolated Studio stack on MSI (:8091 & :8095)..."
if (!$DryRun) {
    $healthOut = Invoke-MsiBash -Script @"
set -euo pipefail
cd "$RemoteRoot/repo"
docker compose --project-directory "$RemoteRoot/repo" --env-file "$RemoteRoot/repo/.env.studio" -f "$RemoteRoot/repo/compose.studio.yaml" build backtest
docker compose --project-directory "$RemoteRoot/repo" --env-file "$RemoteRoot/repo/.env.studio" -f "$RemoteRoot/repo/compose.studio.yaml" up -d
for i in `$(seq 1 25); do
    if curl -fsS http://127.0.0.1:8091/api/v1/studio/probe 2>/dev/null; then
        echo ""
        break
    fi
    sleep 1
done
docker ps --format "  {{.Names}} -> {{.Ports}} ({{.Status}})" | grep -E "8088|8090|8091|8095" || true
"@
    Write-Host $healthOut.TrimEnd()
}
Write-Host "Done! MSI Studio (:8091), Research Paper (:8095), and Landing (:8088) are updated."
