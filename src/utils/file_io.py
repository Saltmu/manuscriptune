import os


def read_file(filepath: str | None) -> str:
    """Reads the contents of a file. Returns empty string if filepath is None or doesn't exist."""
    if not filepath or not os.path.exists(filepath):
        return ""
    with open(filepath, encoding="utf-8") as f:
        return f.read()
