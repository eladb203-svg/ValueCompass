# Deploys the 15 Edge Functions and sets the function secret SEC_USER_AGENT from .env, without printing it (python-dotenv reads .env; the value goes through a temp file that is deleted).
# Needs Node (npx) and a one-time login:  npx supabase login     (or SUPABASE_ACCESS_TOKEN in the environment).
# Usage (test):        .\scripts\deploy_functions.ps1 -ProjectRef wbhxjcegoobkbnjnuise
# Usage (production):  only after the production checklist in the report: -ProjectRef zwpftrjryxyymrxsprqh
param([Parameter(Mandatory = $true)][string]$ProjectRef)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root "..\valuecompass\.venv\Scripts\python.exe"

$functions = "signup-request", "portfolio-save", "portfolio-delete", "watchlist-add", "watchlist-remove", "broker-import", "support-send",
             "profile-update", "account-delete", "request-company", "smart-search", "notifications-read", "admin-invite", "admin-users", "admin-tickets"
foreach ($f in $functions) {
    Write-Host "deploy $f"
    npx supabase functions deploy $f --project-ref $ProjectRef --no-verify-jwt
    if ($LASTEXITCODE -ne 0) { throw "deploy failed: $f" }
}

$tmp = Join-Path $env:TEMP ("vc_secrets_" + [guid]::NewGuid().ToString("N") + ".env")
try {
    & $py -c "import sys; from dotenv import dotenv_values; v = dotenv_values('.env').get('SEC_USER_AGENT'); assert v, 'SEC_USER_AGENT missing in .env'; open(sys.argv[1], 'w', encoding='utf-8').write('SEC_USER_AGENT=' + v + '\n')" $tmp
    if ($LASTEXITCODE -ne 0) { throw "could not read SEC_USER_AGENT from .env" }
    npx supabase secrets set --env-file $tmp --project-ref $ProjectRef
    if ($LASTEXITCODE -ne 0) { throw "secrets set failed" }
} finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}
Write-Host "done. Optional secrets (set separately): SITE_URL, RESEND_API_KEY, EMAIL_FROM, GEMINI_SEARCH_KEY"
