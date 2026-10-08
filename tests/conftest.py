"""Shared fixtures: sample files carrying known, identifiable metadata."""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

SECRET = "Jane Secret"
REQUIRED_TOOLS = ("exiftool", "qpdf", "mat2", "file")

missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
if missing:
    pytest.exit(f"Missing required tools on PATH: {', '.join(missing)}", returncode=2)


def exiftool_write(path, *assignments):
    subprocess.run(
        ["exiftool", "-q", "-overwrite_original", *assignments, "--", str(path)],
        check=True,
    )


@pytest.fixture
def jpeg_with_metadata(tmp_path):
    path = tmp_path / "photo.jpg"
    shutil.copy(FIXTURES / "tiny.jpg", path)
    exiftool_write(
        path,
        f"-Artist={SECRET}",
        "-Model=Pixel 9",
        "-GPSLatitude=40.4168",
        "-GPSLatitudeRef=N",
        "-GPSLongitude=3.7038",
        "-GPSLongitudeRef=W",
        "-Orientation#=6",
        f"-XMP-dc:Creator={SECRET}",
    )
    return path


@pytest.fixture
def png_with_metadata(tmp_path):
    path = tmp_path / "image.png"
    shutil.copy(FIXTURES / "tiny.png", path)
    exiftool_write(path, f"-PNG:Author={SECRET}", f"-XMP-dc:Creator={SECRET}")
    return path


def build_pdf(author):
    """Minimal one-page PDF whose Info dictionary names an author."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R /Resources << >> >>",
        b"<< /Length 18 >>\nstream\n0 0 m 100 100 l S\nendstream",
        f"<< /Author ({author}) /Producer (Secret Office 1.0) /CreationDate (D:20240101000000Z) >>".encode(),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 5 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture
def pdf_with_metadata(tmp_path):
    path = tmp_path / "report.pdf"
    path.write_bytes(build_pdf(SECRET))
    exiftool_write(path, f"-XMP-dc:Creator={SECRET}")
    return path


def build_docx(path, creator):
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Quarterly numbers</w:t></w:r></w:p></w:body></w:document>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:creator>{creator}</dc:creator><cp:lastModifiedBy>{creator}</cp:lastModifiedBy>"
        '<dcterms:created xsi:type="dcterms:W3CDTF">2024-01-01T00:00:00Z</dcterms:created>'
        "</cp:coreProperties>"
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        "<Application>Microsoft Office Word</Application><Company>Secret Corp</Company></Properties>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)


@pytest.fixture
def docx_with_metadata(tmp_path):
    path = tmp_path / "letter.docx"
    build_docx(path, SECRET)
    return path


@pytest.fixture
def text_file(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("just some plain text\n")
    return path


@pytest.fixture
def unknown_binary(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"\xde\xad\xbe\xef\x00\x13\x37" * 300)
    return path
