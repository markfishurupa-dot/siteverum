$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$config = Join-Path $root 'deploy/.env'
$compose = Join-Path $root 'deploy/compose.yaml'

try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker was not found. Install and start Docker Desktop.' }
    docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'The Docker Compose plugin is unavailable.' }
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker is not running. Start Docker Desktop and try again.' }
    if (-not (Test-Path -LiteralPath $config)) {
        $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $database = New-Object byte[] 32
            $administrator = New-Object byte[] 32
            $random.GetBytes($database)
            $random.GetBytes($administrator)
            $dbSecret = [BitConverter]::ToString($database).Replace('-', '')
            $adminSecret = [BitConverter]::ToString($administrator).Replace('-', '')
            $content = "SV_DB_PASSWORD=$dbSecret`nSV_ADMIN_PASSWORD=$adminSecret`n"
            $stream = [System.IO.File]::Open($config, [System.IO.FileMode]::CreateNew)
            try {
                $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
                try { $writer.Write($content) } finally { $writer.Dispose() }
            } finally { $stream.Dispose() }
        } finally { $random.Dispose() }
    }
    docker compose -f $compose up -d --build --wait
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed. Inspect the output above and run docker compose -f deploy/compose.yaml logs.' }
    $address = (docker compose -f $compose port api 8000 | Select-Object -First 1).Trim()
    Write-Host "StreetView is running. Open http://$address/."
    Write-Host "Sign in as admin using SV_ADMIN_PASSWORD in $config. Keep this file private and preserve it."
} catch {
    Write-Error "StreetView setup failed: $_"
    exit 1
}
