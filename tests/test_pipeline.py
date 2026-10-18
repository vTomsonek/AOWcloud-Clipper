"""Test logiki kodowania bez interfejsu: sondowanie, szacunek, eksport, weryfikacja.

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


def show_verification(ver: core.Verification) -> None:
    for c in ver.checks:
        print(f"    [{'OK ' if c.ok else 'ŹLE'}] {c.name}: {c.detail}")
    print(f"    => {'SPEŁNIA STANDARD' if ver.ok else 'NIE SPEŁNIA STANDARDU'}")


def run_case(tools, path: Path, start=0.0, duration=None, crossfade=0.0) -> bool:
    print(f"\n=== {path.name} ===")
    try:
        info = core.probe(tools, str(path))
        print(f"  źródło: {info.coded_w}x{info.coded_h}, obrót {info.rotation}°, "
              f"wyświetlane {info.width}x{info.height}, {info.duration:.2f} s, "
              f"{info.fps:.2f} fps, audio: {info.has_audio}")
        core.check_source(info)
    except core.ClipperError as e:
        print(f"  ODRZUCONE: {e}")
        return False
    crop = core.Crop.centered(info.width, info.height)
    dur = duration or info.duration
    work = tempfile.mkdtemp(prefix="aowclipper_test_")
    try:
        t0 = time.time()
        an = core.analyze(tools, info, crop, work)
        pred = an.prediction(start, dur, crossfade)
        diff = core.loop_difference(tools, an.master, start, start + dur)
        print(f"  szacunek ({time.time() - t0:.1f} s analizy): CRF20 ≈ {core.fmt_mb(pred['size_start'])} MB, "
              f"CRF{S.CRF_MAX:g} ≈ {core.fmt_mb(pred['size_max'])} MB, "
              f"mieści się: {pred['fits']}, skróć o: {pred['shorten']} s; różnica pętli {diff:.3f}")
        t0 = time.time()
        try:
            res = core.export(tools, info, crop, start, dur, work, crossfade)
        except core.TooLong as e:
            print(f"  EKSPORT WSTRZYMANY: {e}")
            return False
        print(f"  eksport {time.time() - t0:.1f} s, wybrany CRF {res.crf:g}, próby: "
              + ", ".join(f"CRF {c:g} = {s} B" for c, s in res.passes))
        print(f"  błąd szacunku: przewidziano {pred['size']} B, wyszło {res.size} B "
              f"({(pred['size'] - res.size) / res.size * 100:+.1f}%)")
        RESULTS.mkdir(exist_ok=True)
        frag = f"_{int(dur)}s" if duration else ""
        dst = RESULTS / (path.stem + frag + ("_xfade" if crossfade else "") + "_250.mp4")
        shutil.move(res.path, dst)
        ver = core.verify(tools, str(dst))
        print(f"  wynik: {dst.name}, {ver.width}x{ver.height}, {ver.fps:g} fps, "
              f"{ver.duration:.2f} s, {ver.size} B, {ver.bitrate // 1000} kb/s")
        show_verification(ver)
        return ver.ok
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    tools = core.find_tools()
    assert tools, "brak ffmpeg/ffprobe"
    make_videos()
    run_case(tools, OUT / "pion_1080x1920.mp4")
    run_case(tools, OUT / "poziom_1920x1080.mov", start=1.0, duration=8.0, crossfade=0.5)
    run_case(tools, OUT / "za_male_200x200.mp4")
    run_case(tools, OUT / "telefon_obrot90.mp4")
    run_case(tools, OUT / "za_dlugie_60s.mp4")
    print("\n--- za_dlugie_60s.mp4 skrócone zgodnie z podpowiedzią (33 s) ---")
    run_case(tools, OUT / "za_dlugie_60s.mp4", start=0.0, duration=33.0)
    print("\n--- za_dlugie_60s.mp4, fragment 20 s (wymaga podniesienia CRF) ---")
    run_case(tools, OUT / "za_dlugie_60s.mp4", start=5.0, duration=20.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
