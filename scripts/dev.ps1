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
    Write-Host "  flash     Install CircuitPython on Pico 2 W (BOOTSEL mode)"
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

function Get-ServerIP {
    <#
    .SYNOPSIS
    Detecta o IP da interface de rede real do host (exclui interfaces virtuais).
    Usa a rota default do sistema pra identificar a interface correta.
    #>

    # Estrategia 1: interface da rota default (mais confiavel)
    $defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
        Sort-Object -Property RouteMetric |
        Select-Object -First 1
    if ($defaultRoute) {
        $ifIndex = $defaultRoute.InterfaceIndex
        $addr = Get-NetIPAddress -InterfaceIndex $ifIndex -AddressFamily IPv4 |
            Where-Object { $_.IPAddress -ne "127.0.0.1" } |
            Select-Object -First 1
        if ($addr) {
            return $addr.IPAddress
        }
    }

    # Estrategia 2: filtrar interfaces virtuais conhecidas
    $virtualPattern = "VirtualBox|vEthernet|Hyper-V|WSL|Docker|Loopback|VMware|Bluetooth"
    $addr = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object {
            $_.IPAddress -notmatch "^(127\.|169\.254\.)" -and
            $_.InterfaceAlias -notmatch $virtualPattern -and
            $_.PrefixOrigin -ne "WellKnown"
        } |
        Sort-Object -Property InterfaceMetric |
        Select-Object -First 1
    if ($addr) {
        return $addr.IPAddress
    }

    Write-Host "WARNING: Could not detect server IP automatically" -ForegroundColor Yellow
    return "0.0.0.0"
}

function Deploy-Pico {
    $drives = @(Get-Volume | Where-Object { $_.FileSystemLabel -eq "CIRCUITPY" })
    if ($drives.Count -eq 0) {
        Write-Host "ERROR: No CIRCUITPY drives found. Is a Pico W connected via USB?" -ForegroundColor Red
        exit 1
    }

    # Detectar configuracao uma vez
    $serverIP = Get-ServerIP
    $serverPort = "8000"
    $ssid = ""
    $password = ""
    $deviceName = "unnamed"

    if (Test-Path ".env") {
        $envContent = Get-Content ".env"
        $s = ($envContent | Select-String "^WIFI_SSID=(.+)$").Matches.Groups[1].Value
        if ($s) { $ssid = $s }
        $p = ($envContent | Select-String "^WIFI_PASSWORD=(.+)$").Matches.Groups[1].Value
        if ($p) { $password = $p }
        $sp = ($envContent | Select-String "^SERVER_PORT=(.+)$").Matches.Groups[1].Value
        if ($sp) { $serverPort = $sp }
        $dn = ($envContent | Select-String "^DEVICE_NAME=(.+)$").Matches.Groups[1].Value
        if ($dn) { $deviceName = $dn }
    }

    Write-Host ""
    Write-Host "Bootstrap config:" -ForegroundColor Cyan
    Write-Host "  Server IP:   $serverIP" -ForegroundColor Cyan
    Write-Host "  Server Port: $serverPort" -ForegroundColor Cyan
    Write-Host "  Wi-Fi SSID:  $ssid" -ForegroundColor Cyan
    Write-Host "  Devices:     $($drives.Count) Pico W(s) detected" -ForegroundColor Cyan
    Write-Host ""

    $count = 0
    foreach ($drive in $drives) {
        $driveLetter = $drive.DriveLetter
        $dest = "${driveLetter}:\"
        $count++

        Write-Host "[$count/$($drives.Count)] Deploying to CIRCUITPY ($dest)..." -ForegroundColor Yellow
        Copy-Item "pico\code.py" "${dest}code.py" -Force
        Write-Host "  code.py copied" -ForegroundColor Green

        $settingsContent = @"
CIRCUITPY_WIFI_SSID = "$ssid"
CIRCUITPY_WIFI_PASSWORD = "$password"
DISPLAY_SERVER_IP = "$serverIP"
DISPLAY_SERVER_PORT = "$serverPort"
FETCH_INTERVAL = "0.5"
DEVICE_NAME = "$deviceName"
DEVICE_POSITION = "auto"
COLOR_DEPTH = "8"
STREAM_PORT = "8001"
"@
        Set-Content -Path "${dest}settings.toml" -Value $settingsContent -NoNewline
        Write-Host "  settings.toml generated" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "Deploy complete: $count Pico W(s) updated (server: ${serverIP}:${serverPort})" -ForegroundColor Green
}

function Set-Firewall {
    $port = "8000"
    if (Test-Path ".env") {
        $envContent = Get-Content ".env"
        $p = ($envContent | Select-String "^SERVER_PORT=(.+)$").Matches.Groups[1].Value
        if ($p) { $port = $p }
    }

    # HTTP server port
    $ruleName = "PicoDV Display Server"
    $existing = Get-NetFirewallRule -DisplayName $ruleName 2>$null
    if ($existing) {
        Write-Host "Firewall rule '$ruleName' already exists." -ForegroundColor Yellow
    } else {
        New-NetFirewallRule `
            -DisplayName $ruleName `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort $port `
            -Action Allow `
            -Profile Private,Domain | Out-Null
        Write-Host "Firewall rule created: TCP $port (Private,Domain)" -ForegroundColor Green
    }

    # Stream server port
    $streamPort = "8001"
    $streamRuleName = "PicoDV Stream Server"
    $existingStream = Get-NetFirewallRule -DisplayName $streamRuleName 2>$null
    if ($existingStream) {
        Write-Host "Firewall rule '$streamRuleName' already exists." -ForegroundColor Yellow
    } else {
        New-NetFirewallRule `
            -DisplayName $streamRuleName `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort $streamPort `
            -Action Allow `
            -Profile Private,Domain | Out-Null
        Write-Host "Firewall rule created: TCP $streamPort (Private,Domain)" -ForegroundColor Green
    }
}

function Flash-Firmware {
    <#
    .SYNOPSIS
    Instala CircuitPython nos Pico 2 W via bootloader UF2.
    Detecta todas as drives RPI-RP2 (modo BOOTSEL) e copia o firmware.
    #>

    $uf2Path = "firmware\circuitpython-pico2w-10.1.4.uf2"
    if (-not (Test-Path $uf2Path)) {
        Write-Host "ERROR: Firmware not found at $uf2Path" -ForegroundColor Red
        Write-Host "Run: curl -L -o firmware/circuitpython-pico2w-10.1.4.uf2 https://downloads.circuitpython.org/bin/raspberry_pi_pico2_w/en_US/adafruit-circuitpython-raspberry_pi_pico2_w-en_US-10.1.4.uf2" -ForegroundColor Yellow
        exit 1
    }

    $drives = @(Get-Volume | Where-Object { $_.FileSystemLabel -eq "RP2350" -or $_.FileSystemLabel -eq "RPI-RP2" })
    if ($drives.Count -eq 0) {
        Write-Host ""
        Write-Host "No Pico 2 W in BOOTSEL mode detected." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "To enter BOOTSEL mode:" -ForegroundColor Cyan
        Write-Host "  1. Hold the BOOTSEL button on the Pico 2 W" -ForegroundColor Cyan
        Write-Host "  2. While holding, plug the USB cable" -ForegroundColor Cyan
        Write-Host "  3. Release the button after plugging in" -ForegroundColor Cyan
        Write-Host "  4. A drive named RPI-RP2 or RP2350 should appear" -ForegroundColor Cyan
        Write-Host "  5. Run 'make flash' again" -ForegroundColor Cyan
        Write-Host ""
        exit 1
    }

    Write-Host ""
    Write-Host "Flashing CircuitPython 10.1.4 to $($drives.Count) Pico 2 W(s)..." -ForegroundColor Yellow
    Write-Host ""

    $count = 0
    foreach ($drive in $drives) {
        $driveLetter = $drive.DriveLetter
        $dest = "${driveLetter}:\"
        $count++

        Write-Host "[$count/$($drives.Count)] Flashing to $dest..." -ForegroundColor Yellow
        Copy-Item $uf2Path "${dest}" -Force
        Write-Host "  CircuitPython copied -- Pico will reboot as CIRCUITPY" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "Flash complete: $count Pico 2 W(s) flashed." -ForegroundColor Green
    Write-Host "Wait 5 seconds for reboot, then run 'make deploy'" -ForegroundColor Cyan
    Write-Host ""
}

switch ($Command) {
    "deploy"    { Deploy-Pico }
    "flash"     { Flash-Firmware }
    "firewall"  { Set-Firewall }
    "up"        { Start-Monitoring }
    "down"      { Stop-Monitoring }
    "restart"   { Restart-Monitoring }
    "nuke"      { Remove-Everything }
    default     { Show-Help }
}
