# Redpoint

**Zaznacz tekst gdziekolwiek, naciśnij jeden skrót i czytaj słowo po słowie.**

Redpoint to mały program działający w tle do szybkiego czytania (RSVP). Słowa pokazują się
pojedynczo w tym samym miejscu na czarnym ekranie. Jedna litera każdego słowa, lekko na lewo
od środka (*optymalny punkt rozpoznania*), jest czerwona i nigdy się nie przesuwa, więc oczy
nie skaczą po linii.

![Redpoint w trakcie czytania](docs/images/reader.png)

- Działa w każdym programie: przeglądarka, PDF, poczta, komunikator, edytor.
- Jeden skrót globalny, domyślnie **Ctrl+Alt+Spacja** (na macOS Ctrl+Option+R), do zmiany w ustawieniach.
- Inteligentne tempo: dłuższe słowa, liczby, przecinki, końce zdań i akapitów dostają więcej czasu,
  a pierwsze słowa są wolniejsze na rozbieg.
- Sterowanie klawiaturą i myszą, ikona w zasobniku, start przy logowaniu, interfejs po polsku i angielsku.
- Nic nie wychodzi z komputera: bez sieci, kont i telemetrii.

## Pobieranie

Plik dla swojego systemu weź z [najnowszego wydania](https://github.com/DawidKrynski/redpoint-reader/releases/latest):

| System | Plik | Jak uruchomić |
|---|---|---|
| Windows 10/11 (x64) | `Redpoint-…-windows-x64.exe` | Dwuklik. SmartScreen może ostrzec o nieznanym wydawcy: **Więcej informacji → Uruchom mimo to**. |
| Linux (x86_64) | `Redpoint-…-x86_64.AppImage` | `chmod +x Redpoint-*.AppImage` i uruchom. Bez instalacji. |
| macOS (Apple silicon) | `Redpoint-…-macos-arm64.zip` | Rozpakuj, przenieś do Aplikacji, za pierwszym razem prawy klik → **Otwórz** (aplikacja nie jest notaryzowana). |

Przy pierwszym uruchomieniu krótkie okno ustawień wyjaśnia skrót. Potem Redpoint działa w tle;
ustawienia otworzysz z ikony w zasobniku albo uruchamiając program ponownie.

## Obsługa

Zaznacz tekst, naciśnij skrót, czytaj. Spacja/klik - pauza (z czasem do końca), ↑/↓ lub kółko - tempo
(zapamiętywane), ←/→ - zdanie, Shift+←/→ - słowo, Home - od początku, Esc/prawy klik/ponowny skrót - zamknij.
Bez zaznaczenia czyta schowek, więc *kopiuj + skrót* działa zawsze.

Szczegóły techniczne, testy i budowanie: [README po angielsku](README.md).

## Licencja

GPL-3.0-or-later.
