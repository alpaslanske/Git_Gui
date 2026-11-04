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

> 🔐 **Important GitHub Authentication:** You must run `gh auth login` once in your local terminal to authenticate your machine via your default web browser. Additionally, if you plan to use the repository deletion feature directly from the GUI, grant the required permission scope by executing: `gh auth refresh -s delete_repo`.

---

## 🐍 2. Running with Python (For Developers)

To set up an isolated development environment and run the project from source, execute the following commands within the project's root directory:

```bash
# Create and activate a Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the required dependencies
pip install -r requirements.txt

# Launch the application
python3 git_gui.py
```

---

## 📦 3. One-Click Portable AppImage Build

The repository includes a custom build automation utility to instantly compile your project into a self-contained, standalone `.AppImage` executable that runs seamlessly across all major Linux distributions:

```bash
./build.sh
```

This compilation automation script automatically enforces correct Linux file permissions, links the executable entry point via a local `AppRun` symlink, and generates a lightweight, single-file **`Git_Gui_Portable-x86_64.AppImage`** executable (~15MB) ready for distribution.

---
*Developed with ❤️ for Open Source Developers and Automation Engineers.*
