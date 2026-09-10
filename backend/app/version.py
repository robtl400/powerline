from pathlib import Path

_FALLBACK = "0.0.0-unknown"

_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "VERSION",
    Path("/etc/powerline/VERSION"),
    Path("/app/VERSION"),
)


def _read_version() -> str:
    for path in _CANDIDATES:
        try:
            text = path.read_text().strip()
        except OSError:
            continue
        if text:
            return text
    return _FALLBACK


__version__: str = _read_version()
