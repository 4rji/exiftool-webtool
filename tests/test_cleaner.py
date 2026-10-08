import shutil
import zipfile

import pytest

from cleaner import CleanError, clean_file, detect, read_metadata
from conftest import SECRET


def values(fields):
    return {field["value"] for field in fields}


def tags(fields):
    return {field["tag"] for field in fields}


# ---------- detection ----------

def test_detects_jpeg_as_image(jpeg_with_metadata):
    assert detect(jpeg_with_metadata) == ("image/jpeg", "image")


def test_detects_pdf(pdf_with_metadata):
    assert detect(pdf_with_metadata) == ("application/pdf", "pdf")


def test_detects_docx_as_office(docx_with_metadata):
    mime, category = detect(docx_with_metadata)
    assert category == "office"
    assert "wordprocessingml" in mime


def test_detects_by_content_not_extension(jpeg_with_metadata, tmp_path):
    disguised = tmp_path / "invoice.pdf"
    shutil.copy(jpeg_with_metadata, disguised)
    assert detect(disguised) == ("image/jpeg", "image")


def test_detects_plain_text_as_other(text_file):
    assert detect(text_file)[1] == "other"


# ---------- metadata reading ----------

def test_read_metadata_lists_document_fields(jpeg_with_metadata):
    fields = read_metadata(jpeg_with_metadata)
    assert SECRET in values(fields)
    assert "GPSLatitude" in tags(fields)
    assert all({"group", "tag", "value"} <= field.keys() for field in fields)


def test_read_metadata_hides_server_side_file_info(jpeg_with_metadata):
    groups = {field["group"] for field in read_metadata(jpeg_with_metadata)}
    assert not groups & {"System", "ExifTool", "Composite"}


# ---------- cleaning ----------

def test_cleans_jpeg_gps_and_author(jpeg_with_metadata, tmp_path):
    out = tmp_path / "clean.jpg"
    clean_file(jpeg_with_metadata, out, "image")
    fields = read_metadata(out)
    assert SECRET not in values(fields)
    assert "Pixel 9" not in values(fields)
    assert not {"GPSLatitude", "GPSLongitude"} & tags(fields)
    assert SECRET.encode() not in out.read_bytes()


def test_cleaning_jpeg_keeps_orientation(jpeg_with_metadata, tmp_path):
    out = tmp_path / "clean.jpg"
    clean_file(jpeg_with_metadata, out, "image")
    assert "Orientation" in tags(read_metadata(out))


def test_cleaning_leaves_original_untouched(jpeg_with_metadata, tmp_path):
    before = jpeg_with_metadata.read_bytes()
    clean_file(jpeg_with_metadata, tmp_path / "clean.jpg", "image")
    assert jpeg_with_metadata.read_bytes() == before


def test_cleans_png(png_with_metadata, tmp_path):
    out = tmp_path / "clean.png"
    clean_file(png_with_metadata, out, "image")
    assert SECRET.encode() not in out.read_bytes()


def test_cleans_pdf_without_leaving_recoverable_revisions(pdf_with_metadata, tmp_path):
    out = tmp_path / "clean.pdf"
    clean_file(pdf_with_metadata, out, "pdf")
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert SECRET.encode() not in data
    assert b"Secret Office" not in data
    assert SECRET not in values(read_metadata(out))


def test_cleans_docx_properties(docx_with_metadata, tmp_path):
    out = tmp_path / "clean.docx"
    clean_file(docx_with_metadata, out, "office")
    with zipfile.ZipFile(out) as archive:
        assert "word/document.xml" in archive.namelist()
        assert b"Quarterly numbers" in archive.read("word/document.xml")
        everything = b"".join(archive.read(name) for name in archive.namelist())
    assert SECRET.encode() not in everything
    assert b"Secret Corp" not in everything


def test_plain_text_passes_through(text_file, tmp_path):
    out = tmp_path / "clean.txt"
    clean_file(text_file, out, "other")
    assert out.read_text() == text_file.read_text()


def test_unknown_binary_is_unsupported(unknown_binary, tmp_path):
    out = tmp_path / "clean.bin"
    with pytest.raises(CleanError, match="Unsupported"):
        clean_file(unknown_binary, out, "other")
    assert not out.exists()


def test_corrupt_pdf_reports_error(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\nthis is not really a pdf\n")
    with pytest.raises(CleanError):
        clean_file(broken, tmp_path / "clean.pdf", "pdf")
