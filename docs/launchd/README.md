# LaunchD Configuration

**Note:** The plist file in this directory is a **reference template only**.

The actual plist file is **generated dynamically** by `scripts/install_autostart.sh` with paths specific to your system.

## Why Dynamic Generation?

The plist needs to contain:
- Your project directory path
- The actual Python binary (resolving symlinks)
- Your Python version for site-packages
- Your username for log paths

These vary by:
- User and installation location
- Python version (3.10, 3.11, 3.14, etc.)
- Homebrew updates that change version paths

## Installation

Use the installation script:

```bash
./scripts/install_autostart.sh
```

This will:
1. Auto-detect all required paths
2. Generate `~/Library/LaunchAgents/com.codex.relay.plist`
3. Load the service
4. Display the Python binary path for Full Disk Access

See [AUTO_START_SETUP.md](../AUTO_START_SETUP.md) for complete instructions.
