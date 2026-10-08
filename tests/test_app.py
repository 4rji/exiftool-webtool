import io
import os
import time

import pytest

from app import create_app
from conftest import SECRET


@pytest.fixture
def app(tmp_path):
    return create_app({"STORAGE_DIR": str(tmp_path / "storage"), "START_JANITOR": False})


@pytest.fixture
def client(app):
    return app.test_client()


def upload(client, *paths, names=None):
    names = names or [path.name for path in paths]
    files = [(io.BytesIO(path.read_bytes()), name) for path, name in zip(paths, names)]
    return client.post("/clean", data={"files": files}, content_type="multipart/form-data")


def test_index_page_is_the_metadata_cleaner(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"metadata" in response.data.lower()
    assert b"Markdown" not in response.data


def test_clean_returns_a_result_per_file(client, jpeg_with_metadata, docx_with_metadata):
    response = upload(client, jpeg_with_metadata, docx_with_metadata)
    assert response.status_code == 200
    jpeg, docx = response.get_json()["files"]
    assert jpeg["status"] == "ok"
    assert jpeg["category"] == "image"
    assert jpeg["clean_name"] == "photo_clean.jpg"
    assert jpeg["removed_count"] > 0
    assert docx["status"] == "ok"
    assert docx["category"] == "office"
    assert docx["clean_name"] == "letter_clean.docx"


def test_download_serves_the_cleaned_file(client, jpeg_with_metadata):
    file_id = upload(client, jpeg_with_metadata).get_json()["files"][0]["id"]
    response = client.get(f"/download/{file_id}")
    assert response.status_code == 200
    assert "photo_clean.jpg" in response.headers["Content-Disposition"]
    assert response.data.startswith(b"\xff\xd8")
    assert SECRET.encode() not in response.data


def test_metadata_lists_original_fields_and_what_was_removed(client, jpeg_with_metadata):
    file_id = upload(client, jpeg_with_metadata).get_json()["files"][0]["id"]
    report = client.get(f"/metadata/{file_id}").get_json()
    assert report["original_name"] == "photo.jpg"
    by_tag = {field["tag"]: field for field in report["fields"]}
    assert by_tag["Artist"]["value"] == SECRET
    assert by_tag["Artist"]["removed"] is True
    assert by_tag["GPSLatitude"]["removed"] is True
    assert by_tag["Orientation"]["removed"] is False


def test_unsupported_file_fails_alone_in_a_batch(client, unknown_binary, jpeg_with_metadata):
    results = upload(client, unknown_binary, jpeg_with_metadata).get_json()["files"]
    assert results[0]["status"] == "error"
    assert results[0]["original_name"] == "blob.bin"
    assert "Unsupported" in results[0]["error"]
    assert results[1]["status"] == "ok"


def test_misnamed_file_is_cleaned_by_its_real_type(client, jpeg_with_metadata):
    result = upload(client, jpeg_with_metadata, names=["invoice.pdf"]).get_json()["files"][0]
    assert result["status"] == "ok"
    assert result["category"] == "image"
    assert result["clean_name"] == "invoice_clean.jpg"


def test_client_path_is_stripped_from_names(client, jpeg_with_metadata):
    result = upload(client, jpeg_with_metadata, names=["../../etc/photo.jpg"]).get_json()["files"][0]
    assert result["original_name"] == "photo.jpg"


def test_original_upload_is_not_kept_on_disk(app, client, jpeg_with_metadata):
    file_id = upload(client, jpeg_with_metadata).get_json()["files"][0]["id"]
    job_dir = os.path.join(app.config["STORAGE_DIR"], file_id)
    stored = b"".join(
        open(os.path.join(job_dir, name), "rb").read()
        for name in os.listdir(job_dir)
        if not name.endswith(".json")
    )
    assert SECRET.encode() not in stored


def test_request_without_files_is_rejected(client):
    response = client.post("/clean", data={}, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "error" in response.get_json()


@pytest.mark.parametrize("file_id", ["0" * 32, "not-a-real-id", "..%2F..%2Fetc"])
def test_unknown_ids_are_not_found(client, file_id):
    assert client.get(f"/download/{file_id}").status_code == 404
    assert client.get(f"/metadata/{file_id}").status_code == 404


def test_oversized_upload_returns_json_error(tmp_path, jpeg_with_metadata):
    app = create_app({
        "STORAGE_DIR": str(tmp_path / "storage"),
        "START_JANITOR": False,
        "MAX_CONTENT_LENGTH": 100,
    })
    response = upload(app.test_client(), jpeg_with_metadata)
    assert response.status_code == 413
    assert "too large" in response.get_json()["error"].lower()


def test_expired_jobs_are_purged(app, client, jpeg_with_metadata):
    file_id = upload(client, jpeg_with_metadata).get_json()["files"][0]["id"]
    store = app.extensions["job_store"]
    old = time.time() - 31 * 60
    os.utime(os.path.join(app.config["STORAGE_DIR"], file_id), (old, old))

    assert store.purge_expired(max_age_seconds=30 * 60) == 1
    assert client.get(f"/download/{file_id}").status_code == 404


def test_fresh_jobs_survive_purge(app, client, jpeg_with_metadata):
    file_id = upload(client, jpeg_with_metadata).get_json()["files"][0]["id"]
    assert app.extensions["job_store"].purge_expired(max_age_seconds=30 * 60) == 0
    assert client.get(f"/download/{file_id}").status_code == 200
