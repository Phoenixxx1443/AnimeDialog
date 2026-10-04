"""Archive only explicit source and example project paths; record release hashes."""

import hashlib
import json
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from animedialog import __version__

release = root / "release"
release.mkdir(exist_ok=True)
source = release / f"AnimeDialog-{__version__}-Source.zip"
roots = ["animedialog", "tests", "scripts", "licenses"]
files = [
    ".gitignore",
    "AnimeDialog.spec",
    "LICENSE",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
    "requirements-lock.txt",
    "main.py",
    "使用说明.html",
    "验收记录.md",
    "更新说明-1.1.md",
    "验收记录-1.1.md",
    "代码整理-1.1.1.md",
    "更新说明-1.1.2.md",
]
with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as out:
    for name in files:
        out.write(root / name, "AnimeDialog/" + name)
    for name in roots:
        for path in sorted((root / name).rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix not in [".pyc", ".log"]
            ):
                out.write(path, "AnimeDialog/" + path.relative_to(root).as_posix())
backup = release / "超时空辉夜姬_AnimeDialog项目备份.zip"
if not backup.exists():
    project = root / "作品/超时空辉夜姬"
    from sqlite3 import connect

    snapshot = root / ".qa/project-backup.sqlite"
    snapshot.parent.mkdir(exist_ok=True)
    db = connect(project / "project.sqlite")
    copy = connect(snapshot)
    db.backup(copy)
    copy.close()
    db.close()
    with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for path in sorted(project.rglob("*")):
            if (
                path.is_file()
                and "cache" not in path.relative_to(project).parts
                and path.suffix not in [".lock", ".log"]
                and path.name not in ["project.sqlite-wal", "project.sqlite-shm"]
            ):
                out.write(
                    snapshot if path.name == "project.sqlite" else path,
                    "超时空辉夜姬/" + path.relative_to(project).as_posix(),
                )
manifest = {}
for path in [release / f"AnimeDialog-{__version__}-Windows-x64-Setup.exe", source, backup]:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            sha.update(block)
    manifest[path.name] = dict(bytes=path.stat().st_size, sha256=sha.hexdigest())
(release / f"SHA256-{__version__}.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8"
)
(release / "SHA256.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8"
)
print(json.dumps(manifest, ensure_ascii=True, indent=2))
