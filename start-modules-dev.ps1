
[CmdletBinding()]
param(
    [ValidateRange(1024,65535)][int]$Port = 18090,
    [switch]$Ml,
    [switch]$Gpu
)
$ErrorActionPreference = 'Stop'
$project = 'streetview-v2-modules-dev'
$deploy = Join-Path $PSScriptRoot 'deploy'
$config = Join-Path $deploy '.env.modules-dev'
if (-not (Test-Path -LiteralPath $config)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        throw "Port $Port is busy. Specify an available port."
    }
    $lines = @(
        "SV_DB_PASSWORD=$([guid]::NewGuid().ToString('N'))"
        "SV_ADMIN_PASSWORD=$([guid]::NewGuid().ToString('N'))"
        "SV_PORT=$Port"
    )
    [IO.File]::WriteAllLines($config, $lines)
}
[IO.Directory]::CreateDirectory((Join-Path $deploy 'module-models')) | Out-Null
$compose = @('--env-file', $config, '-p', $project,
    '-f', (Join-Path $deploy 'compose.yaml'), '-f', (Join-Path $deploy 'compose.modules.yaml'))
$started = $false
if ($Ml -or $Gpu) {
    $compose += @('-f', (Join-Path $deploy 'compose.modules-ml.yaml'))
}
if ($Gpu) {
    docker run --rm --gpus all --network none --entrypoint python python:3.13-slim-bookworm -c "print('Container NVIDIA adapter exposed')"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'Docker cannot access an NVIDIA adapter. Starting the CPU runtime.'
        $Gpu = $false
    }
}
if ($Gpu) {
    $compose += @('-f', (Join-Path $deploy 'compose.modules-gpu.yaml'))
    docker compose @compose up --build -d --wait
    if ($LASTEXITCODE -ne 0) {
        Write-Warning 'The GPU configuration could not start. Retrying with the CPU configuration.'
        $compose = $compose[0..($compose.Length - 3)]
    } else {
        $started = $true
    }
}
if (-not $started) {
    docker compose @compose up --build -d --wait
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose could not start StreetView.' }
}
$activePort = ((Get-Content -LiteralPath $config | Where-Object { $_ -like 'SV_PORT=*' }) -split '=', 2)[1]
Write-Host "StreetView is available at http://127.0.0.1:$activePort"
Write-Host "Sign in as admin using SV_ADMIN_PASSWORD in $config"
