import json
import queue
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx

from .domain import now
from .media import hidden_flags
from .models import model_path
from .settings import executable, protected_key, settings, translation_endpoint


class Paused(Exception):
    pass


class Cancelled(Exception):
    pass


class Control:
    def __init__(self, project, job_id):
        self.project = project
        self.job_id = job_id
        self.child = None

    def check(self):
        request = self.project.get("jobs", self.job_id).get("request", "run")
        if request == "pause":
            raise Paused("任务已暂停，继续时从检查点恢复")
        if request == "cancel":
            raise Cancelled("任务已取消，已保存的成果保留")

    def progress(self, stage, value, message=""):
        self.project.update_job(
            self.job_id,
            stage=stage,
            progress=max(0, min(100, value)),
            message=message,
            updated=now(),
        )
        print(
            json.dumps(
                dict(type="progress", stage=stage, progress=value, message=message),
                ensure_ascii=True,
            ),
            flush=True,
        )

    def process(self, args, log):
        self.check()
        with Path(log).open("wb") as f:
            child = subprocess.Popen(
                args, stdout=f, stderr=subprocess.STDOUT, creationflags=hidden_flags()
            )
            self.child = child
            try:
                while child.poll() is None:
                    self.check()
                    time.sleep(0.25)
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                self.child = None
        if child.returncode:
            raise RuntimeError(Path(log).read_text(encoding="utf8", errors="replace")[-2000:])


def require_model(key):
    p = model_path(key)
    if not p.exists():
        raise FileNotFoundError(f"缺少模型 {key}，请先在“模型与工具”中下载或导入。")
    return str(p)


def transcribe(audio, prefix, language, control, large=False):
    model = require_model("whisper-large" if large else "whisper-turbo")
    import numpy as np
    import soundfile as sf

    signal, _ = sf.read(audio, dtype="float32")
    if signal.size == 0 or float(np.max(np.abs(signal))) < 0.0001:
        return [], language or "auto"
    del signal
    base = [
        executable("whisper-cli"),
        "-m",
        model,
        "-f",
        str(audio),
        "-l",
        language or "auto",
        "-t",
        "6",
        "-ojf",
        "-of",
        str(prefix),
        "-mc",
        "0",
        "-ml",
        "100",
    ]
    json_path = prefix.with_suffix(".json")
    done = prefix.with_suffix(".done")
    raw = None
    if done.exists() and json_path.exists():
        try:
            raw = json.loads(json_path.read_text(encoding="utf8", errors="replace"))
        except ValueError:
            pass
    if raw is None:
        try:
            control.process(base, prefix.with_suffix(".log"))
        except RuntimeError:
            control.progress("声音识别", 0, "显卡运行失败，改用 CPU 重试本片段")
            control.process(base + ["-ng"], prefix.with_suffix(".cpu.log"))
        raw = json.loads(json_path.read_text(encoding="utf8", errors="replace"))
        done.touch()
    result = []
    for item in raw.get("transcription", []):
        text = item.get("text", "").strip()
        a = item.get("offsets", {}).get("from", 0)
        b = item.get("offsets", {}).get("to", 0)
        if not text or b <= a:
            continue
        probabilities = [
            t.get("p", 0) for t in item.get("tokens", []) if t.get("id", 99999) < 50257
        ]
        confidence = sum(probabilities) / len(probabilities) if probabilities else None
        flags = ["低置信度声音识别，需复听"] if confidence is not None and confidence < 0.65 else []
        if re.search(r"(.{1,12}?)(?:[\s、，,！!。…]*\1){5,}", text):
            flags.append("识别文字大量重复，可能为卡顿、哭声或幻觉，请复听")
        if len(text) <= 2 and re.fullmatch(r"[A-Za-z0-9\W]+", text):
            flags.append("极短识别结果，可能不是台词，请复听")
        result.append(
            dict(start_ms=a, end_ms=b, original=text, asr_confidence=confidence, flags=flags)
        )
    return result, raw.get("result", {}).get("language", language or "auto")


class Voices:
    def __init__(self):
        import sherpa_onnx as so

        cfg = so.OfflineSpeakerDiarizationConfig(
            segmentation=so.OfflineSpeakerSegmentationModelConfig(
                pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=require_model("segmentation")
                ),
                num_threads=3,
            ),
            embedding=so.SpeakerEmbeddingExtractorConfig(
                model=require_model("embedding"), num_threads=3
            ),
            clustering=so.FastClusteringConfig(num_clusters=-1, threshold=0.65),
            min_duration_on=0.25,
            min_duration_off=0.3,
        )
        if not cfg.validate():
            raise ValueError("声音分离模型不兼容")
        self.sd = so.OfflineSpeakerDiarization(cfg)
        self.extractor = so.SpeakerEmbeddingExtractor(
            so.SpeakerEmbeddingExtractorConfig(model=require_model("embedding"), num_threads=3)
        )

    def embed(self, audio, sample_rate=16000):
        import numpy as np

        s = self.extractor.create_stream()
        s.accept_waveform(sample_rate=sample_rate, waveform=audio)
        s.input_finished()
        if not self.extractor.is_ready(s):
            return None
        v = np.asarray(self.extractor.compute(s), dtype="float32")
        v /= np.linalg.norm(v) + 1e-9
        return v

    def diarize(self, audio, control):
        control.check()
        result = self.sd.process(audio).sort_by_start_time()
        control.check()
        return [
            dict(start_ms=round(s.start * 1000), end_ms=round(s.end * 1000), speaker=int(s.speaker))
            for s in result
        ]


class SemanticModel:
    def __init__(self, control, cache, api=None):
        self.control = control
        self.cache = cache
        self.api = api
        self.child = None
        self.log = None
        self.client = None

    def __enter__(self):
        if self.api:
            self.endpoint = translation_endpoint(self.api["url"])
            if not isinstance(self.api.get("model"), str) or not self.api["model"].strip():
                raise ValueError("请填写翻译模型名称。")
            key = protected_key(
                settings().get("translation_keys", {}).get(self.endpoint, ""), decrypt=True
            )
            self.client = httpx.Client(
                timeout=httpx.Timeout(600, connect=10),
                trust_env=False,
                headers={"Authorization": "Bearer " + key} if key else {},
            )
            return self
        model = require_model("qwen")
        binary = executable("llama-server")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        self.endpoint = self.url + "/v1/chat/completions"
        self.log = (self.cache / "semantic-server.log").open("wb")
        self.client = httpx.Client(timeout=600, trust_env=False)
        for gpu in [99, 0]:
            args = [
                binary,
                "-m",
                model,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "-ngl",
                str(gpu),
                "-c",
                "8192",
                "--jinja",
            ]
            self.child = subprocess.Popen(
                args, stdout=self.log, stderr=subprocess.STDOUT, creationflags=hidden_flags()
            )
            try:
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    self.control.check()
                    if self.child.poll() is not None:
                        break
                    try:
                        if self.client.get(self.url + "/health", timeout=2).status_code == 200:
                            return self
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.4)
                if self.child.poll() is None:
                    self.child.terminate()
                    self.child.wait(timeout=10)
            except BaseException:
                self.__exit__(None, None, None)
                raise
        self.__exit__(None, None, None)
        raise RuntimeError("本地语义模型启动失败，请查看 semantic-server.log")

    def chat(self, prompt):
        self.control.check()
        body = dict(
            model=self.api["model"] if self.api else "local",
            messages=[
                dict(
                    role="system",
                    content="你是台词整理助手。只依据提供的内容，不编造台词、时间或姓名。输出合法JSON。/no_think",
                ),
                dict(role="user", content=prompt),
            ],
            temperature=0.4,
            max_tokens=2048,
        )
        if not self.api:
            body.update(
                response_format={"type": "json_object"},
                chat_template_kwargs={"enable_thinking": False},
            )
        results = queue.Queue()

        def request():
            try:
                results.put(self.client.post(self.endpoint, json=body))
            except Exception as error:
                results.put(error)

        thread = threading.Thread(target=request, daemon=True)
        thread.start()
        while thread.is_alive():
            self.control.check()
            thread.join(0.25)
        response = results.get()
        if isinstance(response, Exception):
            if self.api and isinstance(response, httpx.HTTPError):
                raise RuntimeError(
                    "翻译服务连接失败或超时，请检查 API 地址与网络后重试。"
                ) from None
            raise response
        if self.api and not response.is_success:
            raise RuntimeError(
                f"翻译服务返回 HTTP {response.status_code}，请检查 API 地址、模型、密钥或服务配额。"
            )
        response.raise_for_status()
        self.control.check()
        try:
            text = response.json()["choices"][0]["message"]["content"]
            if not isinstance(text, str):
                raise ValueError("回复内容不是文字")
        except (KeyError, IndexError, TypeError, ValueError):
            raise ValueError(
                "模型未返回有效文字，请使用支持 Chat Completions 的对话模型。"
            ) from None
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("模型回复须为 JSON 对象")
        return result

    def __exit__(self, *_):
        if self.child and self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait()
        if self.log:
            self.log.close()
            self.log = None
        if self.client:
            self.client.close()
            self.client = None
