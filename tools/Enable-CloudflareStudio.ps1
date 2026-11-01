[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ApiToken,
    [Parameter(Mandatory)][string]$AllowedEmail,
    [string]$AccountId = 'f329bdab4bd752472acbcc5a1311bd07',
    [string]$TunnelId = '21eabb27-8f63-46fe-9bc5-d29a63b7ee8d',
    [string]$ZoneName = 'freqpilot.dev',
    [string]$Subdomain = 'studio'
)
$ErrorActionPreference = 'Stop'
$fqdn = "$Subdomain.$ZoneName"
$headers = @{
    Authorization  = "Bearer $ApiToken"
    'Content-Type' = 'application/json'
}

# 1. Create or reuse Cloudflare Zero Trust Access Application FIRST (fail-closed before opening DNS!)
Write-Host "[1/3] Configuring Cloudflare Access gate for $fqdn (Allow: $AllowedEmail)..."
$appsResp = Invoke-RestMethod -Method Get -Uri "https://api.cloudflare.com/client/v4/accounts/$AccountId/access/apps" -Headers $headers
$app = $appsResp.result | Where-Object { $_.domain -eq $fqdn } | Select-Object -First 1
if (!$app) {
    $appBody = @{
        name                      = 'FreqPilot Studio (MSI 24/7)'
        domain                    = $fqdn
        type                      = 'self_hosted'
        session_duration          = '24h'
        app_launcher_visible      = $true
        auto_redirect_to_identity = $false
    } | ConvertTo-Json -Depth 6
    $app = (Invoke-RestMethod -Method Post -Uri "https://api.cloudflare.com/client/v4/accounts/$AccountId/access/apps" -Headers $headers -Body $appBody).result
}

$pols = @((Invoke-RestMethod -Method Get -Uri "https://api.cloudflare.com/client/v4/accounts/$AccountId/access/apps/$($app.id)/policies" -Headers $headers).result)
$polBody = @{
    name       = 'Owner Email Allowlist'
    decision   = 'allow'
    precedence = 1
    include    = @(@{ email = @{ email = $AllowedEmail } })
} | ConvertTo-Json -Depth 6

foreach ($p in $pols) {
    if ($p.decision -in @('bypass', 'non_identity')) {
        throw "Refusing to open Studio: existing Cloudflare Access policy '$($p.name)' uses unsafe decision '$($p.decision)'."
    }
}
if ($pols.Count -eq 0) {
    [void](Invoke-RestMethod -Method Post -Uri "https://api.cloudflare.com/client/v4/accounts/$AccountId/access/apps/$($app.id)/policies" -Headers $headers -Body $polBody)
} elseif ($pols.Count -eq 1) {
    [void](Invoke-RestMethod -Method Put -Uri "https://api.cloudflare.com/client/v4/accounts/$AccountId/access/apps/$($app.id)/policies/$($pols[0].id)" -Headers $headers -Body $polBody)
} else {
    throw "Refusing to open Studio: multiple ($($pols.Count)) Access policies exist on $fqdn; keep only the single owner-email policy."
}
$verifiedPols = @((Invoke-RestMethod -Method Get -Uri "https://api.cloudflare.com/client/v4/accounts/$AccountId/access/apps/$($app.id)/policies" -Headers $headers).result)
if ($verifiedPols.Count -ne 1 -or $verifiedPols[0].decision -ne 'allow' -or $verifiedPols[0].include.Count -ne 1 -or $verifiedPols[0].include[0].email.email -ne $AllowedEmail) {
    throw "Access policy verification failed for $fqdn; refusing to expose tunnel."
}
Write-Host "      Verified strict owner-only Cloudflare Access gate ($AllowedEmail, App ID: $($app.id))."
# 2. Lookup freqpilot.dev Zone ID and upsert proxied CNAME -> <TunnelId>.cfargotunnel.com
Write-Host "[2/3] Creating proxied DNS CNAME $fqdn -> $TunnelId.cfargotunnel.com..."
$zones = (Invoke-RestMethod -Method Get -Uri "https://api.cloudflare.com/client/v4/zones?name=$ZoneName" -Headers $headers).result
if (!$zones -or $zones.Count -eq 0) { throw "Zone '$ZoneName' not accessible with this API token." }
$zoneId = $zones[0].id

$existingDns = (Invoke-RestMethod -Method Get -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/dns_records?name=$fqdn" -Headers $headers).result
$cnameBody = @{
    type    = 'CNAME'
    name    = $Subdomain
    content = "$TunnelId.cfargotunnel.com"
    proxied = $true
    ttl     = 1
} | ConvertTo-Json
if ($existingDns -and $existingDns.Count -gt 0) {
    $recId = $existingDns[0].id
    [void](Invoke-RestMethod -Method Put -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/dns_records/$recId" -Headers $headers -Body $cnameBody)
} else {
    [void](Invoke-RestMethod -Method Post -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/dns_records" -Headers $headers -Body $cnameBody)
}

Write-Host "[3/3] Activating tunnel ingress ($fqdn -> http://127.0.0.1:8091 on MSI)..."
$ingBody = @{
    config = @{
        ingress = @(
            @{ hostname = $fqdn; service = 'http://127.0.0.1:8091'; originRequest = @{} },
            @{ service = 'http_status:404' }
        )
    }
} | ConvertTo-Json -Depth 6
[void](Invoke-RestMethod -Method Put -Uri "https://api.cloudflare.com/client/v4/accounts/$AccountId/cfd_tunnel/$TunnelId/configurations" -Headers $headers -Body $ingBody)
Write-Host "Done! https://$fqdn is now live behind Cloudflare Access ($AllowedEmail) -> MSI :8091."
