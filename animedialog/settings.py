import json
import os
import sys
from pathlib import Path


def data_root():
    root = Path(
        os.environ.get(
            "ANIMEDIALOG_HOME",
            str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AnimeDialog"),
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def resource_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def settings():
    p = data_root() / "settings.json"
    try:
        return json.loads(p.read_text(encoding="utf8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(value):
    p = data_root() / "settings.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
    tmp.replace(p)


def models_root():
    p = Path(settings().get("models_dir", str(data_root() / "models")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def executable(name):
    configured = settings().get(name)
    candidates = [Path(configured)] if configured else []
    for base in [resource_root() / "vendor", data_root() / "tools"]:
        candidates += [base / (name + ".exe"), base / name / (name + ".exe")]
        if name == "whisper-cli":
            candidates.append(base / "whisper" / "whisper-cli.exe")
        if name == "llama-server":
            candidates.append(base / "llama" / "llama-server.exe")
    for p in candidates:
        if p.is_file():
            return str(p)
    import shutil

    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    raise FileNotFoundError(f"缺少 {name}，请在模型与工具设置中安装或指定路径。")
