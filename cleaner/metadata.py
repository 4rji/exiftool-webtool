"""Read a file's metadata in a display-friendly shape."""

from .engines import exiftool_read

# Facts about the copy on this server (path, permissions, exiftool version)
# or values exiftool derives from other tags, not metadata inside the file.
HIDDEN_GROUPS = {"System", "ExifTool", "Composite"}


def read_metadata(path):
    """Return [{"group", "tag", "value"}] for the metadata stored in path."""
    fields = []
    for key, value in exiftool_read(path).items():
        group, _, tag = key.partition(":")
        if not tag or group in HIDDEN_GROUPS:
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        fields.append({"group": group, "tag": tag, "value": str(value)})
    return fields
