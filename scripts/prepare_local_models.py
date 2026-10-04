"""Reuse previous local assets and download the publisher's Qwen model for validation."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from animedialog.models import model_path,import_model,download_model
old=Path(r'C:\Users\Administrator\Documents\Codex\2026-10-03\zhe\work')
sources={
 'whisper-turbo':old/'gpu_model/turbo-q5.bin',
 'whisper-large':old/'gpu_model_large/turbo-q5.bin',
 'embedding':old/'diarization_models/embedding_3d.onnx',
 'segmentation':old/'diarization_models/sherpa-onnx-pyannote-segmentation-3-0/model.onnx',
}
for key,source in sources.items():
    if not model_path(key).exists() and source.exists():
        print('Import',key,source.stat().st_size,flush=True);import_model(key,source)
last=[0]
def progress(done,total):
    if time.monotonic()-last[0]>15:
        print(f'Qwen {done/1024**2:.0f} / {total/1024**2:.0f} MiB',flush=True);last[0]=time.monotonic()
if not model_path('qwen').exists():download_model('qwen',progress)
print('All local models ready',flush=True)
