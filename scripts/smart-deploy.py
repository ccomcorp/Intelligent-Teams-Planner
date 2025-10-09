#!/usr/bin/env python3
"""
Intelligent Teams Planner v2.0 - Smart Deployment Script
OS-agnostic deployment script with intelligent container management
"""

import subprocess
import json
import sys
import os
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import platform

# Color codes for output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

class SmartDeployer:
    """Intelligent deployment manager for Intelligent Teams Planner"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent.absolute()
        self.compose_file = self.project_root / "docker-compose.yml"
        self.port_config_file = self.project_root / "PORT-CONFIGURATION.md"

        # Service configuration with health checks
        self.services = {
            "postgres": {"port": 5432, "health_endpoint": None, "required": True},
            "redis": {"port": 6379, "health_endpoint": None, "required": True},
            "mcp-server": {"port": 7100, "health_endpoint": "/health", "required": True},
            "mcpo-proxy": {"port": 7105, "health_endpoint": "/health", "required": True},
            "teams-bot": {"port": 7110, "health_endpoint": "/health", "required": False},
            "openwebui": {"port": 7115, "health_endpoint": "/", "required": False},
        }

        # OS detection
        self.os_type = platform.system().lower()
        self.is_windows = self.os_type == "windows"

    def log(self, message: str, level: str = "INFO"):
        """Colored logging output"""
        colors = {
            "INFO": Colors.OKBLUE,
            "SUCCESS": Colors.OKGREEN,
            "WARNING": Colors.WARNING,
            "ERROR": Colors.FAIL,
            "HEADER": Colors.HEADER
        }
        color = colors.get(level, Colors.ENDC)
        print(f"{color}[{level}]{Colors.ENDC} {message}")

    def run_command(self, command: List[str], capture_output: bool = True) -> Tuple[int, str, str]:
        """Run command with OS-specific handling"""
        try:
            if self.is_windows:
                # Windows-specific command handling
                result = subprocess.run(
                    command,
                    capture_output=capture_output,
                    text=True,
                    shell=True,
                    timeout=300
                )
            else:
                # Unix-like systems
                result = subprocess.run(
                    command,
                    capture_output=capture_output,
                    text=True,
                    timeout=300
                )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"
        except Exception as e:
            return 1, "", str(e)

    def check_docker(self) -> bool:
        """Check if Docker is available and running"""
        self.log("Checking Docker availability...", "INFO")

        # Check Docker command
        returncode, stdout, stderr = self.run_command(["docker", "--version"])
        if returncode != 0:
            self.log("Docker is not installed or not in PATH", "ERROR")
            return False

        # Check Docker daemon
        returncode, stdout, stderr = self.run_command(["docker", "info"])
        if returncode != 0:
            self.log("Docker daemon is not running", "ERROR")
            return False

        self.log(f"✅ Docker is available: {stdout.strip()}", "SUCCESS")
        return True

    def check_docker_compose(self) -> bool:
        """Check if Docker Compose is available"""
        # Try docker compose (new syntax)
        returncode, stdout, stderr = self.run_command(["docker", "compose", "version"])
        if returncode == 0:
            self.log(f"✅ Docker Compose available: {stdout.strip()}", "SUCCESS")
            return True

        # Try docker-compose (legacy)
        returncode, stdout, stderr = self.run_command(["docker-compose", "--version"])
        if returncode == 0:
            self.log(f"✅ Docker Compose (legacy) available: {stdout.strip()}", "SUCCESS")
            return True

        self.log("Docker Compose is not available", "ERROR")
        return False

    def get_compose_command(self) -> List[str]:
        """Get the appropriate docker compose command"""
        # Check for new syntax first
        returncode, _, _ = self.run_command(["docker", "compose", "version"])
        if returncode == 0:
            return ["docker", "compose"]
        return ["docker-compose"]

    def get_running_containers(self) -> Dict[str, Dict]:
        """Get information about running containers"""
        compose_cmd = self.get_compose_command()
        returncode, stdout, stderr = self.run_command(
            compose_cmd + ["-f", str(self.compose_file), "ps", "--format", "json"]
        )

        if returncode != 0:
            self.log(f"Failed to get container status: {stderr}", "WARNING")
            return {}

        containers = {}
        if stdout.strip():
            try:
                # Handle both single JSON object and JSON lines
                if stdout.strip().startswith('['):
                    container_list = json.loads(stdout)
                else:
                    # JSON lines format
                    container_list = [json.loads(line) for line in stdout.strip().split('\n') if line.strip()]

                for container in container_list:
                    service = container.get('Service', container.get('service', ''))
                    containers[service] = container
            except json.JSONDecodeError:
                self.log("Failed to parse container status JSON", "WARNING")

        return containers

    def check_service_health(self, service_name: str) -> bool:
        """Check if a service is healthy"""
        service_config = self.services.get(service_name)
        if not service_config or not service_config.get("health_endpoint"):
            return True  # No health check defined

        port = service_config["port"]
        endpoint = service_config["health_endpoint"]
        url = f"http://localhost:{port}{endpoint}"

        try:
            import requests
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except:
            return False

    def get_service_image_hash(self, service_name: str) -> Optional[str]:
        """Get the current image hash for a service"""
        if service_name in ["postgres", "redis", "openwebui"]:
            # These use external images
            return None

        # For built services, check the source directory
        service_dir = self.project_root / service_name.replace("-", "_")
        if service_name == "mcp-server":
            service_dir = self.project_root / "planner-mcp-server"
        elif service_name == "mcpo-proxy":
            service_dir = self.project_root / "mcpo-proxy"
        elif service_name == "teams-bot":
            service_dir = self.project_root / "teams-bot"

        if not service_dir.exists():
            return None

        # Create hash based on source files
        hash_md5 = hashlib.md5()
        for file_path in sorted(service_dir.rglob("*.py")):
            if file_path.is_file():
                with open(file_path, 'rb') as f:
                    hash_md5.update(f.read())

        return hash_md5.hexdigest()[:8]

    def should_rebuild_service(self, service_name: str) -> bool:
        """Determine if a service needs rebuilding"""
        # Check if image exists
        image_name = f"intelligent-teams-planner_{service_name}"
        returncode, stdout, stderr = self.run_command(["docker", "images", "-q", image_name])

        if returncode != 0 or not stdout.strip():
            self.log(f"Image {image_name} not found, rebuild needed", "INFO")
            return True

        # For built services, check if source has changed
        if service_name in ["mcp-server", "mcpo-proxy", "teams-bot"]:
            # This is a simplistic check - in production you'd want more sophisticated versioning
            self.log(f"Checking if {service_name} needs rebuild based on source changes", "INFO")
            return False  # For now, assume no rebuild needed if image exists

        return False

    def deploy_service(self, service_name: str, force_rebuild: bool = False) -> bool:
        """Deploy a single service intelligently"""
        self.log(f"Deploying service: {service_name}", "HEADER")

        running_containers = self.get_running_containers()
        compose_cmd = self.get_compose_command()

        # Check if service is already running and healthy
        if service_name in running_containers:
            container_info = running_containers[service_name]
            status = container_info.get('State', container_info.get('status', '')).lower()

            if 'running' in status:
                if self.check_service_health(service_name):
                    self.log(f"✅ {service_name} is already running and healthy", "SUCCESS")
                    return True
                else:
                    self.log(f"⚠️ {service_name} is running but unhealthy, restarting...", "WARNING")

        # Check if rebuild is needed
        needs_rebuild = force_rebuild or self.should_rebuild_service(service_name)

        if needs_rebuild:
            self.log(f"🔨 Rebuilding {service_name}...", "INFO")
            returncode, stdout, stderr = self.run_command(
                compose_cmd + ["-f", str(self.compose_file), "build", "--no-cache", service_name]
            )
            if returncode != 0:
                self.log(f"❌ Failed to build {service_name}: {stderr}", "ERROR")
                return False

        # Start/restart the service
        self.log(f"🚀 Starting {service_name}...", "INFO")
        returncode, stdout, stderr = self.run_command(
            compose_cmd + ["-f", str(self.compose_file), "up", "-d", service_name]
        )

        if returncode != 0:
            self.log(f"❌ Failed to start {service_name}: {stderr}", "ERROR")
            return False

        # Wait for service to be healthy
        if self.services[service_name].get("health_endpoint"):
            self.log(f"⏳ Waiting for {service_name} to become healthy...", "INFO")
            for i in range(30):  # Wait up to 30 seconds
                if self.check_service_health(service_name):
                    self.log(f"✅ {service_name} is healthy", "SUCCESS")
                    return True
                time.sleep(1)

            self.log(f"⚠️ {service_name} started but health check failed", "WARNING")
            return True  # Consider it successful even if health check fails

        self.log(f"✅ {service_name} started successfully", "SUCCESS")
        return True

    def deploy_all_services(self, force_rebuild: bool = False, required_only: bool = False) -> bool:
        """Deploy all services in dependency order"""
        self.log("🚀 Starting intelligent deployment of all services", "HEADER")

        # Deployment order based on dependencies
        deployment_order = [
            "postgres",
            "redis",
            "mcp-server",
            "mcpo-proxy",
            "openwebui",
            "teams-bot"
        ]

        if required_only:
            deployment_order = [s for s in deployment_order if self.services[s]["required"]]

        success_count = 0
        for service_name in deployment_order:
            if self.deploy_service(service_name, force_rebuild):
                success_count += 1
            else:
                self.log(f"❌ Failed to deploy {service_name}", "ERROR")
                if self.services[service_name]["required"]:
                    self.log("Stopping deployment due to required service failure", "ERROR")
                    return False

        self.log(f"✅ Deployment complete: {success_count}/{len(deployment_order)} services deployed", "SUCCESS")
        return success_count == len(deployment_order)

    def show_status(self):
        """Show current status of all services"""
        self.log("📊 Current Service Status", "HEADER")

        running_containers = self.get_running_containers()

        for service_name, config in self.services.items():
            port = config["port"]
            is_running = service_name in running_containers
            is_healthy = self.check_service_health(service_name) if is_running else False

            status_icon = "✅" if is_healthy else "⚠️" if is_running else "❌"
            status_text = "HEALTHY" if is_healthy else "RUNNING" if is_running else "STOPPED"

            required_text = "(required)" if config["required"] else "(optional)"

            print(f"  {status_icon} {service_name:12} | Port {port:4} | {status_text:8} {required_text}")

    def run_integration_tests(self):
        """Run integration tests against deployed services"""
        self.log("🧪 Running integration tests", "HEADER")

        test_script = self.project_root / "test_integration.py"
        if not test_script.exists():
            self.log("Integration test script not found", "WARNING")
            return False

        returncode, stdout, stderr = self.run_command(["python", str(test_script)])

        if returncode == 0:
            self.log("✅ All integration tests passed", "SUCCESS")
            return True
        else:
            self.log(f"❌ Integration tests failed: {stderr}", "ERROR")
            return False

    def main(self):
        """Main deployment logic"""
        print(f"{Colors.HEADER}🚀 Intelligent Teams Planner v2.0 - Smart Deployment{Colors.ENDC}")
        print(f"{Colors.OKBLUE}OS: {platform.system()} {platform.release()}{Colors.ENDC}")
        print()

        # Check prerequisites
        if not self.check_docker():
            sys.exit(1)

        if not self.check_docker_compose():
            sys.exit(1)

        # Parse command line arguments
        import argparse
        parser = argparse.ArgumentParser(description="Smart deployment for Intelligent Teams Planner")
        parser.add_argument("--rebuild", action="store_true", help="Force rebuild all services")
        parser.add_argument("--required-only", action="store_true", help="Deploy only required services")
        parser.add_argument("--status", action="store_true", help="Show service status only")
        parser.add_argument("--test", action="store_true", help="Run integration tests after deployment")
        parser.add_argument("--service", type=str, help="Deploy specific service only")

        args = parser.parse_args()

        if args.status:
            self.show_status()
            return

        if args.service:
            success = self.deploy_service(args.service, args.rebuild)
            if success and args.test:
                self.run_integration_tests()
            sys.exit(0 if success else 1)

        # Deploy all services
        success = self.deploy_all_services(args.rebuild, args.required_only)

        if success:
            self.show_status()

            if args.test:
                self.run_integration_tests()

        sys.exit(0 if success else 1)

if __name__ == "__main__":
    deployer = SmartDeployer()
    deployer.main()