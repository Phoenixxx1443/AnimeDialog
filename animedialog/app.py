import argparse
import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    if "--worker" in sys.argv:
        try:
            from .worker import main as worker_main

            sys.argv.remove("--worker")
            return worker_main()
        except Exception:
            import traceback

            from .settings import data_root

            report = traceback.format_exc()
            (data_root() / "worker-fatal.log").write_text(report, encoding="utf8")
            if sys.stderr is not None:
                print(report, file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    args = parser.parse_args()
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import __version__
    from .settings import data_root, resource_root
    from .ui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("AnimeDialog")
    app.setOrganizationName("AnimeDialog")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(resource_root() / "animedialog/assets/app.ico")))

    def error_handler(kind, error, tb):
        import traceback

        from PySide6.QtWidgets import QMessageBox

        report = "".join(traceback.format_exception(kind, error, tb))
        log = data_root() / "error.log"
        with log.open("a", encoding="utf8") as stream:
            stream.write(report + "\n")
        QMessageBox.warning(
            None, "AnimeDialog 操作失败", str(error) + "\n详细信息保存在 " + str(log)
        )

    sys.excepthook = error_handler
    window = MainWindow(args.project)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
