#!/bin/bash
set -eo pipefail

# Intelligent Teams Planner v2.0 - Mac/Linux Setup Script
# Smart setup script that checks container status and configuration,
# only creates/updates what's necessary for optimal performance.

# Script configuration
SCRIPT_VERSION="2.0.0"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Container configuration (for older bash compatibility)
CONTAINER_NAMES="itp-postgres itp-redis itp-openwebui itp-mcpo-proxy itp-planner-mcp itp-teams-bot"

get_container_config() {
    case "$1" in
        "itp-postgres") echo "pgvector/pgvector:pg16|pg_isready -U itp_user -d intelligent_teams_planner|5432" ;;
        "itp-redis") echo "redis:7-alpine|redis-cli --raw incr ping|6379" ;;
        "itp-openwebui") echo "ghcr.io/open-webui/open-webui:main|curl -f http://localhost:8080/health|3000" ;;
        "itp-mcpo-proxy") echo "BUILD|curl -f http://localhost:8001/health|8001" ;;
        "itp-planner-mcp") echo "BUILD|curl -f http://localhost:8000/health|8000" ;;
        "itp-teams-bot") echo "BUILD|curl -f http://localhost:3978/api/messages|3978" ;;
    esac
}

# Utility functions
write_header() {
    local message="$1"
    echo ""
    echo -e "${BLUE}$(printf '=%.0s' {1..80})${NC}"
    echo -e "${BLUE}  $message${NC}"
    echo -e "${BLUE}$(printf '=%.0s' {1..80})${NC}"
    echo ""
}

write_step() {
    echo -e "${CYAN}🔄 $1${NC}"
}

write_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

write_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

write_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
check_prerequisites() {
    write_header "Checking Prerequisites"

    local missing=()

    # Check Docker
    if command_exists docker; then
        local docker_version
        docker_version=$(docker --version)
        write_success "Docker found: $docker_version"

        # Test Docker daemon
        if docker info >/dev/null 2>&1; then
            write_success "Docker daemon is running"
        else
            write_error "Docker daemon is not running. Please start Docker."
            return 1
        fi
    else
        missing+=("Docker")
    fi

    # Check Docker Compose
    if command_exists docker-compose; then
        local compose_version
        compose_version=$(docker-compose --version)
        write_success "Docker Compose found: $compose_version"
    elif docker compose version >/dev/null 2>&1; then
        local compose_version
        compose_version=$(docker compose version)
        write_success "Docker Compose (v2) found: $compose_version"
    else
        missing+=("Docker Compose")
    fi

    # Check curl (for health checks)
    if command_exists curl; then
        write_success "curl found"
    else
        write_warning "curl not found - health checks may be limited"
    fi

    # Check Git
    if command_exists git; then
        local git_version
        git_version=$(git --version)
        write_success "Git found: $git_version"
    else
        write_warning "Git not found - some features may be limited"
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        write_error "Missing prerequisites: ${missing[*]}"
        echo ""
        echo "Please install:"
        for item in "${missing[@]}"; do
            case "$item" in
                "Docker")
                    echo "  - Docker: https://docs.docker.com/get-docker/"
                    if [[ "$OSTYPE" == "darwin"* ]]; then
                        echo "    macOS: brew install --cask docker"
                    else
                        echo "    Linux: Follow Docker installation guide for your distribution"
                    fi
                    ;;
                "Docker Compose")
                    echo "  - Docker Compose: https://docs.docker.com/compose/install/"
                    ;;
            esac
        done
        return 1
    fi

    return 0
}

# Get container status
get_container_status() {
    local container_name="$1"
    local status
    status=$(docker inspect "$container_name" --format '{{.State.Status}}' 2>/dev/null || echo "not-found")
    echo "$status"
}

# Test container health
test_container_health() {
    local container_name="$1"
    local health_check="$2"

    # First check if container has health status
    local health_status
    health_status=$(docker inspect "$container_name" --format '{{.State.Health.Status}}' 2>/dev/null || echo "none")

    if [ "$health_status" = "healthy" ]; then
        return 0
    elif [ "$health_status" = "none" ]; then
        # No built-in health check, test manually
        if docker exec "$container_name" bash -c "$health_check" >/dev/null 2>&1; then
            return 0
        fi
    fi

    return 1
}

# Check environment file
check_environment_file() {
    write_step "Checking environment configuration"

    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            write_warning ".env file not found. Creating from .env.example"
            cp ".env.example" ".env"
            echo ""
            write_warning "Please edit .env file with your Microsoft credentials:"
            echo "  - MICROSOFT_CLIENT_ID"
            echo "  - MICROSOFT_CLIENT_SECRET"
            echo "  - MICROSOFT_TENANT_ID"
            echo "  - BOT_ID (Teams Bot)"
            echo "  - BOT_PASSWORD (Teams Bot)"
            echo ""
            read -p "Press Enter after updating .env file..."
        else
            write_error ".env.example file not found. Please ensure you're in the project root directory."
            return 1
        fi
    else
        write_success ".env file exists"
    fi

    return 0
}

# Analyze container status
analyze_containers() {
    write_header "Analyzing Container Status"

    local needs_update=false

    for container_name in $CONTAINER_NAMES; do
        IFS='|' read -r image health_check port <<< "$(get_container_config "$container_name")"

        local status
        status=$(get_container_status "$container_name")

        local healthy=false
        if [ "$status" = "running" ]; then
            if test_container_health "$container_name" "$health_check"; then
                healthy=true
            fi
        fi

        local action="none"

        # Determine what action is needed
        case "$status" in
            "not-found")
                action="create"
                needs_update=true
                write_warning "$container_name - Not found (will create)"
                ;;
            "exited")
                action="restart"
                needs_update=true
                write_warning "$container_name - Stopped (will restart)"
                ;;
            "running")
                if [ "$healthy" = true ]; then
                    if [ "$image" = "BUILD" ]; then
                        action="check_update"
                        write_success "$container_name - Running (will check for updates)"
                    else
                        action="none"
                        write_success "$container_name - Running and healthy"
                    fi
                else
                    action="recreate"
                    needs_update=true
                    write_warning "$container_name - Unhealthy (will recreate)"
                fi
                ;;
            *)
                action="recreate"
                needs_update=true
                write_warning "$container_name - Status: $status (will recreate)"
                ;;
        esac

        # Export analysis for this container
        export "ANALYSIS_${container_name//-/_}=$action"
    done

    # Set global flag for whether updates are needed
    NEEDS_UPDATE="$needs_update"
}

# Update services
update_services() {
    write_header "Updating Services"

    local services_to_build=()
    local services_to_start=()
    local all_healthy=true

    # Collect services that need action
    for container_name in $CONTAINER_NAMES; do
        local action_var="ANALYSIS_${container_name//-/_}"
        local action="${!action_var}"

        IFS='|' read -r image health_check port <<< "$(get_container_config "$container_name")"
        local service_name="${container_name#itp-}"

        case "$action" in
            "create"|"recreate"|"check_update")
                if [ "$image" = "BUILD" ]; then
                    services_to_build+=("$service_name")
                else
                    services_to_start+=("$service_name")
                fi
                ;;
            "restart")
                services_to_start+=("$service_name")
                ;;
        esac
    done

    # Build services that need building
    if [ ${#services_to_build[@]} -gt 0 ] || [ "$FORCE_MODE" = "true" ]; then
        write_step "Building services: ${services_to_build[*]}"
        local build_args=("docker-compose" "build")

        if [ "$FORCE_MODE" = "true" ]; then
            build_args+=("--no-cache")
        fi

        if [ ${#services_to_build[@]} -gt 0 ]; then
            build_args+=("${services_to_build[@]}")
        fi

        if "${build_args[@]}"; then
            write_success "Build completed successfully"
        else
            write_error "Build failed"
            all_healthy=false
        fi
    fi

    # Start/restart services
    local all_services=()
    for service in "${services_to_build[@]}" "${services_to_start[@]}"; do
        if [[ ! " ${all_services[*]} " =~ " $service " ]]; then
            all_services+=("$service")
        fi
    done

    if [ ${#all_services[@]} -gt 0 ] || [ "$FORCE_MODE" = "true" ]; then
        write_step "Starting services"

        if [ "$FORCE_MODE" = "true" ]; then
            docker-compose down
            docker-compose up -d
        else
            docker-compose up -d "${all_services[@]}"
        fi

        if [ $? -eq 0 ]; then
            write_success "Services started successfully"
        else
            write_error "Failed to start services"
            all_healthy=false
        fi
    fi

    return $([ "$all_healthy" = true ] && echo 0 || echo 1)
}

# Wait for health
wait_for_health() {
    write_header "Waiting for Services to be Healthy"

    local max_wait=180  # 3 minutes
    local interval=5
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        local all_healthy=true
        local statuses=()

        for container_name in $CONTAINER_NAMES; do
            IFS='|' read -r image health_check port <<< "$(get_container_config "$container_name")"

            local status
            status=$(get_container_status "$container_name")

            local healthy=false
            if [ "$status" = "running" ]; then
                if test_container_health "$container_name" "$health_check"; then
                    healthy=true
                fi
            fi

            if [ "$status" = "running" ] && [ "$healthy" = true ]; then
                statuses+=("✅ $container_name")
            elif [ "$status" = "running" ]; then
                statuses+=("🔄 $container_name (starting)")
                all_healthy=false
            else
                statuses+=("❌ $container_name ($status)")
                all_healthy=false
            fi
        done

        # Clear screen and show status
        clear
        echo -e "${BLUE}Health Check Status (${elapsed}s / ${max_wait}s):${NC}"
        echo ""
        for status in "${statuses[@]}"; do
            echo "  $status"
        done

        if [ "$all_healthy" = true ]; then
            echo ""
            write_success "All services are healthy!"
            return 0
        fi

        sleep $interval
        elapsed=$((elapsed + interval))
    done

    write_error "Timeout waiting for services to become healthy"
    return 1
}

# Show service status
show_service_status() {
    write_header "Service Status & Access URLs"

    echo -e "${BLUE}Container Status:${NC}"
    for container_name in $CONTAINER_NAMES; do
        IFS='|' read -r image health_check port <<< "$(get_container_config "$container_name")"

        local status
        status=$(get_container_status "$container_name")

        local healthy=false
        if [ "$status" = "running" ]; then
            if test_container_health "$container_name" "$health_check"; then
                healthy=true
            fi
        fi

        local status_icon color
        if [ "$status" = "running" ] && [ "$healthy" = true ]; then
            status_icon="✅"
            color="${GREEN}"
        elif [ "$status" = "running" ]; then
            status_icon="🔄"
            color="${YELLOW}"
        else
            status_icon="❌"
            color="${RED}"
        fi

        echo -e "  $status_icon $container_name - $status ${color}${NC}"
    done

    echo ""
    echo -e "${BLUE}Access URLs:${NC}"
    echo -e "  🌐 ${GREEN}OpenWebUI (Main Interface):  http://localhost:3000${NC}"
    echo -e "  🔧 ${GREEN}MCPO Proxy API:             http://localhost:8001${NC}"
    echo -e "  ⚙️  ${GREEN}MCP Server API:             http://localhost:8000${NC}"
    echo -e "  🤖 ${GREEN}Teams Bot Endpoint:         http://localhost:3978${NC}"
    echo -e "  🗄️  ${GREEN}PostgreSQL:                 localhost:5432${NC}"
    echo -e "  🔴 ${GREEN}Redis:                       localhost:6379${NC}"

    echo ""
    echo -e "${MAGENTA}Next Steps:${NC}"
    echo "  1. Open http://localhost:3000 in your browser"
    echo "  2. Configure OpenWebUI with MCPO Proxy endpoint"
    echo "  3. Start conversational Teams Planner management!"
}

# Show recent logs
show_logs() {
    write_header "Recent Service Logs"

    echo -e "${BLUE}Checking for any errors in recent logs...${NC}"
    echo ""

    for container_name in $CONTAINER_NAMES; do
        local status
        status=$(get_container_status "$container_name")

        if [ "$status" = "running" ]; then
            echo -e "${CYAN}📋 $container_name logs:${NC}"
            if docker logs "$container_name" --tail 3 2>/dev/null; then
                :
            else
                echo "    (unable to fetch logs)"
            fi | sed 's/^/    /'
            echo ""
        fi
    done
}

# Show usage
show_usage() {
    echo "Usage: $0 [environment] [force]"
    echo ""
    echo "Arguments:"
    echo "  environment    Environment to set up (dev, prod, test) [default: prod]"
    echo "  force         Force recreation of all containers [default: false]"
    echo ""
    echo "Examples:"
    echo "  $0                    # Setup production environment"
    echo "  $0 dev                # Setup development environment"
    echo "  $0 prod true          # Force recreation of all containers"
}

# Main execution
main() {
    # Set parameters
    local ENVIRONMENT="${1:-prod}"
    local FORCE_MODE="${2:-false}"

    # Handle help request
    if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
        show_usage
        exit 0
    fi

    write_header "Intelligent Teams Planner v2.0 - Mac/Linux Setup"
    echo -e "${CYAN}Environment: $ENVIRONMENT${NC}"
    echo -e "${CYAN}Force Mode: $FORCE_MODE${NC}"

    # Check prerequisites
    if ! check_prerequisites; then
        exit 1
    fi

    # Check environment file
    if ! check_environment_file; then
        exit 1
    fi

    # Analyze current state
    analyze_containers

    # Update services if needed
    if ! update_services; then
        write_error "Service update failed"
        exit 1
    fi

    # Wait for health
    if ! wait_for_health; then
        write_warning "Some services may not be fully healthy yet"
        show_logs
    fi

    # Show final status
    show_service_status

    echo ""
    write_success "Setup completed! Intelligent Teams Planner v2.0 is ready for use."

    echo ""
    echo -e "${GREEN}🚀 All systems operational! Ready for conversational project management.${NC}"
}

# Trap for cleanup
trap 'echo -e "\n${YELLOW}Setup interrupted${NC}"' INT TERM

# Execute main function
main "$@"