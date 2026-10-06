import hashlib
import json
import os
import subprocess
from fractions import Fraction
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


def export_clips(project, opts, cache, control):
    """Re-encode accurate cuts, then mux them individually or concatenate in order."""
    from .pipeline import ensure_space

    clips = opts.get("clips", [])
    if not clips or opts.get("mode") not in ["separate", "joined"]:
        raise ValueError("请添加片段并选择分段或合并导出。")
    output = Path(opts["output"]).resolve()
    folder = output if opts["mode"] == "separate" else output.parent
    sources, inputs = {}, []
    control.progress("检查片段", 0)
    for clip in clips:
        control.check()
        episode = project.get("episodes", clip["episode_id"])
        if not episode:
            raise ValueError("片段所属剧集已移除，请重新添加台词。")
        path = Path(episode["path"]).resolve()
        if path not in sources:
            metadata = probe(path)
            video = next(
                (
                    s
                    for s in metadata["streams"]
                    if s.get("codec_type") == "video"
                    and not s.get("disposition", {}).get("attached_pic")
                ),
                None,
            )
            if not video:
                raise ValueError("文件没有可导出的画面：" + path.name)
            duration = round(float(metadata["format"].get("duration", 0)) * 1000)
            sources[path] = (metadata, video, duration)
        metadata, video, duration = sources[path]
        a, b = clip["start_ms"], clip["end_ms"]
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= duration:
            raise ValueError(
                f"片段时间超出视频范围：{path.name}，有效时长 {duration / 1000:.3f} 秒"
            )
        audio = [s["index"] for s in metadata["streams"] if s.get("codec_type") == "audio"]
        index = clip.get("audio_index", episode.get("audio_index"))
        if index is None:
            index = audio[0] if audio else None
        if index is not None and index not in audio:
            raise ValueError("所选音轨已不存在，请重新选择音轨并添加导出任务。")
        if output == path:
            raise ValueError("导出位置不能覆盖原视频。")
        inputs.append((clip, path, video, index))
    folder.mkdir(parents=True, exist_ok=True)
    limit = opts.get("max_height", 1080)
    if limit not in [0, 720, 1080]:
        raise ValueError("不支持的输出画质。")

    def video_format(video):
        sar = (
            Fraction(video.get("sample_aspect_ratio", "1:1").replace(":", "/"))
            if video.get("sample_aspect_ratio", "N/A") != "N/A"
            else Fraction(1)
        )
        width, height = video["width"] * (float(sar) or 1), video["height"]
        rotation = next(
            (
                s.get("rotation", 0)
                for s in video.get("side_data_list", [])
                if s.get("side_data_type") == "Display Matrix"
            ),
            0,
        )
        if abs(round(rotation)) % 180 == 90:
            width, height = height, width
        scale = min(1, limit / height, limit * 16 / 9 / width) if limit else 1
        w, h = max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)
        try:
            fps = Fraction(video.get("avg_frame_rate", "0/1"))
        except (ValueError, ZeroDivisionError):
            fps = Fraction(30)
        fps = fps if 1 <= fps <= 120 else Fraction(30)
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,setpts=PTS-STARTPTS,fps={fps}"
        return w, h, fps, vf

    ffmpeg = [
        executable("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-abort_on",
        "empty_output_stream",
        "-y",
    ]

    def process(args, target):
        if not target.exists():
            partial = target.with_name(target.stem + "-partial" + target.suffix)
            try:
                control.process(args + [str(partial)], cache / "clips.log")
                control.check()
                if partial.stat().st_size == 0:
                    raise ValueError("片段为空，请调整时间后重试。")
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)

    encoded = []
    for i, (clip, path, video, index) in enumerate(inputs):
        control.check()
        w, h, fps, vf = video_format(inputs[0][2] if opts["mode"] == "joined" else video)
        seconds = (clip["end_ms"] - clip["start_ms"]) / 1000
        stat = path.stat()
        signature = json.dumps(
            [
                str(path),
                stat.st_size,
                stat.st_mtime_ns,
                clip["start_ms"],
                clip["end_ms"],
                index,
                w,
                h,
                str(fps),
            ],
            ensure_ascii=True,
        ).encode()
        key = hashlib.sha256(signature).hexdigest()[:20]
        target = cache / ("clip-" + key + ".mkv")
        if not target.exists():
            ensure_space(cache, int(seconds * 1500000) + 64 * 1024**2)
        control.progress(
            "裁剪片段", 85 * i / len(inputs), f"{i + 1}/{len(inputs)} · {clip.get('text', '')[:40]}"
        )
        args = ffmpeg + ["-ss", str(clip["start_ms"] / 1000), "-i", str(path)]
        if index is None:
            args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        args += [
            "-map",
            f"0:{video['index']}",
            "-map",
            f"0:{index}" if index is not None else "1:a:0",
            "-t",
            str(seconds),
            "-vf",
            vf,
            "-af",
            f"aresample=48000:async=1:first_pts=0,apad,atrim=duration={seconds}",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "pcm_s16le",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
        ]
        process(args, target)
        encoded.append(target)
    if opts["mode"] == "joined":
        key = hashlib.sha256("\n".join(p.name for p in encoded).encode()).hexdigest()[:20]
        listing = cache / "concat.txt"
        listing.write_text("\n".join(f"file '{p.name}'" for p in encoded), encoding="ascii")
        deliveries = [
            (
                cache / ("joined-" + key + ".mp4"),
                output,
                ffmpeg + ["-f", "concat", "-safe", "0", "-i", str(listing)],
            )
        ]
    else:
        deliveries = []
        for i, (clip, path, video, index) in enumerate(inputs):
            text = (
                "".join(
                    "_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in clip.get("text", "片段")
                )[:40].strip(". ")
                or "片段"
            )
            deliveries.append(
                (
                    encoded[i].with_suffix(".mp4"),
                    folder / f"{i + 1:03d}-{text}.mp4",
                    ffmpeg + ["-i", str(encoded[i])],
                )
            )
    for i, (target, destination, args) in enumerate(deliveries):
        control.check()
        if not target.exists():
            ensure_space(
                cache,
                sum(p.stat().st_size for p in encoded) + 32 * 1024**2
                if opts["mode"] == "joined"
                else encoded[i].stat().st_size + 32 * 1024**2,
            )
        control.progress(
            "写入视频", 85 + 14 * i / len(deliveries), f"{i + 1}/{len(deliveries)} · {destination}"
        )
        process(
            args
            + [
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
            ],
            target,
        )
        if destination.exists():
            # A crash after publishing but before completion may leave our exact file.
            with target.open("rb") as source, destination.open("rb") as existing:
                while True:
                    control.check()
                    chunk = source.read(1024**2)
                    if chunk != existing.read(1024**2):
                        raise FileExistsError("已存在不同的文件，未覆盖：" + str(destination))
                    if not chunk:
                        break
            continue
        ensure_space(folder, target.stat().st_size + 32 * 1024**2)
        partial = folder / ("." + destination.name + "-" + control.job_id + ".partial")
        try:
            with target.open("rb") as source, partial.open("wb") as copy:
                while chunk := source.read(1024**2):
                    control.check()
                    copy.write(chunk)
            control.check()
            if os.name == "nt":
                partial.rename(destination)  # Windows refuses to replace an existing file.
            else:
                os.link(partial, destination)
        finally:
            partial.unlink(missing_ok=True)
    control.progress("片段导出完成", 100, str(output))
