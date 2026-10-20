"""Test dymny interfejsu: wczytuje nagranie, czeka na analizę, robi zrzuty, eksportuje.

Uruchomienie:  .venv\\Scripts\\python.exe -m tests.smoke_gui <nagranie|folder> <folder_zrzutów> [pelny]
SMOKE_STD=opis wybiera standard „Opis produktu”. Folder zamiast nagrania: tryb „Popraw gotowe nagrania”.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from clipper import APP_ORG, core  # noqa: E402
from clipper.ui import theme  # noqa: E402
from clipper.ui.main_window import MainWindow  # noqa: E402


def main():
    src, shots = sys.argv[1], Path(sys.argv[2])
    shots.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    theme.apply(app)
    # test nie może zostawić śladu w ustawieniach użytkownika: kopia i przywrócenie
    user = QSettings(APP_ORG, "Clipper")
    saved = {k: user.value(k) for k in user.allKeys()}

    def restore():
        user.clear()
        for k, v in saved.items():
            user.setValue(k, v)
        user.sync()

    app.aboutToQuit.connect(restore)
    win = MainWindow(core.find_tools())
    win.resize(1280, 820)
    win.show()
    if os.environ.get("SMOKE_STD"):
        win.on_standard_clicked(os.environ["SMOKE_STD"])
    if Path(src).is_dir():
        return smoke_batch(app, win, src, shots)
    # SMOKE_OUT / SMOKE_NAME: folder i nazwa pliku widoczne na zrzutach (np. do README)
    out_dir = os.environ.get("SMOKE_OUT") or tempfile.mkdtemp(prefix="aowclipper_smoke_out_")
    os.makedirs(out_dir, exist_ok=True)
    stem = Path(src).stem
    win.load_file(src)
    win.ed_dir.setText(out_dir)
    if os.environ.get("SMOKE_NAME"):
        win.ed_name.setText(os.environ["SMOKE_NAME"])
    if len(sys.argv) > 3 and sys.argv[3] == "pelny":   # cały plik jako fragment
        stem += "_pelny"
        full = int(win.info.duration * 1000)
        win.timeline.set_range(0, full)
        win.on_range_changed(0, full)
    log = []

    def shot(name):
        win.grab().save(str(shots / f"{stem}_{name}.png"))
        log.append(name)

    def wait_analysis():
        if win.analysis is None:
            QTimer.singleShot(300, wait_analysis)
            return
        win.toggle_play()
        QTimer.singleShot(1500, lambda: (shot("edycja"), win.start_export(), wait_export()))

    def wait_export():
        if win.exporting():
            QTimer.singleShot(300, wait_export)
            return
        QTimer.singleShot(1500, finish)

    def finish():
        modal = QApplication.activeModalWidget()
        if modal is not None:      # np. komunikat "Skróć fragment"
            modal.grab().save(str(shots / f"{stem}_komunikat.png"))
            print("komunikat:", getattr(modal, "text", lambda: "")())
            modal.close()
        shot("wynik")
        print("verdict:", win.lbl_verdict.text(), "|", win.lbl_quality.text())
        win.close()
        app.quit()

    QTimer.singleShot(500, wait_analysis)
    QTimer.singleShot(180000, app.quit)
    app.exec()
    print("zrzuty:", log)


def smoke_batch(app, win, folder, shots):
    out_dir = os.environ.get("SMOKE_OUT") or tempfile.mkdtemp(prefix="aowclipper_smoke_out_")
    win.open_batch()
    win.batch_add([folder])
    win.ed_batch_dir.setText(out_dir)
    win._batch_dir_auto = False
    name = f"popraw_{win.std.key}"

    def wait():
        if win.batch_running():
            QTimer.singleShot(500, wait)
            return
        win.grab().save(str(shots / f"{name}.png"))
        print("podsumowanie:", win.lbl_batch_summary.text())
        for r in range(win.batch_table.rowCount()):
            print("  ", " | ".join(win.batch_table.item(r, c).text() for c in range(4)))
        win.close()
        app.quit()

    win.batch_start()
    QTimer.singleShot(1000, wait)
    QTimer.singleShot(900000, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
