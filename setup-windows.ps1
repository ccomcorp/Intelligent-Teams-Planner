#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Intelligent Teams Planner v2.0 - Windows Setup Script

.DESCRIPTION
    Smart setup script that checks container status and configuration,
    only creates/updates what's necessary for optimal performance.

.PARAMETER Force
    Force recreation of all containers even if they exist

.PARAMETER Environment
    Environment to set up (dev, prod, test)

.EXAMPLE
    .\setup-windows.ps1
    .\setup-windows.ps1 -Force
    .\setup-windows.ps1 -Environment dev
#>

param(
    [switch]$Force,
    [string]$Environment = "prod"
)

# Script configuration
$ErrorActionPreference = "Stop"
$WarningPreference = "Continue"

# Colors for output
$Script:Colors = @{
    Green = "Green"
    Yellow = "Yellow"
    Red = "Red"
    Blue = "Blue"
    Cyan = "Cyan"
    Magenta = "Magenta"
}

# Container configuration
$Script:Containers = @{
    "itp-postgres" = @{
        image = "pgvector/pgvector:pg16"
        healthcheck = "pg_isready -U itp_user -d intelligent_teams_planner"
        port = 5432
    }
    "itp-redis" = @{
        image = "redis:7-alpine"
        healthcheck = "redis-cli --raw incr ping"
        port = 6379
    }
    "itp-openwebui" = @{
        image = "ghcr.io/open-webui/open-webui:main"
        healthcheck = "curl -f http://localhost:8080/health"
        port = 3000
    }
    "itp-mcpo-proxy" = @{
        build = $true
        healthcheck = "curl -f http://localhost:8001/health"
        port = 8001
    }
    "itp-planner-mcp" = @{
        build = $true
        healthcheck = "curl -f http://localhost:8000/health"
        port = 8000
    }
    "itp-teams-bot" = @{
        build = $true
        healthcheck = "curl -f http://localhost:3978/api/messages"
        port = 3978
    }
}

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "=" * 80 -ForegroundColor $Script:Colors.Blue
    Write-Host "  $Message" -ForegroundColor $Script:Colors.Blue
    Write-Host "=" * 80 -ForegroundColor $Script:Colors.Blue
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host "🔄 $Message" -ForegroundColor $Script:Colors.Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor $Script:Colors.Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "⚠️  $Message" -ForegroundColor $Script:Colors.Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor $Script:Colors.Red
}

function Test-Command {
    param([string]$Command)
    try {
        Get-Command $Command -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Test-Prerequisites {
    Write-Header "Checking Prerequisites"

    $missing = @()

    # Check Docker
    if (Test-Command "docker") {
        try {
            $dockerVersion = docker --version
            Write-Success "Docker found: $dockerVersion"

            # Test Docker daemon
            $null = docker info 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Docker daemon is running"
            } else {
                Write-Error "Docker daemon is not running. Please start Docker Desktop."
                return $false
            }
        }
        catch {
            Write-Error "Docker command failed. Please check Docker installation."
            return $false
        }
    } else {
        $missing += "Docker"
    }

    # Check Docker Compose
    if (Test-Command "docker-compose") {
        $composeVersion = docker-compose --version
        Write-Success "Docker Compose found: $composeVersion"
    } elseif (docker compose version 2>$null) {
        $composeVersion = docker compose version
        Write-Success "Docker Compose (v2) found: $composeVersion"
    } else {
        $missing += "Docker Compose"
    }

    # Check Git
    if (Test-Command "git") {
        $gitVersion = git --version
        Write-Success "Git found: $gitVersion"
    } else {
        Write-Warning "Git not found - some features may be limited"
    }

    if ($missing.Count -gt 0) {
        Write-Error "Missing prerequisites: $($missing -join ', ')"
        Write-Host ""
        Write-Host "Please install:"
        foreach ($item in $missing) {
            switch ($item) {
                "Docker" {
                    Write-Host "  - Docker Desktop: https://www.docker.com/products/docker-desktop/"
                }
                "Docker Compose" {
                    Write-Host "  - Docker Compose: https://docs.docker.com/compose/install/"
                }
            }
        }
        return $false
    }

    return $true
}

function Get-ContainerStatus {
    param([string]$ContainerName)

    try {
        $status = docker inspect $ContainerName --format '{{.State.Status}}' 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $status
        }
    }
    catch {}

    return "not-found"
}

function Test-ContainerHealth {
    param([string]$ContainerName, [string]$HealthCheck)

    try {
        $health = docker inspect $ContainerName --format '{{.State.Health.Status}}' 2>$null
        if ($LASTEXITCODE -eq 0 -and $health -eq "healthy") {
            return $true
        }
    }
    catch {}

    return $false
}

function Test-EnvironmentFile {
    Write-Step "Checking environment configuration"

    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Write-Warning ".env file not found. Creating from .env.example"
            Copy-Item ".env.example" ".env"
            Write-Host ""
            Write-Warning "Please edit .env file with your Microsoft credentials:"
            Write-Host "  - MICROSOFT_CLIENT_ID"
            Write-Host "  - MICROSOFT_CLIENT_SECRET"
            Write-Host "  - MICROSOFT_TENANT_ID"
            Write-Host "  - BOT_ID (Teams Bot)"
            Write-Host "  - BOT_PASSWORD (Teams Bot)"
            Write-Host ""
            Read-Host "Press Enter after updating .env file"
        } else {
            Write-Error ".env.example file not found. Please ensure you're in the project root directory."
            return $false
        }
    } else {
        Write-Success ".env file exists"
    }

    return $true
}

function Get-ImageStatus {
    param([string]$ImageName)

    try {
        $null = docker image inspect $ImageName 2>$null
        if ($LASTEXITCODE -eq 0) {
            return "exists"
        }
    }
    catch {}

    return "not-found"
}

function Invoke-ContainerAnalysis {
    Write-Header "Analyzing Container Status"

    $analysis = @{}

    foreach ($containerName in $Script:Containers.Keys) {
        $config = $Script:Containers[$containerName]
        $status = Get-ContainerStatus $containerName
        $healthy = Test-ContainerHealth $containerName $config.healthcheck

        $analysis[$containerName] = @{
            status = $status
            healthy = $healthy
            needsUpdate = $false
            needsRecreate = $false
        }

        # Determine what action is needed
        if ($status -eq "not-found") {
            $analysis[$containerName].needsRecreate = $true
            Write-Warning "$containerName - Not found (will create)"
        }
        elseif ($status -eq "exited") {
            $analysis[$containerName].needsRecreate = $true
            Write-Warning "$containerName - Stopped (will restart)"
        }
        elseif ($status -eq "running" -and -not $healthy) {
            $analysis[$containerName].needsRecreate = $true
            Write-Warning "$containerName - Unhealthy (will recreate)"
        }
        elseif ($status -eq "running" -and $healthy) {
            # Check if image needs update for built containers
            if ($config.build) {
                $analysis[$containerName].needsUpdate = $true
                Write-Success "$containerName - Running (will check for updates)"
            } else {
                Write-Success "$containerName - Running and healthy"
            }
        }
        else {
            $analysis[$containerName].needsRecreate = $true
            Write-Warning "$containerName - Status: $status (will recreate)"
        }
    }

    return $analysis
}

function Invoke-ServiceUpdate {
    param([hashtable]$Analysis)

    Write-Header "Updating Services"

    $servicesToBuild = @()
    $servicesToStart = @()
    $allHealthy = $true

    foreach ($containerName in $Analysis.Keys) {
        $info = $Analysis[$containerName]
        $config = $Script:Containers[$containerName]

        if ($Force -or $info.needsRecreate -or $info.needsUpdate) {
            if ($config.build) {
                $servicesToBuild += $containerName.Replace("itp-", "")
            } else {
                $servicesToStart += $containerName.Replace("itp-", "")
            }
        }
    }

    # Build services that need building
    if ($servicesToBuild.Count -gt 0) {
        Write-Step "Building updated services: $($servicesToBuild -join ', ')"
        try {
            $buildArgs = @("docker-compose", "build")
            if ($Force) { $buildArgs += "--no-cache" }
            $buildArgs += $servicesToBuild

            & $buildArgs[0] $buildArgs[1..($buildArgs.Length-1)]
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Build completed successfully"
            } else {
                Write-Error "Build failed"
                $allHealthy = $false
            }
        }
        catch {
            Write-Error "Build error: $($_.Exception.Message)"
            $allHealthy = $false
        }
    }

    # Start/restart services
    $allServices = ($servicesToBuild + $servicesToStart) | Sort-Object -Unique
    if ($allServices.Count -gt 0 -or $Force) {
        Write-Step "Starting services"
        try {
            if ($Force) {
                docker-compose down
                docker-compose up -d
            } else {
                docker-compose up -d $allServices
            }

            if ($LASTEXITCODE -eq 0) {
                Write-Success "Services started successfully"
            } else {
                Write-Error "Failed to start services"
                $allHealthy = $false
            }
        }
        catch {
            Write-Error "Service start error: $($_.Exception.Message)"
            $allHealthy = $false
        }
    }

    return $allHealthy
}

function Wait-ForHealth {
    Write-Header "Waiting for Services to be Healthy"

    $maxWait = 180  # 3 minutes
    $interval = 5
    $elapsed = 0

    while ($elapsed -lt $maxWait) {
        $allHealthy = $true
        $statuses = @()

        foreach ($containerName in $Script:Containers.Keys) {
            $config = $Script:Containers[$containerName]
            $status = Get-ContainerStatus $containerName
            $healthy = Test-ContainerHealth $containerName $config.healthcheck

            if ($status -eq "running" -and $healthy) {
                $statuses += "✅ $containerName"
            } elseif ($status -eq "running") {
                $statuses += "🔄 $containerName (starting)"
                $allHealthy = $false
            } else {
                $statuses += "❌ $containerName ($status)"
                $allHealthy = $false
            }
        }

        Clear-Host
        Write-Host "Health Check Status (${elapsed}s / ${maxWait}s):" -ForegroundColor $Script:Colors.Blue
        Write-Host ""
        foreach ($status in $statuses) {
            Write-Host "  $status"
        }

        if ($allHealthy) {
            Write-Host ""
            Write-Success "All services are healthy!"
            return $true
        }

        Start-Sleep $interval
        $elapsed += $interval
    }

    Write-Error "Timeout waiting for services to become healthy"
    return $false
}

function Show-ServiceStatus {
    Write-Header "Service Status & Access URLs"

    Write-Host "Container Status:" -ForegroundColor $Script:Colors.Blue
    foreach ($containerName in $Script:Containers.Keys) {
        $config = $Script:Containers[$containerName]
        $status = Get-ContainerStatus $containerName
        $healthy = Test-ContainerHealth $containerName $config.healthcheck

        $statusIcon = if ($status -eq "running" -and $healthy) { "✅" }
                     elseif ($status -eq "running") { "🔄" }
                     else { "❌" }

        Write-Host "  $statusIcon $containerName - $status" -ForegroundColor $(
            if ($status -eq "running" -and $healthy) { $Script:Colors.Green }
            elseif ($status -eq "running") { $Script:Colors.Yellow }
            else { $Script:Colors.Red }
        )
    }

    Write-Host ""
    Write-Host "Access URLs:" -ForegroundColor $Script:Colors.Blue
    Write-Host "  🌐 OpenWebUI (Main Interface):  http://localhost:3000" -ForegroundColor $Script:Colors.Green
    Write-Host "  🔧 MCPO Proxy API:             http://localhost:8001" -ForegroundColor $Script:Colors.Green
    Write-Host "  ⚙️  MCP Server API:             http://localhost:8000" -ForegroundColor $Script:Colors.Green
    Write-Host "  🤖 Teams Bot Endpoint:         http://localhost:3978" -ForegroundColor $Script:Colors.Green
    Write-Host "  🗄️  PostgreSQL:                 localhost:5432" -ForegroundColor $Script:Colors.Green
    Write-Host "  🔴 Redis:                       localhost:6379" -ForegroundColor $Script:Colors.Green

    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor $Script:Colors.Magenta
    Write-Host "  1. Open http://localhost:3000 in your browser"
    Write-Host "  2. Configure OpenWebUI with MCPO Proxy endpoint"
    Write-Host "  3. Start conversational Teams Planner management!"
}

function Show-Logs {
    Write-Header "Recent Service Logs"

    Write-Host "Checking for any errors in recent logs..." -ForegroundColor $Script:Colors.Blue
    Write-Host ""

    foreach ($containerName in $Script:Containers.Keys) {
        $status = Get-ContainerStatus $containerName
        if ($status -eq "running") {
            Write-Host "📋 $containerName logs:" -ForegroundColor $Script:Colors.Cyan
            try {
                $logs = docker logs $containerName --tail 3 2>&1
                if ($logs) {
                    $logs | ForEach-Object { Write-Host "    $_" }
                } else {
                    Write-Host "    (no recent logs)"
                }
            }
            catch {
                Write-Host "    (unable to fetch logs)"
            }
            Write-Host ""
        }
    }
}

# Main execution
function Main {
    Write-Header "Intelligent Teams Planner v2.0 - Windows Setup"
    Write-Host "Environment: $Environment" -ForegroundColor $Script:Colors.Cyan
    Write-Host "Force Mode: $Force" -ForegroundColor $Script:Colors.Cyan

    # Check prerequisites
    if (-not (Test-Prerequisites)) {
        exit 1
    }

    # Check environment file
    if (-not (Test-EnvironmentFile)) {
        exit 1
    }

    # Analyze current state
    $analysis = Invoke-ContainerAnalysis

    # Update services if needed
    $success = Invoke-ServiceUpdate $analysis
    if (-not $success) {
        Write-Error "Service update failed"
        exit 1
    }

    # Wait for health
    $healthy = Wait-ForHealth
    if (-not $healthy) {
        Write-Warning "Some services may not be fully healthy yet"
        Show-Logs
    }

    # Show final status
    Show-ServiceStatus

    Write-Host ""
    Write-Success "Setup completed! Intelligent Teams Planner v2.0 is ready for use."

    if ($healthy) {
        Write-Host ""
        Write-Host "🚀 All systems operational! Ready for conversational project management." -ForegroundColor $Script:Colors.Green
    }
}

# Execute main function
try {
    Main
}
catch {
    Write-Error "Setup failed: $($_.Exception.Message)"
    Write-Host ""
    Write-Host "For support, check:" -ForegroundColor $Script:Colors.Yellow
    Write-Host "  - Container logs: docker-compose logs"
    Write-Host "  - Service status: docker-compose ps"
    Write-Host "  - GitHub Issues: https://github.com/your-repo/issues"
    exit 1
}