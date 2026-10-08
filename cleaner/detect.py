"""Classify uploads by their content (libmagic), not by their extension."""

from pathlib import Path

from .engines import file_mime

OFFICE_MIME_PREFIXES = (
    "application/vnd.openxmlformats-officedocument.",
    "application/vnd.oasis.opendocument.",
    "application/epub+zip",
)
# Some generators write OOXML/ODF zips that libmagic only sees as a plain zip.
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".odg", ".epub"}


def detect(path):
    """Return (mime_type, category); category is image|pdf|office|media|other."""
    mime = file_mime(path)
    if mime == "application/pdf":
        return mime, "pdf"
    if mime.startswith(OFFICE_MIME_PREFIXES):
        return mime, "office"
    if mime == "application/zip" and Path(path).suffix.lower() in OFFICE_EXTENSIONS:
        return mime, "office"
    if mime.startswith("image/") and mime != "image/svg+xml":
        return mime, "image"
    if mime.startswith(("audio/", "video/")):
        return mime, "media"
    return mime, "other"
