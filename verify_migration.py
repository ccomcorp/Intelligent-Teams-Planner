#!/usr/bin/env python3
"""
Verification script for Poetry to uv migration.
Tests that all critical dependencies can be imported successfully.
"""

import sys
import subprocess
from pathlib import Path

def test_service(service_name, venv_path, test_imports):
    """Test a service's virtual environment and imports."""
    print(f"\n{'='*60}")
    print(f"Testing {service_name}")
    print(f"{'='*60}")
    
    python_path = venv_path / "bin" / "python"
    
    if not python_path.exists():
        print(f"❌ Virtual environment not found: {venv_path}")
        return False
    
    # Test Python version
    result = subprocess.run(
        [str(python_path), "--version"],
        capture_output=True,
        text=True
    )
    print(f"✅ Python version: {result.stdout.strip()}")
    
    # Test each import
    all_passed = True
    for module in test_imports:
        result = subprocess.run(
            [str(python_path), "-c", f"import {module}"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"✅ Successfully imported: {module}")
        else:
            print(f"❌ Failed to import: {module}")
            print(f"   Error: {result.stderr.strip()}")
            all_passed = False
    
    return all_passed

def main():
    """Run verification tests for all services."""
    project_root = Path(__file__).parent
    
    services = {
        "planner-mcp-server": {
            "venv": project_root / "planner-mcp-server" / ".venv",
            "imports": [
                "fastapi",
                "uvicorn",
                "asyncpg",
                "sqlalchemy",
                "msal",
                "spacy",
                "torch",
                "transformers",
                "sentence_transformers",
                "redis",
                "pydantic",
                "structlog"
            ]
        },
        "mcpo-proxy": {
            "venv": project_root / "mcpo-proxy" / ".venv",
            "imports": [
                "fastapi",
                "uvicorn",
                "httpx",
                "redis",
                "pydantic",
                "pydantic_settings",
                "structlog"
            ]
        },
        "teams-bot": {
            "venv": project_root / "teams-bot" / ".venv",
            "imports": [
                "botbuilder.core",
                "botbuilder.schema",
                "botbuilder.integration.aiohttp",
                "botframework.connector",
                "aiohttp",
                "redis",
                "pydantic",
                "structlog"
            ]
        }
    }
    
    print("🔍 Poetry to uv Migration Verification")
    print("=" * 60)
    
    all_services_passed = True
    
    for service_name, config in services.items():
        passed = test_service(service_name, config["venv"], config["imports"])
        if not passed:
            all_services_passed = False
    
    print(f"\n{'='*60}")
    if all_services_passed:
        print("✅ ALL SERVICES PASSED VERIFICATION!")
        print("=" * 60)
        print("\nMigration successful! All dependencies are working correctly.")
        print("\nNext steps:")
        print("1. Start each service and test functionality")
        print("2. Run existing test suites")
        print("3. Update documentation")
        return 0
    else:
        print("❌ SOME SERVICES FAILED VERIFICATION")
        print("=" * 60)
        print("\nPlease review the errors above and fix any issues.")
        print("If needed, restore from backups in .migration-backup/")
        return 1

if __name__ == "__main__":
    sys.exit(main())

