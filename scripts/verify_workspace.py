"""Render and measure our Qt widgets; do not control any other desktop app.

The copied project and isolated settings leave the user's review data unchanged.
Screenshots verify the layout, not native video decoding on a clean Windows VM.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
qa = root / '.qa/ui-1.1'
qa.mkdir(parents=True, exist_ok=True)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['ANIMEDIALOG_HOME'] = str(qa / 'settings')
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
from animedialog.ui import MainWindow
from animedialog.dialogs import EpisodeDialog, ExportDialog, ModelsDialog
from animedialog.settings import save_settings
from animedialog import __version__

project_folder = qa / '旧项目副本'
project_folder.mkdir(exist_ok=True)
source = sqlite3.connect(root / '作品/超时空辉夜姬/project.sqlite')
target = sqlite3.connect(project_folder / 'project.sqlite')
source.backup(target); target.close(); source.close()
save_settings({})
app = QApplication([]); app.setStyle('Fusion')
# Windows offscreen QPA has no system font database; explicitly load the same
# fonts as the native desktop. These fonts are only referenced, never shipped.
for filename in ['msyh.ttc', 'segoeui.ttf']:
    QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR']) / 'Fonts' / filename))
w = MainWindow(project_folder)
# Leave playback stopped: offscreen rendering checks Qt controls and text layout.
row = next(r for r in w.table_model.rows if r['original'] and r['translation'] and r['kind'] == '对白')
w.current_row = row; w.load_editor()
w.loading = True; w.table.selectRow(w.table_model.rows.index(row)); w.loading = False
w.update_commands(); w.show(); app.processEvents()
report = {'version': __version__, 'records': len(w.project.rows()), 'sizes': [], 'dialogs': []}
assert report['records'] == 1694

for width, height in [(1480, 900), (1280, 720), (1100, 680)]:
    w.resize(width, height); app.processEvents()
    w.grab().save(str(qa / f'workspace-{width}.png'))
    assert w.width() <= width and w.height() <= height, (w.size(), width, height)
    assert w.search.isVisible() and w.review_splitter.isVisible()
    report['sizes'].append({'width': w.width(), 'height': w.height(),
                            'columns': w.splitter.sizes(), 'editor_and_table': w.review_splitter.sizes()})

for dialog in [EpisodeDialog(w.project.episodes()[0], w), ExportDialog(w), ModelsDialog(w)]:
    dialog.show(); app.processEvents()
    name = type(dialog).__name__
    dialog.grab().save(str(qa / f'{name}.png'))
    if isinstance(dialog, EpisodeDialog):
        box = dialog.findChild(QDialogButtonBox)
        assert box.geometry().bottom() < dialog.height() and box.isVisible()
        assert dialog.height() <= 680
    report['dialogs'].append({'name': name, 'width': dialog.width(), 'height': dialog.height()})
    dialog.close()

def capture_shortcuts():
    dialog = app.activeModalWidget()
    assert isinstance(dialog, QDialog)
    dialog.grab().save(str(qa / 'ShortcutsDialog.png')); dialog.accept()
QTimer.singleShot(100, capture_shortcuts); w.show_shortcuts()
w.close()
(qa / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
print(json.dumps(report, ensure_ascii=False))
