"""Standardy wideo sklepu i wspólne progi kodowania. Jedno miejsce na wszystkie liczby.

Nowy standard to dopisanie jednego wpisu VideoStandard do STANDARDS.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoStandard:
    key: str                # identyfikator zapisywany w ustawieniach
    name: str               # nazwa w interfejsie i w wyniku
    size: int               # kwadrat size x size px
    max_bytes: int          # twardy limit wagi
    crf_start: float        # pierwsza próba: wysoka jakość
    crf_max: float          # próg: powyżej obraz w tym rozmiarze jest już za słaby
    suffix: str             # domyślny dopisek nazwy pliku
    preview: str            # "tile" (kafelek) albo "phone" (szerokość ekranu telefonu)
    preview_px: int         # bok podglądu w px interfejsu
    preview_title: str      # nagłówek podglądu
    preview_hint: str       # podpis pod podglądem
    usage: str              # gdzie i jak wideo jest pokazywane (tooltip)

    @property
    def min_source_side(self) -> int:
        """Krótszy bok źródła po obrocie: bez powiększania."""
        return self.size

    @property
    def min_crop(self) -> int:
        """Kadr nie mniejszy niż size x size px źródła."""
        return self.size

    @property
    def dims(self) -> str:
        return f"{self.size}x{self.size}"

    @property
    def limit_label(self) -> str:
        mb = self.max_bytes / 1048576
        return f"{mb:g} MB".replace(".", ",")

    @property
    def label(self) -> str:
        return f"{self.name} ({self.dims}, {self.limit_label})"

    @property
    def tooltip(self) -> str:
        return "\n".join([
            f"{self.name}.",
            f"{self.usage}",
            f"MP4, kwadrat dokładnie {self.dims} px, najwyżej {self.limit_label} ({self.max_bytes} B).",
            f"{OUT_FPS} fps, H.264 profil High, yuv420p, bez dźwięku, faststart, bez metadanych obrotu.",
            f"Nagranie musi mieć krótszy bok co najmniej {self.min_source_side} px.",
        ])


HOVER = VideoStandard(
    key="najechanie",
    name="Wideo po najechaniu",
    size=250,
    max_bytes=524288,           # 0,5 MB
    crf_start=20.0,
    crf_max=27.0,
    suffix="_250",
    preview="tile",
    preview_px=250,
    preview_title="PODGLĄD W KAFELKU 250x250",
    preview_hint="Na telefonie kafelek ma ok. 170 px, na komputerze ok. 255 px.",
    usage="Gra w kafelku na liście produktów po najechaniu myszką (ok. 255 px na komputerze, 170 px na telefonie).",
)

DESCRIPTION = VideoStandard(
    key="opis",
    name="Opis produktu",
    size=600,
    max_bytes=1048576,          # 1 MB
    # Kalibracja VMAF (model telefonu) na nagraniach produktów, spadek względem CRF 18:
    # CRF 22 traci najwyżej 0,5 pkt (niewidoczne), a plik jest o ok. 22% lżejszy niż przy CRF 20;
    # CRF 27,5 daje ten sam spadek (mediana ok. 1,7 pkt) co próg 27 w standardzie 250x250.
    crf_start=22.0,
    crf_max=27.5,
    suffix="_opis",
    preview="phone",
    preview_px=375,
    preview_title="PODGLĄD NA TELEFONIE (375 px)",
    preview_hint="W opisie wideo zajmuje całą szerokość ekranu telefonu. Na gęstych ekranach to realnie "
                 "ponad 600 px, dlatego plik ma 600x600.",
    usage="Gra w opisie produktu na pełną szerokość ekranu telefonu (ok. 375 px, realnie ponad 600 px "
          "na gęstych ekranach), ładuje się dopiero po przewinięciu.",
)

STANDARDS: dict[str, VideoStandard] = {s.key: s for s in (HOVER, DESCRIPTION)}
DEFAULT = HOVER


def get(key: str | None) -> VideoStandard:
    return STANDARDS.get(key or "", DEFAULT)


# Wspólne dla wszystkich standardów
OUT_FPS = 30
OUT_CODEC = "h264"
OUT_PROFILE = "High"
OUT_PIX_FMT = "yuv420p"

MIN_FRAGMENT_S = 1.0           # najkrótszy sensowny fragment

CRF_PRECISION = 0.5            # dokładność szukania CRF
MAX_PASSES = 7                 # górny limit prób kodowania
FILL_ENOUGH = 0.96             # plik zajmuje >= 96% limitu: dalsze szukanie nic nie da
PRESET = "veryslow"
TUNE = "film"                  # materiał z kamery/telefonu

LOOP_DIFF_WARN = 0.10          # średnia różnica 1. i ostatniej klatki (0..1), powyżej ostrzegamy
CROSSFADE_S = 0.5              # domyślna długość przenikania końca w początek
