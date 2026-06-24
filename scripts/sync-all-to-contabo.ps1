# PM Studio — copy ALL missing local data to Contabo (no duplicate rows)
#
# Prerequisites:
#   1. Local Docker postgres running (this script starts it if needed)
#   2. SSH tunnel to VPS Postgres OR direct access to VPS :5435
#
# Usage:
#   .\scripts\sync-all-to-contabo.ps1              # preview
#   .\scripts\sync-all-to-contabo.ps1 -Apply        # insert missing rows
#   .\scripts\sync-all-to-contabo.ps1 -Apply -Uploads  # + requirement files

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

# Start local postgres
docker compose up -d postgres | Out-Null
Start-Sleep -Seconds 3

# Remote URL: tunnel on localhost OR direct VPS IP (port 5435 is exposed on Contabo)
$remoteViaTunnel = "postgresql://pmstudio:prod_secure_password_123@127.0.0.1:${RemotePort}/pmstudio"
$remoteDirect = "postgresql://pmstudio:prod_secure_password_123@${VpsHost}:${RemotePort}/pmstudio"

$env:LOCAL_DATABASE_URL = "postgresql://pmstudio:devpassword123@127.0.0.1:5432/pmstudio"

function Test-PgConnection([string]$Url) {
    python -c @"
import sys
try:
    import psycopg2
    psycopg2.connect('$Url').close()
    sys.exit(0)
except Exception as e:
    print(e, file=sys.stderr)
    sys.exit(1)
"@
}

$remoteUrl = $null
if (Test-PgConnection $remoteViaTunnel) {
    $remoteUrl = $remoteViaTunnel
    Write-Host "Remote: localhost:${RemotePort} (SSH tunnel)" -ForegroundColor Green
} elseif (Test-PgConnection $remoteDirect) {
    $remoteUrl = $remoteDirect
    Write-Host "Remote: ${VpsHost}:${RemotePort} (direct)" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Cannot reach VPS Postgres. Open a tunnel in another terminal:" -ForegroundColor Yellow
    Write-Host "  ssh -L ${RemotePort}:127.0.0.1:${RemotePort} ${SshUser}@${VpsHost} -N" -ForegroundColor White
    Write-Host ""
    Write-Host "Then re-run this script." -ForegroundColor Yellow
    exit 1
}

$env:REMOTE_DATABASE_URL = $remoteUrl

pip install psycopg2-binary -q 2>$null

$args = @("scripts/sync-new-to-vps.py")
if (-not $Apply) { $args += "--dry-run" }
if ($Uploads) { $args += "--with-uploads" }

Write-Host ""
python @args
$code = $LASTEXITCODE

if ($code -eq 0 -and -not $Apply) {
    Write-Host ""
    Write-Host "Preview done. To apply:" -ForegroundColor Cyan
    Write-Host "  .\scripts\sync-all-to-contabo.ps1 -Apply -Uploads" -ForegroundColor White
}

exit $code
