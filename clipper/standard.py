"""Standard wideo sklepu i progi kodowania. Jedno miejsce na wszystkie liczby."""

# Standard panelu sklepu
OUT_SIZE = 250                 # kwadrat 250x250 px
OUT_FPS = 30
MAX_BYTES = 524288             # 0,5 MB, twardy limit
OUT_CODEC = "h264"
OUT_PROFILE = "High"
OUT_PIX_FMT = "yuv420p"

# Wejście
MIN_SOURCE_SIDE = 250          # krótszy bok źródła (po obrocie) w px
MIN_CROP = OUT_SIZE            # kadr nie mniejszy niż 250x250 px źródła
MIN_FRAGMENT_S = 1.0           # najkrótszy sensowny fragment

# Dobór jakości
CRF_START = 20.0               # pierwsza próba: wysoka jakość
CRF_MAX = 27.0                 # próg: powyżej obraz 250x250 jest już za słaby
CRF_PRECISION = 0.5            # dokładność szukania CRF
MAX_PASSES = 7                 # górny limit prób kodowania
FILL_ENOUGH = 0.96             # plik zajmuje >= 96% limitu: dalsze szukanie nic nie da
PRESET = "veryslow"
TUNE = "film"                  # materiał z kamery/telefonu

# Pętla
LOOP_DIFF_WARN = 0.10          # średnia różnica 1. i ostatniej klatki (0..1), powyżej ostrzegamy
CROSSFADE_S = 0.5              # domyślna długość przenikania końca w początek
