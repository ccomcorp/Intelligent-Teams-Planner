#!/bin/bash
# Intelligent Teams Planner - Cross-platform startup script
# Supports macOS, Linux, and WSL

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/scripts/intelligent-startup.py"

# Function to print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to find Python
find_python() {
    local python_candidates=("python3" "python" "py")

    for cmd in "${python_candidates[@]}"; do
        if command_exists "$cmd"; then
            local version
            version=$($cmd --version 2>&1)
            if [[ $version =~ Python\ 3\.[6-9]|Python\ 3\.1[0-9] ]]; then
                echo "$cmd"
                return 0
            fi
        fi
    done

    return 1
}

# Function to detect OS
detect_os() {
    case "$(uname -s)" in
        Darwin*)
            echo "macos"
            ;;
        Linux*)
            if grep -q Microsoft /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        CYGWIN*|MINGW*|MSYS*)
            echo "windows"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

# Function to check system requirements
check_requirements() {
    local os
    os=$(detect_os)

    print_color "$BLUE" "🔍 Checking system requirements for $os..."

    # Check Python
    local python_cmd
    if python_cmd=$(find_python); then
        local python_version
        python_version=$($python_cmd --version 2>&1)
        print_color "$GREEN" "✅ Found Python: $python_version ($python_cmd)"
    else
        print_color "$RED" "❌ Python 3.6+ not found!"
        print_color "$YELLOW" "Please install Python 3.6 or higher:"
        case $os in
            macos)
                echo "  brew install python3"
                echo "  or download from https://python.org"
                ;;
            linux)
                echo "  sudo apt-get install python3 python3-pip  # Ubuntu/Debian"
                echo "  sudo yum install python3 python3-pip     # CentOS/RHEL"
                ;;
            wsl)
                echo "  sudo apt-get install python3 python3-pip"
                ;;
        esac
        return 1
    fi

    # Check Docker
    if command_exists docker; then
        if docker --version >/dev/null 2>&1; then
            local docker_version
            docker_version=$(docker --version)
            print_color "$GREEN" "✅ Found Docker: $docker_version"
        else
            print_color "$RED" "❌ Docker daemon not running!"
            print_color "$YELLOW" "Please start Docker Desktop or Docker daemon"
            return 1
        fi
    else
        print_color "$RED" "❌ Docker not found!"
        print_color "$YELLOW" "Please install Docker:"
        case $os in
            macos)
                echo "  Download Docker Desktop from https://docker.com"
                ;;
            linux)
                echo "  curl -fsSL https://get.docker.com -o get-docker.sh"
                echo "  sh get-docker.sh"
                ;;
            wsl)
                echo "  Install Docker Desktop for Windows with WSL2 integration"
                ;;
        esac
        return 1
    fi

    # Check Docker Compose
    if docker compose version >/dev/null 2>&1; then
        local compose_version
        compose_version=$(docker compose version)
        print_color "$GREEN" "✅ Found Docker Compose: $compose_version"
    elif command_exists docker-compose; then
        local compose_version
        compose_version=$(docker-compose --version)
        print_color "$GREEN" "✅ Found Docker Compose: $compose_version"
    else
        print_color "$RED" "❌ Docker Compose not found!"
        print_color "$YELLOW" "Please install Docker Compose (usually included with Docker Desktop)"
        return 1
    fi

    return 0
}

# Function to check if running in project directory
check_project_directory() {
    if [[ ! -f "docker-compose.simple.yml" ]]; then
        print_color "$RED" "❌ docker-compose.simple.yml not found!"
        print_color "$YELLOW" "Please run this script from the project root directory"
        return 1
    fi

    if [[ ! -f "$PYTHON_SCRIPT" ]]; then
        print_color "$RED" "❌ Python startup script not found at: $PYTHON_SCRIPT"
        return 1
    fi

    return 0
}

# Function to create directories if needed
setup_directories() {
    local dirs=("scripts" "logs")

    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            print_color "$GREEN" "✅ Created directory: $dir"
        fi
    done
}

# Function to stop existing services
stop_existing_services() {
    print_color "$YELLOW" "🛑 Stopping any existing services..."

    if docker compose -f docker-compose.simple.yml ps --services 2>/dev/null | grep -q .; then
        docker compose -f docker-compose.simple.yml down --remove-orphans
        print_color "$GREEN" "✅ Stopped existing services"
    else
        print_color "$BLUE" "ℹ️  No existing services to stop"
    fi
}

# Function to clean up Docker resources
cleanup_docker() {
    print_color "$YELLOW" "🧹 Cleaning up Docker resources..."

    # Remove stopped containers
    if docker ps -aq --filter "status=exited" | grep -q .; then
        docker rm $(docker ps -aq --filter "status=exited") 2>/dev/null || true
    fi

    # Clean up unused networks and volumes
    docker network prune -f >/dev/null 2>&1 || true
    docker volume prune -f >/dev/null 2>&1 || true

    print_color "$GREEN" "✅ Docker cleanup completed"
}

# Function to show usage
show_usage() {
    cat << EOF
${GREEN}Intelligent Teams Planner - Startup Script${NC}

${BLUE}Usage:${NC}
    $0 [OPTIONS]

${BLUE}Options:${NC}
    -h, --help              Show this help message
    -c, --check             Only check requirements (don't start services)
    -s, --stop              Stop all services
    -r, --restart           Restart all services
    --cleanup               Clean up Docker resources and stop services
    --status                Show current service status
    --logs <service>        Show logs for specific service

${BLUE}Examples:${NC}
    $0                      Start all services with intelligent monitoring
    $0 --check              Check if system requirements are met
    $0 --restart            Stop and restart all services
    $0 --logs postgres      Show PostgreSQL logs

${BLUE}Services:${NC}
    Infrastructure: postgres, redis, neo4j
    Applications:   planner-mcp-server, mcpo-proxy, teams-bot, rag-service

EOF
}

# Function to show service status
show_status() {
    if [[ ! -f "docker-compose.simple.yml" ]]; then
        print_color "$RED" "❌ Not in project directory"
        return 1
    fi

    print_color "$BLUE" "📊 Current Service Status:"
    docker compose -f docker-compose.simple.yml ps
}

# Function to show logs for a service
show_logs() {
    local service=$1

    if [[ ! -f "docker-compose.simple.yml" ]]; then
        print_color "$RED" "❌ Not in project directory"
        return 1
    fi

    print_color "$BLUE" "📋 Logs for service: $service"
    docker compose -f docker-compose.simple.yml logs --tail=50 -f "$service"
}

# Main function
main() {
    local action="start"
    local target_service=""

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -c|--check)
                action="check"
                shift
                ;;
            -s|--stop)
                action="stop"
                shift
                ;;
            -r|--restart)
                action="restart"
                shift
                ;;
            --cleanup)
                action="cleanup"
                shift
                ;;
            --status)
                action="status"
                shift
                ;;
            --logs)
                action="logs"
                shift
                if [[ $# -gt 0 ]]; then
                    target_service=$1
                    shift
                else
                    print_color "$RED" "❌ --logs requires a service name"
                    exit 1
                fi
                ;;
            *)
                print_color "$RED" "❌ Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # Print header
    print_color "$PURPLE" "
╔══════════════════════════════════════════════════════════════╗
║               Intelligent Teams Planner                     ║
║                  Smart Startup System                       ║
╚══════════════════════════════════════════════════════════════╝
"

    # Execute action
    case $action in
        check)
            check_requirements
            exit $?
            ;;
        stop)
            if check_project_directory; then
                stop_existing_services
            fi
            exit 0
            ;;
        restart)
            if check_project_directory; then
                stop_existing_services
                action="start"  # Continue to start
            else
                exit 1
            fi
            ;;
        cleanup)
            if check_project_directory; then
                stop_existing_services
                cleanup_docker
            fi
            exit 0
            ;;
        status)
            show_status
            exit 0
            ;;
        logs)
            if [[ -z "$target_service" ]]; then
                print_color "$RED" "❌ Service name required for --logs"
                exit 1
            fi
            show_logs "$target_service"
            exit 0
            ;;
        start)
            # Continue with startup process
            ;;
    esac

    # Check requirements first
    if ! check_requirements; then
        exit 1
    fi

    # Check project directory
    if ! check_project_directory; then
        exit 1
    fi

    # Setup directories
    setup_directories

    # Stop any existing services
    stop_existing_services

    # Optional cleanup
    cleanup_docker

    # Find Python and start the intelligent orchestrator
    local python_cmd
    python_cmd=$(find_python)

    print_color "$GREEN" "🚀 Starting Intelligent Teams Planner with Python orchestrator..."
    print_color "$BLUE" "📝 Logs will be written to: intelligent-startup.log"
    print_color "$YELLOW" "⏳ This may take several minutes for first-time setup..."

    # Make Python script executable
    chmod +x "$PYTHON_SCRIPT"

    # Start the Python orchestrator
    exec "$python_cmd" "$PYTHON_SCRIPT"
}

# Run main function with all arguments
main "$@"