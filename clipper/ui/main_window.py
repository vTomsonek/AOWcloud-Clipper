"""Główne okno: wczytanie, kadr, fragment, eksport, wynik."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QImage, QKeySequence, QShortcut, QTransform
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QFileDialog, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import APP_NAME, APP_ORG, APP_VERSION, core, standard as S
from . import icon, theme as T
from .widgets import CropView, SizeBar, StepHeader, TileView, Timeline, fmt_time
from .workers import AnalysisWorker, BatchWorker, ExportWorker, LoopCheckWorker

VIDEO_FILTER = ("Nagrania wideo (*.mp4 *.mov *.m4v *.webm *.mkv *.avi *.wmv *.mts *.m2ts "
                "*.3gp *.mpg *.mpeg *.flv);;Wszystkie pliki (*.*)")
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".wmv", ".mts", ".m2ts", ".3gp",
             ".mpg", ".mpeg", ".flv"}
TEMP_PREFIX = "aowclipper_"
BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def crf_txt(c: float) -> str:
    return f"{c:g}".replace(".", ",")


def clean_stale_temp() -> None:
    """Usuwa katalogi tymczasowe po poprzednich uruchomieniach (np. po awarii)."""
    base = Path(tempfile.gettempdir())
    now = time.time()
    for d in base.glob(TEMP_PREFIX + "*"):
        try:
            if d.is_dir() and now - d.stat().st_mtime > 6 * 3600:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def panel(title: str) -> QGroupBox:
    """Karta jak w Reelmakerze: tytuł na ramce."""
    return QGroupBox(title)


def label(text: str = "", obj: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


def tip(*lines: str) -> str:
    """Tooltip: każde zdanie zaczyna się od nowej linii."""
    return "\n".join(lines)


def button(text: str, tip: str, slot=None, obj: str | None = None) -> QPushButton:
    b = QPushButton(text)
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    if obj:
        b.setObjectName(obj)
    if slot:
        b.clicked.connect(slot)
    return b


class MainWindow(QMainWindow):
    PAGE_DROP, PAGE_EDIT, PAGE_RESULT, PAGE_BATCH = 0, 1, 2, 3

    def __init__(self, tools: core.Tools):
        super().__init__()
        self.tools = tools
        self.settings = QSettings(APP_ORG, "Clipper")
        clean_stale_temp()
        self.tmp_root = tempfile.mkdtemp(prefix=TEMP_PREFIX)

        self.info: Optional[core.MediaInfo] = None
        self.image: Optional[QImage] = None
        self.analysis: Optional[core.Analysis] = None
        self._analysis_dir: Optional[str] = None
        self.analysis_worker: Optional[AnalysisWorker] = None
        self._old_workers: list = []
        self.export_worker: Optional[ExportWorker] = None
        self.loop_worker: Optional[LoopCheckWorker] = None
        self._seq = 0
        self.start_ms = 0
        self.end_ms = 0
        self.prediction: Optional[dict] = None
        self.loop_diff: Optional[float] = None
        self.result_path: Optional[str] = None
        self.result_saved = False
        self.std: S.VideoStandard = S.get(self.settings.value("standard"))
        self.result_std: S.VideoStandard = self.std
        self.batch_worker: Optional[BatchWorker] = None
        self.batch_files: list[str] = []
        self._batch_dir_auto = True

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setAcceptDrops(True)
        self.setMinimumSize(1000, 680)

        self.player = QMediaPlayer(self)            # bez QAudioOutput: zawsze bez dźwięku
        self.sink = QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.on_frame)
        self.player.positionChanged.connect(self.on_position)
        self.player.playbackStateChanged.connect(self.update_play_button)
        self.player.mediaStatusChanged.connect(self.on_media_status)
        self.player.errorOccurred.connect(self.on_player_error)

        self.result_player = QMediaPlayer(self)
        self.result_player.setLoops(QMediaPlayer.Loops.Infinite)

        self.crop_timer = QTimer(self, singleShot=True, interval=700, timeout=self.start_analysis)
        self.loop_timer = QTimer(self, singleShot=True, interval=400, timeout=self.start_loop_check)

        self._build()
        self.apply_standard_ui()
        self._shortcuts()
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1280, 820)

    # ================================================================ UI

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._header())

        steps_bar = QWidget()
        steps_bar.setObjectName("stepsBar")
        steps_bar.setAttribute(Qt.WA_StyledBackground, True)
        sl = QHBoxLayout(steps_bar)
        sl.setContentsMargins(4, 0, 18, 0)
        self.steps = StepHeader()
        sl.addWidget(self.steps)
        sl.addStretch(1)
        self.btn_batch_top = button("Popraw gotowe nagrania…", tip(
            "Przerób kilka gotowych plików albo cały folder do wybranego standardu.",
            "Bez ręcznego kadrowania: kwadrat jest skalowany, prostokąt kadrowany do środka.",
            "Program usuwa dźwięk, ustawia 30 fps i faststart, pilnuje limitu wagi."), self.open_batch)
        sl.addWidget(self.btn_batch_top)
        sl.addSpacing(8)
        self.btn_open_top = button("Otwórz nagranie…", "Wybierz nagranie z dysku (Ctrl+O). "
                                   "Możesz też przeciągnąć plik na okno.", self.open_dialog)
        sl.addWidget(self.btn_open_top)
        v.addWidget(steps_bar)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(18, 6, 18, 14)
        self.stack = QStackedWidget()
        cl.addWidget(self.stack)
        v.addWidget(content, 1)
        self.stack.addWidget(self._build_drop())
        self.stack.addWidget(self._build_edit())
        self.stack.addWidget(self._build_result())
        self.stack.addWidget(self._build_batch())

        self.status_busy = QLabel("")
        self.statusBar().addPermanentWidget(self.status_busy)
        self.statusBar().setSizeGripEnabled(True)

    def _header(self) -> QWidget:
        """Logo, nazwa i wersja po lewej, stan ffmpeg po prawej (jak w Reelmakerze)."""
        bar = QWidget()
        bar.setObjectName("header")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 10, 18, 6)
        lay.setSpacing(10)
        logo = QLabel()
        dpr = self.devicePixelRatioF()
        pm = icon.draw(int(34 * dpr))
        pm.setDevicePixelRatio(dpr)
        logo.setPixmap(pm)
        name = QLabel("Clipper")
        name.setObjectName("appName")
        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("appVersion")
        lay.addWidget(logo)
        lay.addWidget(name)
        lay.addWidget(ver)
        lay.addStretch(1)
        std_lbl = QLabel("Standard:")
        std_lbl.setObjectName("appVersion")
        lay.addWidget(std_lbl)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.std_group = QButtonGroup(self)
        self.std_group.setExclusive(True)
        self.std_buttons: dict[str, QPushButton] = {}
        stds = list(S.STANDARDS.values())
        for i, st in enumerate(stds):
            b = QPushButton(st.label)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setObjectName("segL" if i == 0 else ("segR" if i == len(stds) - 1 else "segM"))
            b.setToolTip(st.tooltip + "\nProgram zapamiętuje ostatni wybór.")
            b.clicked.connect(lambda _=False, k=st.key: self.on_standard_clicked(k))
            self.std_group.addButton(b)
            self.std_buttons[st.key] = b
            seg.addWidget(b)
        lay.addLayout(seg)
        lay.addSpacing(14)
        chip = QLabel(f'<span style="color:{T.OK}">●</span>&nbsp; ffmpeg {core.ffmpeg_version(self.tools)}')
        chip.setObjectName("chip")
        chip.setToolTip(f"Kodowanie przez systemowy ffmpeg: {self.tools.ffmpeg}")
        lay.addWidget(chip)
        return bar

    def set_busy(self, text: str = "") -> None:
        self.status_busy.setText(f"{text}  " if text else "")

    def _build_drop(self) -> QWidget:
        w = panel("Wczytaj nagranie")
        lay = QVBoxLayout(w)
        lay.addStretch(1)
        big = label("Przeciągnij tutaj nagranie produktu", "h1")
        big.setAlignment(Qt.AlignCenter)
        lay.addWidget(big)
        self.lbl_drop_sub = label("", "muted")
        self.lbl_drop_sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl_drop_sub)
        lay.addSpacing(16)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Otwórz nagranie…", "Wybierz nagranie z dysku (Ctrl+O).",
                             self.open_dialog, "primary"))
        row.addSpacing(8)
        row.addWidget(button("Popraw gotowe nagrania…", tip(
            "Przerób kilka gotowych plików albo cały folder do wybranego standardu.",
            "Bez ręcznego kadrowania."), self.open_batch))
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(26)
        self.lbl_drop_spec = label("", "small")
        self.lbl_drop_spec.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl_drop_spec)
        lay.addStretch(1)
        return w

    def _build_edit(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        # ---- lewa kolumna: podgląd, transport, oś czasu, waga
        left = panel("Kadr i fragment")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(4, 6, 4, 2)
        lv.setSpacing(8)
        head = QHBoxLayout()
        self.lbl_source = label("", "small")
        head.addWidget(self.lbl_source, 1)
        self.btn_reset_crop = button("Największy kadr", "Ustaw największy możliwy kwadrat "
                                     "na środku obrazu (to samo co dwuklik na podglądzie).",
                                     self.reset_crop)
        head.addWidget(self.btn_reset_crop)
        lv.addLayout(head)

        self.crop_view = CropView()
        self.crop_view.cropChanged.connect(self.on_crop_changed)
        self.crop_view.cropFinished.connect(self.on_crop_finished)
        lv.addWidget(self.crop_view, 1)

        tr = QHBoxLayout()
        self.btn_play = button("▶  Odtwórz", "Odtwarzaj wybrany fragment w pętli, jak w sklepie "
                               "(spacja).", self.toggle_play, "icon")
        self.btn_play.setMinimumWidth(120)
        tr.addWidget(self.btn_play)
        self.lbl_time = label("0:00,0 / 0:00,0", "muted")
        self.lbl_time.setMinimumWidth(130)
        tr.addWidget(self.lbl_time)
        tr.addStretch(1)
        self.btn_in = button("Początek tutaj  [I]", "Ustaw początek fragmentu w bieżącym "
                             "miejscu odtwarzania (klawisz I).", self.set_in)
        self.btn_out = button("Koniec tutaj  [O]", "Ustaw koniec fragmentu w bieżącym "
                              "miejscu odtwarzania (klawisz O).", self.set_out)
        tr.addWidget(self.btn_in)
        tr.addWidget(self.btn_out)
        lv.addLayout(tr)

        self.timeline = Timeline()
        self.timeline.rangeChanged.connect(self.on_range_changed)
        self.timeline.seekRequested.connect(self.on_seek)
        self.timeline.interacted.connect(self.on_timeline_interacted)
        lv.addWidget(self.timeline)

        frag = QHBoxLayout()
        frag.setSpacing(16)
        fcol = QVBoxLayout()
        fcol.setSpacing(2)
        fcol.addWidget(label("FRAGMENT", "section"))
        self.lbl_fragment = label("", "muted")
        fcol.addWidget(self.lbl_fragment)
        frag.addLayout(fcol)
        scol = QVBoxLayout()
        scol.setSpacing(4)
        self.size_bar = SizeBar()
        scol.addWidget(self.size_bar)
        srow = QHBoxLayout()
        self.lbl_quality = label("", "small", wrap=True)
        srow.addWidget(self.lbl_quality, 1)
        self.btn_autoshort = button("Skróć automatycznie", "", self.auto_shorten)
        self.btn_autoshort.hide()
        srow.addWidget(self.btn_autoshort)
        scol.addLayout(srow)
        frag.addLayout(scol, 1)
        lv.addLayout(frag)
        h.addWidget(left, 1)

        # ---- prawa kolumna: kafelek, plik, eksport
        right_inner = QWidget()
        rv = QVBoxLayout(right_inner)
        rv.setContentsMargins(2, 6, 6, 2)
        rv.setSpacing(8)
        self.lbl_preview = label("", "section")
        rv.addWidget(self.lbl_preview)
        self.tile = TileView(self.std.preview_px, self.std.preview)
        rv.addWidget(self.tile, 0, Qt.AlignHCenter)
        self.lbl_preview_hint = label("", "small", wrap=True)
        rv.addWidget(self.lbl_preview_hint)

        self.lbl_loop = label("", "small", wrap=True)
        self.lbl_loop.hide()
        rv.addWidget(self.lbl_loop)
        self.chk_xfade = QCheckBox("Płynna pętla (przenikanie)")
        self.chk_xfade.setToolTip("Ostatnie pół sekundy fragmentu przenika w pierwszą klatkę, więc "
                                  "w pętli nie widać skoku. Plik będzie krótszy o te pół sekundy.")
        self.chk_xfade.setChecked(self.settings.value("crossfade", False, type=bool))
        self.chk_xfade.setFocusPolicy(Qt.NoFocus)
        self.chk_xfade.toggled.connect(self.on_xfade_toggled)
        rv.addWidget(self.chk_xfade)
        rv.addWidget(label(f"Koniec fragmentu przenika w początek ({core.fmt_s(S.CROSSFADE_S)} s), "
                           "więc w pętli nie widać skoku.", "small", wrap=True))
        rv.addStretch(1)

        # plik i eksport: zawsze widoczne, niezależnie od wysokości podglądu
        bottom = QWidget()
        rv = QVBoxLayout(bottom)
        rv.setContentsMargins(10, 8, 12, 4)
        rv.setSpacing(8)
        rv.addWidget(label("PLIK WYNIKOWY", "section"))
        rv.addWidget(label("Nazwa pliku (np. numer produktu):", "small"))
        self.ed_name = QLineEdit()
        self.ed_name.setToolTip("Nazwa gotowego pliku. Rozszerzenie .mp4 zostanie dodane samo.")
        rv.addWidget(self.ed_name)
        rv.addWidget(label("Folder zapisu:", "small"))
        frow = QHBoxLayout()
        self.ed_dir = QLineEdit()
        self.ed_dir.setReadOnly(True)
        self.ed_dir.setToolTip("Folder, do którego trafi gotowy plik. Program go zapamiętuje.")
        frow.addWidget(self.ed_dir, 1)
        frow.addWidget(button("Zmień…", "Wybierz inny folder zapisu.", self.choose_dir))
        rv.addLayout(frow)

        rv.addSpacing(8)
        self.btn_export = button("Eksportuj", "Zakoduj fragment w standardzie sklepu, sprawdź "
                                 "wynik i zapisz w wybranym folderze (Ctrl+E).",
                                 self.start_export, "primary")
        rv.addWidget(self.btn_export)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.hide()
        rv.addWidget(self.progress)
        self.lbl_progress = label("", "small", wrap=True)
        self.lbl_progress.hide()
        rv.addWidget(self.lbl_progress)
        self.btn_cancel = button("Anuluj eksport", "Przerwij kodowanie. Nic nie zostanie zapisane.",
                                 self.cancel_export, "danger")
        self.btn_cancel.hide()
        rv.addWidget(self.btn_cancel)

        self.right_inner = right_inner
        scroll = QScrollArea()
        scroll.setWidget(right_inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right = panel("Podgląd i eksport")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(scroll, 1)
        rl.addWidget(bottom)
        self.right_panel = right
        h.addWidget(right)
        self.edit_controls = [left, self.chk_xfade, self.ed_name, self.ed_dir, self.btn_export,
                              self.btn_open_top]
        return page

    def _build_result(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        left = panel("Wynik")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 4)
        lv.setSpacing(10)
        self.lbl_verdict = label("", "h1", wrap=True)
        lv.addWidget(self.lbl_verdict)
        self.lbl_saved = label("", "muted", wrap=True)
        self.lbl_saved.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lv.addWidget(self.lbl_saved)
        lv.addSpacing(6)
        self.params_grid = QGridLayout()
        self.params_grid.setHorizontalSpacing(24)
        self.params_grid.setVerticalSpacing(6)
        lv.addLayout(self.params_grid)
        lv.addSpacing(10)
        lv.addWidget(label("SPRAWDZENIE STANDARDU (FFPROBE)", "section"))
        self.checks_box = QVBoxLayout()
        self.checks_box.setSpacing(3)
        lv.addLayout(self.checks_box)
        lv.addStretch(1)
        h.addWidget(left, 1)

        right = panel("Gotowy plik")
        self.result_right = right
        outer = QVBoxLayout(right)
        outer.setContentsMargins(0, 0, 0, 0)
        res_inner = QWidget()
        rv = QVBoxLayout(res_inner)
        rv.setContentsMargins(8, 8, 8, 4)
        rv.setSpacing(10)
        self.lbl_result_preview = label("", "section")
        rv.addWidget(self.lbl_result_preview)
        self.result_tile = TileView(self.std.preview_px, self.std.preview)
        self.result_tile.setToolTip("Gotowy plik odtwarzany w pętli, bez dźwięku, jak w sklepie.")
        self.result_sink = QVideoSink(self)
        self.result_sink.videoFrameChanged.connect(self.on_result_frame)
        self.result_player.setVideoSink(self.result_sink)
        rv.addWidget(self.result_tile, 0, Qt.AlignHCenter)
        rv.addStretch(1)
        res_scroll = QScrollArea()
        res_scroll.setWidget(res_inner)
        res_scroll.setWidgetResizable(True)
        res_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(res_scroll, 1)
        buttons = QWidget()
        rv = QVBoxLayout(buttons)
        rv.setContentsMargins(10, 6, 12, 4)
        rv.setSpacing(8)
        self.btn_reveal = button("Pokaż w folderze", "Otwórz Eksplorator z zaznaczonym plikiem.",
                                 self.reveal, "primary")
        rv.addWidget(self.btn_reveal)
        rv.addWidget(button("Wróć do edycji", "Wróć do kadru i fragmentu tego samego nagrania.",
                            self.back_to_edit))
        rv.addWidget(button("Nowe nagranie…", "Wczytaj kolejne nagranie.", self.open_dialog))
        outer.addWidget(buttons)
        h.addWidget(right)
        return page

    def _shortcuts(self) -> None:
        for key, slot in ((Qt.Key_Space, self.toggle_play), (Qt.Key_I, self.set_in),
                          (Qt.Key_O, self.set_out), (Qt.Key_Left, lambda: self.step_frame(-1)),
                          (Qt.Key_Right, lambda: self.step_frame(1))):
            QShortcut(QKeySequence(key), self, slot)
        QShortcut(QKeySequence("Ctrl+O"), self, self.open_dialog)
        QShortcut(QKeySequence("Ctrl+E"), self, self.start_export)

    # ================================================================ wczytanie

    def open_dialog(self) -> None:
        if self.busy():
            return
        start = self.settings.value("open_dir", str(Path.home() / "Videos"))
        path, _ = QFileDialog.getOpenFileName(self, "Otwórz nagranie", start, VIDEO_FILTER)
        if path:
            self.settings.setValue("open_dir", str(Path(path).parent))
            self.load_file(path)

    def dragEnterEvent(self, e):
        if not self.busy() and e.mimeData().hasUrls() and any(
                u.isLocalFile() for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if self.stack.currentIndex() == self.PAGE_BATCH:
            self.batch_add(files)
        elif files:
            self.load_file(files[0])

    def load_file(self, path: str) -> None:
        if self.busy():
            return
        self.setCursor(Qt.WaitCursor)
        try:
            info = core.probe(self.tools, path)
            core.check_source(info, self.std)
        except core.ClipperError as e:
            self.unsetCursor()
            QMessageBox.warning(self, "Nie można użyć tego nagrania", str(e))
            return
        finally:
            self.unsetCursor()
        self._stop_result()
        self.cancel_analysis()
        self.player.stop()
        self.info = info
        self.image = None
        self.analysis = None
        self.prediction = None
        self.loop_diff = None
        rot = f", obrót {info.rotation}°" if info.rotation else ""
        self.lbl_source.setText(
            f"   {Path(path).name}:  {info.width}x{info.height} px{rot}, "
            f"{core.fmt_s(info.duration)} s, {info.fps:.0f} fps"
            + (", z dźwiękiem (zostanie usunięty)" if info.has_audio else ""))
        self.crop_view.set_source(info.width, info.height)
        dur_ms = int(info.duration * 1000)
        self.timeline.set_duration(dur_ms)
        self.start_ms = 0
        self.end_ms = dur_ms if info.duration <= 15 else 10000
        self.timeline.set_range(self.start_ms, self.end_ms)
        self.timeline.set_alert(False)
        self.ed_name.setText(f"{Path(path).stem}{self.std.suffix}")
        out_dir = self.settings.value("out_dir", "")
        if not out_dir or not os.path.isdir(out_dir):
            out_dir = str(Path(path).parent)
        self.ed_dir.setText(out_dir)
        self.lbl_loop.hide()
        self.btn_autoshort.hide()
        self.lbl_progress.hide()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.pause()
        self.update_fragment_label()
        self.stack.setCurrentIndex(self.PAGE_EDIT)
        self.steps.set_step(2)
        self.start_analysis()

    # ================================================================ odtwarzacz

    def _orient(self, img: QImage) -> QImage:
        """Qt zwykle sam obraca klatkę; gdyby nie, obracamy wg metadanych."""
        info = self.info
        if info is None or img.isNull() or info.rotation not in (90, 270) or info.width == info.height:
            return img
        if (img.width() > img.height()) != (info.width > info.height):
            return img.transformed(QTransform().rotate(info.rotation))
        return img

    def on_frame(self, frame) -> None:
        if not frame.isValid() or self.info is None:
            return
        img = frame.toImage()
        if img.isNull():
            return
        self.image = self._orient(img)
        self.crop_view.set_image(self.image)
        self.tile.set_state(self.image, self.info.width, self.crop_view.crop)

    def on_position(self, ms: int) -> None:
        if self.info is None:
            return
        self.timeline.set_position(ms)
        self.lbl_time.setText(f"{fmt_time(ms)} / {fmt_time(self.info.duration * 1000)}")
        if self.player.playbackState() == QMediaPlayer.PlayingState and ms >= self.end_ms:
            self.player.setPosition(self.start_ms)

    def on_media_status(self, status) -> None:
        if status == QMediaPlayer.EndOfMedia and self.stack.currentIndex() == self.PAGE_EDIT \
                and getattr(self, "_want_play", False):
            self.player.setPosition(self.start_ms)
            self.player.play()

    def on_player_error(self, _err, msg: str) -> None:
        if self.info is not None:
            self.lbl_source.setText(self.lbl_source.text() + f"   (podgląd: {msg})")

    def update_play_button(self, *_):
        playing = self.player.playbackState() == QMediaPlayer.PlayingState
        self.btn_play.setText("❚❚  Pauza" if playing else "▶  Odtwórz")

    def toggle_play(self) -> None:
        if self.stack.currentIndex() != self.PAGE_EDIT or self.info is None or self.exporting():
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._want_play = False
            self.player.pause()
            return
        pos = self.player.position()
        if pos < self.start_ms or pos >= self.end_ms - 40:
            self.player.setPosition(self.start_ms)
        self._want_play = True
        self.player.play()

    def step_frame(self, d: int) -> None:
        if self.stack.currentIndex() != self.PAGE_EDIT or self.info is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        step = 1000.0 / (self.info.fps or 30)
        self.player.setPosition(int(max(0, min(self.info.duration * 1000,
                                               self.player.position() + d * step))))

    def on_seek(self, ms: int) -> None:
        self.player.setPosition(ms)

    def on_timeline_interacted(self) -> None:
        self.steps.set_step(3)
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._want_play = False
            self.player.pause()

    # ================================================================ kadr i fragment

    def on_crop_changed(self, crop) -> None:
        self.steps.set_step(2)
        self.tile.set_state(self.image, self.info.width if self.info else 0, crop)

    def on_crop_finished(self, _crop) -> None:
        self.size_bar.set_pending("Przeliczam szacunek dla nowego kadru…")
        self.lbl_quality.setText("")
        self.crop_timer.start()

    def reset_crop(self) -> None:
        if self.info:
            self.crop_view.set_crop(core.Crop.centered(self.info.width, self.info.height))
            self.on_crop_changed(self.crop_view.crop)
            self.on_crop_finished(self.crop_view.crop)

    def on_range_changed(self, start: int, end: int) -> None:
        self.start_ms, self.end_ms = start, end
        self.update_fragment_label()
        self.update_estimate()
        self.loop_timer.start()

    def set_in(self) -> None:
        if self.stack.currentIndex() != self.PAGE_EDIT or self.info is None or self.exporting():
            return
        pos = self.player.position()
        self.start_ms = max(0, min(pos, self.end_ms - int(S.MIN_FRAGMENT_S * 1000)))
        self.timeline.set_range(self.start_ms, self.end_ms)
        self.steps.set_step(3)
        self.on_range_changed(self.start_ms, self.end_ms)

    def set_out(self) -> None:
        if self.stack.currentIndex() != self.PAGE_EDIT or self.info is None or self.exporting():
            return
        pos = self.player.position()
        self.end_ms = min(int(self.info.duration * 1000),
                          max(pos, self.start_ms + int(S.MIN_FRAGMENT_S * 1000)))
        self.timeline.set_range(self.start_ms, self.end_ms)
        self.steps.set_step(3)
        self.on_range_changed(self.start_ms, self.end_ms)

    def fragment_s(self) -> tuple[float, float]:
        return self.start_ms / 1000.0, (self.end_ms - self.start_ms) / 1000.0

    def crossfade(self) -> float:
        return S.CROSSFADE_S if self.chk_xfade.isChecked() else 0.0

    def update_fragment_label(self) -> None:
        start, dur = self.fragment_s()
        out = core.output_duration(dur, self.crossfade())
        extra = f", w pliku {core.fmt_s(out)} s (przenikanie)" if self.crossfade() else ""
        self.lbl_fragment.setText(f"{fmt_time(self.start_ms)} do {fmt_time(self.end_ms)}\n"
                                  f"długość {core.fmt_s(dur)} s{extra}")

    def on_xfade_toggled(self, on: bool) -> None:
        self.settings.setValue("crossfade", on)
        self.update_fragment_label()
        self.update_estimate()
        self.update_loop_label()

    def auto_shorten(self) -> None:
        if not self.prediction or self.prediction.get("max_dur") is None:
            return
        max_dur = self.prediction["max_dur"]
        if self.crossfade():
            max_dur += core._crossfade_len(max_dur, self.crossfade())
        new_end = self.start_ms + int(max(S.MIN_FRAGMENT_S, max_dur) * 1000)
        self.end_ms = min(self.end_ms, new_end)
        self.timeline.set_range(self.start_ms, self.end_ms)
        self.on_range_changed(self.start_ms, self.end_ms)

    # ================================================================ analiza wagi

    def cancel_analysis(self) -> None:
        w = self.analysis_worker
        if w is not None and w.isRunning():
            w.cancel.set()
            self._old_workers.append(w)
        self.analysis_worker = None

    def start_analysis(self) -> None:
        if self.info is None or self.crop_view.crop is None:
            return
        self.cancel_analysis()
        self._seq += 1
        workdir = os.path.join(self.tmp_root, f"analysis_{self._seq}")
        w = AnalysisWorker(self.tools, self.info, self.crop_view.crop, workdir, self.std, self)
        seq = self._seq
        w.progress.connect(lambda f, _l, seq=seq: self._analysis_progress(seq, f))
        w.done.connect(lambda res, seq=seq, d=workdir: self._analysis_done(seq, res, d))
        w.failed.connect(lambda msg: (self.size_bar.set_pending(f"Nie udało się oszacować wagi: {msg[:80]}"),
                                      self.set_busy("")))
        w.finished.connect(lambda w=w: self._worker_finished(w))
        self.analysis_worker = w
        self.size_bar.set_pending("Analizuję nagranie…")
        self.set_busy("Analizuję nagranie…")
        w.start()

    def _worker_finished(self, w) -> None:
        if w in self._old_workers:
            self._old_workers.remove(w)
        if self.analysis_worker is w:
            self.analysis_worker = None
        w.deleteLater()

    def _analysis_progress(self, seq: int, f: float) -> None:
        if seq == self._seq:
            self.size_bar.set_pending(f"Analizuję nagranie: {int(f * 100)}%")

    def _analysis_done(self, seq: int, res: core.Analysis, workdir: str) -> None:
        if seq != self._seq:
            shutil.rmtree(workdir, ignore_errors=True)
            return
        old = self._analysis_dir
        self.analysis, self._analysis_dir = res, workdir
        if not self.exporting():
            self.set_busy("")
        if old and old != workdir:
            QTimer.singleShot(3000, lambda: shutil.rmtree(old, ignore_errors=True))
        self.update_estimate()
        self.start_loop_check()

    def update_estimate(self) -> None:
        if self.analysis is None:
            return
        start, dur = self.fragment_s()
        pred = self.analysis.prediction(start, dur, self.crossfade())
        self.prediction = pred
        if pred["fits"] and pred["crf"] <= self.analysis.std.crf_start + 0.01:
            self.size_bar.set_value(pred["size"], "ok")
            self.lbl_quality.setText("Najwyższa jakość. Plik zmieści się w limicie.")
            self.timeline.set_alert(False)
            self.btn_autoshort.hide()
        elif pred["fits"]:
            self.size_bar.set_value(pred["size"], "warn")
            self.lbl_quality.setText(
                f"Zmieści się przy lekko obniżonej jakości (ok. CRF {pred['crf']:.0f}). "
                f"Krótszy fragment da lepszy obraz.")
            self.timeline.set_alert(False)
            self.btn_autoshort.hide()
        else:
            self.size_bar.set_value(pred["size"], "bad")
            self.lbl_quality.setText(
                f"Za długi fragment: skróć o ok. {core.fmt_s(pred['shorten'])} s "
                f"(do ok. {core.fmt_s(pred['max_dur'])} s).")
            self.timeline.set_alert(True)
            self.btn_autoshort.setVisible(pred["max_dur"] >= S.MIN_FRAGMENT_S)

    # ================================================================ pętla

    def start_loop_check(self) -> None:
        if self.analysis is None or not os.path.exists(self.analysis.master):
            return
        if self.loop_worker is not None and self.loop_worker.isRunning():
            self.loop_timer.start()
            return
        w = LoopCheckWorker(self.tools, self.analysis.master, self.start_ms, self.end_ms, self)
        w.done.connect(self._loop_done)
        w.finished.connect(lambda w=w: self._loop_finished(w))
        self.loop_worker = w
        w.start()

    def _loop_finished(self, w) -> None:
        if self.loop_worker is w:
            self.loop_worker = None
        w.deleteLater()

    def _loop_done(self, diff: float, s: int, e: int) -> None:
        if (s, e) != (self.start_ms, self.end_ms):
            self.loop_timer.start()
            return
        self.loop_diff = diff
        self.update_loop_label()

    def update_loop_label(self) -> None:
        if self.loop_diff is None or self.loop_diff < S.LOOP_DIFF_WARN:
            self.lbl_loop.hide()
            return
        if self.crossfade():
            self.lbl_loop.setText("Koniec różni się od początku, ale przenikanie wygładzi przejście.")
            self.lbl_loop.setStyleSheet(f"color: {T.MUTED};")
        else:
            self.lbl_loop.setText("Uwaga: ostatnia klatka wyraźnie różni się od pierwszej, w pętli "
                                  "będzie widać skok. Przesuń uchwyty albo włącz płynną pętlę.")
            self.lbl_loop.setStyleSheet(f"color: {T.WARN};")
        self.lbl_loop.show()

    # ================================================================ eksport

    def exporting(self) -> bool:
        return self.export_worker is not None and self.export_worker.isRunning()

    def choose_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Folder zapisu", self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)
            self.settings.setValue("out_dir", d)

    def target_path(self) -> Optional[str]:
        name = self.ed_name.text().strip()
        if name.lower().endswith(".mp4"):
            name = name[:-4]
        name = BAD_CHARS.sub("_", name).strip(" .")
        if not name:
            QMessageBox.warning(self, "Brak nazwy pliku", "Wpisz nazwę pliku wynikowego, np. numer produktu.")
            return None
        d = self.ed_dir.text().strip()
        if not d or not os.path.isdir(d):
            QMessageBox.warning(self, "Brak folderu", "Wybierz istniejący folder zapisu.")
            return None
        return os.path.join(d, name + ".mp4")

    def start_export(self) -> None:
        if self.stack.currentIndex() != self.PAGE_EDIT or self.info is None or self.exporting():
            return
        target = self.target_path()
        if not target:
            return
        if os.path.exists(target):
            r = QMessageBox.question(self, "Plik już istnieje",
                                     f"Plik {Path(target).name} już istnieje w tym folderze. Zastąpić go?")
            if r != QMessageBox.Yes:
                return
        self._want_play = False
        self.player.pause()
        self.target = target
        start, dur = self.fragment_s()
        workdir = os.path.join(self.tmp_root, "export")
        shutil.rmtree(workdir, ignore_errors=True)
        self.result_std = self.std
        w = ExportWorker(self.tools, self.info, self.crop_view.crop, start, dur,
                         self.crossfade(), workdir, self.std, self)
        w.progress.connect(self._export_progress)
        w.finished_ok.connect(self._export_done)
        w.too_long.connect(self._export_too_long)
        w.failed.connect(self._export_failed)
        w.cancelled.connect(self._export_cancelled)
        w.finished.connect(w.deleteLater)
        self.export_worker = w
        self._set_exporting(True)
        w.start()

    def _set_exporting(self, on: bool) -> None:
        for c in self.edit_controls + [self.btn_batch_top] + list(self.std_buttons.values()):
            c.setEnabled(not on)
        self.btn_export.setVisible(not on)
        self.progress.setVisible(on)
        self.btn_cancel.setVisible(on)
        self.btn_cancel.setEnabled(on)
        self.lbl_progress.setVisible(on)
        self.set_busy("Pracuję…" if on else "")
        if on:
            self.progress.setValue(0)
            self.lbl_progress.setStyleSheet("")
            self.lbl_progress.setText("Przygotowanie…")
            self.steps.set_step(4)

    def _export_progress(self, f: float, text: str) -> None:
        self.progress.setValue(int(f * 1000))
        self.lbl_progress.setText(text)

    def cancel_export(self) -> None:
        if self.exporting():
            self.btn_cancel.setEnabled(False)
            self.lbl_progress.setText("Przerywam…")
            self.export_worker.cancel.set()

    def _export_cancelled(self) -> None:
        self.export_worker = None
        self._set_exporting(False)
        self.lbl_progress.setText("Eksport anulowany. Nic nie zapisano.")
        self.lbl_progress.setStyleSheet(f"color: {T.MUTED};")
        self.lbl_progress.show()
        self.steps.set_step(3)

    def _export_failed(self, msg: str) -> None:
        self.export_worker = None
        self._set_exporting(False)
        self.steps.set_step(3)
        QMessageBox.critical(self, "Eksport nie powiódł się", msg)

    def _export_too_long(self, msg: str, shorten: float, max_dur: float, size_at_max: int) -> None:
        self.export_worker = None
        self._set_exporting(False)
        self.steps.set_step(3)
        self.timeline.set_alert(True)
        self.lbl_quality.setText(f"Za długi fragment: skróć o ok. {core.fmt_s(shorten)} s "
                                 f"(do ok. {core.fmt_s(max_dur)} s).")
        self.size_bar.set_value(size_at_max, "bad")
        if self.prediction is not None:
            self.prediction.update(max_dur=max_dur, shorten=shorten, fits=False)
        self.btn_autoshort.setVisible(max_dur >= S.MIN_FRAGMENT_S)
        QMessageBox.information(self, "Skróć fragment", msg)

    def _export_done(self, res: core.ExportResult, ver: core.Verification) -> None:
        self.export_worker = None
        self._set_exporting(False)
        self.result_saved = False
        path = res.path
        save_error = None
        if ver.ok:
            try:
                shutil.copyfile(res.path, self.target)
                if os.path.getsize(self.target) != res.size:
                    raise OSError("rozmiar zapisanego pliku się nie zgadza")
                path = self.target
                self.result_saved = True
                self.settings.setValue("out_dir", str(Path(self.target).parent))
                os.remove(res.path)
            except OSError as e:
                save_error = str(e)
        self.result_path = path
        self.show_result(res, ver, save_error)

    # ================================================================ wynik

    def show_result(self, res: core.ExportResult, ver: core.Verification, save_error) -> None:
        ok = ver.ok and self.result_saved
        if ok:
            self.lbl_verdict.setText(f"✔  Spełnia standard: {self.result_std.label}")
            self.lbl_verdict.setStyleSheet(f"color: {T.OK};")
            self.lbl_saved.setText(f"Zapisano: {self.result_path}")
        elif ver.ok:
            self.lbl_verdict.setText("✖  Plik jest poprawny, ale nie udało się go zapisać")
            self.lbl_verdict.setStyleSheet(f"color: {T.BAD};")
            self.lbl_saved.setText(f"Błąd zapisu: {save_error}. Wybierz inny folder i eksportuj ponownie.")
        else:
            self.lbl_verdict.setText(f"✖  Nie spełnia standardu „{self.result_std.name}”, "
                                     "plik NIE został zapisany")
            self.lbl_verdict.setStyleSheet(f"color: {T.BAD};")
            self.lbl_saved.setText("Poniżej lista problemów. Wróć do edycji i spróbuj ponownie.")
        self.btn_reveal.setEnabled(ok)

        while self.params_grid.count():
            it = self.params_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        rows = [("Standard", self.result_std.label),
                ("Wymiary", f"{ver.width} x {ver.height} px"),
                ("Klatki", f"{ver.fps:.2f} fps".replace(".", ",")),
                ("Czas", f"{core.fmt_s(ver.duration)} s"),
                ("Waga", f"{core.fmt_mb(ver.size)} MB ({core.fmt_int(ver.size)} B, "
                         f"limit {core.fmt_int(self.result_std.max_bytes)} B)"),
                ("Bitrate", f"{ver.bitrate // 1000} kb/s"),
                ("Kodek", f"H.264 {ver.profile}, CRF {crf_txt(res.crf)}"),
                ("Próby kodowania", ", ".join(f"CRF {crf_txt(c)}: {core.fmt_mb(s)} MB"
                                               for c, s in res.passes))]
        for i, (k, val) in enumerate(rows):
            self.params_grid.addWidget(label(k, "muted"), i, 0)
            v = label(val, wrap=True)
            self.params_grid.addWidget(v, i, 1)
        self.params_grid.setColumnStretch(1, 1)

        while self.checks_box.count():
            it = self.checks_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for c in sorted(ver.checks, key=lambda c: c.ok):
            lb = label(f"{'✔' if c.ok else '✖'}  {c.name}:  {c.detail}", wrap=True)
            lb.setStyleSheet(f"color: {T.OK if c.ok else T.BAD};")
            self.checks_box.addWidget(lb)

        self.stack.setCurrentIndex(self.PAGE_RESULT)
        self.steps.set_step(5)
        self.result_player.setSource(QUrl.fromLocalFile(self.result_path))
        self.result_player.play()

    def on_result_frame(self, frame) -> None:
        if not frame.isValid():
            return
        img = frame.toImage()
        if not img.isNull():
            self.result_tile.set_state(img, img.width(), core.Crop(0, 0, img.width()))

    def _stop_result(self) -> None:
        self.result_player.stop()
        self.result_player.setSource(QUrl())
        self.result_tile.set_state(None, 0, None)
        if self.result_path and not self.result_saved and os.path.exists(self.result_path):
            try:
                os.remove(self.result_path)
            except OSError:
                pass
        self.result_path = None

    def reveal(self) -> None:
        if self.result_path and os.path.exists(self.result_path):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(self.result_path)}"')

    def back_to_edit(self) -> None:
        self._stop_result()
        if self.info is None:
            self.stack.setCurrentIndex(self.PAGE_DROP)
            self.steps.set_step(1)
            return
        self.stack.setCurrentIndex(self.PAGE_EDIT)
        self.steps.set_step(3)

    # ================================================================ standard

    def busy(self) -> bool:
        return self.exporting() or self.batch_running()

    def on_standard_clicked(self, key: str) -> None:
        std = S.get(key)
        if std is self.std:
            return
        if self.busy():
            self._sync_std_buttons()
            return
        if self.info is not None and self.info.short_side < std.min_source_side:
            try:
                core.check_source(self.info, std)
            except core.ClipperError as e:
                QMessageBox.warning(self, "Nie można przełączyć standardu",
                                    f"{e}\n\nZostaje standard „{self.std.label}”.")
            self._sync_std_buttons()
            return
        if self.stack.currentIndex() == self.PAGE_RESULT:
            self.back_to_edit()
        old, self.std = self.std, std
        self.settings.setValue("standard", std.key)
        self.apply_standard_ui()
        if self.info is not None:
            name = self.ed_name.text()
            if name.endswith(old.suffix):
                self.ed_name.setText(name[: -len(old.suffix)] + std.suffix)
            self.analysis = None
            self.prediction = None
            self.lbl_quality.setText("")
            self.timeline.set_alert(False)
            self.btn_autoshort.hide()
            self.start_analysis()

    def _sync_std_buttons(self) -> None:
        for k, b in self.std_buttons.items():
            b.setChecked(k == self.std.key)

    def apply_standard_ui(self) -> None:
        """Wszystkie napisy, limity i podglądy zależne od standardu."""
        std = self.std
        self._sync_std_buttons()
        self.crop_view.set_min_crop(std.min_crop)
        self.tile.set_mode(std.preview_px, std.preview)
        self.result_tile.set_mode(std.preview_px, std.preview)
        self.tile.set_state(self.image, self.info.width if self.info else 0, self.crop_view.crop)
        self.tile.setToolTip(tip(f"Tak kadr będzie wyglądał u klienta ({std.name.lower()}).",
                                 f"Plik ma {std.dims} px."))
        self.lbl_preview.setText(std.preview_title)
        self.lbl_preview_hint.setText(std.preview_hint)
        self.lbl_result_preview.setText(std.preview_title + ", W PĘTLI")
        inner = max(282, self.tile.width() + 4)
        self.right_inner.setFixedWidth(inner)
        self.right_panel.setFixedWidth(inner + 48)
        self.result_right.setFixedWidth(max(330, self.result_tile.width() + 48))
        self.size_bar.set_limit(std.max_bytes)
        self.btn_autoshort.setToolTip(tip("Przesuń koniec fragmentu tak, żeby plik zmieścił się w limicie "
                                          f"{std.limit_label}."))
        self.lbl_drop_sub.setText(f"mp4, mov, webm, mkv i inne. Pion, poziom albo kwadrat. "
                                  f"Krótszy bok co najmniej {std.min_source_side} px.")
        self.lbl_drop_spec.setText(f"Wynik w standardzie „{std.name}”: MP4 {std.dims} px, 30 fps, H.264 High, "
                                   f"bez dźwięku, start natychmiast (faststart), do {std.limit_label}.")
        self.lbl_batch_std.setText(f"Standard: {std.label}. Zmienisz go przełącznikiem u góry okna.")
        if self._batch_dir_auto and self.batch_files:
            self.ed_batch_dir.setText(self._default_batch_dir())

    # ================================================================ popraw gotowe nagrania

    def batch_running(self) -> bool:
        return self.batch_worker is not None and self.batch_worker.isRunning()

    def _build_batch(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        left = panel("Popraw gotowe nagrania")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 4)
        lv.setSpacing(8)
        lv.addWidget(label("Gotowe pliki są przerabiane do wybranego standardu bez ręcznego kadrowania: "
                           "kwadrat jest tylko skalowany, prostokąt kadrowany do środka. Dźwięk jest usuwany, "
                           "obraz dostaje 30 fps i faststart. Pliki, których obraz już spełnia standard, są "
                           "tylko przepakowane, bez utraty jakości. Plik, który nie zmieści się w limicie przy "
                           "najniższej dopuszczalnej jakości, jest oznaczany do ręcznego skrócenia.",
                           "muted", wrap=True))
        self.lbl_batch_std = label("", "small", wrap=True)
        lv.addWidget(self.lbl_batch_std)
        row = QHBoxLayout()
        self.btn_batch_files = button("Dodaj pliki…", tip("Wybierz jeden albo kilka plików wideo.",
                                                          "Możesz też przeciągnąć pliki na okno."),
                                      self.batch_add_files)
        self.btn_batch_folder = button("Dodaj folder…", tip("Dodaj wszystkie nagrania z wybranego folderu.",
                                                            "Podfoldery nie są przeszukiwane."),
                                       self.batch_add_folder)
        self.btn_batch_clear = button("Wyczyść listę", tip("Usuń wszystkie pliki z listy.",
                                                           "Pliki na dysku zostają bez zmian."),
                                      self.batch_clear)
        for b in (self.btn_batch_files, self.btn_batch_folder, self.btn_batch_clear):
            row.addWidget(b)
        row.addStretch(1)
        lv.addLayout(row)

        t = QTableWidget(0, 4)
        t.setHorizontalHeaderLabels(["Plik", "Przed", "Po", "Wynik"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setFocusPolicy(Qt.NoFocus)
        t.setWordWrap(True)
        t.setTextElideMode(Qt.ElideNone)
        t.setAlternatingRowColors(True)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Interactive)
        hh.setSectionResizeMode(1, QHeaderView.Interactive)
        hh.setSectionResizeMode(2, QHeaderView.Interactive)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setMinimumSectionSize(80)
        t.setColumnWidth(0, 190)
        t.setColumnWidth(1, 255)
        t.setColumnWidth(2, 220)
        t.setToolTip("Najedź na wynik, żeby zobaczyć pełny opis.")
        self.batch_table = t
        lv.addWidget(t, 1)
        self.lbl_batch_summary = label("Dodaj pliki albo folder. Możesz też przeciągnąć je na okno.", "small",
                                       wrap=True)
        lv.addWidget(self.lbl_batch_summary)
        h.addWidget(left, 1)

        right = panel("Zapis")
        right.setFixedWidth(330)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 8, 8, 4)
        rv.setSpacing(8)
        rv.addWidget(label("FOLDER ZAPISU", "section"))
        frow = QHBoxLayout()
        self.ed_batch_dir = QLineEdit()
        self.ed_batch_dir.setReadOnly(True)
        self.ed_batch_dir.setToolTip(tip("Folder na poprawione pliki.",
                                         "Domyślnie podfolder obok pierwszego pliku z listy."))
        frow.addWidget(self.ed_batch_dir, 1)
        self.btn_batch_dir = button("Zmień…", tip("Wybierz inny folder zapisu."), self.batch_choose_dir)
        frow.addWidget(self.btn_batch_dir)
        rv.addLayout(frow)
        rv.addWidget(label("Pliki zachowują swoje nazwy. Gdy folder zapisu jest tym samym folderem co "
                           "oryginał, dostają dopisek standardu, więc oryginały nigdy nie są nadpisywane.",
                           "small", wrap=True))
        rv.addSpacing(8)
        self.btn_batch_start = button("Popraw wszystkie", tip(
            "Przerób wszystkie pliki z listy do wybranego standardu.",
            "Zapisane zostaną tylko pliki, które przejdą weryfikację."), self.batch_start, "primary")
        rv.addWidget(self.btn_batch_start)
        self.batch_progress = QProgressBar()
        self.batch_progress.setRange(0, 1000)
        self.batch_progress.hide()
        rv.addWidget(self.batch_progress)
        self.lbl_batch_progress = label("", "small", wrap=True)
        self.lbl_batch_progress.hide()
        rv.addWidget(self.lbl_batch_progress)
        self.btn_batch_cancel = button("Przerwij", tip("Zatrzymaj po bieżącym kroku.",
                                                       "Pliki już zapisane zostają w folderze."),
                                       self.batch_cancel, "danger")
        self.btn_batch_cancel.hide()
        rv.addWidget(self.btn_batch_cancel)
        self.btn_batch_reveal = button("Pokaż folder", tip("Otwórz folder zapisu w Eksploratorze."),
                                       self.batch_reveal)
        rv.addWidget(self.btn_batch_reveal)
        self.btn_batch_back = button("Wróć", tip("Wróć do pracy z jednym nagraniem.",
                                                 "Lista plików zostaje."), self.batch_back)
        rv.addWidget(self.btn_batch_back)
        rv.addStretch(1)
        h.addWidget(right)
        self.batch_controls = [self.btn_batch_files, self.btn_batch_folder, self.btn_batch_clear,
                               self.btn_batch_dir, self.btn_batch_start, self.btn_batch_back,
                               self.btn_open_top, self.btn_batch_top]
        return page

    def open_batch(self) -> None:
        if self.busy():
            return
        self._want_play = False
        self.player.pause()
        if self.stack.currentIndex() == self.PAGE_RESULT:
            self._stop_result()
        self.stack.setCurrentIndex(self.PAGE_BATCH)
        self.steps.set_step(0)

    def batch_back(self) -> None:
        if self.batch_running():
            return
        if self.info is None:
            self.stack.setCurrentIndex(self.PAGE_DROP)
            self.steps.set_step(1)
        else:
            self.stack.setCurrentIndex(self.PAGE_EDIT)
            self.steps.set_step(2)

    def _default_batch_dir(self) -> str:
        first = Path(self.batch_files[0]).parent
        return str(first / f"poprawione{self.std.suffix}")

    def batch_add(self, paths: list[str]) -> None:
        if self.batch_running():
            return
        files = []
        for p in paths:
            pp = Path(p)
            if pp.is_dir():
                files += sorted(str(f) for f in pp.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXT)
            elif pp.is_file() and pp.suffix.lower() in VIDEO_EXT:
                files.append(str(pp))
        known = {os.path.normcase(f) for f in self.batch_files}
        for f in files:
            if os.path.normcase(f) in known:
                continue
            known.add(os.path.normcase(f))
            self.batch_files.append(f)
            r = self.batch_table.rowCount()
            self.batch_table.insertRow(r)
            item = QTableWidgetItem(Path(f).name)
            item.setToolTip(f)
            self.batch_table.setItem(r, 0, item)
            for c, txt in ((1, ""), (2, ""), (3, "czeka")):
                self.batch_table.setItem(r, c, QTableWidgetItem(txt))
        if self.batch_files and (self._batch_dir_auto or not self.ed_batch_dir.text()):
            self.ed_batch_dir.setText(self._default_batch_dir())
        self.lbl_batch_summary.setText(f"Plików na liście: {len(self.batch_files)}.")

    def batch_add_files(self) -> None:
        start = self.settings.value("open_dir", str(Path.home() / "Videos"))
        paths, _ = QFileDialog.getOpenFileNames(self, "Dodaj nagrania", start, VIDEO_FILTER)
        if paths:
            self.settings.setValue("open_dir", str(Path(paths[0]).parent))
            self.batch_add(paths)

    def batch_add_folder(self) -> None:
        start = self.settings.value("open_dir", str(Path.home() / "Videos"))
        d = QFileDialog.getExistingDirectory(self, "Dodaj folder z nagraniami", start)
        if d:
            self.settings.setValue("open_dir", d)
            self.batch_add([d])

    def batch_clear(self) -> None:
        if self.batch_running():
            return
        self.batch_files = []
        self.batch_table.setRowCount(0)
        self._batch_dir_auto = True
        self.ed_batch_dir.setText("")
        self.lbl_batch_summary.setText("Dodaj pliki albo folder. Możesz też przeciągnąć je na okno.")

    def batch_choose_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Folder zapisu", self.ed_batch_dir.text())
        if d:
            self.ed_batch_dir.setText(d)
            self._batch_dir_auto = False

    def _batch_targets(self, out_dir: str) -> list[str]:
        targets, used = [], set()
        for f in self.batch_files:
            stem = Path(f).stem
            same = os.path.normcase(os.path.abspath(Path(f).parent)) == os.path.normcase(os.path.abspath(out_dir))
            name = stem + (self.std.suffix if same else "")
            cand, k = name, 2
            while os.path.normcase(cand) in used:
                cand, k = f"{name}_{k}", k + 1
            used.add(os.path.normcase(cand))
            targets.append(os.path.join(out_dir, cand + ".mp4"))
        return targets

    def batch_start(self) -> None:
        if self.busy() or not self.batch_files:
            return
        out_dir = self.ed_batch_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "Brak folderu", "Wybierz folder zapisu.")
            return
        targets = self._batch_targets(out_dir)
        exist = [t for t in targets if os.path.exists(t)]
        if exist:
            r = QMessageBox.question(self, "Pliki już istnieją",
                                     f"W folderze zapisu jest już {len(exist)} z tych plików. Zastąpić je?")
            if r != QMessageBox.Yes:
                return
        for r in range(self.batch_table.rowCount()):
            for c, txt in ((1, ""), (2, ""), (3, "czeka")):
                self.batch_table.setItem(r, c, QTableWidgetItem(txt))
        self.batch_counts = {"ok": 0, "too_long": 0, "bad": 0}
        self.batch_out_dir = out_dir
        self.batch_std = self.std
        w = BatchWorker(self.tools, list(self.batch_files), targets, self.std,
                        os.path.join(self.tmp_root, "batch"), self)
        w.progress.connect(self._batch_progress)
        w.row_started.connect(lambda r: self._batch_cell(r, 3, "w toku…", T.ACCENT))
        w.row_done.connect(self._batch_row_done)
        w.all_done.connect(self._batch_done)
        w.finished.connect(w.deleteLater)
        self.batch_worker = w
        self._set_batch_running(True)
        w.start()

    def _set_batch_running(self, on: bool) -> None:
        for c in self.batch_controls + list(self.std_buttons.values()):
            c.setEnabled(not on)
        self.btn_batch_start.setVisible(not on)
        self.batch_progress.setVisible(on)
        self.lbl_batch_progress.setVisible(on)
        self.btn_batch_cancel.setVisible(on)
        self.btn_batch_cancel.setEnabled(on)
        self.set_busy("Pracuję…" if on else "")
        if on:
            self.batch_progress.setValue(0)
            self.lbl_batch_progress.setText("Przygotowanie…")

    def _batch_progress(self, f: float, text: str) -> None:
        self.batch_progress.setValue(int(f * 1000))
        if text:
            self.lbl_batch_progress.setText(text)

    def _batch_cell(self, row: int, col: int, text: str, color: Optional[str] = None,
                    tooltip: str = "") -> None:
        item = QTableWidgetItem(text)
        if color:
            item.setForeground(QColor(color))
        if tooltip:
            item.setToolTip(tooltip)
        self.batch_table.setItem(row, col, item)

    @staticmethod
    def _fps_txt(f: float) -> str:
        return f"{f:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " fps"

    def _batch_row_done(self, row: int, res: core.FixResult, saved: str) -> None:
        b = res.before
        if b is not None:
            self._batch_cell(row, 1, f"{b.width}x{b.height}, {self._fps_txt(b.fps)}, "
                                     f"{core.fmt_mb(b.size_bytes)} MB, "
                                     f"{'z dźwiękiem' if b.has_audio else 'bez dźwięku'}")
        v = res.verification
        if v is not None and res.status in ("ok", "not_ok"):
            self._batch_cell(row, 2, f"{v.width}x{v.height}, {self._fps_txt(v.fps)}, "
                                     f"{core.fmt_mb(v.size)} MB, bez dźwięku")
        full = res.message.replace(". ", ".\n")       # podpowiedź: każde zdanie w nowej linii
        std = self.batch_std
        if res.status == "ok" and saved:
            self.batch_counts["ok"] += 1
            self._batch_cell(row, 3, f"✔  spełnia ({res.method})", T.OK, f"Zapisano: {saved}\n{full}")
        elif res.status == "too_long":
            self.batch_counts["too_long"] += 1
            self._batch_cell(row, 3, f"✂  do ręcznego skrócenia o ok. {core.fmt_s(res.shorten_s)} s",
                             T.WARN, full)
        else:
            self.batch_counts["bad"] += 1
            if res.status == "too_small" and b is not None:
                short = f"✖  za małe: {b.short_side} px, wymagane {std.min_source_side} px"
            elif res.status == "not_ok" and v is not None:
                short = "✖  nie spełnia: " + ", ".join(c.name for c in v.failures)
            else:
                short = "✖  błąd: " + (res.message[:70] + "…" if len(res.message) > 70 else res.message)
            self._batch_cell(row, 3, short, T.BAD, full)
        self.batch_table.resizeRowsToContents()

    def _batch_done(self, cancelled: bool) -> None:
        self.batch_worker = None
        self._set_batch_running(False)
        c = self.batch_counts
        txt = (f"Spełnia i zapisano: {c['ok']}. Do ręcznego skrócenia: {c['too_long']}. "
               f"Odrzucone albo błąd: {c['bad']}. Standard: {self.batch_std.label}.")
        if cancelled:
            txt = "Przerwano. " + txt
            for r in range(self.batch_table.rowCount()):
                it = self.batch_table.item(r, 3)
                if it is not None and it.text() in ("czeka", "w toku…"):
                    self._batch_cell(r, 3, "pominięto (przerwano)", T.MUTED)
        self.lbl_batch_summary.setText(txt)
        self.lbl_batch_progress.setText(txt)
        self.lbl_batch_progress.show()

    def batch_cancel(self) -> None:
        if self.batch_running():
            self.btn_batch_cancel.setEnabled(False)
            self.lbl_batch_progress.setText("Przerywam…")
            self.batch_worker.cancel.set()

    def batch_reveal(self) -> None:
        d = self.ed_batch_dir.text().strip()
        if d and os.path.isdir(d):
            subprocess.Popen(f'explorer "{os.path.normpath(d)}"')

    # ================================================================ zamykanie

    def closeEvent(self, e):
        if self.batch_running():
            r = QMessageBox.question(self, "Trwa poprawianie nagrań",
                                     "Poprawianie nagrań jeszcze trwa. Przerwać i zamknąć program?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.batch_worker.cancel.set()
            self.batch_worker.wait(10000)
        if self.exporting():
            r = QMessageBox.question(self, "Trwa eksport", "Eksport jeszcze trwa. Przerwać i zamknąć program?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.export_worker.cancel.set()
            self.export_worker.wait(5000)
        self.cancel_analysis()
        for w in list(self._old_workers):
            w.wait(5000)
        if self.loop_worker is not None:
            self.loop_worker.wait(3000)
        self.player.stop()
        self.player.setSource(QUrl())
        self._stop_result()
        self.settings.setValue("geometry", self.saveGeometry())
        if self.ed_dir.text():
            self.settings.setValue("out_dir", self.ed_dir.text())
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        super().closeEvent(e)
