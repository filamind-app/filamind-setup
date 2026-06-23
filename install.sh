#!/usr/bin/env bash
# FilaMind Setup - one-line bootstrap for the whole suite.
#
#   curl -fsSL https://raw.githubusercontent.com/filamind-app/filamind-setup/main/install.sh | bash
#
# Clones this installer, puts `filamind-setup` on your PATH, and runs the first-run wizard
# (detects your printer, then installs the FilaMind suite or adopts an existing setup).
# Re-runnable. Pass an explicit command to skip the wizard, e.g. `... | bash -s -- menu`.
set -euo pipefail

REPO="${FILAMIND_SETUP_REPO:-https://github.com/filamind-app/filamind-setup.git}"
APP="${FILAMIND_SETUP_DIR:-$HOME/filamind-setup}"
CMD="${1:-bootstrap}"

info() { printf '\n\033[1;33m==>\033[0m %s\n' "$*"; }

command -v git >/dev/null || {
  echo "git not found; install git first." >&2
  exit 1
}
command -v python3 >/dev/null || {
  echo "python3 not found; install python3 first." >&2
  exit 1
}

if [ ! -d "$APP/.git" ]; then
  info "Cloning FilaMind Setup -> $APP"
  git clone --depth 1 "$REPO" "$APP"
else
  info "Updating FilaMind Setup"
  # Don't fail the whole bootstrap on a pull error, but never hide it either - say so and continue
  # with the cached checkout instead of silently running stale code.
  git -C "$APP" pull --ff-only || echo "  (update failed; continuing with the existing checkout)" >&2
fi

chmod +x "$APP/filamind-setup"

# Put `filamind-setup` on PATH (system-wide if we can, else the user's ~/.local/bin).
if sudo -n true 2>/dev/null; then
  sudo ln -sf "$APP/filamind-setup" /usr/local/bin/filamind-setup
  info "Installed the 'filamind-setup' command (/usr/local/bin)."
else
  mkdir -p "$HOME/.local/bin"
  ln -sf "$APP/filamind-setup" "$HOME/.local/bin/filamind-setup"
  info "Installed 'filamind-setup' to ~/.local/bin (ensure it's on your PATH)."
fi

exec python3 "$APP/filamind-setup" "$CMD"
