"""Okno „Opcje”: skróty klawiszowe i płynna pętla. Ustawienia trzymane w QSettings."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QCheckBox, QDialog, QGridLayout, QHBoxLayout, QKeySequenceEdit, QLabel,
                               QMessageBox, QPushButton, QVBoxLayout)


@dataclass(frozen=True)
class KeyAction:
    key: str          # identyfikator w ustawieniach (keys/<key>)
    label: str        # nazwa akcji w oknie Opcje
    default: str      # domyślny skrót (format QKeySequence.PortableText)


ACTIONS: list[KeyAction] = [
    KeyAction("play", "Odtwarzaj / pauza (pętla fragmentu)", "Space"),
    KeyAction("in", "Początek fragmentu w bieżącym miejscu", "I"),
    KeyAction("out", "Koniec fragmentu w bieżącym miejscu", "O"),
    KeyAction("prev", "Klatka wstecz", "Left"),
    KeyAction("next", "Klatka naprzód", "Right"),
    KeyAction("open", "Otwórz nagranie", "Ctrl+O"),
    KeyAction("export", "Eksportuj", "Ctrl+E"),
    KeyAction("options", "Opcje", "Ctrl+,"),
]

# Ustawienie: czy w oknie edycji pokazywać przełącznik płynnej pętli (domyślnie nie: pętla zawsze włączona)
ALLOW_XFADE_TOGGLE = "allow_xfade_toggle"

_NAMES = {"Space": "Spacja", "Left": "←", "Right": "→", "Up": "↑", "Down": "↓", "Return": "Enter",
          "Del": "Delete", "Esc": "Esc", "PgUp": "PageUp", "PgDown": "PageDown"}


def load_key(settings: QSettings, action: KeyAction) -> str:
    v = settings.value(f"keys/{action.key}", None)
    return action.default if v is None else str(v)


def key_label(seq: str) -> str:
    """Skrót do pokazania w interfejsie, np. "Space" → "Spacja", "Ctrl+O" bez zmian."""
    if not seq:
        return ""
    return "+".join(_NAMES.get(p, p) for p in seq.split("+")) if seq != "+" else "+"


def _portable(edit: QKeySequenceEdit) -> str:
    seq = edit.keySequence()
    if seq.isEmpty():
        return ""
    return QKeySequence(seq[0]).toString(QKeySequence.PortableText)


class OptionsDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Opcje")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)

        sec = QLabel("SKRÓTY KLAWISZOWE")
        sec.setObjectName("section")
        v.addWidget(sec)
        hint = QLabel("Kliknij pole i naciśnij nowy klawisz albo kombinację. Pole puste oznacza brak skrótu.")
        hint.setObjectName("small")
        hint.setWordWrap(True)
        v.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.edits: dict[str, QKeySequenceEdit] = {}
        for row, a in enumerate(ACTIONS):
            grid.addWidget(QLabel(a.label), row, 0)
            ed = QKeySequenceEdit(QKeySequence(load_key(settings, a)))
            ed.setMaximumSequenceLength(1)
            ed.setClearButtonEnabled(True)
            ed.setToolTip(f"Skrót: {a.label.lower()}.\nDomyślnie: {key_label(a.default)}.")
            ed.setMinimumWidth(170)
            grid.addWidget(ed, row, 1)
            reset = QPushButton("Domyślny")
            reset.setToolTip(f"Przywróć domyślny skrót tej akcji.\nDomyślnie: {key_label(a.default)}.")
            reset.setCursor(Qt.PointingHandCursor)
            reset.clicked.connect(lambda _=False, e=ed, d=a.default: e.setKeySequence(QKeySequence(d)))
            grid.addWidget(reset, row, 2)
            self.edits[a.key] = ed
        grid.setColumnStretch(0, 1)
        v.addLayout(grid)
        all_reset = QPushButton("Przywróć wszystkie domyślne")
        all_reset.setToolTip("Ustaw domyślne skróty dla wszystkich akcji.\nZmiany zapiszą się po kliknięciu „Zapisz”.")
        all_reset.setCursor(Qt.PointingHandCursor)
        all_reset.clicked.connect(self.reset_all)
        row = QHBoxLayout()
        row.addWidget(all_reset)
        row.addStretch(1)
        v.addLayout(row)

        v.addSpacing(10)
        sec2 = QLabel("PŁYNNA PĘTLA")
        sec2.setObjectName("section")
        v.addWidget(sec2)
        self.chk_allow = QCheckBox("Pozwól wyłączać płynną pętlę w oknie edycji")
        self.chk_allow.setToolTip("Domyślnie płynna pętla jest zawsze włączona.\n"
                                  "Po zaznaczeniu w oknie edycji pojawi się pole, którym można ją wyłączyć.")
        self.chk_allow.setChecked(settings.value(ALLOW_XFADE_TOGGLE, False, type=bool))
        v.addWidget(self.chk_allow)
        info = QLabel("Płynna pętla przenika ostatnie 0,5 s fragmentu w jego początek, więc w sklepie nie widać "
                      "skoku przy powtórce. Plik jest wtedy krótszy o te pół sekundy.")
        info.setObjectName("small")
        info.setWordWrap(True)
        v.addWidget(info)

        v.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Anuluj")
        cancel.setToolTip("Zamknij bez zapisywania zmian.")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Zapisz")
        ok.setObjectName("primary")
        ok.setToolTip("Zapisz skróty i ustawienia.\nZmiany działają od razu.")
        ok.setDefault(True)
        ok.clicked.connect(self.save)
        for b in (cancel, ok):
            b.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(b)
        v.addLayout(buttons)

    def reset_all(self) -> None:
        for a in ACTIONS:
            self.edits[a.key].setKeySequence(QKeySequence(a.default))

    def save(self) -> None:
        used: dict[str, str] = {}
        for a in ACTIONS:
            k = _portable(self.edits[a.key])
            if k and k in used:
                QMessageBox.warning(self, "Powtórzony skrót",
                                    f"Skrót {key_label(k)} jest przypisany do dwóch akcji:\n"
                                    f"„{used[k]}” i „{a.label}”.\nZmień jeden z nich.")
                return
            if k:
                used[k] = a.label
        for a in ACTIONS:
            self.settings.setValue(f"keys/{a.key}", _portable(self.edits[a.key]))
        self.settings.setValue(ALLOW_XFADE_TOGGLE, self.chk_allow.isChecked())
        self.accept()
