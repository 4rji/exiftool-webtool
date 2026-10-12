"""Thin wrappers around the external tools: file, exiftool, qpdf and mat2.

Every command runs without a shell, with a timeout, and from the file's own
directory so error messages never leak server paths.
"""

import json
import subprocess
from pathlib import Path

TIMEOUT_SECONDS = 60


class CleanError(Exception):
    """A file could not be cleaned. The message is safe to show to users."""


class UnsupportedFormat(CleanError):
    """The tool does not know how to write this kind of file."""


def _run(cmd, cwd=None):
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        raise CleanError(f"{cmd[0]} is not installed on the server") from None
    except subprocess.TimeoutExpired:
        raise CleanError(f"{cmd[0]} timed out after {TIMEOUT_SECONDS}s") from None


def _first_message(proc):
    for line in (proc.stderr + "\n" + proc.stdout).splitlines():
        line = line.strip(" -[]")
        if line and not line.lower().startswith("warning"):
            return line
    return f"exit code {proc.returncode}"


def file_mime(path):
    proc = _run(["file", "--brief", "--mime-type", "--", str(path)])
    return proc.stdout.strip() or "application/octet-stream"


def exiftool_read(path):
    """Return exiftool's metadata for path as a {"Group:Tag": value} dict."""
    path = Path(path)
    proc = _run(["exiftool", "-json", "-a", "-G1", "--", path.name], cwd=path.parent)
    try:
        entries = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return {}
    return entries[0] if entries else {}


def exiftool_strip(path, keep=()):
    """Remove all writable metadata in place, then copy back the `keep` tags."""
    path = Path(path)
    proc = _run(
        ["exiftool", "-all=", *keep, "-overwrite_original", "--", path.name],
        cwd=path.parent,
    )
    if proc.returncode != 0:
        message = _first_message(proc)
        error = UnsupportedFormat if "not supported" in message or "not yet supported" in message else CleanError
        raise error(f"exiftool: {message}")


def qpdf_objects(path):
    """Return the PDF's objects as qpdf JSON v2 ({"obj:N G R": ...}), without stream data."""
    path = Path(path)
    proc = _run(
        ["qpdf", "--json-output", "--json-stream-data=none", "--json-key=qpdf", path.name, "-"],
        cwd=path.parent,
    )
    if proc.returncode not in (0, 3):
        raise CleanError(f"qpdf: {_first_message(proc)}")
    try:
        return json.loads(proc.stdout)["qpdf"][1]
    except (json.JSONDecodeError, KeyError, IndexError):
        raise CleanError("qpdf: could not read the PDF structure") from None


def qpdf_rewrite(src, dst, updates=None):
    """Rewrite a PDF from scratch, dropping Info, XMP and old revisions.

    `updates` maps "obj:N G R" to replacement objects in qpdf JSON v2;
    streams given without data keep their original data.
    """
    src, dst = Path(src), Path(dst)
    update_args = []
    if updates:
        update_file = src.with_name("updates.json")
        update_file.write_text(json.dumps({"qpdf": [{"jsonversion": 2}, updates]}))
        update_args = [f"--update-from-json={update_file.name}"]
    proc = _run(
        [
            "qpdf",
            "--remove-info",
            "--remove-metadata",
            *update_args,
            "--linearize",
            "--deterministic-id",
            src.name,
            dst.name,
        ],
        cwd=src.parent,
    )
    # qpdf exits with 3 when it succeeded with warnings.
    if proc.returncode not in (0, 3) or not dst.exists():
        raise CleanError(f"qpdf: {_first_message(proc)}")


def mat2_clean(path):
    """Clean an Office/ODF/EPUB (or any mat2-supported) file in place."""
    path = Path(path)
    proc = _run(
        ["mat2", "--inplace", "--unknown-members", "keep", "--", path.name],
        cwd=path.parent,
    )
    if proc.returncode != 0:
        message = _first_message(proc)
        error = UnsupportedFormat if "not supported" in message else CleanError
        raise error(f"mat2: {message}")
