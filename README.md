# Metadata Cleaner

A small self-hosted web tool that removes hidden metadata (GPS location, author,
company, device model, software, edit history…) from images, PDFs, Office
documents and media files. Drop files in the browser, download clean copies,
and open a report listing every metadata field found in the original.

Built for a private / internal network: there is no login and no rate limiting.

## How files are cleaned

The file type is detected from its **content** (libmagic), not its extension.

| Type | Tool chain |
| --- | --- |
| PDF | `exiftool -all=` then `qpdf --remove-info --remove-metadata --linearize --deterministic-id` |
| Images (JPEG, PNG, HEIC, TIFF, GIF, WebP…) | `exiftool -all=`, keeping Orientation and the color profile so the picture looks the same; falls back to `mat2` |
| Office / ODF / EPUB (docx, xlsx, pptx, odt, ods, odp, epub) | `mat2` |
| Audio / video and anything else | `exiftool -all=`, falling back to `mat2` |

Why the PDF needs both tools: `exiftool` only appends an incremental update
to a PDF, so the old values can still be recovered. `qpdf` then rewrites the
whole file and keeps only the objects that are still in use.

Files that no tool can rewrite (for example legacy `.doc`/`.xls` or unknown
binaries) are reported as *Unsupported format*; the rest of the batch is still
cleaned.

Uploads are processed in `<storage>/<random-id>/`. The original upload is
deleted as soon as it has been cleaned. Only the clean copy and the metadata
report are kept, and both are deleted after the retention period (30 minutes
by default).

## Install on a Linux server (systemd)

Requires Debian 13 (trixie), or another distribution that ships
**qpdf ≥ 11.10**, because `--remove-info` and `--remove-metadata` first
appeared in that version.

```bash
sudo ./deploy/install.sh
```

The script:

1. Installs `exiftool`, `qpdf`, `mat2`, `file`, `python3-flask` and `gunicorn` with apt.
2. Creates the `exiftool-webtool` system user.
3. Copies the app to `/opt/exiftool-webtool`.
4. Enables the `exiftool-webtool` systemd service, which runs gunicorn on `0.0.0.0:8777`.

Run it again after pulling changes to update the deployed copy.

Settings live in `/etc/default/exiftool-webtool`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `CLEANER_BIND` | `0.0.0.0:8777` | Address gunicorn listens on |
| `CLEANER_MAX_UPLOAD_MB` | `200` | Max size of one upload request |
| `CLEANER_RETENTION_MINUTES` | `30` | When cleaned files are deleted |
| `CLEANER_STORAGE_DIR` | `/var/cache/exiftool-webtool/jobs` | Working directory |

```bash
sudo systemctl restart exiftool-webtool   # apply changes
journalctl -u exiftool-webtool -f         # logs
```

## Development

```bash
sudo apt install libimage-exiftool-perl libarchive-zip-perl qpdf mat2 file python3-flask gunicorn python3-pytest
python3 app.py            # http://<this-host>:8777 (Flask dev server)
python3 -m pytest         # tests need exiftool, qpdf, mat2 and file on PATH
```

## HTTP API

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/clean` | Multipart field `files` (one or more). Returns `{"files": [...]}` with one result per file. |
| `GET` | `/download/<id>` | Cleaned file, named `<name>_clean.<ext>` |
| `GET` | `/metadata/<id>` | Metadata found in the original, with `removed: true/false` per field |

```bash
curl -F files=@photo.jpg -F files=@report.pdf http://server:8777/clean
```
