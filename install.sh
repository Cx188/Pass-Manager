#!/usr/bin/env bash
# Sets up Pass Manager: installs system + Python dependencies, then optionally
# adds a Start Menu / application-launcher entry. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn()  { printf '\033[1;33m!!\033[0m %s\n' "$1"; }
die()   { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

[ "$(uname -s)" = "Linux" ] || die "this installer targets Linux (the unlock path uses the freedesktop Secret Service API)."

# --------------------------------------------------------------------- system
install_system_deps() {
    if command -v python3 >/dev/null 2>&1 && python3 -c "import ensurepip" >/dev/null 2>&1; then
        return
    fi
    info "Installing Python + pip via your package manager — you may be asked for your password."
    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3 python3-pip
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update -y && sudo apt-get install -y python3 python3-pip
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm python python-pip
    elif command -v zypper >/dev/null 2>&1; then
        sudo zypper install -y python3 python3-pip
    else
        die "couldn't find dnf/apt/pacman/zypper — install Python 3.10+ (with pip) yourself and re-run."
    fi
}

install_system_deps

# --------------------------------------------------------------------- deps
info "Installing dependencies…"
python3 -m pip install --user -q --no-warn-script-location -r requirements.txt \
    || python3 -m pip install --user --break-system-packages -q --no-warn-script-location -r requirements.txt
info "Dependencies installed."

# --------------------------------------------------------------------- icon
python3 - <<'PY' >/dev/null 2>&1 || true
from PySide6.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
from ui.icon import save_icon_files
save_icon_files("assets/icons")
PY

# --------------------------------------------------------------------- menu entry
add_desktop_entry() {
    local apps_dir="$HOME/.local/share/applications"
    local icon_dir="$HOME/.local/share/icons/hicolor/256x256/apps"
    mkdir -p "$apps_dir" "$icon_dir"
    cp "$APP_DIR/assets/icons/app.png" "$icon_dir/pass-manager.png"

    cat > "$apps_dir/pass-manager.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Pass Manager
Comment=Local encrypted password manager
Exec=$APP_DIR/run.sh
Icon=pass-manager
Terminal=false
Categories=Utility;Security;
StartupWMClass=pass-manager
EOF
    chmod +x "$apps_dir/pass-manager.desktop"

    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps_dir" >/dev/null 2>&1 || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true

    info "Added to your applications menu as \"Pass Manager\"."
}

remove_desktop_entry() {
    rm -f "$HOME/.local/share/applications/pass-manager.desktop"
    rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/pass-manager.png"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
    info "Removed the Start Menu entry."
}

if [ "${1:-}" = "--uninstall-menu-entry" ]; then
    remove_desktop_entry
    exit 0
fi

want_entry="y"
if [ -t 0 ]; then
    read -r -p "Add Pass Manager to your Start Menu / app launcher? [Y/n] " reply || true
    case "$reply" in
        [nN]*) want_entry="n" ;;
        *) want_entry="y" ;;
    esac
else
    warn "Non-interactive shell — adding a Start Menu entry by default (re-run with --no-menu-entry to skip)."
    [ "${1:-}" = "--no-menu-entry" ] && want_entry="n"
fi

if [ "$want_entry" = "y" ]; then
    add_desktop_entry
else
    info "Skipped Start Menu entry — launch anytime with ./run.sh"
fi

echo
info "Done. Launch Pass Manager with:  ./run.sh"
if [ "$want_entry" = "y" ]; then
    info "…or find \"Pass Manager\" in your Start Menu / app launcher."
fi
exit 0
