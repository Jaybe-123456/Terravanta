"""Exercise the evidence-object backup/restore procedure against isolated local files."""

import hashlib
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from app.config import settings
from app.evidence_storage import delete_private, get_private, put_private, safe_key


def main() -> None:
    original_backend = settings.evidence_storage_backend
    original_uploads = settings.uploads_dir
    original_environment = settings.app_env
    with tempfile.TemporaryDirectory(prefix="terravanta-evidence-restore-") as directory:
        root = Path(directory)
        settings.evidence_storage_backend = "local"
        settings.uploads_dir = str(root / "live")
        settings.app_env = "test"
        organization_id, case_id, artifact_id = uuid4(), uuid4(), uuid4()
        key = safe_key(organization_id, case_id, artifact_id, ".csv")
        payload = b"evidence_reference,amount\nRESTORE-CI,125.00\n"
        digest = hashlib.sha256(payload).hexdigest()
        source = Path(settings.uploads_dir) / "receivables" / key
        backup = root / "backup" / key
        try:
            put_private(key, payload, "text/csv")
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup)
            delete_private(key)
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, source)
            restored = get_private(key)
            assert hashlib.sha256(restored).hexdigest() == digest
            print("Evidence object restore verified: restored bytes match the manifest SHA-256.")
        finally:
            settings.evidence_storage_backend = original_backend
            settings.uploads_dir = original_uploads
            settings.app_env = original_environment


if __name__ == "__main__":
    main()
