# Third party components

AnimeDialog is an aggregate of independently licensed components. Model files are downloaded or imported separately and retain their publisher's license.

| Component | License | Source |
|---|---|---|
| CPython | Python Software Foundation | https://github.com/python/cpython |
| PySide6 and Qt | LGPL 3 / GPL 3 / commercial options | https://code.qt.io/pyside/pyside-setup.git and https://code.qt.io/qt/qtbase.git |
| FFmpeg with libx264 | GPL 3, bundled executable built by Gyan | https://www.gyan.dev/ffmpeg/builds/ and https://ffmpeg.org/download.html |
| whisper.cpp | MIT | https://github.com/ggml-org/whisper.cpp |
| llama.cpp | MIT | https://github.com/ggml-org/llama.cpp |
| sherpa-onnx | Apache 2 | https://github.com/k2-fsa/sherpa-onnx |
| RapidOCR | Apache 2 | https://github.com/RapidAI/RapidOCR |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| NumPy | BSD 3 and bundled notices | https://github.com/numpy/numpy |
| OpenCV | Apache 2 and bundled notices | https://github.com/opencv/opencv |
| soundfile / libsndfile | BSD / LGPL | https://github.com/bastibe/python-soundfile and https://github.com/libsndfile/libsndfile |
| python-docx and lxml | MIT / BSD | https://github.com/python-openxml/python-docx and https://github.com/lxml/lxml |
| httpx and dependencies | BSD 3 / MIT and individual notices | https://github.com/encode/httpx |

Full license notices copied from distributed packages and publisher repositories are included in `licenses/`. Native engine release metadata and FFmpeg build configuration are also retained there. Qt shared libraries remain replaceable in the installed `_internal/PySide6` folder, and FFmpeg is invoked as a separate program. Users may modify, replace and debug the LGPL components in accordance with their licenses.

FFmpeg's exact distributed build identification is in `licenses/ffmpeg-build.txt`. Corresponding upstream release source and the build publisher's scripts are available at the source links above; the unmodified upstream FFmpeg source archive for this build is included in `licenses/` when available. Distribution must keep all notices and the applicable source available. External large model files are excluded from the software installer.
