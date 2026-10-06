import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit


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


def translation_endpoint(value):
    value = value.strip().rstrip("/")
    url = urlsplit(value)
    if (
        not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or any(c.isspace() for c in value)
        or url.scheme != "https"
        and not (url.scheme == "http" and url.hostname in ["localhost", "127.0.0.1", "::1"])
    ):
        raise ValueError("API 地址须使用 HTTPS；本机服务可使用 HTTP。地址不能包含密钥或参数。")
    url.port  # Validate a supplied port before handing the address to httpx.
    return value if url.path.endswith("/chat/completions") else value + "/chat/completions"


def protected_key(value, decrypt=False):
    """Keep API credentials outside projects, protected by the Windows user account."""
    import base64
    import ctypes

    if not value:
        return ""

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.c_void_p)]

    raw = base64.b64decode(value, validate=True) if decrypt else value.encode("utf8")
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.c_void_p))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(Blob),
    ]
    operation.restype = ctypes.c_int
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError("无法保存或读取 API Key，请在当前 Windows 账号下重新输入。")
    free = ctypes.WinDLL("kernel32").LocalFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_void_p
    try:
        result = ctypes.string_at(target.data, target.size)
        return result.decode("utf8") if decrypt else base64.b64encode(result).decode("ascii")
    finally:
        free(target.data)


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
