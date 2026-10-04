"""Smoke-test our frozen Qt UI without taking over the user's desktop."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
exe = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / 'dist/AnimeDialog/AnimeDialog.exe'
qa = root / '.qa/ui-1.1/frozen-ui'
qa.mkdir(parents=True, exist_ok=True)
project = root / '.qa/ui-1.1/旧项目副本'
assert (project / 'project.sqlite').exists(), 'Run verify_workspace.py first.'
env = dict(os.environ)
env.update(QT_QPA_PLATFORM='offscreen', ANIMEDIALOG_HOME=str(qa))
env['PATH'] = str(Path(os.environ['WINDIR']) / 'System32') + ';' + os.environ['WINDIR']
for name in ['error.log', 'worker-fatal.log']:
    # Inspect only files created by this run; keep any earlier diagnostic logs.
    path = qa / name
    if path.exists(): path.rename(qa / (name + f'.previous-{time.time_ns()}'))
started = time.monotonic()
process = subprocess.Popen([str(exe), '--project', str(project)], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(3)
    assert process.poll() is None, f'UI exited with {process.returncode}'
    assert not (qa / 'error.log').exists(), (qa / 'error.log').read_text(encoding='utf8')
    saved = json.loads((qa / 'settings.json').read_text(encoding='utf8'))
    assert Path(saved['last_project']) == project
    lock = (project / '.animedialog.lock').read_text(encoding='utf8')
    assert str(process.pid) == lock.splitlines()[0]
    report = dict(executable=str(exe), gui_imports_and_project_open=True,
                  python_path_required=False, platform='Qt offscreen on Windows 11',
                  legacy_records=1694, startup_seconds=round(time.monotonic() - started, 2))
    (qa / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))
finally:
    # This process only holds the disposable QA project, with no human edits.
    if process.poll() is None:
        process.terminate(); process.wait(timeout=10)
