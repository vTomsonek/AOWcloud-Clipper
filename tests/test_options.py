"""Test okna „Opcje”: skróty klawiszowe i płynna pętla. Nie zmienia ustawień użytkownika.

Uruchomienie:  .venv\\Scripts\\python.exe -m tests.test_options [folder_zrzutów]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from clipper import APP_ORG, core, standard as S  # noqa: E402
from clipper.ui import options, theme  # noqa: E402
from clipper.ui.main_window import MainWindow  # noqa: E402

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(f"  [{'OK ' if ok else 'ŹLE'}] {name}")


def main() -> int:
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    theme.apply(app)
    user = QSettings(APP_ORG, "Clipper")
    saved = {k: user.value(k) for k in user.allKeys()}
    try:
        # stan jak po pierwszej instalacji
        for k in list(user.allKeys()):
            if k.startswith("keys/") or k in (options.ALLOW_XFADE_TOGGLE, "crossfade"):
                user.remove(k)
        win = MainWindow(core.find_tools())
        win.show()
        app.processEvents()

        print("Płynna pętla domyślnie:")
        check("pole wyboru ukryte", win.chk_xfade.isHidden())
        check("przenikanie włączone (0,5 s)", win.crossfade() == S.CROSSFADE_S)
        check("opis mówi, że pętla jest zawsze włączona", "zawsze włączona" in win.lbl_xfade.text())

        print("Domyślne skróty:")
        check("„Początek tutaj  [I]”", win.btn_in.text() == "Początek tutaj  [I]")
        check("odtwarzanie: Spacja", win.shortcuts["play"].key() == QKeySequence("Space"))
        check("opcje: Ctrl+,", win.shortcuts["options"].key() == QKeySequence("Ctrl+,"))

        dlg = options.OptionsDialog(user, win)
        dlg.show()
        app.processEvents()
        if shots:
            shots.mkdir(parents=True, exist_ok=True)
            dlg.grab().save(str(shots / "opcje.png"))

        print("Powtórzony skrót jest odrzucany:")
        dlg.edits["in"].setKeySequence(QKeySequence("O"))
        boxes = []

        def close_box():
            box = QApplication.activeModalWidget()
            if isinstance(box, QMessageBox):
                boxes.append(box.text())
                box.close()

        QTimer.singleShot(200, close_box)
        dlg.save()
        check("pokazano ostrzeżenie o powtórzeniu", bool(boxes) and "O" in boxes[0])
        check("nic nie zapisano", user.value("keys/in") is None)

        print("Zmiana skrótu i pozwolenie na wyłączanie pętli:")
        dlg.edits["in"].setKeySequence(QKeySequence("B"))
        dlg.edits["prev"].setKeySequence(QKeySequence())
        dlg.chk_allow.setChecked(True)
        dlg.save()
        win.apply_keys()
        win.apply_xfade_setting()
        app.processEvents()
        check("zapisano keys/in = B", user.value("keys/in") == "B")
        check("przycisk pokazuje nowy skrót „[B]”", win.btn_in.text() == "Początek tutaj  [B]")
        check("skrót I już nie działa jako początek", win.shortcuts["in"].key() == QKeySequence("B"))
        check("pusty skrót = brak skrótu", win.shortcuts["prev"].key().isEmpty())
        check("pole wyboru pętli widoczne", not win.chk_xfade.isHidden())
        win.chk_xfade.setChecked(False)
        check("po odznaczeniu przenikanie wyłączone", win.crossfade() == 0.0)

        print("Przywrócenie domyślnych:")
        dlg2 = options.OptionsDialog(user, win)
        dlg2.reset_all()
        dlg2.chk_allow.setChecked(False)
        dlg2.save()
        win.apply_keys()
        win.apply_xfade_setting()
        app.processEvents()
        check("znów „[I]”", win.btn_in.text() == "Początek tutaj  [I]")
        check("pole wyboru znów ukryte, pętla włączona",
              win.chk_xfade.isHidden() and win.crossfade() == S.CROSSFADE_S)
        win.close()
    finally:
        user.clear()
        for k, v in saved.items():
            user.setValue(k, v)
        user.sync()
    bad = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
