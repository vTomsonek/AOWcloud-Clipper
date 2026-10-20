"""Test logiki kodowania bez interfejsu, w obu standardach: sondowanie, szacunek, eksport,
weryfikacja, tryb „Popraw gotowe nagrania” i regresja standardu 250x250.

Uruchomienie:  .venv\\Scripts\\python.exe -m tests.test_pipeline
"""
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clipper import core, standard as S  # noqa: E402
from tests.make_test_videos import OUT, main as make_videos  # noqa: E402

RESULTS = Path(__file__).parent / "out"

# Wyniki standardu 250x250 sprzed dodania drugiego standardu (v0.1.1, tests/wyniki_testow.txt).
# x264 jest deterministyczny, więc po zmianach muszą się zgadzać co do bajta.
BASELINE_250 = {
    ("pion_1080x1920.mp4", None): (20.0, 349026),
    ("poziom_1920x1080.mov", 8.0): (20.0, 250174),
    ("telefon_obrot90.mp4", None): (20.0, 405325),
    ("za_dlugie_60s.mp4", None): "Fragment jest za długi na limit 0,5 MB nawet przy najniższej dopuszczalnej "
                                 "jakości (CRF 27: 0,87 MB). Skróć fragment o ok. 27,0 s (do ok. 33,0 s).",
    ("za_dlugie_60s.mp4", 33.0): (26.75, 514790),
    ("za_dlugie_60s.mp4", 20.0): (22.25, 513104),
    ("za_male_200x200.mp4", None): "Nagranie jest za małe: 200x200 px. Krótszy bok musi mieć co najmniej "
                                   "250 px, żeby kadr 250x250 nie był powiększany.",
}
regression: list[str] = []
summary: list[tuple[str, str, str]] = []


def show_verification(ver: core.Verification) -> None:
    for c in ver.checks:
        print(f"    [{'OK ' if c.ok else 'ŹLE'}] {c.name}: {c.detail}")
    print(f"    => {'SPEŁNIA STANDARD' if ver.ok else 'NIE SPEŁNIA STANDARDU'}")


def check_baseline(std, key, got) -> None:
    if std is not S.HOVER or key not in BASELINE_250:
        return
    want = BASELINE_250[key]
    ok = got == want
    regression.append(f"{'zgodne' if ok else 'RÓŻNICA'}: {key[0]}"
                      f"{f' ({key[1]:g} s)' if key[1] else ''}: przed {want}, teraz {got}")


def run_case(tools, std, path: Path, start=0.0, duration=None, crossfade=0.0) -> bool:
    print(f"\n=== [{std.dims}] {path.name}" + (f", fragment {duration:g} s" if duration else "") + " ===")
    key = (path.name, duration)
    try:
        info = core.probe(tools, str(path))
        print(f"  źródło: {info.coded_w}x{info.coded_h}, obrót {info.rotation}°, "
              f"wyświetlane {info.width}x{info.height}, {info.duration:.2f} s, "
              f"{info.fps:.2f} fps, audio: {info.has_audio}")
        core.check_source(info, std)
    except core.ClipperError as e:
        print(f"  ODRZUCONE: {e}")
        check_baseline(std, key, str(e))
        summary.append((std.dims, key_txt(key), "odrzucone (za małe)"))
        return False
    crop = core.Crop.centered(info.width, info.height)
    dur = duration or info.duration
    work = tempfile.mkdtemp(prefix="aowclipper_test_")
    try:
        t0 = time.time()
        an = core.analyze(tools, info, crop, work, std)
        pred = an.prediction(start, dur, crossfade)
        print(f"  szacunek ({time.time() - t0:.1f} s analizy): CRF{std.crf_start:g} ≈ "
              f"{core.fmt_mb(pred['size_start'])} MB, CRF{std.crf_max:g} ≈ {core.fmt_mb(pred['size_max'])} MB, "
              f"mieści się: {pred['fits']}, skróć o: {pred['shorten']} s")
        t0 = time.time()
        try:
            res = core.export(tools, info, crop, start, dur, work, std, crossfade)
        except core.TooLong as e:
            print(f"  EKSPORT WSTRZYMANY: {e}")
            check_baseline(std, key, str(e))
            summary.append((std.dims, key_txt(key), f"za długi: skróć o {core.fmt_s(e.shorten_s)} s"))
            return False
        print(f"  eksport {time.time() - t0:.1f} s, wybrany CRF {res.crf:g}, próby: "
              + ", ".join(f"CRF {c:g} = {s} B" for c, s in res.passes))
        print(f"  błąd szacunku: przewidziano {pred['size']} B, wyszło {res.size} B "
              f"({(pred['size'] - res.size) / res.size * 100:+.1f}%)")
        check_baseline(std, key, (res.crf, res.size))
        RESULTS.mkdir(exist_ok=True)
        frag = f"_{int(dur)}s" if duration else ""
        dst = RESULTS / (path.stem + frag + ("_xfade" if crossfade else "") + std.suffix + ".mp4")
        shutil.move(res.path, dst)
        ver = core.verify(tools, str(dst), std)
        print(f"  wynik: {dst.name}, {ver.width}x{ver.height}, {ver.fps:g} fps, "
              f"{ver.duration:.2f} s, {ver.size} B, {ver.bitrate // 1000} kb/s")
        show_verification(ver)
        summary.append((std.dims, key_txt(key), f"CRF {res.crf:g}, {core.fmt_mb(res.size)} MB, "
                        + ("spełnia" if ver.ok else "NIE spełnia")))
        return ver.ok
    finally:
        shutil.rmtree(work, ignore_errors=True)


def key_txt(key) -> str:
    return key[0] + (f" ({key[1]:g} s)" if key[1] else "")


def run_fix(tools, std, path: Path) -> None:
    print(f"\n=== [{std.dims}] POPRAW GOTOWE: {path.name} ===")
    work = tempfile.mkdtemp(prefix="aowclipper_fix_")
    try:
        r = core.fix_file(tools, str(path), std, work)
        b = r.before
        if b:
            print(f"  przed: {b.width}x{b.height}, {b.fps:.2f} fps, {b.codec} {b.profile}, "
                  f"{b.size_bytes} B, dźwięk: {b.has_audio}")
        print(f"  status: {r.status}, metoda: {r.method or '-'}; {r.message}")
        if r.verification is not None:
            v = r.verification
            print(f"  po: {v.width}x{v.height}, {v.fps:g} fps, {v.size} B")
            show_verification(v)
            if r.status == "ok":
                RESULTS.mkdir(exist_ok=True)
                shutil.copyfile(r.output, RESULTS / f"poprawione_{path.stem}{std.suffix}.mp4")
        summary.append((std.dims, "popraw: " + path.name,
                        {"ok": f"spełnia ({r.method})", "too_long": f"do ręcznego skrócenia o "
                         f"{core.fmt_s(r.shorten_s)} s", "too_small": "odrzucone (za małe)"}.get(r.status, r.status)))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    tools = core.find_tools()
    assert tools, "brak ffmpeg/ffprobe"
    make_videos()
    for std in (S.HOVER, S.DESCRIPTION):
        print(f"\n################ STANDARD: {std.label} (CRF {std.crf_start:g} do {std.crf_max:g})")
        run_case(tools, std, OUT / "pion_1080x1920.mp4")
        run_case(tools, std, OUT / "poziom_1920x1080.mov", start=1.0, duration=8.0, crossfade=0.5)
        run_case(tools, std, OUT / "za_male_200x200.mp4")
        run_case(tools, std, OUT / "za_male_500x500.mp4")
        run_case(tools, std, OUT / "telefon_obrot90.mp4")
        run_case(tools, std, OUT / "za_dlugie_60s.mp4")
        if std is S.HOVER:
            run_case(tools, std, OUT / "za_dlugie_60s.mp4", start=0.0, duration=33.0)
            run_case(tools, std, OUT / "za_dlugie_60s.mp4", start=5.0, duration=20.0)
        else:
            run_case(tools, std, OUT / "za_dlugie_60s.mp4", start=0.0, duration=10.0)
        for name in ("kwadrat_600x600_60fps.mp4", "kwadrat_600x600_gotowy.mp4", "za_male_500x500.mp4",
                     "pion_1080x1920.mp4", "za_dlugie_60s.mp4"):
            run_fix(tools, std, OUT / name)

    print("\n################ REGRESJA STANDARDU 250x250 (przed zmianą = v0.1.1)")
    for line in regression:
        print("  " + line)
    print("\n################ PODSUMOWANIE")
    for dims, case, res in summary:
        print(f"  {dims:8} {case:42} {res}")
    return 0 if all(line.startswith("zgodne") for line in regression) else 1


if __name__ == "__main__":
    sys.exit(main())
