"""divide — an IDE for developing generators with the Divengine ecosystem."""

from pathlib import Path


def _version() -> str:
    """The version in the VERSION file: the one beside this package (the standalone binary), the checkout's,
    else the one the installed package was built with."""
    here = Path(__file__).resolve().parent
    for path in (here / "VERSION", here.parent.parent / "VERSION"):
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    from importlib import metadata
    for name in metadata.packages_distributions().get("divide", []):
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    return "unknown"


__version__ = _version()
