#!/usr/bin/env bash
#
# freecad-mcp :: addon installer / updater for Linux
#
# What it does:
#   1. verifies it is running on Linux
#   2. locates headless FreeCAD (freecadcmd on PATH, or the Flatpak app)
#   3. asks FreeCAD itself for its version and its authoritative Mod directory,
#      so version-scoped layouts such as v1-1 need no hardcoding
#   4. makes sure FreeCAD is not running
#   5. fetches addon/FreeCADMCP from GitHub (git, or a tarball fallback)
#   6. backs up any existing install, copies the new one in, verifies it, and
#      rolls back if the copy fails
#
# This updates ONLY the addon. The freecad-mcp package is a separate install.
#
# Usage:
#   ./install_addon.sh
#   ./install_addon.sh -b v0.1.24
#   ./install_addon.sh -c "snap run --command=freecadcmd freecad"
#   ./install_addon.sh /usr/bin/freecadcmd
#
# Options:
#   -b, --ref REF       install from this git branch or tag (default: main)
#   -c, --freecadcmd CMD
#                       command that starts headless FreeCAD, split on
#                       whitespace; use this for Snap, AppImage or a custom
#                       install. Overrides auto-detection.
#   -h, --help          show this help
#
set -euo pipefail

REPO_SLUG="neka-nat/freecad-mcp"
REPO_URL="https://github.com/${REPO_SLUG}.git"
ARCHIVE_URL_BASE="https://github.com/${REPO_SLUG}/archive"
FLATPAK_APP="org.freecad.FreeCAD"

REF="main"
CMD=()
FC_VER=""
FC_MOD=""
ADDON_SRC=""
BACKUP=""

# ---------------------------------------------------------------- output ----
info() { printf '      %s\n' "$*"; }
warn() { printf '      [warn] %s\n' "$*" >&2; }
die()  { printf '      [x] %s\n' "$*" >&2; exit 1; }
step() { printf '\n[%s] %s\n' "$1" "$2"; }

# The work tree is removed on every exit path, including failures and signals.
work="$(mktemp -d "${TMPDIR:-/tmp}/fcmcp.XXXXXX")"
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

usage() {
    cat <<'EOF'

freecad-mcp addon installer for Linux

Usage:
  install_addon.sh [options] [freecadcmd-path]

Options:
  -b, --ref REF         install from this git branch or tag (default: main)
  -c, --freecadcmd CMD  command that starts headless FreeCAD, split on
                        whitespace. Use for Snap, AppImage or custom installs.
  -h, --help            show this help

Examples:
  install_addon.sh
  install_addon.sh -b v0.1.24
  install_addon.sh -c "snap run --command=freecadcmd freecad"
  install_addon.sh /usr/bin/freecadcmd

The addon is copied into the Mod directory FreeCAD reports for the running
installation, so version-scoped layouts such as
~/.local/share/FreeCAD/v1-1/Mod are handled automatically.
EOF
}

# ------------------------------------------------------------------ args ----
while [ $# -gt 0 ]; do
    case "$1" in
        -b|--ref)
            [ $# -ge 2 ] || die "-b requires a branch or tag name"
            REF="$2"
            shift 2
            ;;
        -c|--freecadcmd)
            [ $# -ge 2 ] || die "-c requires a command"
            read -r -a CMD <<< "$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            die "unknown option: $1 (try --help)"
            ;;
        *)
            CMD=("$1")
            shift
            ;;
    esac
done

# ------------------------------------------------------- 1. operating system ----
step 1/6 "Checking operating system"
os="$(uname -s)"
if [ "$os" != "Linux" ]; then
    if [ "$os" = "Darwin" ]; then
        die "macOS is not supported by this script; see docs/installation.md for the manual copy step."
    fi
    die "This script targets Linux; detected $os. See docs/installation.md."
fi
info "OS     : Linux ($(uname -m))"
info "Kernel : $(uname -r)"

# ------------------------------------------------- 2. locate headless FreeCAD ----
step 2/6 "Locating headless FreeCAD"

# Same candidates the MCP server's own headless runner probes, in the same
# order: see src/freecad_mcp/headless.py detect_freecadcmd().
if [ "${#CMD[@]}" -eq 0 ]; then
    for cand in freecadcmd FreeCADCmd freecadcmd.exe freecad.cmd; do
        if p="$(command -v "$cand" 2>/dev/null)"; then
            CMD=("$p")
            break
        fi
    done
fi

if [ "${#CMD[@]}" -eq 0 ] && command -v flatpak >/dev/null 2>&1; then
    if flatpak info "$FLATPAK_APP" >/dev/null 2>&1; then
        CMD=(flatpak run --command=freecadcmd "$FLATPAK_APP")
    fi
fi

# ------------------------------------------------- 3. version and Mod directory ----
detect_via_freecad() {
    local out k v
    out="$(
        "${CMD[@]}" -c "import FreeCAD,os;v=FreeCAD.Version();print('FCMCP_VERSION='+'.'.join(str(x) for x in list(v)[:3]));print('FCMCP_MODDIR='+os.path.join(FreeCAD.getUserAppDataDir(),'Mod'))" 2>/dev/null
    )" || return 1
    while IFS='=' read -r k v; do
        case "$k" in
            FCMCP_VERSION) FC_VER="$v" ;;
            FCMCP_MODDIR)  FC_MOD="$v" ;;
        esac
    done <<< "$out"
    [ -n "$FC_MOD" ] || return 1
    [ -n "$FC_VER" ] || FC_VER="unknown"
    return 0
}

guess_moddir() {
    local base d last name
    for base in "$HOME/.local/share/FreeCAD" \
                "$HOME/.var/app/${FLATPAK_APP}/data/FreeCAD" \
                "$HOME/.FreeCAD"; do
        [ -d "$base" ] || continue
        last=""
        for d in "$base"/v[0-9]*; do
            [ -d "$d" ] && last="$d"
        done
        if [ -n "$last" ]; then
            FC_MOD="$last/Mod"
            name="${last##*/}"
            FC_VER="${name#v}"
            FC_VER="${FC_VER//-/.}"
        else
            FC_MOD="$base/Mod"
            FC_VER="unknown"
        fi
        info "Guessed Mod directory: $FC_MOD"
        return 0
    done
    FC_MOD="$HOME/.local/share/FreeCAD/Mod"
    FC_VER="unknown"
    info "Guessed Mod directory: $FC_MOD"
    return 0
}

step 3/6 "Reading FreeCAD version and addon directory"
if [ "${#CMD[@]}" -gt 0 ]; then
    info "Using: ${CMD[*]}"
    if detect_via_freecad; then
        info "FreeCAD version : $FC_VER"
        info "Mod directory   : $FC_MOD"
    else
        warn "FreeCAD did not report a Mod directory."
        warn "For Snap or AppImage, pass the command with -c so this can be read."
        guess_moddir
    fi
else
    warn "Could not find headless FreeCAD (no freecadcmd on PATH, no Flatpak app)."
    warn "For Snap, AppImage or a custom install, pass the command explicitly:"
    warn "  $0 -c \"snap run --command=freecadcmd freecad\""
    guess_moddir
fi

[ -n "$FC_MOD" ] || die "could not determine the FreeCAD addon directory"

# --------------------------------------------------- 4. FreeCAD must be closed ----
step 4/6 "Checking that FreeCAD is not running"
if command -v pgrep >/dev/null 2>&1; then
    if pids="$(pgrep -x 'FreeCAD|freecad|FreeCADCmd|freecadcmd' 2>/dev/null)" && [ -n "$pids" ]; then
        warn "Close FreeCAD and run this script again. Files in the Mod directory"
        die "FreeCAD is running (pids: $(tr '\n' ' ' <<< "$pids"))."
    fi
    info "FreeCAD is not running."
else
    warn "pgrep not found; skipping the running-process check."
fi

# --------------------------------------------------------------- 5. fetch ----
try_git() {
    command -v git >/dev/null 2>&1 || return 1
    local repo="$work/repo"
    info "Cloning with git..."
    if ! git clone --depth 1 --branch "$REF" --filter=blob:none --sparse \
            "$REPO_URL" "$repo" >/dev/null 2>&1; then
        info "Sparse clone failed, retrying a plain shallow clone..."
        rm -rf "$repo"
        git clone --depth 1 --branch "$REF" "$REPO_URL" "$repo" >/dev/null 2>&1 || return 1
    fi
    git -C "$repo" sparse-checkout set addon >/dev/null 2>&1 || true
    [ -f "$repo/addon/FreeCADMCP/InitGui.py" ] || return 1
    ADDON_SRC="$repo/addon/FreeCADMCP"
    return 0
}

try_archive() {
    local url="$ARCHIVE_URL_BASE/$REF.tar.gz" tgz="$work/repo.tar.gz" hit
    info "Downloading $url"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$url" -o "$tgz" || return 1
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$tgz" "$url" || return 1
    else
        warn "Neither curl nor wget is available."
        return 1
    fi
    mkdir -p "$work/unpacked"
    tar -xzf "$tgz" -C "$work/unpacked" || return 1
    hit="$(find "$work/unpacked" -maxdepth 4 -type f \
            -path '*/addon/FreeCADMCP/InitGui.py' -print -quit 2>/dev/null)"
    [ -n "$hit" ] || return 1
    ADDON_SRC="$(dirname "$hit")"
    return 0
}

step 5/6 "Fetching the addon from $REPO_URL"
info "Ref: $REF"
if try_git; then
    info "Used git."
elif try_archive; then
    info "Used the source archive."
else
    die "could not obtain addon/FreeCADMCP from $REPO_SLUG at ref '$REF'"
fi
info "Source : $ADDON_SRC"

# ------------------------------------------------------------- 6. install ----
step 6/6 "Installing the addon"
dest="$FC_MOD/FreeCADMCP"

mkdir -p "$FC_MOD" || die "could not create $FC_MOD"

if [ -e "$dest" ]; then
    BACKUP="$FC_MOD/FreeCADMCP.bak-$(date +%Y%m%d-%H%M%S)"
    info "Backing up the existing install to:"
    info "  $BACKUP"
    mv "$dest" "$BACKUP" || die "could not move the existing addon aside"
fi

# A Mod/FreeCADMCP without InitGui.py is not a usable addon, so a partial copy
# is removed before restoring the backup.
rollback() {
    [ -n "$BACKUP" ] || return 0
    rm -rf "$dest" 2>/dev/null || true
    if mv "$BACKUP" "$dest" 2>/dev/null && [ -f "$dest/InitGui.py" ]; then
        info "[i] Restored the previous addon to: $dest"
    else
        info "[i] The previous addon was left at: $BACKUP"
    fi
    return 0
}

info "Copying to $dest"
if ! cp -a "$ADDON_SRC" "$dest"; then
    rollback
    die "copy failed"
fi
if [ ! -f "$dest/InitGui.py" ]; then
    rollback
    die "verification failed: $dest/InitGui.py is missing"
fi

printf '\n[OK] The addon was installed and verified.\n'
printf '       FreeCAD version : %s\n' "$FC_VER"
printf '       Addon directory : %s\n' "$dest"
if [ -n "$BACKUP" ]; then
    printf '       Previous install: %s\n' "$BACKUP"
fi
cat <<'EOF'

Next steps
  1. Start FreeCAD and select the "MCP Addon" workbench.
  2. Click "Start RPC Server" in the FreeCAD MCP toolbar.
  3. Point your MCP client at the matching server package:
       "command": "uvx", "args": ["freecad-mcp"]

Note: the addon and the "freecad-mcp" package ship separately and are versioned
separately. This script updates only the addon; keep the package current with
"uvx freecad-mcp@latest" or "pip install -U freecad-mcp".
EOF
