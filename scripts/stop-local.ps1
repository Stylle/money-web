#requires -Version 7.0
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
foreach ($component in @('worker', 'web')) {
    $statePath = Join-Path $projectRoot "data\$component-process.json"
    if (-not (Test-Path -LiteralPath $statePath)) { continue }
    $saved = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($saved.project -ne $projectRoot) { throw 'Process state belongs to another project; refusing to stop it.' }
    $process = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
    if ($process -and $process.StartTime.ToUniversalTime().Ticks -eq ([datetime]$saved.started_at).ToUniversalTime().Ticks) {
        $process.Kill($true)
        if (-not $process.WaitForExit(5000)) { throw "Cannot confirm $component stopped; leases retained." }
        Write-Output "Stopped $component (PID $($saved.pid))."
    }
    Remove-Item -LiteralPath $statePath
}
$launchPath = Join-Path $projectRoot 'data\local-launch.json'
if (Test-Path -LiteralPath $launchPath) {
    $launch = Get-Content -LiteralPath $launchPath -Raw | ConvertFrom-Json
    if ($launch.python -and (Test-Path -LiteralPath $launch.python)) {
        & $launch.python (Join-Path $PSScriptRoot 'release_local_leases.py')
        if ($LASTEXITCODE -ne 0) { throw 'Services stopped, but local task leases could not be released.' }
    }
}
