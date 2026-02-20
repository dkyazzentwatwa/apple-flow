#!/bin/bash
# install_automation.sh — Install apple-flow automation launchd agents
#
# This script generates launchd plists with correct paths and loads them.
# It reads the connector setting from .env to ensure consistency with the daemon.
#
# Usage:
#   ./scripts/install_automation.sh [--uninstall]

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
TEMPLATES_DIR="$PROJECT_ROOT/docs/launchd/automation"

# Default office path (can be overridden)
OFFICE_PATH="${APPLE_FLOW_OFFICE_PATH:-$PROJECT_ROOT/agent-office}"

# Current PATH for launchd environment
CURRENT_PATH="$PATH"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Read connector from .env
get_connector_from_env() {
    local env_file="$PROJECT_ROOT/.env"
    if [[ -f "$env_file" ]]; then
        grep -E "^apple_flow_connector=" "$env_file" 2>/dev/null | head -1 | cut -d'=' -f2 | tr -d ' "' || echo "cline"
    else
        echo "cline"
    fi
}

# Generate plist from template
generate_plist() {
    local template="$1"
    local output="$2"
    
    if [[ ! -f "$template" ]]; then
        log_error "Template not found: $template"
        return 1
    fi
    
    # Replace placeholders
    sed -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" \
        -e "s|{{OFFICE_PATH}}|$OFFICE_PATH|g" \
        -e "s|{{PATH}}|$CURRENT_PATH|g" \
        "$template" > "$output"
    
    log_info "Generated: $output"
}

# Load a launchd agent
load_agent() {
    local plist_path="$1"
    local label
    label=$(basename "$plist_path" .plist)
    
    # Check if already loaded
    if launchctl list "$label" &>/dev/null; then
        log_warn "Agent $label is already loaded. Unloading first..."
        launchctl unload "$plist_path" 2>/dev/null || true
    fi
    
    # Load the agent
    launchctl load "$plist_path"
    log_info "Loaded: $label"
}

# Unload a launchd agent
unload_agent() {
    local plist_path="$1"
    local label
    label=$(basename "$plist_path" .plist)
    
    if launchctl list "$label" &>/dev/null; then
        launchctl unload "$plist_path"
        log_info "Unloaded: $label"
    else
        log_warn "Agent $label is not loaded"
    fi
}

# -----------------------------------------------------------------------------
# Main installation
# -----------------------------------------------------------------------------

install() {
    log_info "Installing apple-flow automation agents..."
    log_info "Project root: $PROJECT_ROOT"
    log_info "Office path: $OFFICE_PATH"
    log_info "Connector: $(get_connector_from_env)"
    
    # Ensure LaunchAgents directory exists
    mkdir -p "$LAUNCH_AGENTS_DIR"
    
    # Ensure logs directory exists
    mkdir -p "$PROJECT_ROOT/logs"
    
    # Make scripts executable
    chmod +x "$PROJECT_ROOT/scripts/automation/"*.sh
    
    # Generate and load each plist
    local plists=(
        "local.apple-flow-hourly"
        "local.apple-flow-daily-am"
        "local.apple-flow-daily-pm"
    )
    
    for plist_name in "${plists[@]}"; do
        local template="$TEMPLATES_DIR/${plist_name}.plist"
        local output="$LAUNCH_AGENTS_DIR/${plist_name}.plist"
        
        generate_plist "$template" "$output"
        load_agent "$output"
    done
    
    echo ""
    log_info "Installation complete!"
    echo ""
    echo "Installed agents:"
    echo "  - local.apple-flow-hourly    (runs every hour at :05)"
    echo "  - local.apple-flow-daily-am  (runs daily at 08:30)"
    echo "  - local.apple-flow-daily-pm  (runs daily at 18:00)"
    echo ""
    echo "Logs:"
    echo "  - $PROJECT_ROOT/logs/automation-*.log"
    echo "  - $OFFICE_PATH/90_logs/automation-log.md"
    echo ""
    echo "Commands:"
    echo "  launchctl list local.apple-flow-hourly    # Check status"
    echo "  launchctl start local.apple-flow-hourly   # Run manually"
    echo "  launchctl stop local.apple-flow-hourly    # Stop if running"
}

# -----------------------------------------------------------------------------
# Uninstallation
# -----------------------------------------------------------------------------

uninstall() {
    log_info "Uninstalling apple-flow automation agents..."
    
    local plists=(
        "local.apple-flow-hourly"
        "local.apple-flow-daily-am"
        "local.apple-flow-daily-pm"
    )
    
    for plist_name in "${plists[@]}"; do
        local plist_path="$LAUNCH_AGENTS_DIR/${plist_name}.plist"
        
        if [[ -f "$plist_path" ]]; then
            unload_agent "$plist_path"
            rm "$plist_path"
            log_info "Removed: $plist_path"
        else
            log_warn "Plist not found: $plist_path"
        fi
    done
    
    echo ""
    log_info "Uninstallation complete!"
}

# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

case "${1:-}" in
    --uninstall|-u)
        uninstall
        ;;
    --help|-h)
        echo "Usage: $0 [--uninstall]"
        echo ""
        echo "Installs apple-flow automation launchd agents."
        echo ""
        echo "Options:"
        echo "  --uninstall, -u  Remove installed agents"
        echo "  --help, -h       Show this help message"
        ;;
    *)
        install
        ;;
esac