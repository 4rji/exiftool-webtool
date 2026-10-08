"""Pick the tool chain for each kind of file and produce a clean copy."""

import shutil
import tempfile
from pathlib import Path

from .engines import CleanError, UnsupportedFormat, exiftool_strip, mat2_clean, qpdf_rewrite

# Keep what changes how an image looks: phone photos rely on Orientation,
# and dropping the ICC profile shifts colors.
IMAGE_KEEP_TAGS = ("-tagsFromFile", "@", "-ColorSpaceTags", "-Orientation")


def _pdf(work):
    # exiftool alone only appends an incremental update (the old values stay
    # recoverable); qpdf then rewrites the file keeping only live objects.
    exiftool_strip(work)
    rewritten = work.with_name("rewritten" + work.suffix)
    qpdf_rewrite(work, rewritten)
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
