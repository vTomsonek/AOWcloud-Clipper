"""Wątki robocze: analiza wagi, sprawdzenie pętli, eksport, poprawianie gotowych nagrań.
Okno nigdy nie czeka na ffmpeg."""
from __future__ import annotations

import os
import shutil
import threading

from PySide6.QtCore import QThread, Signal

from .. import core


class AnalysisWorker(QThread):
    progress = Signal(float, str)
    done = Signal(object)          # core.Analysis
    failed = Signal(str)

    def __init__(self, tools, info, crop, workdir, std, parent=None):
        super().__init__(parent)
        self.tools, self.info, self.crop, self.workdir, self.std = tools, info, crop, workdir, std
        self.cancel = threading.Event()

    def run(self):
        try:
            res = core.analyze(self.tools, self.info, self.crop, self.workdir, self.std, self.cancel,
                               lambda f, l: self.progress.emit(f, l))
        except core.Cancelled:
            shutil.rmtree(self.workdir, ignore_errors=True)
            return
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(self.workdir, ignore_errors=True)
            self.failed.emit(str(e))
            return
        self.done.emit(res)


class LoopCheckWorker(QThread):
    done = Signal(float, int, int)   # różnica, start_ms, end_ms

    def __init__(self, tools, master, start_ms, end_ms, parent=None):
        super().__init__(parent)
        self.tools, self.master, self.start_ms, self.end_ms = tools, master, start_ms, end_ms

    def run(self):
        try:
            d = core.loop_difference(self.tools, self.master, self.start_ms / 1000, self.end_ms / 1000)
        except Exception:  # noqa: BLE001
            return
        self.done.emit(d, self.start_ms, self.end_ms)


class ExportWorker(QThread):
    progress = Signal(float, str)
    finished_ok = Signal(object, object)    # ExportResult, Verification
    too_long = Signal(str, float, float, int)    # komunikat, skróć o, maks. długość, waga przy CRF_MAX
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, tools, info, crop, start, duration, crossfade, workdir, std, parent=None):
        super().__init__(parent)
        self.args = (tools, info, crop, start, duration, workdir, crossfade)
        self.tools = tools
        self.workdir = workdir
        self.std = std
        self.cancel = threading.Event()

    def run(self):
        tools, info, crop, start, duration, workdir, crossfade = self.args
        try:
            res = core.export(tools, info, crop, start, duration, workdir, self.std, crossfade,
                              lambda f, l: self.progress.emit(f, l), self.cancel)
            ver = core.verify(tools, res.path, self.std)
        except core.Cancelled:
            self._cleanup()
            self.cancelled.emit()
            return
        except core.TooLong as e:
            self._cleanup()
            self.too_long.emit(str(e), e.shorten_s, e.max_duration_s, e.size_at_max)
            return
        except Exception as e:  # noqa: BLE001
            self._cleanup()
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(res, ver)

    def _cleanup(self):
        shutil.rmtree(self.workdir, ignore_errors=True)
        os.makedirs(self.workdir, exist_ok=True)


class BatchWorker(QThread):
    """Tryb „Popraw gotowe nagrania”: plik po pliku, zapis tylko plików zgodnych ze standardem."""
    progress = Signal(float, str)            # cały przebieg 0..1, opis
    row_started = Signal(int)
    row_done = Signal(int, object, str)      # wiersz, core.FixResult, zapisany plik ("" gdy brak)
    all_done = Signal(bool)                  # True gdy przerwano

    def __init__(self, tools, files, targets, std, workdir, parent=None):
        super().__init__(parent)
        self.tools, self.files, self.targets, self.std, self.workdir = tools, files, targets, std, workdir
        self.cancel = threading.Event()

    def run(self):
        n = len(self.files)
        for i, (src, dst) in enumerate(zip(self.files, self.targets)):
            if self.cancel.is_set():
                break
            self.row_started.emit(i)
            name = os.path.basename(src)

            def prog(f, label, i=i, name=name):
                self.progress.emit((i + f) / n, f"{i + 1}/{n}  {name}: {label}")

            prog(0.0, "sprawdzam")
            work = os.path.join(self.workdir, f"plik_{i}")
            try:
                res = core.fix_file(self.tools, src, self.std, work, prog, self.cancel)
            except core.Cancelled:
                shutil.rmtree(work, ignore_errors=True)
                break
            saved = ""
            if res.status == "ok" and res.output:
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(res.output, dst)
                    if os.path.getsize(dst) != os.path.getsize(res.output):
                        raise OSError("rozmiar zapisanego pliku się nie zgadza")
                    saved = dst
                except OSError as e:
                    res.status, res.message = "error", f"Nie udało się zapisać: {e}"
            shutil.rmtree(work, ignore_errors=True)
            self.row_done.emit(i, res, saved)
        self.progress.emit(1.0, "")
        self.all_done.emit(self.cancel.is_set())
