# Quick Start: Package Management with uv

## TL;DR

```bash
# Install uv (one time)
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# OR
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# Daily workflow
uv venv                              # Create virtual environment
source .venv/bin/activate            # Activate (Linux/Mac)
# OR .venv\Scripts\activate          # Activate (Windows)

uv pip install -r requirements.txt   # Install dependencies
uv pip install <package>             # Add new package
uv pip freeze > requirements.txt     # Update requirements file
```

## Why uv?

- ⚡ **10-100x faster** than pip (2-5 seconds vs 30-60 seconds)
- 🔒 **Better dependency resolution** - Handles complex dependency trees
- 🔄 **Backward compatible** - Works with existing requirements.txt
- 🌍 **Cross-platform** - Identical behavior on Windows/Mac/Linux
- 🚀 **Unified tooling** - Replaces pip, venv, pipx, pyenv, pip-tools

## Installation

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Via pip (if needed)

```bash
pip install uv
```

### Verify Installation

```bash
uv --version
```

## Basic Workflow

### 1. Create Virtual Environment

```bash
uv venv
```

This creates a `.venv` directory in your project.

### 2. Activate Virtual Environment

**Linux/Mac:**
```bash
source .venv/bin/activate
```

**Windows:**
```cmd
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
uv pip install -r requirements.txt
```

### 4. Add New Package

```bash
uv pip install <package-name>
uv pip freeze > requirements.txt
```

### 5. Remove Package

```bash
uv pip uninstall <package-name>
uv pip freeze > requirements.txt
```

### 6. Upgrade Package

```bash
uv pip install --upgrade <package-name>
uv pip freeze > requirements.txt
```

## Advanced Workflow (Optional)

### Initialize New Project

```bash
uv init
```

This creates:
- `pyproject.toml` - Project configuration
- `.venv` - Virtual environment
- `.gitignore` - Git ignore file
- `README.md` - Project readme
- `hello.py` - Sample Python file

### Add Dependency (with auto-update)

```bash
uv add <package-name>
```

This automatically:
- Installs the package
- Updates `pyproject.toml`
- Updates `uv.lock` file

### Sync Environment

```bash
uv sync
```

Installs all dependencies from lock file.

### Run Command (without activation)

```bash
uv run python script.py
uv run pytest
uv run python -m flask run
```

No need to activate virtual environment!

### Run Tool Temporarily

```bash
uvx <tool-name>
```

Example:
```bash
uvx black .
uvx ruff check .
uvx httpie https://api.github.com
```

## Common Commands Reference

| Task | uv Command | pip Equivalent |
|------|------------|----------------|
| Create venv | `uv venv` | `python -m venv venv` |
| Install package | `uv pip install <pkg>` | `pip install <pkg>` |
| Install from file | `uv pip install -r requirements.txt` | `pip install -r requirements.txt` |
| Uninstall package | `uv pip uninstall <pkg>` | `pip uninstall <pkg>` |
| Upgrade package | `uv pip install --upgrade <pkg>` | `pip install --upgrade <pkg>` |
| List packages | `uv pip list` | `pip list` |
| Freeze packages | `uv pip freeze > requirements.txt` | `pip freeze > requirements.txt` |
| Run in venv | `uv run <command>` | `source venv/bin/activate && <command>` |

## Troubleshooting

### uv not found

**Solution:** Install uv or use pip as fallback:
```bash
pip install uv
```

### Resolution conflict

**Solution:** Check version constraints in requirements.txt:
```bash
# Simplify version constraints
# Change: package==1.2.3
# To: package>=1.2.0,<2.0.0
```

### Slow first install

**This is normal!** uv builds a cache on first install. Subsequent installs will be 10-100x faster.

### Corporate proxy

**Solution:** Set environment variables:
```bash
export UV_HTTP_PROXY=http://proxy.company.com:8080
export UV_HTTPS_PROXY=https://proxy.company.com:8080
```

### Offline install

**Solution:** Use local package directory:
```bash
uv pip install --no-index --find-links /path/to/packages <package>
```

## Migration from pip

### Step 1: Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Step 2: Replace pip with uv pip

**Before:**
```bash
pip install -r requirements.txt
pip install requests
pip freeze > requirements.txt
```

**After:**
```bash
uv pip install -r requirements.txt
uv pip install requests
uv pip freeze > requirements.txt
```

### Step 3: (Optional) Adopt advanced features

```bash
uv init                    # Initialize project
uv add requests            # Add dependency
uv sync                    # Sync environment
uv run python script.py    # Run without activation
```

## Migration from Poetry

### Step 1: Export requirements

```bash
poetry export -f requirements.txt > requirements.txt
```

### Step 2: Install with uv

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Step 3: (Optional) Migrate to uv project

```bash
uv init
uv add <packages>
```

## Migration from Conda

### Step 1: Export requirements

```bash
conda list --export > requirements.txt
```

### Step 2: Clean conda-specific syntax

Edit `requirements.txt` to remove conda-specific markers.

### Step 3: Install with uv

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Best Practices

### ✅ DO

- ✅ Always use virtual environments
- ✅ Use `uv pip install` for package installation
- ✅ Update `requirements.txt` after adding/removing packages
- ✅ Use `uv pip freeze > requirements.txt` to capture exact versions
- ✅ Commit `requirements.txt` to version control
- ✅ Use `uv run` for quick commands without activation

### ❌ DON'T

- ❌ Never manually edit `requirements.txt` or `pyproject.toml`
- ❌ Never install packages globally (always use venv)
- ❌ Never mix package managers (uv + pip + poetry) in same project
- ❌ Never use `pip install` without venv active
- ❌ Never commit `.venv` directory to version control

## Performance Comparison

| Operation | pip | uv | Improvement |
|-----------|-----|-----|-------------|
| Install 20 packages | 30-60s | 2-5s | **90% faster** |
| Create venv | 5-10s | 1-2s | **80% faster** |
| Resolve dependencies | 10-20s | 1-2s | **90% faster** |
| Upgrade package | 15-30s | 2-4s | **87% faster** |

## Getting Help

### Documentation

- Official uv docs: https://github.com/astral-sh/uv
- This project's package management guide: `docs/package-management-implementation.md`

### Common Issues

- **uv not found:** Install uv or use pip fallback
- **Resolution conflict:** Simplify version constraints
- **Slow first install:** Normal - building cache
- **Corporate proxy:** Set UV_HTTP_PROXY and UV_HTTPS_PROXY

### Support

- Project issues: GitHub Issues
- Team chat: Slack #dev-support
- Documentation: `docs/` folder

## Summary

**uv is the recommended package manager for this project because:**

1. ⚡ **10-100x faster** than pip
2. 🔒 **Better dependency resolution**
3. 🔄 **Backward compatible** with pip
4. 🌍 **Cross-platform** consistency
5. 🚀 **Unified tooling** (replaces multiple tools)

**Start using uv today:**

```bash
# Install
curl -LsSf https://astral.sh/uv/install.sh | sh

# Use
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Enjoy 10-100x faster package management! 🚀
```

