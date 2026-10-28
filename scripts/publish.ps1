param(
    [string]$Tag = '0.1.0',
    [string]$Image = 'stylle/money-web'
)
$ErrorActionPreference = 'Stop'
if ($Tag -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$') { throw 'Invalid image tag' }
if ($Image -notmatch '^[a-z0-9][a-z0-9_-]+/[a-z0-9][a-z0-9_.-]+$') { throw 'Invalid repository' }
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker CLI is missing. Install Docker or use a configured remote builder.' }
    docker info --format '{{.ServerVersion}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker daemon is unavailable' }
    docker buildx build --platform linux/amd64,linux/arm64 --tag "${Image}:${Tag}" --tag "${Image}:latest" --push .
    if ($LASTEXITCODE -ne 0) { throw 'Image build or Docker Hub push failed' }
    docker buildx imagetools inspect "${Image}:${Tag}"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot verify published manifest' }
} finally { Pop-Location }
