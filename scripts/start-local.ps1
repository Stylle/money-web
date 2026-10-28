#requires -Version 7.0
param(
    [string]$Python = '',
    [ValidateRange(1024, 65535)][int]$Port = 8000,
    [string]$TrustedEgressHosts = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$runtimeDir = Join-Path $projectRoot 'data'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$launchConfigPath = Join-Path $runtimeDir 'local-launch.json'
$previousLaunch = if (Test-Path -LiteralPath $launchConfigPath) { Get-Content -LiteralPath $launchConfigPath -Raw | ConvertFrom-Json } else { $null }
if (-not $Python -and $previousLaunch.python) { $Python = $previousLaunch.python }
if (-not $TrustedEgressHosts -and $previousLaunch.trusted_egress_hosts) { $TrustedEgressHosts = $previousLaunch.trusted_egress_hosts }
if (-not $Python) {
    $Python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $Python)) { throw 'Project Python environment missing. Follow README to create .venv, or pass -Python with an existing environment.' }
}
$Python = (Resolve-Path -LiteralPath $Python).Path
& $Python -c 'import fastapi, uvicorn, sqlalchemy, httpx, cryptography, exchange_calendars'
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies are missing. Install backend/requirements.lock in this environment.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Frontend build missing. Run npm ci and npm run build in frontend first.' }

$env:PYTHONPATH = Join-Path $projectRoot 'backend'
$env:WEB_DIR = Join-Path $projectRoot 'frontend\dist'
$env:DATA_DIR = $runtimeDir
$env:PYTHONIOENCODING = 'utf-8'
if ($TrustedEgressHosts) { $env:TRUSTED_EGRESS_HOSTS = $TrustedEgressHosts }

function Start-Component([string]$Name, [string[]]$ComponentArguments) {
    $statePath = Join-Path $runtimeDir "$Name-process.json"
    if (Test-Path -LiteralPath $statePath) {
        $saved = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $existing = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
        if ($existing -and $existing.StartTime.ToUniversalTime().Ticks -eq ([datetime]$saved.started_at).ToUniversalTime().Ticks) {
            Write-Output "$Name is already running (PID $($saved.pid))."
            return
        }
    }
    $process = Start-Process -FilePath $Python -ArgumentList $ComponentArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir "$Name.log") -RedirectStandardError (Join-Path $runtimeDir "$Name-error.log")
    @{ pid = $process.Id; started_at = $process.StartTime.ToUniversalTime().ToString('o'); project = $projectRoot } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
    Write-Output "Started $Name (PID $($process.Id))."
}

$webReady = $false
try { $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2; $webReady = $health.status -eq 'ok' } catch {}
if (-not $webReady) {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is occupied by another service." }
    Start-Component 'web' @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port", '--no-access-log')
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try { $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 1; if ($health.status -eq 'ok') { $webReady = $true; break } } catch {}
        Start-Sleep -Milliseconds 500
    }
}
if (-not $webReady) { throw "Web service did not become ready. Check data/web-error.log." }
Start-Component 'worker' @('-m', 'app.worker')
@{ python = $Python; trusted_egress_hosts = $env:TRUSTED_EGRESS_HOSTS } | ConvertTo-Json | Set-Content -LiteralPath $launchConfigPath -Encoding utf8
Write-Output "Ready: http://127.0.0.1:$Port/ . Services continue running after this command ends. Logs: $runtimeDir . Stop with scripts/stop-local.ps1."
