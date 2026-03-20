# Environment Setup Guide

Before starting quantitative trading, you need a clean, stable, and isolated Python environment.
This guide recommends **uv (Fast & Modern)** for Python environment and dependency management.

---

## Option A: uv (Recommended)

uv is a modern Python toolchain written in Rust. It unifies Python version management, virtual environments, and package installation.

### 1. Install uv

> **Tip**: Users in China can install uv first, then use the Tsinghua PyPI mirror to speed up package downloads.

=== "Windows"

    1.  Open **PowerShell**.
    2.  Run:
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```
    3.  Reopen terminal and run `uv --version` to verify installation.

=== "macOS"

    **Method A: Installer Script (Recommended)**
    Open Terminal and run:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

    **Method B: Via Homebrew**

    1.  After Homebrew is installed, run:
        ```bash
        brew install uv
        ```
    2.  Run `uv --version` to verify installation.

=== "Linux"

    Open terminal and run:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    uv --version
    ```

### 1.5 Configure Mirrors (For Users in China)

If you are located in China, download speeds might be slow. It is recommended to use the Tsinghua University mirror.

```bash
# Configure uv/pip mirror
uv pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. Create Virtual Environment

Do not install libraries directly into your system Python! We need a dedicated "sandbox".

Open your terminal (or CMD/PowerShell on Windows) and type:

```bash
# Create a virtual environment with Python 3.10
uv venv --python 3.10

# Activate the environment
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
```

Once activated, your command prompt prefix will change to `(.venv)`, indicating you are inside the sandbox.

---

## Option B: uv (Project Workflow)

If you want extreme speed and lightweight management, [uv](https://github.com/astral-sh/uv) is the fastest package manager in the Python ecosystem (written in Rust). It replaces `pip` and `virtualenv`.

### 1. Install uv

=== "Windows"

    Run in PowerShell:
    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "macOS / Linux"

    Run in Terminal:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

### 2. Create & Manage Environment

uv does not require pre-installed Python; it manages Python versions for you.

```bash
# 1. Create a project directory
mkdir my_strategy
cd my_strategy

# 2. Initialize virtual env (Specify Python 3.10)
# uv will automatically download Python 3.10 and create .venv folder
uv venv --python 3.10

# 3. Activate environment
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
```

---

## 3. Install AKQuant & Verify

You should now be in an activated uv virtual environment.

### Install

**Install with uv:**
```bash
uv pip install akquant

# Users in China:
# uv pip install akquant --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### Verify

Create a test script `verify.py`:

```python
import akquant
import pandas as pd

print(f"AKQuant Version: {akquant.__version__}")
print(f"Pandas Version: {pd.__version__}")
print("Environment setup successful! Ready to trade.")
```

Run it:

```bash
python verify.py
```

If you see the success message, your arsenal is ready!
Next, go to [Python for Finance](../guide/python_basics.md) to learn syntax, or jump to [Quant Guide](../guide/quant_basics.md) to start coding strategies.
