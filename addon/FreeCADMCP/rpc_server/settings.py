"""Persistence of MCP RPC server settings under FreeCAD's user app data dir."""

import json
import os

import FreeCAD


_SETTINGS_FILENAME = "freecad_mcp_settings.json"

_DEFAULT_SETTINGS = {
    "remote_enabled": False,
    "allowed_ips": "127.0.0.1",
    "auto_start_rpc": False,
    # Capability gates -- see CAPABILITIES below. Secure by default: only
    # inspection and in-document modelling are on. Anything that can touch the
    # filesystem, run arbitrary code, or spawn a process is opt-in.
    "allow_document_edit": True,
    "allow_file_import": False,
    "allow_file_export": False,
    "allow_code_execution": False,
    "allow_external_processes": False,
}

# key -> (dialog label, what it gates)
CAPABILITIES = (
    ("allow_document_edit", "Create, edit and delete objects",
     "create_document, create_object, edit_object, delete_object"),
    ("allow_file_import", "Import: read files from disk",
     "reload_document, insert_part_from_library, future import_file/open_document"),
    ("allow_file_export", "Export: write files to disk",
     "future export_objects/save_document, TechDraw page export"),
    ("allow_code_execution", "Execute arbitrary Python code",
     "execute_code, execute_code_async"),
    ("allow_external_processes", "Run external solvers",
     "run_fem_analysis (spawns CalculiX)"),
)

# Superseded by the import/export split; still honoured when migrating an older
# settings file so a user who had granted file access does not silently lose it.
_LEGACY_FILE_ACCESS_KEY = "allow_file_access"

# Always available regardless of settings, because refusing them would leave the
# client unable to see anything at all -- including why a call was refused:
# ping, list_documents, get_objects, get_object, get_parts_list,
# get_active_screenshot.


def _migrate_file_access(settings):
    """Fan the old single allow_file_access flag out to import and export.

    Only seeds keys that are absent, so a settings file already carrying the new
    keys is left alone. Migrating rather than defaulting to False matters: a user
    who had deliberately granted file access should not silently lose it on
    upgrade and be left wondering why their tools started refusing.
    """
    legacy = settings.pop(_LEGACY_FILE_ACCESS_KEY, None)
    if legacy is None:
        return
    for key in ("allow_file_import", "allow_file_export"):
        settings.setdefault(key, bool(legacy))


def capability_enabled(key):
    """True if the named capability is permitted.

    Read fresh each call rather than cached: the settings dialog can flip these
    mid-session and a stale cache would silently keep a capability open after
    the user revoked it -- the wrong direction to err in for a security gate.
    """
    return bool(load_settings().get(key, _DEFAULT_SETTINGS.get(key, False)))


def _get_settings_path():
    return os.path.join(FreeCAD.getUserAppDataDir(), _SETTINGS_FILENAME)


def load_settings():
    path = _get_settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                settings = json.load(f)
            _migrate_file_access(settings)
            for key, value in _DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
        except Exception as e:
            # Keep the unreadable file for inspection rather than letting the
            # next save silently overwrite the evidence.
            FreeCAD.Console.PrintWarning(
                f"Failed to load MCP settings from {path}: {e}. "
                "Falling back to defaults; the bad file is kept as .bad\n"
            )
            try:
                os.replace(path, f"{path}.bad")
            except OSError:
                pass
    return dict(_DEFAULT_SETTINGS)


def save_settings(settings):
    """Persist settings atomically.

    Writing in place truncates the file before the new content lands, so a crash
    or a kill during that window leaves a 0-byte file -- observed in practice.
    ``load_settings`` then falls back to defaults, silently discarding the user's
    choices, which is one of the ways auto-start appeared not to work. Write to a
    temporary file in the same directory and ``os.replace`` it into position:
    that rename is atomic on POSIX, so the settings file is always either the old
    contents or the new ones, never empty.
    """
    path = _get_settings_path()
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(settings, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception as e:
        FreeCAD.Console.PrintError(f"Failed to save MCP settings: {e}\n")
        try:
            os.remove(tmp_path)
        except OSError:
            pass
