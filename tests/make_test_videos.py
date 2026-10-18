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
]


def main():
    OUT.mkdir(exist_ok=True)
    for name, size, dur, extra in CASES:
        path = OUT / name
        if path.exists():
            continue
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={dur}",
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
