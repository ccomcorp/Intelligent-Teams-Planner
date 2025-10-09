#!/usr/bin/env python3
"""
Lightweight Service Starter for Intelligent Teams Planner v2.0
Starts Python services locally with proper environment and port management
"""

import subprocess
import sys
import os
import time
import signal
import json
from pathlib import Path
from typing import Dict, List, Optional
import threading
import requests

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

class ServiceManager:
    """Lightweight service management for local development"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent.absolute()
        self.services = {}
        self.processes = {}

        # Service configuration
        self.service_configs = {
            "mcp-server": {
                "path": "planner-mcp-server",
                "port": 7100,
                "env": {
                    "PORT": "7100",
                    "DATABASE_URL": "postgresql+asyncpg://itp_user:itp_password_2024@localhost:5432/intelligent_teams_planner",
                    "REDIS_URL": "redis://localhost:6379",
                    "REDIS_PASSWORD": "redis_password_2024",
                    "ENCRYPTION_KEY": "12345678901234567890123456789012",
                    "TESTING_MODE": "true",
                    "MICROSOFT_CLIENT_ID": "test-client-id",
                    "MICROSOFT_CLIENT_SECRET": "test-client-secret",
                    "MICROSOFT_TENANT_ID": "test-tenant-id"
                },
                "health_endpoint": "/health",
                "startup_time": 10
            },
            "mcpo-proxy": {
                "path": "mcpo-proxy",
                "port": 7105,
                "env": {
                    "PORT": "7105",
                    "MCP_SERVER_URL": "http://localhost:7100",
                    "REDIS_URL": "redis://localhost:6379",
                    "REDIS_PASSWORD": "redis_password_2024"
                },
                "health_endpoint": "/health",
                "startup_time": 8,
                "depends_on": ["mcp-server"]
            },
            "teams-bot": {
                "path": "teams-bot",
                "port": 7110,
                "env": {
                    "PORT": "7110",
                    "BOT_ID": "test-bot-id",
                    "BOT_PASSWORD": "test-bot-password",
                    "OPENWEBUI_URL": "http://localhost:7115",
                    "REDIS_URL": "redis://localhost:6379",
                    "REDIS_PASSWORD": "redis_password_2024"
                },
                "health_endpoint": "/health",
                "startup_time": 5,
                "optional": True
            }
        }

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

    def check_dependencies(self, service_name: str) -> bool:
        """Check if service dependencies are running"""
        config = self.service_configs[service_name]
        depends_on = config.get("depends_on", [])

        for dep in depends_on:
            if not self.is_service_healthy(dep):
                self.log(f"Dependency {dep} is not healthy for {service_name}", "WARNING")
                return False

        return True

    def is_service_healthy(self, service_name: str) -> bool:
        """Check if a service is healthy"""
        config = self.service_configs.get(service_name)
        if not config:
            return False

        port = config["port"]
        health_endpoint = config.get("health_endpoint")

        if not health_endpoint:
            return True  # No health check defined

        try:
            url = f"http://localhost:{port}{health_endpoint}"
            response = requests.get(url, timeout=2)
            return response.status_code == 200
        except:
            return False

    def start_service(self, service_name: str) -> bool:
        """Start a single service"""
        if service_name in self.processes:
            self.log(f"Service {service_name} is already running", "WARNING")
            return True

        config = self.service_configs[service_name]
        service_path = self.project_root / config["path"]

        if not service_path.exists():
            self.log(f"Service path not found: {service_path}", "ERROR")
            return False

        self.log(f"Starting {service_name} on port {config['port']}...", "INFO")

        # Check dependencies
        if not self.check_dependencies(service_name):
            if not config.get("optional", False):
                self.log(f"Cannot start {service_name} due to missing dependencies", "ERROR")
                return False

        # Set up environment
        env = os.environ.copy()
        env.update(config["env"])
        env["PATH"] = f"{os.path.expanduser('~/.local/bin')}:{env.get('PATH', '')}"

        # Start the service using Poetry
        try:
            process = subprocess.Popen(
                ["poetry", "run", "python", "-m", "src.main"],
                cwd=service_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            self.processes[service_name] = process
            self.log(f"Started {service_name} (PID: {process.pid})", "SUCCESS")

            # Wait for service to be healthy
            startup_time = config.get("startup_time", 5)
            self.log(f"Waiting {startup_time}s for {service_name} to be healthy...", "INFO")

            for i in range(startup_time):
                if self.is_service_healthy(service_name):
                    self.log(f"✅ {service_name} is healthy", "SUCCESS")
                    return True
                time.sleep(1)

            # Check if process is still running
            if process.poll() is None:
                self.log(f"⚠️ {service_name} started but health check failed", "WARNING")
                return True
            else:
                stdout, stderr = process.communicate()
                self.log(f"❌ {service_name} failed to start: {stderr}", "ERROR")
                del self.processes[service_name]
                return False

        except Exception as e:
            self.log(f"❌ Failed to start {service_name}: {e}", "ERROR")
            return False

    def stop_service(self, service_name: str):
        """Stop a single service"""
        if service_name not in self.processes:
            self.log(f"Service {service_name} is not running", "WARNING")
            return

        process = self.processes[service_name]
        self.log(f"Stopping {service_name} (PID: {process.pid})...", "INFO")

        try:
            process.terminate()
            process.wait(timeout=10)
            self.log(f"✅ Stopped {service_name}", "SUCCESS")
        except subprocess.TimeoutExpired:
            self.log(f"Force killing {service_name}...", "WARNING")
            process.kill()
            process.wait()
        except Exception as e:
            self.log(f"Error stopping {service_name}: {e}", "ERROR")

        del self.processes[service_name]

    def stop_all_services(self):
        """Stop all running services"""
        self.log("Stopping all services...", "HEADER")
        for service_name in list(self.processes.keys()):
            self.stop_service(service_name)

    def start_all_services(self, required_only: bool = False):
        """Start all services in dependency order"""
        self.log("🚀 Starting services in dependency order", "HEADER")

        # Start order based on dependencies
        start_order = ["mcp-server", "mcpo-proxy", "teams-bot"]

        if required_only:
            start_order = [s for s in start_order if not self.service_configs[s].get("optional", False)]

        success_count = 0
        for service_name in start_order:
            if self.start_service(service_name):
                success_count += 1
            else:
                self.log(f"❌ Failed to start {service_name}", "ERROR")
                if not self.service_configs[service_name].get("optional", False):
                    self.log("Stopping due to required service failure", "ERROR")
                    break

        self.log(f"✅ Started {success_count}/{len(start_order)} services", "SUCCESS")
        return success_count == len(start_order)

    def show_status(self):
        """Show current status of all services"""
        self.log("📊 Service Status", "HEADER")

        for service_name, config in self.service_configs.items():
            port = config["port"]
            is_running = service_name in self.processes
            is_healthy = self.is_service_healthy(service_name) if is_running else False

            status_icon = "✅" if is_healthy else "⚠️" if is_running else "❌"
            status_text = "HEALTHY" if is_healthy else "RUNNING" if is_running else "STOPPED"

            optional_text = "(optional)" if config.get("optional", False) else "(required)"

            print(f"  {status_icon} {service_name:12} | Port {port:4} | {status_text:8} {optional_text}")

    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.log("\n🛑 Received shutdown signal", "WARNING")
        self.stop_all_services()
        sys.exit(0)

    def run_interactive(self):
        """Run interactive service management"""
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        self.log("🎮 Interactive Service Manager", "HEADER")
        self.log("Commands: start [service], stop [service], status, restart [service], quit", "INFO")

        while True:
            try:
                cmd = input("\n> ").strip().lower().split()
                if not cmd:
                    continue

                action = cmd[0]

                if action in ["quit", "exit", "q"]:
                    break
                elif action == "status":
                    self.show_status()
                elif action == "start":
                    if len(cmd) > 1:
                        service = cmd[1]
                        if service == "all":
                            self.start_all_services()
                        elif service in self.service_configs:
                            self.start_service(service)
                        else:
                            self.log(f"Unknown service: {service}", "ERROR")
                    else:
                        self.log("Usage: start <service|all>", "INFO")
                elif action == "stop":
                    if len(cmd) > 1:
                        service = cmd[1]
                        if service == "all":
                            self.stop_all_services()
                        elif service in self.service_configs:
                            self.stop_service(service)
                        else:
                            self.log(f"Unknown service: {service}", "ERROR")
                    else:
                        self.log("Usage: stop <service|all>", "INFO")
                elif action == "restart":
                    if len(cmd) > 1:
                        service = cmd[1]
                        if service in self.service_configs:
                            self.stop_service(service)
                            time.sleep(2)
                            self.start_service(service)
                        else:
                            self.log(f"Unknown service: {service}", "ERROR")
                    else:
                        self.log("Usage: restart <service>", "INFO")
                else:
                    self.log(f"Unknown command: {action}", "ERROR")

            except (EOFError, KeyboardInterrupt):
                break

        self.stop_all_services()

    def main(self):
        """Main entry point"""
        import argparse
        parser = argparse.ArgumentParser(description="Lightweight Service Manager")
        parser.add_argument("--start-all", action="store_true", help="Start all services")
        parser.add_argument("--required-only", action="store_true", help="Start only required services")
        parser.add_argument("--status", action="store_true", help="Show service status")
        parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")

        args = parser.parse_args()

        if args.status:
            self.show_status()
        elif args.start_all:
            self.start_all_services(args.required_only)
            self.show_status()
        elif args.interactive:
            self.run_interactive()
        else:
            self.start_all_services(True)  # Start required services by default
            self.show_status()

if __name__ == "__main__":
    manager = ServiceManager()
    manager.main()