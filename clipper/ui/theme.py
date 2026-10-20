"""Wygląd jak w AOWcloud Reelmaker (wersja ciemna): #141414 i gradient #FF7A18 → #FFC21A."""
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Paleta z Reelmakera (THEMES["dark"])
BG = "#121212"
PANEL = "#1b1b1b"          # surface
PANEL_2 = "#202020"        # surface2
RAISED = "#262626"
BORDER = "#2c2c2c"
BORDER_STRONG = "#3a3a3a"
TEXT = "#ececec"
MUTED = "#9a9a9a"
DISABLED = "#5f5f5f"
ACCENT = "#ff7a18"
ACCENT2 = "#ffc21a"
ACCENT_HOVER = ACCENT2
ACCENT_TEXT = "#141414"
ACCENT_SOFT = "#3a2414"
SELECT = "#4a2c14"
HEADER = "#0c0c0c"
HEADER_TEXT = "#f5f5f5"
HEADER_MUTED = "#8f8f8f"
CHIP = "#1f1f1f"
SCROLL = "#3a3a3a"
OK = "#3fb950"
WARN = "#e3b341"
BAD = "#ff6b5b"
BAD_SOFT = "#3a1d1a"

RES = (Path(__file__).resolve().parent / "res").as_posix()

QSS = f"""
QWidget {{ font-family: "Segoe UI"; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QStackedWidget, QStackedWidget > QWidget, QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#root {{ background: {BG}; }}
QToolTip {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; padding: 6px;
           border-radius: 6px; }}

/* nagłówek */
QWidget#header {{ background: {HEADER}; }}
QWidget#header QLabel {{ color: {HEADER_TEXT}; background: transparent; }}
QLabel#appName {{ font-size: 15pt; font-weight: 700; }}
QWidget#header QLabel#appVersion {{ color: {HEADER_MUTED}; font-size: 9pt; padding-top: 6px; }}
QLabel#chip {{ background: {CHIP}; color: {HEADER_TEXT}; border: 1px solid #2e4a33; border-radius: 11px;
              padding: 3px 10px; font-size: 9pt; }}

/* przełącznik standardu */
QPushButton#segL, QPushButton#segM, QPushButton#segR {{ background: {CHIP}; color: {HEADER_MUTED};
    border: 1px solid #333333; padding: 5px 12px; font-weight: 600; font-size: 9pt; border-radius: 0; }}
QPushButton#segL {{ border-top-left-radius: 11px; border-bottom-left-radius: 11px; }}
QPushButton#segR {{ border-top-right-radius: 11px; border-bottom-right-radius: 11px; border-left: none; }}
QPushButton#segM {{ border-left: none; }}
QPushButton#segL:hover, QPushButton#segM:hover, QPushButton#segR:hover {{ color: {HEADER_TEXT}; }}
QPushButton#segL:checked, QPushButton#segM:checked, QPushButton#segR:checked {{ color: {ACCENT_TEXT};
    border-color: {ACCENT};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT2}); }}
QPushButton#segL:disabled, QPushButton#segM:disabled, QPushButton#segR:disabled {{ color: {DISABLED}; }}

/* tabela trybu poprawiania */
QTableWidget, QTableView {{ background: {PANEL}; alternate-background-color: {PANEL_2}; border: 1px solid {BORDER};
                           border-radius: 8px; gridline-color: transparent; outline: 0; }}
QTableWidget::item {{ padding: 6px 8px; border: none; }}
QHeaderView {{ background: {PANEL}; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
                       padding: 8px 8px; font-weight: 700; font-size: 9pt; text-align: left; }}

/* kroki jak główne zakładki Reelmakera */
QWidget#stepsBar {{ background: {HEADER}; border-bottom: 1px solid {BORDER}; }}
QWidget#stepsBar QLabel#step {{ color: {HEADER_MUTED}; padding: 10px 18px 9px 18px; border: none;
                               border-bottom: 3px solid transparent; font-weight: 600; font-size: 10.5pt; }}
QWidget#stepsBar QLabel#step[done="true"] {{ color: #c8c8c8; }}
QWidget#stepsBar QLabel#step[active="true"] {{ color: {HEADER_TEXT}; border-bottom: 3px solid {ACCENT}; }}

/* karty */
QGroupBox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; margin-top: 16px;
            padding: 18px 14px 12px 14px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 12px; top: 2px;
                   padding: 0 6px; color: {TEXT}; font-size: 10.5pt; }}
QLabel {{ background: transparent; font-weight: 400; }}
QLabel#h1 {{ font-size: 15pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#section {{ color: {MUTED}; font-weight: 700; font-size: 9pt; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#small, QLabel#hint {{ color: {MUTED}; font-size: 9pt; }}

/* przyciski */
QPushButton {{ background: {RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
              padding: 7px 14px; font-weight: 500; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {DISABLED}; background: {PANEL_2}; border-color: {BORDER}; }}
QPushButton#primary {{ color: {ACCENT_TEXT}; border: none; font-weight: 700; padding: 9px 18px;
                      background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT2}); }}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT2}, stop:1 {ACCENT}); }}
QPushButton#primary:disabled {{ background: {ACCENT_SOFT}; color: {DISABLED}; }}
QPushButton#danger {{ color: {BAD}; background: transparent; border: 1px solid {BORDER_STRONG}; }}
QPushButton#danger:hover {{ background: {BAD_SOFT}; border-color: {BAD}; }}
QPushButton#danger:disabled {{ color: {DISABLED}; border-color: {BORDER}; }}

/* pola */
QLineEdit {{ background: {PANEL_2}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 6px 9px;
            selection-background-color: {ACCENT}; selection-color: {ACCENT_TEXT}; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled {{ color: {DISABLED}; }}

/* pola wyboru */
QCheckBox {{ spacing: 8px; background: transparent; font-weight: 400; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER_STRONG}; border-radius: 5px;
                       background: {PANEL_2}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url({RES}/check.svg); }}
QCheckBox::indicator:disabled {{ background: {PANEL_2}; border-color: {BORDER}; }}

/* postęp, przewijanie, pasek stanu */
QProgressBar {{ background: {RAISED}; border: none; border-radius: 4px; height: 8px; max-height: 8px;
               text-align: center; color: transparent; }}
QProgressBar::chunk {{ border-radius: 4px;
                      background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT2}); }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SCROLL}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SCROLL}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none;
    width: 0; height: 0; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {MUTED}; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER_STRONG}; padding: 4px; }}
QMenu::item:selected {{ background: {SELECT}; color: #ffffff; }}
QMessageBox {{ background: {PANEL}; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in [
        (QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, PANEL_2),
        (QPalette.AlternateBase, PANEL), (QPalette.Text, TEXT), (QPalette.Button, RAISED),
        (QPalette.ButtonText, TEXT), (QPalette.Highlight, ACCENT),
        (QPalette.HighlightedText, ACCENT_TEXT), (QPalette.ToolTipBase, PANEL),
        (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, "#6b6b6b"),
    ]:
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
