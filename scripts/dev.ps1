param(
    [Parameter(Position=0)]
    [string]$Command
)

$ErrorActionPreference = "SilentlyContinue"

function Show-Help {
    Write-Host ""
    Write-Host "Usage: scripts/dev.ps1 <command>" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  deploy    Copy pico/code.py and settings.toml to CIRCUITPY drive"
    Write-Host "  firewall  Create Windows Firewall rule for server port"
    Write-Host "  up        Start monitoring stack (Prometheus + Grafana)"
    Write-Host "  down      Stop monitoring stack"
    Write-Host "  restart   Restart monitoring stack"
    Write-Host "  nuke      Remove everything (containers + volumes)"
    Write-Host ""
}

function Remove-PicoDVContainers {
    docker ps -a --filter "name=picodv-" -q | ForEach-Object { docker rm -f $_ }
}

function Start-Monitoring {
    Write-Host "Starting monitoring stack..." -ForegroundColor Yellow
    docker compose down --remove-orphans 2>$null
    Remove-PicoDVContainers
    docker compose up -d
    Write-Host ""
    Write-Host "Prometheus: http://localhost:9090" -ForegroundColor Cyan
    Write-Host "Grafana:    http://localhost:3000 (admin/admin)" -ForegroundColor Cyan
    Write-Host "Metrics:    http://localhost:8000/metrics" -ForegroundColor Cyan
    Write-Host ""
}

function Stop-Monitoring {
    Write-Host "Stopping monitoring stack..." -ForegroundColor Yellow
    docker compose down --remove-orphans
    Remove-PicoDVContainers
    Write-Host "Stopped." -ForegroundColor Green
}

function Restart-Monitoring {
    Stop-Monitoring
    Start-Monitoring
}

function Remove-Everything {
    Write-Host "Removing everything (containers + volumes)..." -ForegroundColor Red
    docker compose down --remove-orphans --volumes
    Remove-PicoDVContainers
    Write-Host "Nuked." -ForegroundColor Green
}

function Deploy-Pico {
    $drive = Get-Volume | Where-Object { $_.FileSystemLabel -eq "CIRCUITPY" }
    if (-not $drive) {
        Write-Host "ERROR: CIRCUITPY drive not found. Is the Pico W connected?" -ForegroundColor Red
        exit 1
    }
    $driveLetter = $drive.DriveLetter
    $dest = "${driveLetter}:\"

    Write-Host "Deploying to CIRCUITPY ($dest)..." -ForegroundColor Yellow
    Copy-Item "pico\code.py" "${dest}code.py" -Force
    Write-Host "  code.py copied" -ForegroundColor Green

    if (Test-Path ".env") {
        $envContent = Get-Content ".env"
        $ssid = ($envContent | Select-String "^WIFI_SSID=(.+)$").Matches.Groups[1].Value
        $password = ($envContent | Select-String "^WIFI_PASSWORD=(.+)$").Matches.Groups[1].Value

        $localIPs = (Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object { $_.IPAddress -match "^192\.168\." -and $_.InterfaceAlias -notmatch "Loopback|VirtualBox|vEthernet" } |
            Select-Object -First 1).IPAddress

        $serverPort = ($envContent | Select-String "^SERVER_PORT=(.+)$").Matches.Groups[1].Value
        if (-not $serverPort) { $serverPort = "8000" }

        $settingsContent = @"
CIRCUITPY_WIFI_SSID = "$ssid"
CIRCUITPY_WIFI_PASSWORD = "$password"
DISPLAY_SERVER_IP = "$localIPs"
DISPLAY_SERVER_PORT = "$serverPort"
FETCH_INTERVAL = "30"
"@
        Set-Content -Path "${dest}settings.toml" -Value $settingsContent -NoNewline
        Write-Host "  settings.toml generated (server: ${localIPs}:${serverPort})" -ForegroundColor Green
    }

    Write-Host "Deploy complete." -ForegroundColor Green
}

function Set-Firewall {
    $port = "8000"
    if (Test-Path ".env") {
        $envContent = Get-Content ".env"
        $p = ($envContent | Select-String "^SERVER_PORT=(.+)$").Matches.Groups[1].Value
        if ($p) { $port = $p }
    }

    $ruleName = "PicoDV Display Server"
    $existing = Get-NetFirewallRule -DisplayName $ruleName 2>$null
    if ($existing) {
        Write-Host "Firewall rule '$ruleName' already exists." -ForegroundColor Yellow
        return
    }

    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $port `
        -Action Allow `
        -Profile Private,Domain | Out-Null

    Write-Host "Firewall rule created: TCP $port (Private,Domain)" -ForegroundColor Green
}

switch ($Command) {
    "deploy"    { Deploy-Pico }
    "firewall"  { Set-Firewall }
    "up"        { Start-Monitoring }
    "down"      { Stop-Monitoring }
    "restart"   { Restart-Monitoring }
    "nuke"      { Remove-Everything }
    default     { Show-Help }
}
