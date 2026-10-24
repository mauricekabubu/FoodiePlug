import os
import pwd
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


DATA_DIR = Path("/data")
DATABASE = DATA_DIR / "db.sqlite3"
MEDIA_DIR = DATA_DIR / "media"
SEED_DATABASE = Path("/seed/db.sqlite3")
SEED_MEDIA = Path("/seed/media")
INITIALIZED = DATA_DIR / ".foodieplug-seeded"


def seed_database():
    if not SEED_DATABASE.is_file():
        raise RuntimeError(
            "The original SQLite database is missing at /seed/db.sqlite3."
        )

    source = sqlite3.connect(SEED_DATABASE.as_uri() + "?mode=ro", uri=True)
    temporary_path = None
    try:
        integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(
                f"The original SQLite database failed integrity_check: {integrity}"
            )

        with tempfile.NamedTemporaryFile(
            prefix=".db-seed-",
            suffix=".sqlite3",
            dir=DATA_DIR,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

        destination = sqlite3.connect(temporary_path)
        try:
            source.backup(destination)
            integrity = destination.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(
                    f"The seeded SQLite database failed integrity_check: {integrity}"
                )
        finally:
            destination.close()

        try:
            os.link(temporary_path, DATABASE)
        except FileExistsError:
            pass
    finally:
        source.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def seed_media():
    if not SEED_MEDIA.is_dir():
        raise RuntimeError("The original uploaded-media directory is missing.")
    if not MEDIA_DIR.exists():
        MEDIA_DIR.mkdir(parents=True)
    if not any(MEDIA_DIR.iterdir()):
        shutil.copytree(SEED_MEDIA, MEDIA_DIR, dirs_exist_ok=True)


def set_volume_ownership():
    app = pwd.getpwnam("app")
    for directory, child_directories, files in os.walk(DATA_DIR):
        os.chown(directory, app.pw_uid, app.pw_gid)
        for name in child_directories + files:
            path = os.path.join(directory, name)
            if not os.path.islink(path):
                os.chown(path, app.pw_uid, app.pw_gid)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not INITIALIZED.exists():
        if not DATABASE.exists():
            seed_database()
        seed_media()
        INITIALIZED.touch()

    set_volume_ownership()
    app = pwd.getpwnam("app")
    os.setgroups([])
    os.setgid(app.pw_gid)
    os.setuid(app.pw_uid)
    os.environ.setdefault("HOME", app.pw_dir)

    if not sys.argv[1:]:
        raise RuntimeError("No container command was provided.")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
