"""Update the single release version, or check installed package metadata."""

import argparse
import json
from datetime import date
from importlib.metadata import PackageNotFoundError, version as installed_version
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "addon" / "FreeCADMCP" / "package.xml"
REGISTRY = ROOT / "server.json"
NAMESPACE = "{https://wiki.freecad.org/Package_Metadata}"


def read_version(path: Path) -> str:
    """Read the required release version from addon metadata."""
    value = ET.parse(path).getroot().findtext(f"{NAMESPACE}version")
    if not value or not value.strip():
        raise ValueError(f"Missing version in {path}")
    return value.strip()


def registry_metadata(path: Path) -> dict:
    """Load the registry entry and require the package we publish."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("packages"), list):
        raise ValueError(f"Invalid registry metadata in {path}")
    if not any(p.get("identifier") == "freecad-mcp" for p in data["packages"]):
        raise ValueError(f"Missing freecad-mcp package in {path}")
    return data


def check_registry(path: Path, expected: str) -> None:
    data = registry_metadata(path)
    versions = [data.get("version")] + [
        p.get("version") for p in data["packages"] if p.get("identifier") == "freecad-mcp"
    ]
    if any(value != expected for value in versions):
        raise ValueError(f"Registry versions {versions} != package.xml version {expected}")


def atomic_write(path: Path, text: str) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        temporary.chmod(path.stat().st_mode)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def bump_version(path: Path, new_version: str, release_date: date) -> str:
    """Validate first, then atomically update version and date, keeping XML comments."""
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", new_version):
        raise ValueError("Use a release version in X.Y.Z format, without a v prefix")
    old_version = read_version(path)
    if new_version == old_version:
        return old_version
    if tuple(map(int, new_version.split("."))) < tuple(map(int, old_version.split("."))):
        raise ValueError(f"New version {new_version} must be greater than {old_version}")

    text = path.read_text(encoding="utf-8")
    for tag, value in (("version", new_version), ("date", release_date.isoformat())):
        text, count = re.subn(rf"<{tag}>[^<]*</{tag}>", f"<{tag}>{value}</{tag}>", text)
        if count != 1:
            raise ValueError(f"Expected exactly one <{tag}> in {path}")
    ET.fromstring(text)
    atomic_write(path, text)
    return old_version


def bump_release(metadata: Path, registry: Path, new_version: str, release_date: date) -> str:
    """Validate both files before updating; restore XML if registry writing fails."""
    data = registry_metadata(registry)
    data["version"] = new_version
    for package in data["packages"]:
        if package.get("identifier") == "freecad-mcp":
            package["version"] = new_version
    registry_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    original = metadata.read_text(encoding="utf-8")
    previous = bump_version(metadata, new_version, release_date)
    try:
        if registry_text != registry.read_text(encoding="utf-8"):
            atomic_write(registry, registry_text)
    except OSError:
        if metadata.read_text(encoding="utf-8") != original:
            atomic_write(metadata, original)
        raise
    return previous


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("version", nargs="?", help="New release version (X.Y.Z)")
    mode.add_argument("--check", action="store_true", help="Check installed package against package.xml")
    args = parser.parse_args()
    try:
        if args.check:
            expected = read_version(METADATA)
            actual = installed_version("freecad-mcp")
            if actual != expected:
                raise ValueError(f"Installed version {actual} != package.xml version {expected}")
            check_registry(REGISTRY, expected)
            print(f"Package, addon and registry version: {expected}")
        else:
            previous = bump_release(METADATA, REGISTRY, args.version, date.today())
            print(f"{previous} -> {args.version} ({METADATA.relative_to(ROOT)})")
    except (OSError, ValueError, ET.ParseError, PackageNotFoundError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
