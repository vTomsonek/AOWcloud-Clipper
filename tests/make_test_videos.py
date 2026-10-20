"""Generuje nagrania testowe ffmpeg (testsrc2 + dźwięk), jak z telefonu/aparatu."""
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).parent / "videos"

CASES = [
    # nazwa, wymiary, czas, dodatkowe opcje wyjścia
    ("pion_1080x1920.mp4", "1080x1920", 10, []),
    ("poziom_1920x1080.mov", "1920x1080", 12, []),
    ("za_male_200x200.mp4", "200x200", 5, []),
    ("za_dlugie_60s.mp4", "1920x1080", 60, []),
    ("za_male_500x500.mp4", "500x500", 6, []),
    # stare nagranie do opisu: już kwadrat 600x600, ale 60 fps i z dźwiękiem
    ("kwadrat_600x600_60fps.mp4", "600x600", 6, ["-r", "60"]),
]


def main():
    OUT.mkdir(exist_ok=True)
    for name, size, dur, extra in CASES:
        path = OUT / name
        if path.exists():
            continue
        rate = extra[extra.index("-r") + 1] if "-r" in extra else "30"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={dur}",
               "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
               # drgania jak z ręki i lekki szum matrycy: czysty testsrc2 kompresuje się
               # nierealnie dobrze, a sam mocny szum x264 wycina skokowo przy wyższym CRF
               "-vf", "rotate=a='0.15*sin(t)':c=gray,noise=alls=6:allf=t",
               "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", *extra, str(path)]
        print("tworzę", name)
        subprocess.run(cmd, check=True)
    # Nagranie "z telefonu": zakodowane poziomo 1920x1080 z obrotem 90° w metadanych
    rot = OUT / "telefon_obrot90.mp4"
    if not rot.exists():
        print("tworzę", rot.name)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-display_rotation", "90", "-i", str(OUT / "poziom_1920x1080.mov"),
                        "-c", "copy", str(rot)], check=True)
    # Stare nagranie do opisu, którego obraz już spełnia standard (600x600, 30 fps, H.264 High),
    # ale ma dźwięk i nie ma faststart: tryb poprawiania powinien je tylko przepakować.
    ready = OUT / "kwadrat_600x600_gotowy.mp4"
    if not ready.exists():
        print("tworzę", ready.name)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc2=size=600x600:rate=30:duration=5",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
                        "-vf", "rotate=a='0.15*sin(t)':c=gray,noise=alls=6:allf=t",
                        "-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-b:v", "900k",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(ready)], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
