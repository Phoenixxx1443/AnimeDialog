"""Download only public model assets. Range resume and SHA256 verification."""

import hashlib
import json
import shutil
import tarfile
from pathlib import Path

import httpx

from .settings import models_root

MODEL_SPECS = {
    "whisper-turbo": dict(
        name="声音识别 large-v3-turbo",
        file="whisper-turbo.bin",
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin",
    ),
    "whisper-large": dict(
        name="精细重识别 large-v3",
        file="whisper-large.bin",
        url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-q5_0.bin",
    ),
    "qwen": dict(
        name="本地翻译与人物语义 Qwen3 8B",
        file="qwen.gguf",
        url="https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf",
    ),
    "segmentation": dict(
        name="声音切分 pyannote",
        file="segmentation.onnx",
        url="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
        archive=True,
    ),
    "embedding": dict(
        name="人物声音特征 3D speaker",
        file="embedding.onnx",
        url="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
    ),
}


def model_path(key):
    return models_root() / MODEL_SPECS[key]["file"]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def verify_format(path, key):
    if Path(path).stat().st_size < 1024:
        raise ValueError("模型文件不完整")
    with Path(path).open("rb") as stream:
        head = stream.read(4)
    if key == "qwen" and head != b"GGUF":
        raise ValueError("请选择有效的 GGUF 模型")
    if key.startswith("whisper") and head not in [b"lmgg", b"ggml"]:
        raise ValueError("请选择 whisper.cpp 的 .bin 模型")
    if key in ["embedding", "segmentation"]:
        import onnxruntime as ort

        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        del session


def import_model(key, source):
    verify_format(source, key)
    dest = model_path(key)
    tmp = dest.with_suffix(dest.suffix + ".importing")
    if Path(source).resolve() != dest.resolve():
        shutil.copyfile(source, tmp)
        tmp.replace(dest)
    info = {"sha256": digest(dest), "source": "local", "verified": True}
    dest.with_suffix(dest.suffix + ".json").write_text(json.dumps(info), encoding="utf8")
    return dest


def download_model(key, progress=lambda *_: None, cancel=lambda: False):
    spec = MODEL_SPECS[key]
    dest = model_path(key)
    raw = dest.with_suffix(".archive") if spec.get("archive") else dest
    part = raw.with_suffix(raw.suffix + ".part")
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(90, connect=30),
        headers={"Accept-Encoding": "identity"},
    ) as client:
        publisher_head = client.head(spec["url"], follow_redirects=False)
        head = client.head(spec["url"])
        head.raise_for_status()
        expected = publisher_head.headers.get("x-linked-etag", "").strip('"')
        total = int(head.headers.get("x-linked-size", head.headers.get("content-length", 0)))
        offset = part.stat().st_size if part.exists() else 0
        if total and offset > total:
            part.unlink()
            offset = 0
        if total > 128 * 1024**2 and offset != total:
            from .downloads import parallel_ranges

            parallel_ranges(spec["url"], part, total, progress, cancel)
        elif not total or offset != total:
            with client.stream(
                "GET", spec["url"], headers={"Range": f"bytes={offset}-"} if offset else {}
            ) as response:
                response.raise_for_status()
                if offset and response.status_code != 206:
                    offset = 0
                if response.status_code == 206 and not response.headers.get(
                    "content-range", ""
                ).startswith(f"bytes {offset}-"):
                    raise ValueError("下载服务器返回错误的范围，请重试")
                total = total or offset + int(response.headers.get("content-length", 0))
                with part.open("ab" if offset else "wb") as out:
                    for chunk in response.iter_bytes(1024 * 1024):
                        if cancel():
                            raise InterruptedError("下载已暂停，可再次下载续传")
                        out.write(chunk)
                        offset += len(chunk)
                        progress(offset, total)
        if total and part.stat().st_size != total:
            raise ValueError("模型下载不完整，请重试续传")
        sha = digest(part)
        if len(expected) == 64 and sha.lower() != expected.lower():
            raise ValueError("模型校验失败，请删除残缺下载后重试")
        if spec.get("archive"):
            with tarfile.open(part) as archive:
                candidates = [
                    m for m in archive.getmembers() if m.isfile() and m.name.endswith("/model.onnx")
                ]
                if len(candidates) != 1:
                    raise ValueError("模型压缩包结构不正确")
                stream = archive.extractfile(candidates[0])
                tmp = dest.with_suffix(".extracting")
                with tmp.open("wb") as out:
                    shutil.copyfileobj(stream, out)
                verify_format(tmp, key)
                tmp.replace(dest)
            part.unlink()
        else:
            verify_format(part, key)
            part.replace(dest)
        dest.with_suffix(dest.suffix + ".json").write_text(
            json.dumps(
                dict(sha256=digest(dest), download_sha256=sha, source=spec["url"], verified=True)
            ),
            encoding="utf8",
        )
    return dest
