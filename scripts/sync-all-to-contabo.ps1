# PM Studio — copy ALL missing local data to Contabo (no duplicate rows)
#
# Run from project root:
#   cd F:\knowledgebase\ProjectPreparation\PMS\pm-studio
#   .\scripts\sync-all-to-contabo.ps1              # preview
#   .\scripts\sync-all-to-contabo.ps1 -Apply        # insert missing rows
#   .\scripts\sync-all-to-contabo.ps1 -Apply -Uploads  # + requirement files
#
# VPS Postgres is on port 5435 (direct). SSH tunnel is optional fallback.

param(
    [switch]$Apply,
    [switch]$Uploads,
    [string]$VpsHost = "185.185.80.147",
    [string]$SshUser = "sabya",
    [int]$RemotePort = 5435
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "=== PM Studio: local -> Contabo (all data, no duplicates) ===" -ForegroundColor Cyan
Write-Host "Project: $Root" -ForegroundColor DarkGray

# Start local postgres (must run from project root — compose file is here)
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
docker compose up -d postgres 2>$null | Out-Null
$ErrorActionPreference = $prevEap
Start-Sleep -Seconds 3

$remoteDirect = "postgresql://pmstudio:prod_secure_password_123@${VpsHost}:${RemotePort}/pmstudio"
$remoteViaTunnel = "postgresql://pmstudio:prod_secure_password_123@127.0.0.1:${RemotePort}/pmstudio"
$env:LOCAL_DATABASE_URL = "postgresql://pmstudio:devpassword123@127.0.0.1:5432/pmstudio"

function Test-PgConnection([string]$Url) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $null = python -c @"
import sys
try:
    import psycopg2
    psycopg2.connect(r'$Url').close()
    sys.exit(0)
except Exception:
    sys.exit(1)
"@ 2>$null
    $ok = $LASTEXITCODE -eq 0
    $ErrorActionPreference = $prev
    return $ok
}

$remoteUrl = $null
# Try direct VPS first (Contabo exposes 5435 — no SSH tunnel required)
if (Test-PgConnection $remoteDirect) {
    $remoteUrl = $remoteDirect
    Write-Host "Remote: ${VpsHost}:${RemotePort} (direct)" -ForegroundColor Green
} elseif (Test-PgConnection $remoteViaTunnel) {
    $remoteUrl = $remoteViaTunnel
    Write-Host "Remote: localhost:${RemotePort} (SSH tunnel)" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Cannot reach VPS Postgres." -ForegroundColor Yellow
    Write-Host "  1. Check VPS is up and port ${RemotePort} is open on ${VpsHost}" -ForegroundColor White
    Write-Host "  2. Or open SSH tunnel in a SEPARATE terminal (leave it running):" -ForegroundColor White
    Write-Host "       ssh -L ${RemotePort}:127.0.0.1:${RemotePort} ${SshUser}@${VpsHost} -N" -ForegroundColor White
    Write-Host "  3. Re-run from project folder:" -ForegroundColor White
    Write-Host "       cd $Root" -ForegroundColor White
    Write-Host "       .\scripts\sync-all-to-contabo.ps1" -ForegroundColor White
    exit 1
}

$env:REMOTE_DATABASE_URL = $remoteUrl

$prevEap = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
pip install psycopg2-binary -q 2>$null | Out-Null
$ErrorActionPreference = $prevEap

$pyArgs = @("scripts/sync-new-to-vps.py")
if (-not $Apply) { $pyArgs += "--dry-run" }
if ($Uploads) { $pyArgs += "--with-uploads" }

Write-Host ""
python @pyArgs
$code = $LASTEXITCODE

if ($code -eq 0 -and -not $Apply) {
    Write-Host ""
    Write-Host "Preview done. To apply:" -ForegroundColor Cyan
    Write-Host "  .\scripts\sync-all-to-contabo.ps1 -Apply -Uploads" -ForegroundColor White
}

exit $code
