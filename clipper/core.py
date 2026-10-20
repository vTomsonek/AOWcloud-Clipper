"""Rdzeń: ffprobe, kodowanie z doborem CRF, szacunek wagi, weryfikacja.

Moduł nie zależy od Qt, dzięki czemu da się go testować z wiersza poleceń.
"""
from __future__ import annotations

import bisect
import json
import math
import os
import shutil
import struct
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import standard as S

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

ProgressCb = Callable[[float, str], None]   # (0..1, opis)


class ClipperError(Exception):
    """Błąd z komunikatem gotowym do pokazania użytkownikowi."""


class Cancelled(Exception):
    pass


class TooLong(ClipperError):
    """Nawet przy progowym CRF plik nie mieści się w limicie."""

    def __init__(self, message: str, shorten_s: float, max_duration_s: float, size_at_max: int):
        super().__init__(message)
        self.shorten_s = shorten_s
        self.max_duration_s = max_duration_s
        self.size_at_max = size_at_max


# ---------------------------------------------------------------- narzędzia

def _candidate_dirs() -> list[Path]:
    dirs = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "Microsoft" / "WinGet" / "Links")
    for pf in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if pf:
            dirs.append(Path(pf) / "ffmpeg" / "bin")
    dirs.append(Path("C:/ffmpeg/bin"))
    return dirs


def find_tool(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    for d in _candidate_dirs():
        p = d / f"{name}.exe"
        if p.is_file():
            return str(p)
    return None


@dataclass
class Tools:
    ffmpeg: str
    ffprobe: str


def find_tools() -> Optional[Tools]:
    ff, fp = find_tool("ffmpeg"), find_tool("ffprobe")
    if ff and fp:
        return Tools(ff, fp)
    return None


def ffmpeg_version(tools: Tools) -> str:
    """Np. "8.1" z pierwszej linii `ffmpeg -version`."""
    try:
        line = _run([tools.ffmpeg, "-hide_banner", "-version"], timeout=10).stdout.decode(
            "utf-8", "replace").splitlines()[0]
        ver = line.split()[2]
        return ver.split("-")[0]
    except (IndexError, OSError, subprocess.SubprocessError):
        return "?"


def _run(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout,
                          creationflags=CREATE_NO_WINDOW)


def run_ffmpeg(tools: Tools, args: list[str], duration: float,
               progress: Optional[ProgressCb] = None, label: str = "",
               cancel: Optional[threading.Event] = None) -> None:
    """Uruchamia ffmpeg z raportem postępu; anulowanie zabija proces."""
    cmd = [tools.ffmpeg, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1",
           "-nostats", "-loglevel", "error"] + args
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=CREATE_NO_WINDOW, text=True,
                            encoding="utf-8", errors="replace")
    err_lines: list[str] = []

    def read_err():
        for line in proc.stderr:
            err_lines.append(line.rstrip())
            del err_lines[:-30]

    t_err = threading.Thread(target=read_err, daemon=True)
    t_err.start()

    stop_watch = threading.Event()

    def watch_cancel():
        while not stop_watch.wait(0.1):
            if cancel is not None and cancel.is_set():
                proc.kill()
                return

    t_watch = threading.Thread(target=watch_cancel, daemon=True)
    t_watch.start()
    try:
        for line in proc.stdout:
            if line.startswith("out_time_us=") and progress and duration > 0:
                try:
                    us = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                progress(max(0.0, min(1.0, us / 1e6 / duration)), label)
        proc.wait()
    finally:
        stop_watch.set()
        t_watch.join()
        t_err.join(timeout=2)
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    if proc.returncode != 0:
        tail = "\n".join(err_lines[-6:])
        raise ClipperError(f"ffmpeg zakończył się błędem ({proc.returncode}).\n{tail}")


# ---------------------------------------------------------------- ffprobe

def _ratio(s: str | None) -> float:
    if not s or s in ("0/0", "N/A"):
        return 0.0
    if "/" in s:
        a, b = s.split("/", 1)
        try:
            return float(a) / float(b) if float(b) else 0.0
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _sar(s: str | None) -> float:
    if not s or s in ("0:1", "N/A", "1:1"):
        return 1.0
    a, _, b = s.partition(":")
    try:
        v = float(a) / float(b)
        return v if v > 0 else 1.0
    except (ValueError, ZeroDivisionError):
        return 1.0


def _rotation_cw(stream: dict) -> int:
    """Obrót do wyświetlania, w stopniach zgodnie z ruchem wskazówek zegara."""
    for sd in stream.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                return int(round(-float(sd["rotation"]) / 90.0)) * 90 % 360
            except (TypeError, ValueError):
                pass
    tag = (stream.get("tags") or {}).get("rotate")
    if tag:
        try:
            return int(round(float(tag) / 90.0)) * 90 % 360
        except ValueError:
            pass
    return 0


def ffprobe_json(tools: Tools, path: str, extra: list[str] | None = None) -> dict:
    args = [tools.ffprobe, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams"] + (extra or []) + [path]
    r = _run(args, timeout=60)
    if r.returncode != 0:
        msg = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ClipperError("Nie udało się odczytać pliku. To nie jest obsługiwane wideo."
                           + (f"\n{msg[-1]}" if msg else ""))
    return json.loads(r.stdout.decode("utf-8", "replace") or "{}")


@dataclass
class MediaInfo:
    path: str
    coded_w: int
    coded_h: int
    rotation: int          # stopnie CW
    sar: float
    width: int             # wymiary wyświetlane (po obrocie i SAR), kwadratowe piksele
    height: int
    duration: float
    fps: float
    codec: str
    has_audio: bool
    size_bytes: int
    profile: str = ""
    pix_fmt: str = ""
    r_fps: float = 0.0

    @property
    def short_side(self) -> int:
        return min(self.width, self.height)


def probe(tools: Tools, path: str) -> MediaInfo:
    data = ffprobe_json(tools, path)
    streams = data.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"
              and not (s.get("disposition") or {}).get("attached_pic")), None)
    if v is None:
        raise ClipperError("Plik nie zawiera ścieżki wideo.")
    cw, ch = int(v.get("width") or 0), int(v.get("height") or 0)
    if cw <= 0 or ch <= 0:
        raise ClipperError("Nie udało się odczytać wymiarów wideo.")
    rot = _rotation_cw(v)
    sar = _sar(v.get("sample_aspect_ratio"))
    w, h, fsar = (ch, cw, 1.0 / sar) if rot in (90, 270) else (cw, ch, sar)
    if abs(fsar - 1.0) > 0.01:
        w = int(round(w * fsar / 2.0)) * 2
    dur = _ratio((data.get("format") or {}).get("duration")) or _ratio(v.get("duration"))
    if dur <= 0:
        raise ClipperError("Nie udało się odczytać długości nagrania.")
    fps = _ratio(v.get("avg_frame_rate")) or _ratio(v.get("r_frame_rate"))
    return MediaInfo(
        path=path, coded_w=cw, coded_h=ch, rotation=rot, sar=sar,
        width=w, height=h, duration=dur, fps=fps,
        codec=v.get("codec_name", "?"),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        size_bytes=int((data.get("format") or {}).get("size") or os.path.getsize(path)),
        profile=v.get("profile", ""), pix_fmt=v.get("pix_fmt", ""),
        r_fps=_ratio(v.get("r_frame_rate")),
    )


def check_source(info: MediaInfo, std: S.VideoStandard) -> None:
    if info.short_side < std.min_source_side:
        msg = (f"Nagranie jest za małe: {info.width}x{info.height} px. "
               f"Krótszy bok musi mieć co najmniej {std.min_source_side} px, "
               f"żeby kadr {std.dims} nie był powiększany.")
        other = [o for o in S.STANDARDS.values() if o is not std and info.short_side >= o.min_source_side]
        if other:
            msg += (f" Powiększone wideo byłoby rozmazane, dlatego standard „{std.name}” go nie przyjmuje."
                    f" To nagranie nadaje się do standardu „{other[0].label}”.")
        raise ClipperError(msg)
    if info.duration < S.MIN_FRAGMENT_S:
        raise ClipperError("Nagranie jest za krótkie (poniżej 1 s).")


# ---------------------------------------------------------------- filtry

@dataclass
class Crop:
    x: int
    y: int
    size: int

    def clamp(self, w: int, h: int, min_size: int) -> "Crop":
        size = max(min(self.size, w, h), min(min_size, w, h))
        x = max(0, min(self.x, w - size))
        y = max(0, min(self.y, h - size))
        return Crop(int(x), int(y), int(size))

    @staticmethod
    def centered(w: int, h: int) -> "Crop":
        s = min(w, h)
        return Crop((w - s) // 2, (h - s) // 2, s)


def _crossfade_len(duration: float, crossfade: float) -> float:
    if crossfade <= 0:
        return 0.0
    return round(min(crossfade, duration / 4.0), 3)


def output_duration(duration: float, crossfade: float) -> float:
    return duration - _crossfade_len(duration, crossfade)


def build_filter(info: MediaInfo, crop: Crop, duration: float, size: int, crossfade: float = 0.0) -> str:
    """Kolejność: przycięcie fragmentu, kadr, skalowanie lanczos, fps=30."""
    parts = [f"trim=duration={duration:.3f}", "setpts=PTS-STARTPTS"]
    if (info.width, info.height) != ((info.coded_h, info.coded_w) if info.rotation in (90, 270)
                                     else (info.coded_w, info.coded_h)):
        parts.append(f"scale={info.width}:{info.height},setsar=1")   # niekwadratowe piksele
    c = crop.clamp(info.width, info.height, size)
    parts += [f"crop={c.size}:{c.size}:{c.x}:{c.y}",
              f"scale={size}:{size}:flags=lanczos",
              f"fps={S.OUT_FPS}",
              "format=yuv420p", "setsar=1"]
    chain = ",".join(parts)
    xf = _crossfade_len(duration, crossfade)
    if xf <= 0:
        return f"[0:v]{chain}[v]"
    # Przenikanie: koniec fragmentu przechodzi w jego początek, więc ostatnia klatka
    # pliku to klatka z chwili xf, a pierwsza klatka pliku też jest z chwili xf.
    off = duration - 2 * xf
    return (f"[0:v]{chain},split[a][b];"
            f"[a]trim=start={xf:.3f},setpts=PTS-STARTPTS[body];"
            f"[b]trim=end={xf:.3f},setpts=PTS-STARTPTS[head];"
            f"[body][head]xfade=transition=fade:duration={xf:.3f}:offset={off:.3f},"
            f"format=yuv420p,setsar=1[v]")


def make_master(tools: Tools, info: MediaInfo, crop: Crop, start: float, duration: float,
                out: str, size: int, crossfade: float = 0.0, progress: Optional[ProgressCb] = None,
                cancel: Optional[threading.Event] = None, label: str = "Przygotowanie") -> None:
    """Bezstratny plik pośredni size x size @30 (FFV1). Źródło dekodujemy tylko raz,
    a kolejne próby CRF kodują już z małego pliku."""
    args = []
    if start > 0:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", info.path,
             "-filter_complex", build_filter(info, crop, duration, size, crossfade),
             "-map", "[v]", "-an", "-sn", "-dn", "-map_metadata", "-1",
             "-c:v", "ffv1", "-level", "3", "-g", "1", out]
    run_ffmpeg(tools, args, duration, progress, label, cancel)


def x264_args(crf: float, frames: int) -> list[str]:
    gop = max(frames + 1, 2)
    return ["-c:v", "libx264", "-preset", S.PRESET, "-tune", S.TUNE,
            "-crf", f"{crf:.2f}", "-profile:v", "high", "-pix_fmt", "yuv420p",
            # Jedna klatka kluczowa na początku: krótka pętla nie potrzebuje przewijania,
            # a każda dodatkowa klatka I kosztuje kilkanaście KB.
            "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
            "-x264-params", "open-gop=0"]


def encode_crf(tools: Tools, master: str, crf: float, duration: float, out: str,
               progress: Optional[ProgressCb] = None, label: str = "",
               cancel: Optional[threading.Event] = None) -> int:
    frames = int(round(duration * S.OUT_FPS))
    args = ["-i", master, "-map", "0:v:0", "-an", "-sn", "-dn",
            "-map_metadata", "-1", "-map_chapters", "-1",
            *x264_args(crf, frames),
            "-r", str(S.OUT_FPS), "-fps_mode", "cfr",
            "-metadata:s:v:0", "handler_name=VideoHandler",
            "-movflags", "+faststart", "-f", "mp4", out]
    run_ffmpeg(tools, args, duration, progress, label, cancel)
    return os.path.getsize(out)


# ---------------------------------------------------------------- dobór CRF

def fmt_mb(n: float, digits: int = 2) -> str:
    return f"{n / 1048576:.{digits}f}".replace(".", ",")


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def fmt_crf(c: float) -> str:
    return f"{c:g}".replace(".", ",")


def fmt_s(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def shorten_needed(size_at_max: int, duration: float, max_bytes: int) -> tuple[float, float]:
    """Ile sekund uciąć, licząc z bitrate przy progowym CRF. Zwraca (skróć_o, maks_długość)."""
    overhead = 2000
    rate = max(1.0, (size_at_max - overhead) / max(duration, 0.1))
    max_dur = (max_bytes * 0.97 - overhead) / rate
    max_dur = math.floor(max(0.0, max_dur) * 2) / 2
    short = math.ceil(max(0.5, duration - max_dur) * 2) / 2
    return short, max_dur


def _interp_crf(c1: float, s1: int, c2: float, s2: int, target: float) -> float:
    """Wielkość pliku zależy od CRF mniej więcej wykładniczo: interpolacja log."""
    if s1 <= 0 or s2 <= 0 or s1 == s2:
        return (c1 + c2) / 2
    l1, l2, lt = math.log(s1), math.log(s2), math.log(target)
    return c1 + (lt - l1) * (c2 - c1) / (l2 - l1)


@dataclass
class ExportResult:
    path: str
    crf: float
    size: int
    passes: list[tuple[float, int]] = field(default_factory=list)


def export(tools: Tools, info: MediaInfo, crop: Crop, start: float, duration: float,
           workdir: str, std: S.VideoStandard, crossfade: float = 0.0,
           progress: Optional[ProgressCb] = None,
           cancel: Optional[threading.Event] = None) -> ExportResult:
    """Pełny eksport: plik pośredni, potem próby CRF od CRF_START w górę, aż plik
    zmieści się w limicie. Powyżej CRF_MAX nie kodujemy, tylko każemy skrócić."""
    os.makedirs(workdir, exist_ok=True)
    out_dur = output_duration(duration, crossfade)
    master = os.path.join(workdir, "master.mkv")
    # Postęp: przygotowanie 30%, próby 70% (szacujemy max. 4 próby)
    est_passes = 4
    state = {"done": 0}

    def p_master(f, lbl):
        if progress:
            progress(0.30 * f, lbl)

    def p_pass(f, lbl):
        if progress:
            k = min(state["done"], est_passes - 1)
            progress(0.30 + 0.70 * (k + f) / est_passes, lbl)

    make_master(tools, info, crop, start, duration, master, std.size, crossfade, p_master, cancel,
                "Przygotowanie kadru")
    limit = std.max_bytes

    passes: list[tuple[float, int]] = []
    files: dict[float, str] = {}

    def try_crf(crf: float) -> int:
        crf = round(crf * 4) / 4
        out = os.path.join(workdir, f"pass_crf{crf:.2f}.mp4")
        size = encode_crf(tools, master, crf, out_dur, out, p_pass,
                          f"Kodowanie, próba {len(passes) + 1}: CRF {crf:g}".replace(".", ","),
                          cancel)
        passes.append((crf, size))
        files[crf] = out
        state["done"] += 1
        return size

    lo_c, lo_s = std.crf_start, try_crf(std.crf_start)
    if lo_s <= limit:
        best = std.crf_start
    else:
        # Najpierw zgadnij CRF z typowej zależności (ok. +6 CRF = połowa wagi)
        guess = min(std.crf_max, lo_c + 6 * math.log2(lo_s / (limit * 0.95)))
        hi_c, hi_s = None, None
        g_s = try_crf(guess)
        g_c = round(guess * 4) / 4
        if g_s <= limit:
            hi_c, hi_s = g_c, g_s
        else:
            lo_c, lo_s = g_c, g_s
            if g_c < std.crf_max:
                m_s = try_crf(std.crf_max)
                if m_s <= limit:
                    hi_c, hi_s = std.crf_max, m_s
                else:
                    lo_c, lo_s = std.crf_max, m_s
        if hi_c is None:
            short, max_dur = shorten_needed(lo_s, out_dur, limit)
            raise TooLong(
                f"Fragment jest za długi na limit {std.limit_label} nawet przy najniższej dopuszczalnej "
                f"jakości (CRF {fmt_crf(std.crf_max)}: {fmt_mb(lo_s)} MB). "
                f"Skróć fragment o ok. {fmt_s(short)} s (do ok. {fmt_s(max_dur)} s).",
                short, max_dur, lo_s)
        # Zawężanie: lo za duży, hi mieści się. Szukamy najniższego CRF, który się mieści.
        # Koniec, gdy przedział jest wąski albo plik i tak wykorzystuje prawie cały limit
        while (hi_c - lo_c > S.CRF_PRECISION and hi_s < limit * S.FILL_ENOUGH
               and len(passes) < S.MAX_PASSES):
            mid = _interp_crf(lo_c, lo_s, hi_c, hi_s, limit * 0.985)
            mid = max(lo_c + 0.25, min(hi_c - 0.25, round(mid * 4) / 4))
            if mid in files:
                break
            m_s = try_crf(mid)
            if m_s <= limit:
                hi_c, hi_s = mid, m_s
            else:
                lo_c, lo_s = mid, m_s
        best = hi_c

    final = os.path.join(workdir, "final.mp4")
    os.replace(files[best], final)
    for c, f in files.items():
        if c != best and os.path.exists(f):
            os.remove(f)
    if os.path.exists(master):
        os.remove(master)
    if progress:
        progress(1.0, "Weryfikacja")
    return ExportResult(final, best, os.path.getsize(final), passes)


# ---------------------------------------------------------------- szacunek wagi

@dataclass
class Analysis:
    """Wynik kodowania całego nagrania (z bieżącym kadrem) przy CRF_START i CRF_MAX.
    Rozmiary pakietów pozwalają natychmiast oszacować wagę dowolnego fragmentu."""
    times: list[float]
    sizes: dict[float, list[int]]
    master: str
    std: S.VideoStandard

    def _sum(self, crf: float, start: float, end: float) -> int:
        t, sz = self.times, self.sizes[crf]
        i, j = bisect.bisect_left(t, start - 1e-6), bisect.bisect_left(t, end - 1e-6)
        if j <= i:
            return 0
        total = sum(sz[i:j])
        # Fragment zaczyna się od klatki I: podmień koszt pierwszej klatki
        total += max(0, sz[0] - sz[i])
        return total

    def estimate(self, crf: float, start: float, duration: float, crossfade: float = 0.0) -> int:
        out_dur = output_duration(duration, crossfade)
        frames = int(round(out_dur * S.OUT_FPS))
        raw = self._sum(crf, start, start + out_dur)
        return int(raw + 1200 + 14 * frames)   # nagłówki mp4 i indeks próbek

    def prediction(self, start: float, duration: float, crossfade: float = 0.0) -> dict:
        std = self.std
        s_start = self.estimate(std.crf_start, start, duration, crossfade)
        s_max = self.estimate(std.crf_max, start, duration, crossfade)
        res = {"size": s_start, "crf": std.crf_start, "fits": True,
               "size_start": s_start, "size_max": s_max, "shorten": 0.0, "max_dur": None}
        if s_start <= std.max_bytes:
            return res
        if s_max <= std.max_bytes:
            crf = _interp_crf(std.crf_start, s_start, std.crf_max, s_max, std.max_bytes)
            res.update(size=std.max_bytes, crf=max(std.crf_start, min(std.crf_max, crf)))
            return res
        short, max_dur = shorten_needed(s_max, output_duration(duration, crossfade), std.max_bytes)
        res.update(size=s_max, crf=std.crf_max, fits=False, shorten=short, max_dur=max_dur)
        return res


def _packet_sizes(tools: Tools, path: str) -> tuple[list[float], list[int]]:
    r = _run([tools.ffprobe, "-v", "error", "-select_streams", "v:0",
              "-show_entries", "packet=pts_time,size", "-of", "csv=p=0", path], timeout=120)
    rows = []
    for line in r.stdout.decode().splitlines():
        a, _, b = line.strip().partition(",")
        try:
            rows.append((float(a), int(b)))
        except ValueError:
            continue
    rows.sort()
    return [t for t, _ in rows], [s for _, s in rows]


def analyze(tools: Tools, info: MediaInfo, crop: Crop, workdir: str, std: S.VideoStandard,
            cancel: Optional[threading.Event] = None,
            progress: Optional[ProgressCb] = None) -> Analysis:
    os.makedirs(workdir, exist_ok=True)
    master = os.path.join(workdir, "analysis_master.mkv")
    dur = info.duration

    def pm(f, l):
        if progress:
            progress(0.5 * f, l)

    make_master(tools, info, crop, 0.0, dur, master, std.size, 0.0, pm, cancel, "Analiza")
    sizes = {}
    times: list[float] = []
    for k, crf in enumerate((std.crf_start, std.crf_max)):
        out = os.path.join(workdir, f"analysis_{int(crf)}.mp4")
        frames = int(round(dur * S.OUT_FPS))
        args = ["-i", master, "-an", *x264_args(crf, frames),
                "-r", str(S.OUT_FPS), "-f", "mp4", out]

        def pp(f, l, k=k):
            if progress:
                progress(0.5 + 0.25 * (k + f), l)

        run_ffmpeg(tools, args, dur, pp, "Analiza", cancel)
        t, s = _packet_sizes(tools, out)
        times = t
        sizes[crf] = s
        os.remove(out)
    n = min(len(times), *(len(v) for v in sizes.values()))
    return Analysis(times[:n], {c: v[:n] for c, v in sizes.items()}, master, std)


def loop_difference(tools: Tools, master: str, start: float, end: float) -> float:
    """Średnia różnica jasności (0..1) między pierwszą i ostatnią klatką fragmentu."""
    def grab(t: float) -> bytes:
        r = _run([tools.ffmpeg, "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", master,
                  "-frames:v", "1", "-vf", "scale=32:32:flags=area,format=gray",
                  "-f", "rawvideo", "-"], timeout=30)
        return r.stdout

    a, b = grab(start), grab(end - 1.0 / S.OUT_FPS)
    if len(a) != 1024 or len(b) != 1024:
        return 0.0
    return sum(abs(x - y) for x, y in zip(a, b)) / (1024 * 255.0)


# ---------------------------------------------------------------- weryfikacja

def mp4_top_atoms(path: str) -> list[str]:
    atoms = []
    size_total = os.path.getsize(path)
    with open(path, "rb") as f:
        pos = 0
        while pos + 8 <= size_total and len(atoms) < 64:
            f.seek(pos)
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            size, typ = struct.unpack(">I4s", hdr)
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
            elif size == 0:
                size = size_total - pos
            atoms.append(typ.decode("latin-1"))
            if size < 8:
                break
            pos += size
    return atoms


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class Verification:
    checks: list[Check]
    width: int = 0
    height: int = 0
    fps: float = 0.0
    duration: float = 0.0
    size: int = 0
    bitrate: int = 0
    codec: str = ""
    profile: str = ""

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]


def verify(tools: Tools, path: str, std: S.VideoStandard) -> Verification:
    checks: list[Check] = []
    try:
        data = ffprobe_json(tools, path)
    except ClipperError as e:
        return Verification([Check("Odczyt pliku", False, str(e))])
    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    vids = [s for s in streams if s.get("codec_type") == "video"]
    auds = [s for s in streams if s.get("codec_type") == "audio"]
    others = [s for s in streams if s.get("codec_type") not in ("video",)]
    size = os.path.getsize(path)
    v = vids[0] if vids else {}
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    r_fps, a_fps = _ratio(v.get("r_frame_rate")), _ratio(v.get("avg_frame_rate"))
    dur = _ratio(fmt.get("duration")) or _ratio(v.get("duration"))
    bitrate = int(size * 8 / dur) if dur > 0 else 0
    rot = _rotation_cw(v) if v else 0
    has_matrix = any("rotation" in sd or sd.get("side_data_type") == "Display Matrix"
                     for sd in (v.get("side_data_list") or []))
    atoms = mp4_top_atoms(path)

    fmt_name = fmt.get("format_name", "")
    checks.append(Check("Kontener MP4", "mp4" in fmt_name and path.lower().endswith(".mp4"),
                        fmt_name or "nieznany"))
    checks.append(Check("Jedna ścieżka wideo", len(vids) == 1, f"ścieżek wideo: {len(vids)}"))
    checks.append(Check(f"Wymiary {std.dims}", (w, h) == (std.size, std.size), f"{w}x{h}"))
    checks.append(Check("30 fps", abs(r_fps - S.OUT_FPS) < 0.01 and abs(a_fps - S.OUT_FPS) < 0.05,
                        f"{a_fps:.2f} fps".replace(".", ",")))
    checks.append(Check("Kodek H.264", v.get("codec_name") == S.OUT_CODEC, v.get("codec_name", "?")))
    checks.append(Check("Profil High", v.get("profile") == S.OUT_PROFILE, v.get("profile", "?")))
    checks.append(Check("Piksele yuv420p", v.get("pix_fmt") == S.OUT_PIX_FMT, v.get("pix_fmt", "?")))
    checks.append(Check("Bez dźwięku", not auds,
                        "brak ścieżki audio" if not auds else f"ścieżek audio: {len(auds)}"))
    checks.append(Check("Bez innych ścieżek", not others,
                        "tylko wideo" if not others else f"dodatkowe: {len(others)}"))
    checks.append(Check(f"Waga do {std.limit_label}", 0 < size <= std.max_bytes,
                        f"{fmt_int(size)} B ({fmt_mb(size)} MB) z {fmt_int(std.max_bytes)} B"))
    checks.append(Check("Bez obrotu", rot == 0 and not has_matrix,
                        "brak metadanych obrotu" if not has_matrix else f"obrót {rot}°"))
    moov_first = "moov" in atoms and "mdat" in atoms and atoms.index("moov") < atoms.index("mdat")
    checks.append(Check("faststart (moov na początku)", moov_first, " > ".join(atoms[:5])))
    checks.append(Check("Czas trwania", dur > 0.3, f"{fmt_s(dur)} s"))
    return Verification(checks, w, h, a_fps, dur, size, bitrate,
                        v.get("codec_name", ""), v.get("profile", ""))


# ---------------------------------------------------------------- poprawianie gotowych nagrań

@dataclass
class FixResult:
    """Wynik trybu „Popraw gotowe nagrania” dla jednego pliku."""
    source: str
    before: Optional[MediaInfo] = None
    status: str = "error"        # ok | not_ok | too_long | too_small | error
    message: str = ""
    method: str = ""             # "bez kodowania" albo "CRF 23"
    output: str = ""             # gotowy plik w katalogu roboczym
    verification: Optional[Verification] = None
    shorten_s: float = 0.0


def can_remux(info: MediaInfo, std: S.VideoStandard) -> bool:
    """Obraz już jest w standardzie: wystarczy przepakować (bez dźwięku, z faststart)."""
    return (info.coded_w == info.coded_h == std.size and info.rotation == 0
            and abs(info.sar - 1.0) < 0.01 and info.codec == S.OUT_CODEC
            and info.profile == S.OUT_PROFILE and info.pix_fmt == S.OUT_PIX_FMT
            and abs(info.r_fps - S.OUT_FPS) < 0.01 and abs(info.fps - S.OUT_FPS) < 0.05
            and info.size_bytes <= std.max_bytes * 1.5)


def remux(tools: Tools, info: MediaInfo, out: str, cancel: Optional[threading.Event] = None) -> None:
    run_ffmpeg(tools, ["-i", info.path, "-map", "0:v:0", "-c:v", "copy", "-an", "-sn", "-dn",
                       "-map_metadata", "-1", "-map_chapters", "-1",
                       "-metadata:s:v:0", "handler_name=VideoHandler",
                       "-movflags", "+faststart", "-f", "mp4", out],
               info.duration, None, "", cancel)


def fix_file(tools: Tools, path: str, std: S.VideoStandard, workdir: str,
             progress: Optional[ProgressCb] = None,
             cancel: Optional[threading.Event] = None) -> FixResult:
    """Przerabia gotowe nagranie do standardu bez ręcznego kadrowania.

    Kwadrat jest tylko skalowany, prostokąt kadrowany do środka, cały plik jako fragment.
    Gdy obraz już spełnia standard, plik jest tylko przepakowany (bez straty jakości)."""
    res = FixResult(path)
    os.makedirs(workdir, exist_ok=True)
    try:
        info = probe(tools, path)
        res.before = info
        try:
            check_source(info, std)
        except ClipperError as e:
            res.status, res.message = "too_small", str(e)
            return res
        if can_remux(info, std):
            out = os.path.join(workdir, "remux.mp4")
            remux(tools, info, out, cancel)
            ver = verify(tools, out, std)
            if ver.ok:
                res.status, res.method, res.output, res.verification = "ok", "bez kodowania", out, ver
                res.message = "Obraz był już w standardzie: usunięto dźwięk i metadane, dodano faststart."
                return res
            os.remove(out)
        crop = Crop.centered(info.width, info.height)
        try:
            er = export(tools, info, crop, 0.0, info.duration, workdir, std, 0.0, progress, cancel)
        except TooLong as e:
            res.status, res.shorten_s = "too_long", e.shorten_s
            res.message = (f"Do ręcznego skrócenia: nawet przy CRF {fmt_crf(std.crf_max)} plik waży "
                           f"{fmt_mb(e.size_at_max)} MB. Skróć o ok. {fmt_s(e.shorten_s)} s "
                           f"(do ok. {fmt_s(e.max_duration_s)} s).")
            return res
        ver = verify(tools, er.path, std)
        res.output, res.verification = er.path, ver
        res.method = f"CRF {fmt_crf(er.crf)}"
        if ver.ok:
            res.status, res.message = "ok", "Spełnia standard."
        else:
            res.status = "not_ok"
            res.message = "Nie spełnia: " + "; ".join(f"{c.name} ({c.detail})" for c in ver.failures)
        return res
    except Cancelled:
        raise
    except ClipperError as e:
        res.status, res.message = "error", str(e)
        return res
