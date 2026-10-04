import json
import os
import subprocess
from pathlib import Path

from .settings import executable


def hidden_flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def run(args, **kw):
    return subprocess.run(args, creationflags=hidden_flags(), capture_output=True, **kw)


def probe(path):
    if not Path(path).is_file():
        raise FileNotFoundError("视频不存在，请重新关联文件。")
    p = run(
        [
            executable("ffprobe"),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout=60,
    )
    if p.returncode:
        raise ValueError(p.stderr.decode("utf8", errors="replace")[-1200:])
    return json.loads(p.stdout.decode("utf8"))


def extract_audio(path, target, audio_index=None, start_ms=None, end_ms=None):
    args = [executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"]
    if start_ms is not None:
        args += ["-ss", str(start_ms / 1000)]
    args += ["-i", str(path)]
    if end_ms is not None:
        args += ["-t", str((end_ms - (start_ms or 0)) / 1000)]
    if audio_index is not None:
        args += ["-map", f"0:{audio_index}"]
    args += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target)]
    return args


def frame(path, target, time_ms=0):
    p = run(
        [
            executable("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(time_ms / 1000),
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale=960:-2",
            str(target),
        ],
        timeout=60,
    )
    if p.returncode:
        raise ValueError("无法读取视频画面：" + p.stderr.decode("utf8", errors="replace")[-500:])


def preview_args(path, target, audio_index=None):
    return [
        executable("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-map",
        f"0:{audio_index}" if audio_index is not None else "0:a:0?",
        "-vf",
        "scale=1280:-2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "25",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(target),
    ]
