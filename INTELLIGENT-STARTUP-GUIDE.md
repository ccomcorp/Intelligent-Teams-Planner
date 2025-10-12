# Intelligent Teams Planner - Smart Startup System

## 🚀 Overview

The Intelligent Teams Planner features a sophisticated, OS-agnostic startup system that automatically manages service dependencies, monitors health, and provides intelligent recovery mechanisms. This system ensures reliable deployment across macOS, Linux, Windows, and WSL environments.

## 📁 Components

### Core Scripts
- **`intelligent-startup.py`** - Python-based orchestrator with advanced dependency management
- **`start-intelligent-teams-planner.sh`** - Cross-platform shell script (macOS/Linux/WSL)
- **`start-intelligent-teams-planner.bat`** - Windows batch script

### Service Architecture
```
Infrastructure Layer:
├── PostgreSQL (with pgvector) - Port 5432
├── Redis Cache - Port 6379
└── Neo4j Knowledge Graph - Ports 7474/7687

Application Layer:
├── MCP Server (Core) - Port 7100
├── MCPO Proxy (Microsoft 365) - Port 7105
├── Teams Bot - Port 7110
└── RAG Service - Port 7120
```

## 🔧 Features

### ✅ Intelligent Dependency Management
- **Topological Sorting**: Automatically calculates optimal startup order
- **Parallel Startup**: Services with no interdependencies start simultaneously
- **Graceful Degradation**: Continues startup even if non-critical services fail

### ✅ Health Monitoring
- **HTTP Health Checks**: Validates service endpoints
- **Container Status Monitoring**: Tracks Docker container health
- **Automatic Recovery**: Restarts failed services (with limits)
- **Real-time Status Reports**: Continuous monitoring with detailed feedback

### ✅ Cross-Platform Compatibility
- **macOS**: Native support with Homebrew integration
- **Linux**: Works with all major distributions
- **Windows**: Full Windows 10/11 support with ANSI colors
- **WSL**: Windows Subsystem for Linux compatibility

### ✅ Robust Error Handling
- **Timeout Management**: Prevents hanging during startup
- **Retry Logic**: Configurable retry attempts for failed services
- **Resource Cleanup**: Automatic Docker resource management
- **Detailed Logging**: Comprehensive logs for troubleshooting

## 🛠 Installation & Requirements

### System Requirements
- **Python 3.6+** (Python 3.8+ recommended)
- **Docker & Docker Compose** (Latest versions)
- **Operating System**: macOS 10.14+, Linux (any modern distro), Windows 10+, or WSL2

### Quick Setup

#### macOS/Linux
```bash
# Clone the repository (if not already done)
cd /path/to/intelligent-teams-planner

# Make scripts executable (done automatically)
chmod +x start-intelligent-teams-planner.sh
chmod +x scripts/intelligent-startup.py

# Check system requirements
./start-intelligent-teams-planner.sh --check
```

#### Windows
```batch
# Open Command Prompt or PowerShell as Administrator
cd C:\path\to\intelligent-teams-planner

# Check system requirements
start-intelligent-teams-planner.bat --check
```

## 📖 Usage Guide

### Basic Commands

#### Start All Services
```bash
# macOS/Linux
./start-intelligent-teams-planner.sh

# Windows
start-intelligent-teams-planner.bat
```

#### Check System Requirements
```bash
# macOS/Linux
./start-intelligent-teams-planner.sh --check

# Windows
start-intelligent-teams-planner.bat --check
```

#### View Service Status
```bash
# macOS/Linux
./start-intelligent-teams-planner.sh --status

# Windows
start-intelligent-teams-planner.bat --status
```

#### Stop All Services
```bash
# macOS/Linux
./start-intelligent-teams-planner.sh --stop

# Windows
start-intelligent-teams-planner.bat --stop
```

#### Restart Services
```bash
# macOS/Linux
./start-intelligent-teams-planner.sh --restart

# Windows
start-intelligent-teams-planner.bat --restart
```

#### View Service Logs
```bash
# macOS/Linux
./start-intelligent-teams-planner.sh --logs <service-name>

# Windows
start-intelligent-teams-planner.bat --logs <service-name>

# Examples:
./start-intelligent-teams-planner.sh --logs postgres
./start-intelligent-teams-planner.sh --logs planner-mcp-server
```

#### Clean Up Docker Resources
```bash
# macOS/Linux
./start-intelligent-teams-planner.sh --cleanup

# Windows
start-intelligent-teams-planner.bat --cleanup
```

### Advanced Usage

#### Custom Compose File
```bash
# Edit the script to use a different compose file
# Default: docker-compose.simple.yml
```

#### Environment Configuration
```bash
# Set environment variables before starting
export POSTGRES_PASSWORD=custom_password
export REDIS_PASSWORD=custom_redis_password
export NEO4J_PASSWORD=custom_neo4j_password

./start-intelligent-teams-planner.sh
```

## 🔍 Startup Sequence

The intelligent startup system follows this dependency-aware sequence:

### Phase 1: Infrastructure (Parallel)
- **PostgreSQL**: Database with pgvector extension
- **Redis**: Caching and session management
- **Neo4j**: Knowledge graph database

### Phase 2: Core Application
- **MCP Server**: Core planning service (depends on all infrastructure)

### Phase 3: Integration Services (Parallel)
- **MCPO Proxy**: Microsoft 365 integration (depends on Redis + MCP Server)
- **RAG Service**: Document processing (depends on all infrastructure + MCP Server)

### Phase 4: User Interfaces
- **Teams Bot**: Microsoft Teams interface (depends on MCPO Proxy + MCP Server)

## 📊 Monitoring & Health Checks

### Health Check Endpoints
```
Infrastructure:
- PostgreSQL: Docker health check (pg_isready)
- Redis: Docker health check (redis-cli ping)
- Neo4j: HTTP GET http://localhost:7474/db/data/

Applications:
- MCP Server: HTTP GET http://localhost:7100/health
- MCPO Proxy: HTTP GET http://localhost:7105/health
- Teams Bot: HTTP GET http://localhost:7110/health
- RAG Service: HTTP GET http://localhost:7120/health
```

### Status Indicators
- **✅ Healthy**: Service is running and responding correctly
- **🟡 Starting**: Service is in startup phase
- **❌ Unhealthy**: Service failed health check
- **💀 Failed**: Service exceeded max restart attempts
- **⏹️ Stopped**: Service intentionally stopped

### Log Files
- **`intelligent-startup.log`**: Main orchestrator logs
- **Container logs**: Accessible via `--logs <service>` command

## 🛠 Troubleshooting

### Common Issues

#### Docker Not Running
```bash
# macOS: Start Docker Desktop
open -a Docker

# Linux: Start Docker daemon
sudo systemctl start docker

# Windows: Start Docker Desktop
# Check system tray for Docker icon
```

#### Python Not Found
```bash
# macOS (using Homebrew)
brew install python3

# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3 python3-pip

# CentOS/RHEL
sudo yum install python3 python3-pip

# Windows
# Download from https://python.org
# Ensure "Add Python to PATH" is checked
```

#### Services Failing to Start
```bash
# Check detailed logs
./start-intelligent-teams-planner.sh --logs <failing-service>

# Check Docker resources
docker system df
docker system prune -f  # Clean up if needed

# Restart specific service
docker compose -f docker-compose.simple.yml restart <service>
```

#### Port Conflicts
```bash
# Check what's using the ports
netstat -tuln | grep -E "5432|6379|7100|7105|7110|7120|7474|7687"

# Stop conflicting services or change ports in docker-compose.simple.yml
```

### Recovery Procedures

#### Full System Reset
```bash
# Stop all services and clean up
./start-intelligent-teams-planner.sh --cleanup

# Remove all containers and volumes (CAUTION: Data loss)
docker compose -f docker-compose.simple.yml down -v

# Restart fresh
./start-intelligent-teams-planner.sh
```

#### Individual Service Recovery
```bash
# Restart specific service
docker compose -f docker-compose.simple.yml restart <service-name>

# Rebuild and restart
docker compose -f docker-compose.simple.yml up -d --build <service-name>
```

## 🔧 Configuration

### Service Configuration
Each service can be configured via environment variables in `docker-compose.simple.yml`:

```yaml
environment:
  - DATABASE_URL=postgresql://user:pass@postgres:5432/db
  - REDIS_URL=redis://redis:6379
  - NEO4J_URI=bolt://neo4j:7687
  # Add custom configuration here
```

### Startup Script Configuration
Modify the Python script (`scripts/intelligent-startup.py`) to customize:

- **Health check timeouts**: Adjust `timeout` and `retries` in `HealthCheck` objects
- **Startup delays**: Modify `startup_delay` and `max_startup_time` for services
- **Restart limits**: Change `max_restarts` for automatic recovery
- **Dependencies**: Update service dependency relationships

## 📈 Performance Optimization

### Resource Allocation
```yaml
# Add to docker-compose.simple.yml for resource limits
services:
  service-name:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
        reservations:
          memory: 512M
          cpus: '0.25'
```

### Network Optimization
The system uses a custom bridge network (`itp-simple-network`) for optimal inter-service communication.

## 🔐 Security Considerations

### Default Passwords
Change default passwords in production:
```bash
export POSTGRES_PASSWORD=your_secure_password
export REDIS_PASSWORD=your_redis_password
export NEO4J_PASSWORD=your_neo4j_password
```

### Network Security
- All services run on a dedicated Docker network
- Only necessary ports are exposed to the host
- Consider using reverse proxy for production deployments

## 📚 API Endpoints

Once started, the following endpoints are available:

### Infrastructure
- **Neo4j Browser**: http://localhost:7474
- **PostgreSQL**: localhost:5432 (database client required)
- **Redis**: localhost:6379 (redis-cli required)

### Applications
- **MCP Server Health**: http://localhost:7100/health
- **MCPO Proxy Health**: http://localhost:7105/health
- **Teams Bot Health**: http://localhost:7110/health
- **RAG Service Health**: http://localhost:7120/health

## 🤝 Contributing

To modify or extend the startup system:

1. **Add new services** in the `_define_services()` method
2. **Update dependencies** in the service definitions
3. **Add health checks** for new services
4. **Test thoroughly** across platforms

## 📝 License

This startup system is part of the Intelligent Teams Planner project and follows the same licensing terms.

---

## 🎯 Quick Start Checklist

- [ ] Install Docker Desktop
- [ ] Install Python 3.6+
- [ ] Clone repository
- [ ] Run `./start-intelligent-teams-planner.sh --check`
- [ ] Run `./start-intelligent-teams-planner.sh`
- [ ] Wait for all services to become healthy
- [ ] Access http://localhost:7474 to verify Neo4j
- [ ] Check service status with `--status` command

**Need help?** Check the logs with `--logs <service>` for any failing services.