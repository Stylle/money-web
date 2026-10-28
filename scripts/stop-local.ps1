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
        $process.WaitForExit(5000) | Out-Null
        Write-Output "Stopped $component (PID $($saved.pid))."
    }
    Remove-Item -LiteralPath $statePath
}
