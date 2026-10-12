"""Pick the tool chain for each kind of file and produce a clean copy."""

import shutil
import tempfile
from pathlib import Path

from .engines import (
    CleanError,
    UnsupportedFormat,
    exiftool_strip,
    mat2_clean,
    qpdf_objects,
    qpdf_rewrite,
)

# Keep what changes how an image looks: phone photos rely on Orientation,
# and dropping the ICC profile shifts colors.
IMAGE_KEEP_TAGS = ("-tagsFromFile", "@", "-ColorSpaceTags", "-Orientation")

# exiftool and qpdf only remove the document-level Info and XMP. Pages, images,
# fonts and form XObjects can carry their own XMP packet, and PieceInfo holds
# private data from the authoring application.
PDF_PRIVATE_KEYS = {"/Metadata", "/PieceInfo", "/LastModified"}
# Comment author and dates. Widgets are skipped: there /T is the form field name.
PDF_ANNOTATION_KEYS = {"/T", "/M", "/CreationDate"}


def _scrub_pdf_value(value):
    if isinstance(value, list):
        return [_scrub_pdf_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    scrubbed = {key: _scrub_pdf_value(item) for key, item in value.items() if key not in PDF_PRIVATE_KEYS}
    is_annotation = "/Rect" in scrubbed and "/Subtype" in scrubbed
    if is_annotation and scrubbed["/Subtype"] != "/Widget":
        scrubbed = {key: item for key, item in scrubbed.items() if key not in PDF_ANNOTATION_KEYS}
    return scrubbed


def _pdf_updates(objects):
    """Objects that carry metadata, rewritten without it (qpdf JSON v2)."""
    updates = {}
    for key, obj in objects.items():
        if not key.startswith("obj:"):
            continue
        if "stream" in obj:
            # Without "data", qpdf keeps the original stream data.
            new = {"stream": {"dict": _scrub_pdf_value(obj["stream"]["dict"])}}
        else:
            new = {"value": _scrub_pdf_value(obj["value"])}
        if new != obj:
            updates[key] = new
    return updates


def _pdf(work):
    # exiftool alone only appends an incremental update (the old values stay
    # recoverable); qpdf then rewrites the file keeping only live objects, so
    # the XMP streams no longer referenced by any object are dropped too.
    exiftool_strip(work)
    rewritten = work.with_name("rewritten" + work.suffix)
    qpdf_rewrite(work, rewritten, _pdf_updates(qpdf_objects(work)))
    return rewritten


def _image(work):
    exiftool_strip(work, keep=IMAGE_KEEP_TAGS)
    return work


def _exiftool(work):
    exiftool_strip(work)
    return work


def _mat2(work):
    mat2_clean(work)
    return work


CHAINS = {
    "pdf": (_pdf,),
    "image": (_image, _mat2),
    "media": (_exiftool, _mat2),
    "office": (_mat2,),
    "other": (_exiftool, _mat2),
}


def clean_file(src, dst, category):
    """Write a metadata-free copy of src to dst. src is never modified.

    Tries each tool in the category's chain until one succeeds.
    Raises CleanError (or UnsupportedFormat) when none can clean the file.
    """
    src, dst = Path(src), Path(dst)
    errors = []
    with tempfile.TemporaryDirectory(dir=dst.parent) as tmp:
        for step in CHAINS[category]:
            work = Path(tmp) / f"work{src.suffix.lower()}"
            shutil.copyfile(src, work)
            try:
                result = step(work)
            except CleanError as error:
                errors.append(error)
                continue
            shutil.move(result, dst)
            return
    real_errors = [error for error in errors if not isinstance(error, UnsupportedFormat)]
    if real_errors:
        raise real_errors[0]
    raise UnsupportedFormat("Unsupported format: no tool can rewrite this file type")
