"""Per-upload working folders that expire after a while."""

import json
import re
import shutil
import time
import uuid
from pathlib import Path

JOB_ID = re.compile(r"[0-9a-f]{32}")
INFO_FILE = "job.json"


class JobStore:
    """Each upload gets <root>/<uuid>/ holding the cleaned file and job.json."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def create(self):
        job_id = uuid.uuid4().hex
        path = self.root / job_id
        path.mkdir(mode=0o700)
        return job_id, path

    def finish(self, path, info):
        (path / INFO_FILE).write_text(json.dumps(info))

    def discard(self, path):
        shutil.rmtree(path, ignore_errors=True)

    def get(self, job_id):
        """Return (folder, info) for a finished job, or None if unknown/expired."""
        if not JOB_ID.fullmatch(job_id):
            return None
        path = self.root / job_id
        try:
            return path, json.loads((path / INFO_FILE).read_text())
        except (OSError, ValueError):
            return None

    def purge_expired(self, max_age_seconds):
        """Delete job folders older than max_age_seconds; return how many."""
        cutoff = time.time() - max_age_seconds
        purged = 0
        for path in self.root.iterdir():
            if not JOB_ID.fullmatch(path.name):
                continue
            try:
                expired = path.stat().st_mtime < cutoff
            except FileNotFoundError:
                continue
            if expired:
                shutil.rmtree(path, ignore_errors=True)
                purged += 1
        return purged
