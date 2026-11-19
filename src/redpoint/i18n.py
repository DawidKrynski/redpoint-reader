"""Tiny translation table: English source strings, Polish translations."""

from __future__ import annotations

import locale
import os

PL = {
    "No selected text": "Brak zaznaczonego tekstu",
    "paused": "pauza",
    "words/min": "słów/min",
    "left": "zostało",
    "keys_help": "spacja wznów · ←/→ zdanie · shift+←/→ słowo · ↑/↓ tempo · Esc zamknij",
    "Read selection": "Czytaj zaznaczenie",
    "Read clipboard": "Czytaj schowek",
    "Settings…": "Ustawienia…",
    "Quit": "Zakończ",
    "Redpoint settings": "Ustawienia Redpoint",
    "welcome": (
        "Redpoint działa w tle. Zaznacz tekst w dowolnym programie i naciśnij skrót - "
        "tekst pojawi się słowo po słowie, z czerwoną literą zawsze w tym samym miejscu."
    ),
    "Shortcut": "Skrót",
    "Change…": "Zmień…",
    "Press the new shortcut… (Esc cancels)": "Naciśnij nowy skrót… (Esc anuluje)",
    "Speed": "Tempo",
    "Font size": "Rozmiar liter",
    "Start at login": "Uruchamiaj przy logowaniu",
    "Language": "Język",
    "Automatic": "Automatycznie",
    "Try it": "Wypróbuj",
    "Close": "Zamknij",
    "Quit Redpoint": "Zakończ Redpoint",
    "shortcut_ok": "Skrót działa w całym systemie.",
    "shortcut_taken": "Ten skrót jest zajęty przez inny program. Wybierz inny.",
    "shortcut_portal": ("Skrót zarejestrowany przez system (portal). Zmienisz go w ustawieniach skrótów pulpitu."),
    "shortcut_manual": (
        "Ten pulpit nie pozwala programom rejestrować skrótów. Dodaj własny skrót w ustawieniach "
        "systemu, który uruchamia polecenie:"
    ),
    "shortcut_mac_access": (
        "macOS: zezwól na Redpoint w Ustawienia systemowe → Prywatność i ochrona → Dostępność, "
        "żeby czytać zaznaczony tekst."
    ),
    "Copy command": "Kopiuj polecenie",
    "sample": (
        "To jest Redpoint. Czytasz jedno słowo naraz, a czerwona litera stoi zawsze w tym samym "
        "miejscu, więc oczy nie muszą skakać po linii. Strzałkami w górę i w dół zmieniasz tempo, "
        "spacją robisz pauzę. Zaznacz dowolny tekst i naciśnij skrót, żeby przeczytać go tak samo."
    ),
}

EN = {
    "keys_help": "space resume · ←/→ sentence · shift+←/→ word · ↑/↓ speed · Esc close",
    "welcome": (
        "Redpoint runs in the background. Select text in any app and press the shortcut - "
        "the text is shown word by word with the red letter always in the same spot."
    ),
    "shortcut_ok": "The shortcut works system-wide.",
    "shortcut_taken": "Another program already uses this shortcut. Pick a different one.",
    "shortcut_portal": (
        "Shortcut registered through the desktop portal. Change it in your desktop's shortcut settings."
    ),
    "shortcut_manual": (
        "This desktop does not let apps register shortcuts. Add a custom shortcut in your system settings that runs:"
    ),
    "shortcut_mac_access": (
        "macOS: allow Redpoint in System Settings → Privacy & Security → Accessibility to read selected text."
    ),
    "sample": (
        "This is Redpoint. You read one word at a time, and the red letter always stays in the same "
        "place, so your eyes do not have to jump along the line. Use the up and down arrows to change "
        "the speed and space to pause. Select any text and press the shortcut to read it the same way."
    ),
}

_lang = "en"


def detect_language() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = os.environ.get(var)
        if v:
            return "pl" if v.lower().startswith("pl") else "en"
    try:
        loc = locale.getlocale()[0] or ""
    except ValueError:
        loc = ""
    if not loc:
        try:
            from PyQt6.QtCore import QLocale

            loc = QLocale.system().name()
        except ImportError:
            pass
    return "pl" if loc.lower().startswith("pl") else "en"


def set_language(setting: str) -> None:
    global _lang
    _lang = detect_language() if setting == "auto" else setting


def tr(s: str) -> str:
    if _lang == "pl":
        return PL.get(s, s)
    return EN.get(s, s)
