"""Metadata Cleaner: upload files, get them back without metadata.

Run in production with:  gunicorn 'app:create_app()'
"""

import mimetypes
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from cleaner import CleanError, clean_file, detect, read_metadata
from storage import JobStore

SAFE_SUFFIX = re.compile(r"\.[a-z0-9]{1,10}")
JANITOR_INTERVAL_SECONDS = 60


def _env_int(name, default):
    return int(os.environ.get(name, default))


def _defaults():
    return {
        "STORAGE_DIR": os.environ.get(
            "CLEANER_STORAGE_DIR", os.path.join(tempfile.gettempdir(), "metadata-cleaner")
        ),
        "MAX_CONTENT_LENGTH": _env_int("CLEANER_MAX_UPLOAD_MB", 200) * 1024 * 1024,
        "RETENTION_SECONDS": _env_int("CLEANER_RETENTION_MINUTES", 30) * 60,
        "START_JANITOR": True,
    }


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(_defaults())
    app.config.update(config or {})

    store = JobStore(app.config["STORAGE_DIR"])
    app.extensions["job_store"] = store
    if app.config["START_JANITOR"]:
        _start_janitor(app, store)

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            max_upload_mb=app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
            retention_minutes=app.config["RETENTION_SECONDS"] // 60,
        )

    @app.post("/clean")
    def clean():
        uploads = [upload for upload in request.files.getlist("files") if upload.filename]
        if not uploads:
            return jsonify(error="No files received"), 400
        return jsonify(files=[_process(app, store, upload) for upload in uploads])

    @app.get("/download/<file_id>")
    def download(file_id):
        folder, info = store.get(file_id) or abort(404)
        response = send_file(
            folder / info["stored_name"],
            mimetype=info["mime"],
            as_attachment=True,
            download_name=info["clean_name"],
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/metadata/<file_id>")
    def metadata(file_id):
        job = store.get(file_id)
        if job is None:
            return jsonify(error="File not found or expired"), 404
        _, info = job
        keys = ("original_name", "clean_name", "category", "mime", "removed_count", "fields")
        return jsonify({key: info[key] for key in keys})

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        limit_mb = app.config["MAX_CONTENT_LENGTH"] / (1024 * 1024)
        return jsonify(error=f"Upload too large (max {limit_mb:g} MB)"), 413

    return app


def _process(app, store, upload):
    """Clean one uploaded file; return its result row for the client."""
    original_name = _display_name(upload.filename)
    job_id, folder = store.create()
    try:
        original = folder / f"original{_safe_suffix(original_name)}"
        upload.save(original)
        mime, category = detect(original)
        suffix = _stored_suffix(original_name, mime, category)
        original = original.rename(folder / f"original{suffix}")
        cleaned = folder / f"clean{suffix}"

        before = read_metadata(original)
        clean_file(original, cleaned, category)
        after = read_metadata(cleaned)
        original.unlink()
    except CleanError as error:
        store.discard(folder)
        return {"status": "error", "original_name": original_name, "error": str(error)}
    except Exception:
        app.logger.exception("Unexpected failure cleaning %r", original_name)
        store.discard(folder)
        return {"status": "error", "original_name": original_name, "error": "Internal error while cleaning"}

    remaining = {(field["group"], field["tag"], field["value"]) for field in after}
    fields = [
        {**field, "removed": (field["group"], field["tag"], field["value"]) not in remaining}
        for field in before
    ]
    info = {
        "original_name": original_name,
        "clean_name": f"{Path(original_name).stem}_clean{suffix}",
        "stored_name": cleaned.name,
        "category": category,
        "mime": mime,
        "removed_count": sum(field["removed"] for field in fields),
        "fields": fields,
    }
    store.finish(folder, info)
    return {
        "status": "ok",
        "id": job_id,
        "original_name": info["original_name"],
        "clean_name": info["clean_name"],
        "category": category,
        "mime": mime,
        "removed_count": info["removed_count"],
        "field_count": len(fields),
    }


def _display_name(raw):
    """Browser-supplied name without any directory part or control chars."""
    name = Path((raw or "").replace("\\", "/")).name
    name = "".join(char for char in name if char.isprintable()).strip()
    return name[:200] or "file"


def _safe_suffix(name):
    suffix = Path(name).suffix.lower()
    return suffix if SAFE_SUFFIX.fullmatch(suffix) else ""


def _stored_suffix(name, mime, category):
    """Extension matching the real content, so the tools parse it correctly.

    Office and unknown files keep their own extension: libmagic often only
    sees them as a generic zip or text, while mat2 relies on the extension.
    """
    suffix = _safe_suffix(name)
    if category in ("office", "other") or mimetypes.guess_type(f"x{suffix}")[0] == mime:
        return suffix
    return mimetypes.guess_extension(mime) or suffix


def _start_janitor(app, store):
    retention = app.config["RETENTION_SECONDS"]

    def sweep_forever():
        while True:
            try:
                store.purge_expired(retention)
            except Exception:
                app.logger.exception("Failed to purge expired files")
            time.sleep(JANITOR_INTERVAL_SECONDS)

    threading.Thread(target=sweep_forever, name="janitor", daemon=True).start()


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8000, debug=True)
