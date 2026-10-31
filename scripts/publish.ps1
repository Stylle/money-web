param(
    [string]$Tag = '0.2.2',
    [string]$Image = 'stylle/money-web',
    [string]$WslDistro = '',
    [string]$DockerConfig = ''
)
$ErrorActionPreference = 'Stop'
if ($Tag -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$') { throw 'Invalid image tag' }
if ($Image -notmatch '^[a-z0-9][a-z0-9_-]+/[a-z0-9][a-z0-9_.-]+$') { throw 'Invalid repository' }
$projectRoot = Split-Path $PSScriptRoot -Parent
if ($WslDistro -and $WslDistro -notmatch '^[A-Za-z0-9_.-]+$') { throw 'Invalid WSL distribution name' }
function Invoke-ReleaseDocker([string[]]$DockerArguments) {
    $arguments = @()
    if ($DockerConfig) { $arguments += @('--config', $DockerConfig) }
    $arguments += $DockerArguments
    if ($WslDistro) {
        & wsl.exe -d $WslDistro -u root --cd $script:linuxProjectRoot --exec docker @arguments
    } else {
        & docker @arguments
    }
    if ($LASTEXITCODE -ne 0) { throw 'Docker command failed; publication is not confirmed.' }
}
Push-Location $projectRoot
try {
    if ($WslDistro) {
        $script:linuxProjectRoot = (& wsl.exe -d $WslDistro -u root --cd / --exec wslpath -a $projectRoot).Trim()
        if ($LASTEXITCODE -ne 0 -or $script:linuxProjectRoot -notmatch '^/') { throw 'Cannot resolve project path in WSL' }
    } elseif (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker CLI missing. For the existing Linux VM, pass -WslDistro wusaqi-build.'
    }
    Invoke-ReleaseDocker -DockerArguments @('info', '--format', '{{.ServerVersion}}')
    Invoke-ReleaseDocker -DockerArguments @('buildx', 'build', '--platform', 'linux/amd64,linux/arm64', '--tag', "${Image}:${Tag}", '--tag', "${Image}:latest", '--push', '.')
    $verificationArguments = @('scripts/verify-image.py', '--image', $Image, '--tags', $Tag, 'latest')
    if ($DockerConfig) { $verificationArguments += @('--docker-config', $DockerConfig) }
    if ($WslDistro) {
        & wsl.exe -d $WslDistro -u root --cd $script:linuxProjectRoot --exec python3 @verificationArguments
    } else {
        & python @verificationArguments
    }
    if ($LASTEXITCODE -ne 0) { throw 'Registry verification failed; publication is not confirmed.' }
} finally { Pop-Location }
