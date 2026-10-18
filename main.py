"""AOWcloud Clipper: punkt startowy."""
import os
import sys

# Mniej komunikatów diagnostycznych z wbudowanego odtwarzacza Qt (FFmpeg)
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.*=false")
os.environ.setdefault("QT_FFMPEG_DEBUG", "0")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton  # noqa: E402

from clipper import APP_NAME, APP_ORG, APP_VERSION, core  # noqa: E402
from clipper.ui import icon, theme  # noqa: E402


def missing_ffmpeg_dialog() -> None:
    box = QMessageBox()
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(f"{APP_NAME}: brak ffmpeg")
    box.setText("Nie znaleziono programów ffmpeg i ffprobe.\n\n"
                "AOWcloud Clipper używa ich do kodowania wideo. Zainstaluj je poleceniem "
                "w terminalu (PowerShell):\n\n    winget install ffmpeg\n\n"
                "Potem zamknij terminal i uruchom program ponownie.")
    copy = QPushButton("Kopiuj polecenie")
    copy.setToolTip("Skopiuj „winget install ffmpeg” do schowka.")
    box.addButton(copy, QMessageBox.ActionRole)
    close = box.addButton("Zamknij", QMessageBox.RejectRole)
    close.setToolTip("Zamknij program.")
    while True:
        box.exec()
        if box.clickedButton() is copy:
            QGuiApplication.clipboard().setText("winget install ffmpeg")
            continue
        break


def main() -> int:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AOWcloud.Clipper")
        except Exception:  # noqa: BLE001
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(icon.app_icon())
    theme.apply(app)

    tools = core.find_tools()
    if tools is None:
        missing_ffmpeg_dialog()
        return 1

    from clipper.ui.main_window import MainWindow
    win = MainWindow(tools)
    win.show()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        win.load_file(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
