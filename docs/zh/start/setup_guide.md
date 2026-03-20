# Python 环境搭建指南 (Environment Setup Guide)

工欲善其事，必先利其器。在开始量化交易之前，你需要一个干净、稳定且独立的 Python 运行环境。
本指南推荐使用 **uv (极速现代)** 来管理 Python 环境与依赖。

---

## 方案一：uv (推荐)

uv 是基于 Rust 的现代 Python 工具链，能够统一管理 Python 版本、虚拟环境和依赖包。

### 1. 安装 uv

> **提示**：国内用户可以先完成 uv 安装，再配合清华 PyPI 镜像提升依赖下载速度。

=== "Windows"

    1.  打开 **PowerShell**。
    2.  运行安装命令：
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```
    3.  重新打开终端，执行 `uv --version` 确认安装成功。

=== "macOS"

    **方法 A：使用安装脚本 (推荐)**
    打开终端 (Terminal)，运行：
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

    **方法 B：使用 Homebrew**

    1.  安装 Homebrew 后执行：
        ```bash
        brew install uv
        ```
    2.  执行 `uv --version` 确认安装成功。

=== "Linux"

    打开终端，运行以下命令安装 uv：
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    uv --version
    ```

### 1.5 配置国内镜像源 (推荐)

国内用户访问官方源可能较慢，建议配置清华大学镜像源以加速下载。

```bash
# 配置 uv/pip 镜像源 (永久生效)
uv pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 创建虚拟环境

不要直接在系统 Python 中安装库！我们需要创建一个专属的“沙盒”。

打开终端（Windows 用户打开 CMD 或 PowerShell），输入：

```bash
# 创建虚拟环境并指定 Python 3.10（AKQuant 支持 Python 3.10 及以上）
uv venv --python 3.10

# 激活环境
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
```

激活成功后，你的命令行前缀会变成 `(.venv)`，说明你已经进入了沙盒。

---

## 方案二：uv (项目工作流)

如果你追求极致的速度和轻量化，[uv](https://github.com/astral-sh/uv) 是目前 Python 生态中最快的包管理器（由 Rust 编写）。它可以替代 `pip` 和 `virtualenv`。

### 1. 安装 uv

=== "Windows"

    在 PowerShell 中运行：
    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "macOS / Linux"

    在终端运行：
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

### 2. 创建并管理环境

uv 不需要预先安装 Python，它会自动帮你下载。

```bash
# 1. 创建一个新的项目目录
mkdir my_strategy
cd my_strategy

# 2. 初始化虚拟环境 (指定 Python 3.10)
# uv 会自动下载 Python 3.10 并创建 .venv 目录
uv venv --python 3.10

# 3. 激活环境
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
```

---

## 3. 安装 AKQuant 并验证

现在你应该处于一个激活的 uv 虚拟环境中。接下来我们安装交易框架。

### 安装

**使用 uv 安装:**
```bash
# 使用清华源加速
uv pip install akquant --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 验证

创建一个测试脚本 `verify.py`：

```python
import akquant
import pandas as pd

print(f"AKQuant Version: {akquant.__version__}")
print(f"Pandas Version: {pd.__version__}")
print("环境搭建成功！可以开始写策略了。")
```

运行它：

```bash
python verify.py
```

如果看到“环境搭建成功”，恭喜你，你的兵器库已经准备完毕！
下一步，请前往 [Python 金融入门](../guide/python_basics.md) 学习基础语法，或直接查看 [量化新手指南](../guide/quant_basics.md) 开始实战。
