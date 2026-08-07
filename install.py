#!/usr/bin/env python3
"""Install the FreeCAD MCP addon and configure an MCP client.

Setting this up by hand means: find the right Mod directory for your FreeCAD
version, copy the addon there, restart FreeCAD, hand-edit a JSON config, restart
the client. Every step has a quiet way to go wrong, and two of them went wrong
during this fork's own development -- a deployed addon five files behind the
source, and a client config pointing at the published package while the checkout
was being edited. This script does the steps and checks for exactly those.

Standard library only: an installer that needs installing is no use.

    python3 install.py                 # install the addon, then offer to wire up the client
    python3 install.py --symlink       # symlink instead of copy (development)
    python3 install.py --check         # report what is installed; change nothing
    python3 install.py --dry-run       # show what would happen
    python3 install.py --uninstall     # remove the addon, restore config from backup
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
ADDON_SRC = PROJECT / "addon" / "FreeCADMCP"
ADDON_NAME = "FreeCADMCP"
RPC_PORT = 9875
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

GREEN, YELLOW, RED, DIM, BOLD, OFF = (
    ("\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m")
    if sys.stdout.isatty() else ("", "", "", "", "", "")
)


def ok(msg): print(f"  {GREEN}✓{OFF} {msg}")
def warn(msg): print(f"  {YELLOW}!{OFF} {msg}")
def bad(msg): print(f"  {RED}✗{OFF} {msg}")
def info(msg): print(f"    {DIM}{msg}{OFF}")
def head(msg): print(f"\n{BOLD}{msg}{OFF}")


# --------------------------------------------------------------- locating FreeCAD

def mod_dir_candidates() -> list[Path]:
    """Every place FreeCAD might keep user modules, most likely first.

    The v1-0 / v1-1 split is the easiest thing to get wrong by hand: FreeCAD 1.1
    ignores an addon dropped in the 1.0 directory, silently, and you are left
    wondering why the toolbar never appears.
    """
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        base = home / "Library" / "Application Support" / "FreeCAD"
        roots = [base / "v1-1", base / "v1-0", base]
    elif system == "Windows":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        base = appdata / "FreeCAD"
        roots = [base / "v1-1", base / "v1-0", base]
    else:
        roots = [
            home / ".local" / "share" / "FreeCAD" / "v1-1",
            home / ".local" / "share" / "FreeCAD" / "v1-0",
            home / ".local" / "share" / "FreeCAD",
            home / ".FreeCAD",
            home / "snap" / "freecad" / "common",
        ]
    return [r / "Mod" for r in roots]


def find_mod_dir() -> tuple[Path | None, list[Path]]:
    """Pick the Mod directory, preferring one that already exists. Returns (choice, probed)."""
    probed = mod_dir_candidates()
    for candidate in probed:
        if candidate.is_dir():
            return candidate, probed
    # None exist yet: fall back to the first (newest) candidate, created on install.
    return (probed[0] if probed else None), probed


def freecad_version() -> str | None:
    """Ask a FreeCAD binary for its version, if one can be found on PATH."""
    for exe in ("freecadcmd", "FreeCADCmd", "freecad", "FreeCAD"):
        path = shutil.which(exe)
        if not path:
            continue
        try:
            out = subprocess.run([path, "--version"], capture_output=True, text=True,
                                 timeout=30).stdout
            match = re.search(r"(\d+\.\d+\.\d+)", out)
            if match:
                return match.group(1)
        except Exception:
            continue
    return None


# ------------------------------------------------------------------ addon install

def addon_state(dest: Path) -> str:
    if dest.is_symlink():
        return f"symlink -> {os.readlink(dest)}"
    if dest.is_dir():
        return "copy"
    return "absent"


def newer_files(src: Path, dst: Path) -> list[str]:
    """Source files newer than their installed counterparts, or missing there."""
    stale = []
    for path in src.rglob("*.py"):
        rel = path.relative_to(src)
        target = dst / rel
        if not target.exists() or path.stat().st_mtime > target.stat().st_mtime + 1:
            stale.append(str(rel))
    return stale


def install_addon(mod_dir: Path, symlink: bool, dry_run: bool) -> bool:
    dest = mod_dir / ADDON_NAME
    head(f"Addon -> {dest}")

    if not ADDON_SRC.is_dir():
        bad(f"source not found: {ADDON_SRC}")
        return False

    if dry_run:
        info(f"would {'symlink' if symlink else 'copy'} {ADDON_SRC} -> {dest}")
        if dest.exists() or dest.is_symlink():
            info(f"would back up the existing {addon_state(dest)} to {dest.name}.backup-{STAMP}")
        return True

    mod_dir.mkdir(parents=True, exist_ok=True)

    # Never overwrite silently: an existing install may be the only copy of a
    # local modification.
    if dest.is_symlink() or dest.exists():
        backup = mod_dir / f"{ADDON_NAME}.backup-{STAMP}"
        shutil.move(str(dest), str(backup))
        ok(f"existing {addon_state(backup)} backed up to {backup.name}")

    if symlink:
        dest.symlink_to(ADDON_SRC, target_is_directory=True)
        ok(f"symlinked -> {ADDON_SRC}")
        info("edits to the checkout take effect on the next FreeCAD restart, no re-copy")
    else:
        shutil.copytree(ADDON_SRC, dest,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        ok("copied")
    return True


# ----------------------------------------------------------------- client config
#
# Config locations verified against each project's own documentation (Aug 2026).
# Three clients share the same `mcpServers` JSON shape, so one writer covers all
# of them; the rest are reported rather than guessed at.
#
#   Claude Desktop  ~/Library/Application Support/Claude/claude_desktop_config.json
#                   %APPDATA%\\Claude\\... on Windows, ~/.config/Claude/... on Linux
#   Cursor          ~/.cursor/mcp.json   (a project .cursor/mcp.json overrides it)
#   Gemini CLI      ~/.gemini/settings.json  (or a project .gemini/settings.json)
#   Claude Code     no file we should edit -- `claude mcp add` owns that state
#   Codex CLI       ~/.codex/config.toml, [mcp_servers.<name>] -- TOML, not JSON,
#                   and `codex mcp add` exists, so let it write its own format
#   ChatGPT desktop connectors are added in the app UI; there is no config file
#   Grok            not an MCP client. The "grok mcp" projects are MCP *servers*
#                   wrapping the Grok CLI -- the opposite direction. Nothing to do.

def claude_desktop_config() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if system == "Windows":
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return appdata / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


JSON_CLIENTS = {
    "claude-desktop": ("Claude Desktop", claude_desktop_config),
    "cursor": ("Cursor", lambda: Path.home() / ".cursor" / "mcp.json"),
    "gemini": ("Gemini CLI", lambda: Path.home() / ".gemini" / "settings.json"),
}
CLI_CLIENTS = {
    "claude-code": ("Claude Code", "claude"),
    "codex": ("Codex CLI", "codex"),
}


def client_present(key: str) -> bool:
    home = Path.home()
    if key == "claude-desktop":
        return claude_desktop_config().exists() or Path("/Applications/Claude.app").exists()
    if key == "cursor":
        return (home / ".cursor").exists() or Path("/Applications/Cursor.app").exists()
    if key == "gemini":
        return shutil.which("gemini") is not None or (home / ".gemini").exists()
    if key in CLI_CLIENTS:
        return shutil.which(CLI_CLIENTS[key][1]) is not None or (home / f".{key.split('-')[0]}").exists()
    return False


def all_clients() -> list[tuple[str, str, bool]]:
    """(key, label, present) for every client this script can set up."""
    out = [(k, label, client_present(k)) for k, (label, _) in JSON_CLIENTS.items()]
    out += [(k, label, client_present(k)) for k, (label, _) in CLI_CLIENTS.items()]
    return out


def server_entry(mode: str) -> dict:
    if mode == "released":
        return {"command": "uvx", "args": ["freecad-mcp"]}
    return {"command": "uv", "args": ["--directory", str(PROJECT), "run", "freecad-mcp"]}


def write_json_client(key: str, mode: str, dry_run: bool) -> bool:
    label, path_fn = JSON_CLIENTS[key]
    config = path_fn()
    entry = server_entry(mode)
    head(f"{label} -> {config}")

    if dry_run:
        info(f"would set mcpServers.freecad = {json.dumps(entry)}")
        return True

    data = {}
    if config.exists():
        try:
            data = json.loads(config.read_text() or "{}")
        except json.JSONDecodeError as e:
            bad(f"existing config is not valid JSON ({e}); refusing to touch it")
            info("fix or move it, then re-run")
            return False
        backup = config.with_suffix(config.suffix + f".backup-{STAMP}")
        shutil.copy2(config, backup)
        ok(f"backed up to {backup.name}")
    else:
        config.parent.mkdir(parents=True, exist_ok=True)

    servers = data.setdefault("mcpServers", {})
    previous = servers.get("freecad")
    # Merge, never template: other MCP servers in this file must survive.
    servers["freecad"] = entry
    config.write_text(json.dumps(data, indent=2) + "\n")

    if previous and previous != entry:
        ok(f"replaced the freecad entry (was: {json.dumps(previous)})")
    elif previous:
        ok("freecad entry already correct")
    else:
        ok("freecad entry added")
    others = [k for k in servers if k != "freecad"]
    if others:
        info(f"left untouched: {', '.join(others)}")
    return True


def write_cli_client(key: str, mode: str, dry_run: bool) -> bool:
    """Let the client's own CLI write its config.

    Codex uses TOML and Claude Code keeps MCP state in a file full of unrelated
    session data. Both ship an `mcp add` command, which is the supported way in
    and cannot drift from their format the way a hand-rolled writer would.
    """
    label, exe = CLI_CLIENTS[key]
    entry = server_entry(mode)
    cmd = [exe, "mcp", "add", "freecad", "--", entry["command"], *entry["args"]]
    head(f"{label} -> {exe} mcp add")

    if dry_run:
        info("would run: " + " ".join(cmd))
        return True
    if not shutil.which(exe):
        warn(f"{exe} not on PATH; skipped")
        return True
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        bad(f"could not run {exe}: {e}")
        return False
    if result.returncode == 0:
        ok("registered")
        return True
    message = (result.stderr or result.stdout).strip().splitlines()
    already = any("already exists" in line.lower() for line in message)
    if already:
        ok("already registered")
        info(f"replace it with: {exe} mcp remove freecad && " + " ".join(cmd))
        return True
    warn(f"{exe} declined: {message[0] if message else 'unknown error'}")
    info("run it yourself: " + " ".join(cmd))
    return True


def configure_clients(keys: list[str], mode: str, dry_run: bool) -> bool:
    fine = True
    for key in keys:
        if key in JSON_CLIENTS:
            fine &= write_json_client(key, mode, dry_run)
        elif key in CLI_CLIENTS:
            fine &= write_cli_client(key, mode, dry_run)
    return fine


def report_unwritable_clients() -> None:
    """Clients with no config we can safely write."""
    notes = []
    if Path("/Applications/ChatGPT.app").exists():
        notes.append(("ChatGPT desktop",
                      "add the connector in the app's settings -- there is no config file"))
    if notes:
        head("Also installed, but set up in-app")
        for label, how in notes:
            print(f"  {DIM}.{OFF} {label}")
            info(how)


# ------------------------------------------------------------------------ asking

def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask_choice(question: str, options: list[str], default: int = 0) -> int:
    """Numbered menu. Returns the chosen index; the default on a bare Enter."""
    print(f"\n{BOLD}{question}{OFF}")
    for i, option in enumerate(options, 1):
        mark = " (default)" if i - 1 == default else ""
        print(f"  {i}. {option}{DIM}{mark}{OFF}")
    while True:
        raw = input("  choice [Enter for default]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"  {YELLOW}enter a number between 1 and {len(options)}{OFF}")


def ask_yes(question: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"  {question} {suffix} ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False


def ask_mod_dir(chosen: Path, probed: list[Path]) -> Path:
    """Confirm where the addon goes, offering every candidate plus a free path.

    Worth asking rather than assuming: FreeCAD 1.1 silently ignores an addon left
    in the 1.0 directory, and someone running two versions side by side has no
    way to tell this script which they meant.
    """
    existing = [p for p in probed if p.is_dir()]
    options = [f"{p}{'' if p.is_dir() else '   (will be created)'}" for p in probed]
    options.append("somewhere else (type a path)")
    default = probed.index(chosen) if chosen in probed else 0

    if len(existing) <= 1:
        print(f"\n{BOLD}FreeCAD modules directory{OFF}")
        print(f"  {chosen}")
        if ask_yes("use this?", True):
            return chosen
    index = ask_choice("Where should the addon go?", options, default)
    if index < len(probed):
        return probed[index]
    while True:
        raw = input("  path to a Mod directory: ").strip()
        if raw:
            return Path(raw).expanduser()


def ask_clients() -> list[str]:
    """Pick which MCP clients to wire up. Detected ones are the default."""
    clients = all_clients()
    detected = [k for k, _, present in clients if present]

    print(f"\n{BOLD}MCP clients{OFF}")
    for i, (_, label, present) in enumerate(clients, 1):
        mark = f"{GREEN}found{OFF}" if present else f"{DIM}not detected{OFF}"
        print(f"  {i}. {label}  [{mark}]")
    print(f"  {DIM}Only Claude Desktop and Claude Code are tested; the rest are")
    print(f"  best-effort from each project's documented config location.{OFF}")

    suggestion = ",".join(str(i) for i, (_, _, p) in enumerate(clients, 1) if p) or "none"
    raw = input(f"\n  numbers, comma-separated, or 'none' [{suggestion}]: ").strip().lower()
    if raw == "none":
        return []
    if not raw:
        return detected
    picked = []
    for part in raw.replace(" ", "").split(","):
        if part.isdigit() and 1 <= int(part) <= len(clients):
            picked.append(clients[int(part) - 1][0])
    return picked


def ask_mode() -> str:
    index = ask_choice(
        "Which build should the client launch?",
        ["the published package  (uvx freecad-mcp)",
         f"this checkout  (uv --directory {PROJECT})"],
        0,
    )
    return "released" if index == 0 else "dev"


# ------------------------------------------------------------------------ checks

def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def run_checks(mod_dir: Path | None) -> None:
    """Report the conditions that silently break this setup."""
    head("Checks")

    version = freecad_version()
    if version:
        ok(f"FreeCAD {version} on PATH")
    else:
        warn("no FreeCAD binary on PATH (fine if you launch it from Applications)")

    if sys.version_info < (3, 12):
        warn(f"this interpreter is {platform.python_version()}; the MCP server needs 3.12+")
        info("only matters for running the server here -- uv fetches its own")
    else:
        ok(f"python {platform.python_version()}")

    if shutil.which("uv"):
        ok("uv found")
    else:
        bad("uv not found -- the MCP client cannot launch the server without it")
        info("install from https://docs.astral.sh/uv/")

    dest = (mod_dir / ADDON_NAME) if mod_dir else None
    if dest and (dest.exists() or dest.is_symlink()):
        ok(f"addon installed as {addon_state(dest)}")
        if dest.is_symlink():
            # A symlink cannot go stale -- FreeCAD reads whatever the target
            # holds. Worth saying which tree that is, though: pointing at a
            # working copy rather than addon/ is deliberate during development
            # but surprising afterwards.
            target = dest.resolve()
            if target != ADDON_SRC.resolve():
                info(f"note: it points at {target}, not {ADDON_SRC}")
        else:
            stale = newer_files(ADDON_SRC, dest)
            if stale:
                warn(f"{len(stale)} source file(s) newer than the installed copy")
                for name in stale[:5]:
                    info(name)
                info("re-run this script to refresh, then restart FreeCAD")
            else:
                ok("installed copy is up to date with addon/")
    else:
        warn("addon not installed yet")

    config = claude_desktop_config()
    if config.exists():
        try:
            entry = json.loads(config.read_text()).get("mcpServers", {}).get("freecad")
        except Exception:
            entry = None
        if not entry:
            warn("Claude Desktop has no freecad entry")
        elif entry.get("command") == "uvx":
            ok("Claude Desktop -> published package (uvx freecad-mcp)")
            if (PROJECT / ".git").exists():
                warn("but you are working in a checkout -- edits to src/ will NOT be used")
                info("re-run with --dev to point it at this folder instead")
        else:
            target = " ".join(entry.get("args", []))
            ok(f"Claude Desktop -> {entry.get('command')} {target}")
    else:
        warn(f"no Claude Desktop config at {config}")

    if port_busy(RPC_PORT):
        ok(f"something is listening on {RPC_PORT} (the RPC server looks up)")
    else:
        info(f"nothing on port {RPC_PORT} -- start it from the MCP toolbar in FreeCAD")

    settings = freecad_settings_path()
    if settings and settings.exists() and settings.stat().st_size == 0:
        warn(f"{settings.name} is 0 bytes -- settings were lost; defaults will be used")
    for suffix in (".bad", ".tmp"):
        if settings and settings.with_suffix(settings.suffix + suffix).exists():
            warn(f"leftover {settings.name}{suffix} from a failed write")


def freecad_settings_path() -> Path | None:
    mod_dir, _ = find_mod_dir()
    return (mod_dir.parent / "freecad_mcp_settings.json") if mod_dir else None


# --------------------------------------------------------------------- uninstall

def uninstall(mod_dir: Path | None, dry_run: bool, touch_client: bool = True) -> None:
    """Remove the addon, and optionally the client entry.

    ``touch_client`` is honoured for --no-client, and forced off when the caller
    named an explicit --mod-dir: uninstalling from a directory you pointed at by
    hand should not reach out and edit the real Claude Desktop config. That
    combination did exactly that during testing here, wiping a live entry.
    """
    head("Uninstall")
    if mod_dir:
        dest = mod_dir / ADDON_NAME
        if dest.is_symlink() or dest.exists():
            if dry_run:
                info(f"would remove {dest}")
            else:
                if dest.is_symlink():
                    dest.unlink()
                else:
                    shutil.rmtree(dest)
                ok(f"removed {dest}")
        else:
            info("addon was not installed")

        backups = sorted(mod_dir.glob(f"{ADDON_NAME}.backup-*"))
        if backups:
            info(f"backups left in place: {', '.join(b.name for b in backups)}")

    if not touch_client:
        info("client config left alone (--no-client, or an explicit --mod-dir was given)")
        return

    config = claude_desktop_config()
    if config.exists():
        if dry_run:
            info(f"would remove the freecad entry from {config}")
        else:
            try:
                data = json.loads(config.read_text())
            except Exception:
                bad("config is not valid JSON; left alone")
                return
            if data.get("mcpServers", {}).pop("freecad", None) is not None:
                shutil.copy2(config, config.with_suffix(f".json.backup-{STAMP}"))
                config.write_text(json.dumps(data, indent=2) + "\n")
                ok("removed the freecad entry (other servers untouched)")
            else:
                info("no freecad entry to remove")


# -------------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the FreeCAD MCP addon and configure Claude Desktop.")
    parser.add_argument("--symlink", action="store_true",
                        help="symlink the addon instead of copying (development)")
    parser.add_argument("--dev", action="store_true",
                        help="point the client at this checkout instead of the published package")
    parser.add_argument("--check", action="store_true", help="report status only, change nothing")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen")
    parser.add_argument("--uninstall", action="store_true", help="remove the addon and the client entry")
    parser.add_argument("--mod-dir", type=Path, help="install into this Mod directory explicitly")
    parser.add_argument("--no-client", action="store_true", help="install the addon only")
    parser.add_argument("--client", action="append", metavar="NAME",
                        help="configure this client (repeatable): "
                             + ", ".join(k for k, _, _ in all_clients()))
    parser.add_argument("-y", "--yes", action="store_true",
                        help="take the defaults; ask nothing (for scripts)")
    args = parser.parse_args()

    print(f"{BOLD}FreeCAD MCP installer{OFF}  {DIM}({PROJECT}){OFF}")

    if args.mod_dir:
        mod_dir, probed = args.mod_dir, [args.mod_dir]
    else:
        mod_dir, probed = find_mod_dir()

    if mod_dir is None:
        bad("could not work out where FreeCAD keeps its modules. Probed:")
        for candidate in probed:
            info(str(candidate))
        info("pass --mod-dir /path/to/Mod to say explicitly")
        return 1

    if args.check:
        run_checks(mod_dir)
        return 0

    if args.uninstall:
        # An explicit --mod-dir means "operate on that tree", not "and also edit
        # my real client config".
        uninstall(mod_dir, args.dry_run,
                  touch_client=not args.no_client and args.mod_dir is None)
        print("\nRestart FreeCAD and Claude Desktop to finish.")
        return 0

    asking = interactive() and not args.yes and not args.dry_run and not args.mod_dir
    if asking:
        mod_dir = ask_mod_dir(mod_dir, probed)
    elif not (mod_dir.exists() or args.mod_dir):
        warn(f"{mod_dir} does not exist yet; it will be created")
        info("if FreeCAD keeps its modules elsewhere, cancel and pass --mod-dir")

    if not install_addon(mod_dir, args.symlink, args.dry_run):
        return 1

    if args.no_client:
        clients, mode = [], "released"
    elif args.client:
        clients, mode = args.client, ("dev" if args.dev else "released")
    elif asking:
        clients = ask_clients()
        mode = ask_mode() if clients else "released"
    else:
        clients = [k for k, _, present in all_clients() if present and k == "claude-desktop"]
        mode = "dev" if args.dev else "released"

    if clients and not configure_clients(clients, mode, args.dry_run):
        return 1
    if not clients and not args.no_client:
        info("no MCP client configured")

    if not args.dry_run:
        run_checks(mod_dir)
    report_unwritable_clients()

    head("Installed. Nothing left to copy by hand.")
    print(f"  The addon is in place at {mod_dir / ADDON_NAME}")
    if clients:
        print(f"  Client config written for: {', '.join(clients)}")
    print("\n  Two restarts are all that remain:")
    print("   1. FreeCAD          -- it loads addons once at startup")
    print("      then: MCP toolbar (top left) -> click the dot to start the server,")
    print("      or open the gear and tick auto-start")
    print("   2. your MCP client  -- it launches the MCP server at startup")
    print(f"\n{DIM}Check anytime with:  python3 install.py --check{OFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
