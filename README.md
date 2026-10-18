<p align="center">
  <img alt="AOWcloud Clipper" src="assets/icon.png" width="160">
</p>

<p align="center">
  <b>Z surowego nagrania produktu do gotowego wideo w kafelku sklepu.</b><br>
  Kwadrat 250x250, 30 fps, H.264, bez dźwięku, do 0,5 MB. Zawsze w standardzie, bez zgadywania.
</p>

<p align="center">
  <a href="https://github.com/vTomsonek/AOWcloud-Clipper/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/vTomsonek/AOWcloud-Clipper?color=ff7a18&label=pobierz"></a>
  <img alt="Windows 10/11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-1f1f1f">
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-1f1f1f">
  <img alt="PySide6" src="https://img.shields.io/badge/Qt-PySide6-1f1f1f">
  <a href="LICENSE"><img alt="Apache 2.0" src="https://img.shields.io/badge/licencja-Apache%202.0-1f1f1f"></a>
</p>

<p align="center">
  <img alt="Okno programu: kadr i fragment" src="docs/zrzut_kadr.png" width="900">
</p>

> **In English:** AOWcloud Clipper is a Windows desktop app that turns any product recording
> (mp4, mov, webm, portrait or landscape) into a short, silent, looping 250x250 MP4 for
> e-commerce product tiles: H.264 High, 30 fps, faststart, no rotation metadata, hard 512 KiB cap.
> You pick the square crop and the fragment, it finds the best x264 quality that fits the limit
> and verifies the result with ffprobe. UI in Polish.

## Spis treści

- [Pobierz i uruchom](#pobierz-i-uruchom)
- [Standard wyniku](#standard-wyniku)
- [Jak się tego używa](#jak-się-tego-używa)
- [Jak program dobiera jakość](#jak-program-dobiera-jakość)
- [Budowanie ze źródeł](#budowanie-ze-źródeł)
- [Testy](#testy)
- [Struktura projektu](#struktura-projektu)
- [Licencja](#licencja)

## Pobierz i uruchom

1. **Pobierz** [`AOWcloud-Clipper.exe`](https://github.com/vTomsonek/AOWcloud-Clipper/releases/latest/download/AOWcloud-Clipper.exe)
   z [Releases](https://github.com/vTomsonek/AOWcloud-Clipper/releases/latest). To jeden plik,
   bez instalacji i bez Pythona.
2. **Zainstaluj ffmpeg** (raz na komputerze). W PowerShell:
   ```
   winget install ffmpeg
   ```
   Potem zamknij okno PowerShell. Jeśli ffmpeg nie będzie dostępny, program sam to powie
   i poda to polecenie.
3. **Uruchom** dwuklikiem.

> [!NOTE]
> Plik nie ma podpisu cyfrowego, więc przy pierwszym uruchomieniu Windows może pokazać okno
> „System Windows ochronił ten komputer”. Kliknij **Więcej informacji**, a potem
> **Uruchom mimo to**. Niektóre antywirusy ostrzegają przed programami spakowanymi PyInstallerem:
> to fałszywy alarm, plik można dodać do wyjątków.

Program działa offline, pliki nie wychodzą poza komputer. Aktualizacja to podmiana pliku .exe.
Ustawienia (folder zapisu, rozmiar okna) zostają w profilu Windows każdego użytkownika.

## Standard wyniku

| Parametr | Wartość |
|---|---|
| Kontener | MP4, `-movflags +faststart` (atom `moov` przed `mdat`, start od razu po najechaniu) |
| Obraz | kwadrat **250x250 px**, 30 fps |
| Kodek | H.264, profil High, yuv420p |
| Dźwięk | brak ścieżki audio |
| Metadane | bez obrotu (panel czyta wymiary przez ffprobe), bez metadanych źródła |
| Waga | **najwyżej 524 288 B** (0,5 MB), twardy limit |

Każdy eksport jest na koniec sprawdzany ffprobe. Plik, który nie spełnia choćby jednego
warunku, **nie jest zapisywany** do folderu i nie wygląda na gotowy.

## Jak się tego używa

| Krok | Co robisz |
|---|---|
| **1. Wczytaj** | Przeciągnij nagranie na okno albo „Otwórz nagranie…”. Za małe nagrania (krótszy bok poniżej 250 px po obrocie z telefonu) są od razu odrzucane z komunikatem. |
| **2. Kadr** | Pomarańczowa ramka zawsze 1:1. Przeciągnij, żeby przesunąć, ciągnij za róg albo kręć kółkiem, żeby zmienić rozmiar. Obok podgląd kafelka 250x250 na żywo. |
| **3. Fragment** | Dwa uchwyty na osi czasu, odtwarzanie w pętli bez dźwięku, jak w sklepie. Pasek „≈ 0,37 / 0,50 MB” na bieżąco szacuje wagę. |
| **4. Eksport** | Kodowanie w tle z paskiem postępu i przyciskiem „Anuluj eksport”. |
| **5. Wynik** | Gotowy plik w kafelku, parametry i zielone „Spełnia standard sklepu” albo czerwona lista problemów. „Pokaż w folderze” otwiera Eksplorator. |

<p align="center">
  <img alt="Wynik eksportu z weryfikacją" src="docs/zrzut_wynik.png" width="900">
</p>

Gdy fragment jest za długi na 0,5 MB nawet przy najniższej dopuszczalnej jakości, program
nie koduje gorzej, tylko mówi, o ile skrócić. Przycisk **„Skróć automatycznie”** robi to sam.

<p align="center">
  <img alt="Za długi fragment: podpowiedź skrócenia" src="docs/zrzut_za_dlugi.png" width="900">
</p>

**Płynna pętla.** Program porównuje pierwszą i ostatnią klatkę fragmentu i ostrzega, gdy w pętli
będzie widać skok. Opcja **„Płynna pętla (przenikanie)”** przenika ostatnie 0,5 s w początek
fragmentu, więc przejście jest niewidoczne.

**Skróty klawiszowe**

| Klawisz | Działanie |
|---|---|
| `Spacja` | odtwarzaj / pauza (pętla fragmentu) |
| `I` / `O` | początek / koniec fragmentu w bieżącym miejscu |
| `←` / `→` | klatka wstecz / naprzód |
| `Ctrl+O` | otwórz nagranie |
| `Ctrl+E` | eksportuj |

## Jak program dobiera jakość

Zasada: **najlepsza jakość przy najmniejszej wadze, w twardym limicie 0,5 MB.**

```
trim (fragment) → crop (kadr) → scale=250:250:flags=lanczos → fps=30 → format=yuv420p
        │
        ▼  plik pośredni FFV1 (bezstratny, źródło dekodowane tylko raz)
        │
        ▼  libx264 -preset veryslow -tune film -crf N, jedna klatka kluczowa, faststart
```

1. Próba przy **CRF 20**. Jeśli plik mieści się w limicie, koniec: lepszej jakości w kafelku
   250 px nie widać, a mniejszy plik szybciej się ładuje.
2. Jeśli jest za duży, program szuka **najniższego CRF, który się mieści**: zgaduje z reguły
   „+6 CRF to mniej więcej połowa wagi”, a potem zawęża przedział interpolacją logarytmiczną.
   Zwykle 2 do 4 prób, każda trwa 1 do 3 s.
3. Powyżej **CRF 27** obraz 250x250 jest już za słaby. Wtedy program wraca do kroku „Fragment”
   z komunikatem, np. „Skróć fragment o ok. 27,0 s (do ok. 33,0 s)”, liczonym z bitrate
   przy CRF 27.

<details>
<summary><b>Przyjęte progi</b></summary>

| Próg | Wartość | Dlaczego |
|---|---|---|
| CRF startowy | 20 | wizualnie bezstratny dla tak małego obrazu |
| CRF progowy | 27 | powyżej w 250x250 widać rozmycie i bloki na krawędziach produktu |
| Dokładność CRF | 0,5 | różnica 0,5 CRF jest niewidoczna |
| Wystarczająco blisko | 96% limitu | dalsze szukanie nie da widocznej różnicy |
| Min. bok źródła | 250 px | kadr nigdy nie jest powiększany |
| Min. fragment | 1 s | krótsza pętla miga |
| Ostrzeżenie o skoku w pętli | różnica > 10% | płynne ujęcia dają 2 do 6% |
| Przenikanie | 0,5 s (maks. 1/4 fragmentu) | wystarcza, żeby ukryć skok |

Wszystkie liczby są w jednym pliku: [`clipper/standard.py`](clipper/standard.py).
</details>

<details>
<summary><b>Dlaczego takie ustawienia x264 (pomiary)</b></summary>

Pomiary na nagraniu testowym 10 s (kadr 1080x1080 → 250x250), SSIM względem bezstratnego
pliku pośredniego.

- **`-preset veryslow`**: przy 250x250 czas kodowania nie gra roli, a wolniejszy preset daje
  mniejszy plik przy tej samej jakości.
- **`-tune film`**: przy równej wadze (~303 KB) film i brak tune wychodzą praktycznie tak samo
  (SSIM 0,9628 i 0,9626), a film lepiej trzyma fakturę materiału z kamery. `-tune ssim` wypada
  lepiej w metrykach (0,9645) tylko dlatego, że wyłącza optymalizacje psychowizualne. Autorzy x264
  zalecają go wyłącznie do testów porównawczych, na ekranie daje „plastikowy” obraz.
- **Jedna klatka kluczowa na cały plik** (`-g` = liczba klatek, `-sc_threshold 0`, zamknięty GOP):
  pętla w `<video loop>` zawsze startuje od klatki 0. Plik o 2% mniejszy niż przy domyślnym GOP
  i o 12% mniejszy niż przy GOP 1 s, przy tej samej jakości.
- **Dwa przebiegi: odrzucone.** Przy danej wadze dają tę samą jakość co CRF, a przy klipach
  kilkunastosekundowych mocno chybiają: cel 303 KB dał plik **404 KB (+33%)**. CRF z doborem
  trafia w limit dokładnie.
</details>

<details>
<summary><b>Szacunek wagi na żywo, weryfikacja, pliki tymczasowe</b></summary>

**Szacunek.** Po wczytaniu i po każdej zmianie kadru program w tle koduje całe nagranie przy
CRF 20 i CRF 27 i zapamiętuje rozmiar każdej klatki. Waga dowolnego fragmentu to suma jego klatek
(plus klatka I na początku i nagłówki MP4), więc przesuwanie uchwytów aktualizuje pasek
natychmiast. W testach szacunek różnił się od wyniku o 0,4 do 3,5%.

**Weryfikacja.** ffprobe sprawdza kontener MP4, jedną ścieżkę wideo, 250x250, 30 fps
(`r_frame_rate` i `avg_frame_rate`), h264 High, yuv420p, brak audio i innych ścieżek,
wagę ≤ 524 288 B, brak metadanych obrotu (Display Matrix i tag `rotate`) i czas trwania.
Dodatkowo program czyta nagłówki atomów MP4 i sprawdza, czy `moov` jest przed `mdat`.

**Obrót z telefonu.** ffmpeg stosuje go przed filtrami, a gotowy plik nie ma metadanych obrotu.
Podgląd w oknie pokazuje obraz w tej samej orientacji co eksport.

**Pliki tymczasowe** powstają w `%TEMP%\aowclipper_xxxx`, są sprzątane po eksporcie i przy
zamknięciu programu. Pozostałości po awarii (starsze niż 6 h) znikają przy następnym starcie.
</details>

## Budowanie ze źródeł

Potrzebny Python 3.12 (tylko do budowania) i ffmpeg w PATH:

```
winget install Python.Python.3.12
winget install ffmpeg
```

Zbudowanie `dist\AOWcloud Clipper.exe` (jeden plik, ok. 55 MB, bez okna konsoli):

```
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Skrypt tworzy `.venv`, instaluje [`requirements.txt`](requirements.txt) (PySide6, PyInstaller,
Pillow), rysuje ikonę i uruchamia PyInstaller. Podgląd wideo korzysta z wbudowanego w Qt backendu
FFmpeg, więc obsługuje mp4, mov, webm, mkv i HEVC z telefonów bez dodatkowych kodeków Windows.

Uruchomienie bez budowania:

```
.venv\Scripts\python.exe main.py
```

## Testy

```
.venv\Scripts\python.exe -m tests.test_pipeline
```

Skrypt generuje ffmpeg nagrania testowe (`testsrc2` z drganiami jak z ręki, lekkim szumem
matrycy i dźwiękiem) i przepuszcza je przez całą logikę bez interfejsu. Ostatni raport:
[`tests/wyniki_testow.txt`](tests/wyniki_testow.txt).

| Nagranie | Wynik |
|---|---|
| pionowe 1080x1920, 10 s | CRF 20, 0,33 MB, spełnia standard |
| poziome 1920x1080 .mov, fragment 8 s z przenikaniem | CRF 20, 0,24 MB, 7,5 s, spełnia standard |
| z telefonu: 1920x1080 z obrotem 90° w metadanych | obraz 1080x1920, 0,39 MB, bez obrotu, spełnia standard |
| za małe 200x200 | odrzucone: „krótszy bok musi mieć co najmniej 250 px” |
| za długie 60 s, cały plik | wstrzymane: „skróć o ok. 27,0 s (do ok. 33,0 s)” |
| to samo, skrócone do 33 s | CRF 26,75, 0,49 MB, spełnia standard |
| to samo, fragment 20 s | CRF 22,25, 0,49 MB, spełnia standard |

[`tests/smoke_gui.py`](tests/smoke_gui.py) uruchamia okno, wczytuje nagranie, eksportuje i zapisuje
zrzuty ekranu (stąd obrazy w tym README). Nie zmienia ustawień użytkownika.

## Struktura projektu

```
main.py                    start, sprawdzenie ffmpeg
clipper/standard.py        standard sklepu i wszystkie progi
clipper/core.py            ffprobe, filtry, dobór CRF, szacunek, weryfikacja (bez Qt)
clipper/ui/main_window.py  okno i przepływ pracy
clipper/ui/widgets.py      kadrowanie, kafelek, oś czasu, pasek wagi, kroki
clipper/ui/workers.py      wątki: analiza, sprawdzenie pętli, eksport
clipper/ui/theme.py        wygląd (styl rodziny AOWcloud)
clipper/ui/icon.py         logo rysowane w kodzie
build.ps1                  budowanie .exe
tools/                     generowanie ikony .ico
tests/                     generator nagrań, test logiki, test okna
```

## Licencja

Kod: [Apache License 2.0](LICENSE). Plik .exe zawiera komponenty zewnętrzne na własnych
licencjach (m.in. Qt/PySide6 i biblioteki FFmpeg na LGPL), szczegóły w [NOTICE](NOTICE).
Do kodowania program używa ffmpeg zainstalowanego osobno przez użytkownika.
