# 🚀 Git Manager

**Git Manager** is a modern graphical user interface (GUI) application built with **PySide6** that allows you to manage Git operations and GitHub repositories effortlessly. You can handle operations like Init, Commit, Push, Rebase, Squash, Tag/Release management, Repository Deletion, and Repository Cloning without ever touching the terminal.

---

## 🛠️ 1. System Requirements

The application runs native Git and GitHub CLI commands under the hood using sub-processes. For the application to function correctly, make sure the following packages are installed on your Linux system:

*   **Arch Linux / Manjaro:**
    ```bash
    sudo pacman -S git github-cli
    ```
*   **Ubuntu / Debian / Linux Mint:**
    ```bash
    sudo apt update && sudo apt install git gh
    ```
*   **Fedora / Red Hat:**
    ```bash
    sudo dnf install git gh
    ```
*   **Windows (winget):**
    ```powershell
    winget install --id Git.Git -e
    winget install --id GitHub.cli -e
    ```
*   **macOS (Homebrew):**
    ```bash
    brew install git gh
    ```

`git` and `gh` are system executables, not Python packages. `requirements.txt` only installs the Python dependencies; install the system tools with your operating system's package manager.

> 🔐 **Important GitHub Authentication:** You must run `gh auth login` once in your local terminal to authenticate your machine via your default web browser. Pushing changes to `.github/workflows` also requires the `workflow` scope; grant it with `gh auth refresh -h github.com -s workflow`. For repository deletion, grant the required scope with `gh auth refresh -s delete_repo`.

---

## 🐍 2. Running with Python (For Developers)

To set up an isolated development environment and run the project from source, execute the following commands within the project's root directory:

```bash
# Create and activate a Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies (Git and GitHub CLI are installed separately above)
pip install -r requirements.txt

# Launch the application
python3 git_gui.py
```

---

## 📦 3. AppImage Build

Install `appimagetool`, then build the AppImage with:

```bash
chmod +x build.sh
./build.sh
```

The output is `Git_Gui_Portable-x86_64.AppImage`. This packages the application files and launcher, but not Python, PySide6, Git, or GitHub CLI. Those must be installed on the target Linux system; use the system requirements above and install the Python dependencies with `pip install -r requirements.txt`.

The GitHub release workflow builds the same AppImage when a `v*` tag is pushed.

---
*Developed with ❤️ for Open Source Developers and Automation Engineers.*
