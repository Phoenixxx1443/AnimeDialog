"""Archive application source and record the installer and source hashes."""

import hashlib
import json
import tomllib
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf8"))["project"]["version"]

release = root / "release"
release.mkdir(exist_ok=True)
source = release / f"AnimeDialog-{version}-Source.zip"
installer = release / f"AnimeDialog-{version}-Windows-x64-Setup.exe"
if not installer.is_file():
    raise FileNotFoundError(f"请先构建安装包：{installer}")
roots = ["animedialog", "scripts", "licenses"]
files = [
    ".gitignore",
    ".gitattributes",
    "AnimeDialog.spec",
    "LICENSE",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
    "requirements-lock.txt",
    "main.py",
    "使用说明.html",
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
manifest = {}
for path in [installer, source]:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            sha.update(block)
    manifest[path.name] = dict(bytes=path.stat().st_size, sha256=sha.hexdigest())
(release / f"SHA256-{version}.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8"
)
(release / "SHA256.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8"
)
print(json.dumps(manifest, ensure_ascii=True, indent=2))
