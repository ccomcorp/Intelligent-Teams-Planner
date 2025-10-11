# uv Quick Start Guide - Intelligent Teams Planner

This project uses **uv** for fast, reliable Python package management.

## Prerequisites

- Python 3.11+ installed
- uv installed (see Installation below)

## Installation

### Install uv

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Via pip (if needed):**
```bash
pip install uv
```

**Verify installation:**
```bash
uv --version
```

## Project Setup

### Initial Setup (New Developer)

```bash
# Clone the repository
git clone <repository-url>
cd Intelligent-Teams-Planner

# Setup planner-mcp-server
cd planner-mcp-server
uv venv --python 3.11
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
deactivate

# Setup mcpo-proxy
cd ../mcpo-proxy
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
deactivate

# Setup teams-bot
cd ../teams-bot
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
deactivate
```

## Common Commands

### Working with Virtual Environments

```bash
# Create virtual environment (Python 3.11)
uv venv --python 3.11

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# Deactivate virtual environment
deactivate
```

### Managing Dependencies

```bash
# Install a package
uv pip install <package-name>

# Install from requirements.txt
uv pip install -r requirements.txt

# Uninstall a package
uv pip uninstall <package-name>

# Upgrade a package
uv pip install --upgrade <package-name>

# List installed packages
uv pip list

# Freeze dependencies to requirements.txt
uv pip freeze > requirements.txt
```

### Development Workflow

```bash
# 1. Activate the service's virtual environment
cd planner-mcp-server  # or mcpo-proxy or teams-bot
source .venv/bin/activate

# 2. Install new dependency
uv pip install <package-name>

# 3. Update requirements.txt
uv pip freeze > requirements.txt

# 4. Deactivate when done
deactivate
```

## Service-Specific Notes

### planner-mcp-server (Port 8000)
- **Dependencies:** 126 packages including ML/NLP libraries
- **Key packages:** torch, transformers, sentence-transformers, spacy
- **Note:** Requires Python 3.11 (torch compatibility)

### mcpo-proxy (Port 8001)
- **Dependencies:** 38 packages
- **Key packages:** FastAPI, httpx, redis
- **Lightweight:** Fast installation (~1-2 seconds)

### teams-bot (Port 3978)
- **Dependencies:** 49 packages
- **Key packages:** botbuilder-core, aiohttp, redis
- **Note:** Microsoft Bot Framework integration

## Troubleshooting

### Python Version Issues

If you get dependency resolution errors:
```bash
# Ensure Python 3.11 is used
uv venv --python 3.11
```

### NumPy Compatibility

If you see NumPy version errors:
```bash
# Install NumPy 1.x (required for ML libraries)
uv pip install "numpy<2"
```

### Dependency Conflicts

If you encounter dependency conflicts:
```bash
# Clear cache and reinstall
rm -rf .venv
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Performance Benefits

Compared to Poetry:
- **10-100x faster** package installation
- **Instant** dependency resolution
- **~21 seconds** total setup time (vs 9-14 minutes with Poetry)

## Migration from Poetry

If you're migrating from Poetry:
1. Backup files are in `.migration-backup/`
2. See `MIGRATION_REPORT.md` for full details
3. Rollback instructions available if needed

## Additional Resources

- **uv Documentation:** https://docs.astral.sh/uv/
- **Project Documentation:** See README.md
- **Migration Report:** See MIGRATION_REPORT.md
- **Package Management Guide:** See CLAUDE.md @PACKAGE_MANAGEMENT section

## Quick Reference

| Task | Command |
|------|---------|
| Create venv | `uv venv --python 3.11` |
| Activate venv | `source .venv/bin/activate` |
| Install package | `uv pip install <package>` |
| Install from file | `uv pip install -r requirements.txt` |
| Freeze deps | `uv pip freeze > requirements.txt` |
| List packages | `uv pip list` |
| Uninstall package | `uv pip uninstall <package>` |

---

**Note:** This project follows the lightweight-first development approach documented in CLAUDE.md. Always use uv for package management - never manually edit requirements.txt files.

