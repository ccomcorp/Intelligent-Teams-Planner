#!/usr/bin/env python3
"""
Intelligent Teams Planner - Smart Startup Script
OS-agnostic startup orchestrator with dependency management and health monitoring
"""

import asyncio
import json
import logging
import os
import platform
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import urllib.request
import urllib.error

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('intelligent-startup.log')
    ]
)
logger = logging.getLogger(__name__)

class ServiceStatus(Enum):
    PENDING = "pending"
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    FAILED = "failed"
    STOPPED = "stopped"

@dataclass
class HealthCheck:
    url: str
    timeout: int = 10
    retries: int = 3
    expected_status: int = 200

@dataclass
class Service:
    name: str
    container_name: str
    dependencies: List[str] = field(default_factory=list)
    health_check: Optional[HealthCheck] = None
    startup_delay: int = 5
    max_startup_time: int = 120
    status: ServiceStatus = ServiceStatus.PENDING
    start_time: Optional[float] = None
    restart_count: int = 0
    max_restarts: int = 3

class DockerManager:
    """Cross-platform Docker management"""

    def __init__(self):
        self.docker_cmd = self._find_docker_command()
        self.compose_cmd = self._find_compose_command()

    def _find_docker_command(self) -> str:
        """Find Docker command based on OS"""
        commands = ['docker', 'podman']
        for cmd in commands:
            try:
                subprocess.run([cmd, '--version'], capture_output=True, check=True)
                logger.info(f"Found container runtime: {cmd}")
                return cmd
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        raise RuntimeError("No container runtime found (docker/podman)")

    def _find_compose_command(self) -> List[str]:
        """Find Docker Compose command"""
        # Try docker compose (new) first, then docker-compose (legacy)
        compose_variants = [
            [self.docker_cmd, 'compose'],
            ['docker-compose']
        ]

        for cmd in compose_variants:
            try:
                subprocess.run(cmd + ['--version'], capture_output=True, check=True)
                logger.info(f"Found compose command: {' '.join(cmd)}")
                return cmd
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        raise RuntimeError("No Docker Compose found")

    def is_service_running(self, container_name: str) -> bool:
        """Check if a container is running"""
        try:
            result = subprocess.run(
                [self.docker_cmd, 'ps', '--filter', f'name={container_name}', '--format', '{{.Names}}'],
                capture_output=True, text=True, check=True
            )
            return container_name in result.stdout
        except subprocess.CalledProcessError:
            return False

    def get_service_status(self, container_name: str) -> str:
        """Get detailed container status"""
        try:
            result = subprocess.run(
                [self.docker_cmd, 'ps', '-a', '--filter', f'name={container_name}', '--format', '{{.Status}}'],
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "unknown"

    def start_service(self, service_name: str, compose_file: str = "docker-compose.simple.yml") -> bool:
        """Start a specific service"""
        try:
            cmd = self.compose_cmd + ['-f', compose_file, 'up', '-d', service_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"Started service: {service_name}")
                return True
            else:
                logger.error(f"Failed to start {service_name}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error starting {service_name}: {e}")
            return False

    def stop_service(self, service_name: str, compose_file: str = "docker-compose.simple.yml") -> bool:
        """Stop a specific service"""
        try:
            cmd = self.compose_cmd + ['-f', compose_file, 'stop', service_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error stopping {service_name}: {e}")
            return False

    def get_logs(self, container_name: str, lines: int = 20) -> str:
        """Get container logs"""
        try:
            result = subprocess.run(
                [self.docker_cmd, 'logs', '--tail', str(lines), container_name],
                capture_output=True, text=True
            )
            return result.stdout + result.stderr
        except subprocess.CalledProcessError:
            return "Failed to get logs"

class HealthMonitor:
    """Health checking and monitoring"""

    @staticmethod
    async def check_http_health(health_check: HealthCheck) -> bool:
        """Check HTTP health endpoint"""
        for attempt in range(health_check.retries):
            try:
                with urllib.request.urlopen(health_check.url, timeout=health_check.timeout) as response:
                    if response.status == health_check.expected_status:
                        return True
            except (urllib.error.URLError, TimeoutError):
                if attempt < health_check.retries - 1:
                    await asyncio.sleep(2)
                continue
        return False

    @staticmethod
    async def check_service_health(service: Service, docker_manager: DockerManager) -> bool:
        """Check if service is healthy"""
        # First check if container is running
        if not docker_manager.is_service_running(service.container_name):
            return False

        # If no health check defined, assume healthy if running
        if not service.health_check:
            return True

        # Perform HTTP health check
        return await HealthMonitor.check_http_health(service.health_check)

class StartupOrchestrator:
    """Main orchestrator for intelligent startup"""

    def __init__(self, compose_file: str = "docker-compose.simple.yml"):
        self.compose_file = compose_file
        self.docker_manager = DockerManager()
        self.services = self._define_services()
        self.startup_order = self._calculate_startup_order()
        self._setup_signal_handlers()

    def _define_services(self) -> Dict[str, Service]:
        """Define all services with their dependencies and health checks"""
        return {
            # Infrastructure Services
            "postgres": Service(
                name="postgres",
                container_name="itp-postgres-simple",
                dependencies=[],
                health_check=None,  # Uses Docker healthcheck
                startup_delay=10,
                max_startup_time=60
            ),
            "redis": Service(
                name="redis",
                container_name="itp-redis-simple",
                dependencies=[],
                health_check=None,  # Uses Docker healthcheck
                startup_delay=5,
                max_startup_time=30
            ),
            "neo4j": Service(
                name="neo4j",
                container_name="itp-neo4j-simple",
                dependencies=[],
                health_check=HealthCheck("http://localhost:7474/db/data/", timeout=15, retries=5),
                startup_delay=15,
                max_startup_time=90
            ),

            # Application Services
            "planner-mcp-server": Service(
                name="planner-mcp-server",
                container_name="itp-planner-mcp-simple",
                dependencies=["postgres", "redis", "neo4j"],
                health_check=HealthCheck("http://localhost:7100/health"),
                startup_delay=10,
                max_startup_time=120
            ),
            "mcpo-proxy": Service(
                name="mcpo-proxy",
                container_name="itp-mcpo-proxy-simple",
                dependencies=["redis", "planner-mcp-server"],
                health_check=HealthCheck("http://localhost:7105/health"),
                startup_delay=8,
                max_startup_time=60
            ),
            "teams-bot": Service(
                name="teams-bot",
                container_name="itp-teams-bot-simple",
                dependencies=["redis", "planner-mcp-server", "mcpo-proxy"],
                health_check=HealthCheck("http://localhost:7110/health"),
                startup_delay=8,
                max_startup_time=60
            ),
            "rag-service": Service(
                name="rag-service",
                container_name="itp-rag-service-simple",
                dependencies=["postgres", "redis", "neo4j", "planner-mcp-server"],
                health_check=HealthCheck("http://localhost:7120/health"),
                startup_delay=10,
                max_startup_time=90
            )
        }

    def _calculate_startup_order(self) -> List[List[str]]:
        """Calculate startup order using topological sort"""
        # Group services by dependency level
        levels = []
        remaining = set(self.services.keys())

        while remaining:
            # Find services with no unmet dependencies
            ready = set()
            for service_name in remaining:
                service = self.services[service_name]
                unmet_deps = set(service.dependencies) & remaining
                if not unmet_deps:
                    ready.add(service_name)

            if not ready:
                # Circular dependency detected
                logger.error(f"Circular dependency detected among: {remaining}")
                break

            levels.append(sorted(ready))
            remaining -= ready

        logger.info(f"Startup order: {levels}")
        return levels

    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self.shutdown())

        if platform.system() != "Windows":
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

    async def start_service_group(self, service_names: List[str]) -> Dict[str, bool]:
        """Start a group of services in parallel"""
        results = {}
        tasks = []

        for service_name in service_names:
            task = asyncio.create_task(self.start_single_service(service_name))
            tasks.append((service_name, task))

        for service_name, task in tasks:
            results[service_name] = await task

        return results

    async def start_single_service(self, service_name: str) -> bool:
        """Start and monitor a single service"""
        service = self.services[service_name]
        logger.info(f"Starting service: {service_name}")

        service.status = ServiceStatus.STARTING
        service.start_time = time.time()

        # Start the service
        if not self.docker_manager.start_service(service_name, self.compose_file):
            service.status = ServiceStatus.FAILED
            return False

        # Wait for startup delay
        await asyncio.sleep(service.startup_delay)

        # Monitor health until healthy or timeout
        start_time = time.time()
        while time.time() - start_time < service.max_startup_time:
            if await HealthMonitor.check_service_health(service, self.docker_manager):
                service.status = ServiceStatus.HEALTHY
                logger.info(f"✅ Service {service_name} is healthy")
                return True

            # Check if container crashed
            if not self.docker_manager.is_service_running(service.container_name):
                logger.error(f"❌ Service {service_name} container stopped")
                logs = self.docker_manager.get_logs(service.container_name)
                logger.error(f"Container logs:\n{logs}")
                service.status = ServiceStatus.FAILED
                return False

            await asyncio.sleep(5)

        # Timeout reached
        logger.error(f"⏰ Service {service_name} failed to become healthy within {service.max_startup_time}s")
        logs = self.docker_manager.get_logs(service.container_name)
        logger.error(f"Container logs:\n{logs}")
        service.status = ServiceStatus.UNHEALTHY
        return False

    async def monitor_services(self):
        """Continuously monitor service health"""
        logger.info("Starting continuous health monitoring...")

        while True:
            unhealthy_services = []

            for service_name, service in self.services.items():
                if service.status in [ServiceStatus.HEALTHY, ServiceStatus.UNHEALTHY]:
                    is_healthy = await HealthMonitor.check_service_health(service, self.docker_manager)

                    if is_healthy and service.status == ServiceStatus.UNHEALTHY:
                        logger.info(f"🔄 Service {service_name} recovered")
                        service.status = ServiceStatus.HEALTHY
                    elif not is_healthy and service.status == ServiceStatus.HEALTHY:
                        logger.warning(f"⚠️ Service {service_name} became unhealthy")
                        service.status = ServiceStatus.UNHEALTHY
                        unhealthy_services.append(service_name)

            # Attempt to restart unhealthy services
            for service_name in unhealthy_services:
                service = self.services[service_name]
                if service.restart_count < service.max_restarts:
                    logger.info(f"🔄 Attempting to restart {service_name} (attempt {service.restart_count + 1})")
                    service.restart_count += 1
                    await self.start_single_service(service_name)
                else:
                    logger.error(f"💀 Service {service_name} exceeded max restarts")
                    service.status = ServiceStatus.FAILED

            await asyncio.sleep(30)  # Check every 30 seconds

    async def startup(self) -> bool:
        """Execute intelligent startup sequence"""
        logger.info("🚀 Starting Intelligent Teams Planner deployment...")

        # Check Docker availability
        try:
            if not self.docker_manager.is_service_running(""):
                logger.info("Docker is available")
        except Exception as e:
            logger.error(f"Docker not available: {e}")
            return False

        # Start services in dependency order
        all_success = True
        for level, service_group in enumerate(self.startup_order):
            logger.info(f"📋 Starting service group {level + 1}: {service_group}")

            results = await self.start_service_group(service_group)

            # Check if all services in group started successfully
            group_success = all(results.values())
            if not group_success:
                failed_services = [name for name, success in results.items() if not success]
                logger.error(f"❌ Failed to start services: {failed_services}")
                all_success = False

                # Decide whether to continue or abort
                critical_services = ["postgres", "redis"]
                if any(svc in failed_services for svc in critical_services):
                    logger.error("Critical infrastructure service failed, aborting startup")
                    return False
                else:
                    logger.warning("Non-critical service failed, continuing startup")

        if all_success:
            logger.info("🎉 All services started successfully!")
        else:
            logger.warning("⚠️ Some services failed to start, but deployment is functional")

        # Start monitoring
        asyncio.create_task(self.monitor_services())

        return True

    async def shutdown(self):
        """Graceful shutdown of all services"""
        logger.info("🛑 Initiating graceful shutdown...")

        # Shutdown in reverse dependency order
        shutdown_order = list(reversed(self.startup_order))

        for service_group in shutdown_order:
            logger.info(f"Stopping services: {service_group}")
            for service_name in service_group:
                self.docker_manager.stop_service(service_name, self.compose_file)
                self.services[service_name].status = ServiceStatus.STOPPED

        logger.info("✅ Graceful shutdown completed")

    def get_status_report(self) -> Dict:
        """Generate comprehensive status report"""
        report = {
            "timestamp": time.time(),
            "overall_health": "healthy",
            "services": {}
        }

        healthy_count = 0
        total_count = len(self.services)

        for service_name, service in self.services.items():
            container_status = self.docker_manager.get_service_status(service.container_name)

            service_report = {
                "status": service.status.value,
                "container_status": container_status,
                "restart_count": service.restart_count,
                "uptime": time.time() - service.start_time if service.start_time else 0
            }

            if service.status == ServiceStatus.HEALTHY:
                healthy_count += 1

            report["services"][service_name] = service_report

        # Determine overall health
        if healthy_count == total_count:
            report["overall_health"] = "healthy"
        elif healthy_count >= total_count * 0.7:
            report["overall_health"] = "degraded"
        else:
            report["overall_health"] = "unhealthy"

        report["health_ratio"] = f"{healthy_count}/{total_count}"

        return report

async def main():
    """Main entry point"""
    orchestrator = StartupOrchestrator()

    try:
        success = await orchestrator.startup()

        if success:
            # Print status report
            report = orchestrator.get_status_report()
            print("\n" + "="*60)
            print("🏥 DEPLOYMENT STATUS REPORT")
            print("="*60)
            print(f"Overall Health: {report['overall_health'].upper()}")
            print(f"Services: {report['health_ratio']}")
            print("-"*60)

            for service_name, service_info in report["services"].items():
                status_emoji = {
                    "healthy": "✅",
                    "unhealthy": "❌",
                    "starting": "🟡",
                    "failed": "💀",
                    "stopped": "⏹️"
                }.get(service_info["status"], "❓")

                print(f"{status_emoji} {service_name:20} | {service_info['status']:10} | {service_info['container_status']}")

            print("="*60)

            # Keep running and monitoring
            logger.info("🔍 Monitoring services... Press Ctrl+C to stop")

            # Wait indefinitely while monitoring runs in background
            try:
                while True:
                    await asyncio.sleep(60)

                    # Print periodic status update
                    report = orchestrator.get_status_report()
                    logger.info(f"Health check: {report['health_ratio']} services healthy")

            except KeyboardInterrupt:
                logger.info("Received shutdown signal")

        await orchestrator.shutdown()

    except Exception as e:
        logger.error(f"Startup failed: {e}")
        return 1

    return 0

if __name__ == "__main__":
    if platform.system() == "Windows":
        # Windows requires specific event loop policy
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    exit_code = asyncio.run(main())
    sys.exit(exit_code)