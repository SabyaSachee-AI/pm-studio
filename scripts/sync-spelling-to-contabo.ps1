# Copy corrected text/JSON from local Postgres to Contabo (updates existing rows).
# Use after fixing spelling locally — unlike sync-all-to-contabo, this UPDATES matching IDs.
#
#   cd F:\knowledgebase\ProjectPreparation\PMS\pm-studio
#   .\scripts\sync-spelling-to-contabo.ps1#   .\scripts\sync-spelling-to-contabo.ps1 -ProjectId 5212c845-c549-4cab-bb2e-9153bc846291

param(
    [string]$ProjectId = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "=== Sync local text/JSON corrections -> Contabo ===" -ForegroundColor Cyan

$prevEap = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
docker compose up -d postgres 2>$null | Out-Null
pip install psycopg2-binary -q 2>$null | Out-Null
$ErrorActionPreference = $prevEap

$env:LOCAL_DATABASE_URL = "postgresql://pmstudio:devpassword123@127.0.0.1:5432/pmstudio"
$env:REMOTE_DATABASE_URL = "postgresql://pmstudio:prod_secure_password_123@185.185.80.147:5435/pmstudio"

$pyArgs = @("scripts/fix-cirtificate-typo.py", "scripts/sync-text-to-contabo.py")
if ($ProjectId) {
    python scripts/fix-cirtificate-typo.py
    python scripts/sync-text-to-contabo.py "--project-id=$ProjectId"
} else {
    python scripts/fix-cirtificate-typo.py
    python scripts/sync-text-to-contabo.py
}

exit $LASTEXITCODE
