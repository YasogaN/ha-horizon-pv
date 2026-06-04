#!/usr/bin/env python3
"""
SunnyPortal CSV Scraper - Manual Mode
Exportiert tägliche Energiebilanz-Daten fuer den Bereich aus config/settings.py.

Die Datumsauswahl muss über den echten Datepicker laufen. Ein direktes Setzen
des Input-Values reicht nicht, weil SunnyPortal den Chart-Zustand clientseitig
für den Download hält.
"""

from playwright.sync_api import sync_playwright
import os
import sys
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    DATA_DIR as CONFIG_DATA_DIR,
    ENERGY_BALANCE_DIR as CONFIG_ENERGY_BALANCE_DIR,
    END_DATE,
    START_DATE,
    SUNNYPORTAL_EMAIL,
    SUNNYPORTAL_LOGIN_URL,
    SUNNYPORTAL_PASSWORD,
)

EMAIL = SUNNYPORTAL_EMAIL
PASSWORD = SUNNYPORTAL_PASSWORD
LOGIN_URL = SUNNYPORTAL_LOGIN_URL

BASE_DATA_DIR = str(CONFIG_DATA_DIR)
DATA_DIR = str(CONFIG_ENERGY_BALANCE_DIR)
LOG_FILE_HANDLE = None
ORIGINAL_STDOUT = sys.stdout
ORIGINAL_STDERR = sys.stderr

COOKIE_CONSENT_TIMEOUT_SECONDS = 15
CHART_RESPONSE_TIMEOUT_MS = 120000
CHART_LOADING_TIMEOUT_MS = 120000
DATEPICKER_TIMEOUT_MS = 30000
LOAD_SETTLE_MS = 5000
AFTER_CHART_LOADED_SETTLE_MS = 5000
BETWEEN_DAYS_SETTLE_MS = 2000
LOGIN_SETTLE_MS = 5000
NAVIGATION_SETTLE_MS = 5000
RETRY_SETTLE_MS = 10000
MAX_EXPORT_ATTEMPTS = 3
CHART_ERROR_TEXT = "The diagram could not be completely created"
TMP_DOWNLOAD_DIR_NAME = ".tmp_downloads"
REJECTED_DOWNLOAD_DIR_NAME = "rejected_downloads"
MIN_EXPECTED_CSV_ROWS = 80
MAX_EXPECTED_CSV_ROWS = 110
SESSION_CHECK_TIMEOUT_MS = 5000


class TeeStream:
    """Schreibt Terminalausgaben gleichzeitig in eine Logdatei."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()


def setup_run_log():
    """Erstellt pro Skriptlauf eine Logdatei und legt den CSV-Ordner an."""
    global LOG_FILE_HANDLE

    run_started_at = datetime.now()
    os.makedirs(DATA_DIR, exist_ok=True)
    log_dir = os.path.join(BASE_DATA_DIR, "export_logs")
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, f"export_{run_started_at.strftime('%Y_%m_%d_%H_%M_%S')}.log")
    LOG_FILE_HANDLE = open(log_path, "a", encoding="utf-8")
    sys.stdout = TeeStream(ORIGINAL_STDOUT, LOG_FILE_HANDLE)
    sys.stderr = TeeStream(ORIGINAL_STDERR, LOG_FILE_HANDLE)

    print(f"Energy-Balance-Ordner: {DATA_DIR}")
    print(f"Logdatei: {log_path}")
    return log_path


def close_run_log():
    """Schließt die Logdatei und stellt stdout/stderr wieder her."""
    global LOG_FILE_HANDLE

    sys.stdout = ORIGINAL_STDOUT
    sys.stderr = ORIGINAL_STDERR
    if LOG_FILE_HANDLE:
        LOG_FILE_HANDLE.close()
        LOG_FILE_HANDLE = None


def expected_download_filename(date):
    """Original-Dateiname, den SunnyPortal für das Tages-CSV liefern sollte."""
    return f"Energy_Balance_{date.strftime('%Y_%m_%d')}.csv"


def iter_dates(start_date, end_date):
    """Iteriert tageweise inklusive Start- und Enddatum."""
    current_date = start_date
    while current_date <= end_date:
        yield current_date
        current_date += timedelta(days=1)


def energy_csv_paths():
    """Liefert nur finale Tages-CSVs aus dem Energy-Balance-Ordner."""
    return [
        path
        for path in Path(DATA_DIR).glob("Energy_Balance_*.csv")
        if path.is_file()
    ]


def file_sha256(path):
    """Berechnet den SHA256-Hash einer Datei."""
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quarantine_file(path, reason):
    """Verschiebt auffällige Dateien, damit der Tag neu geladen werden kann."""
    if not os.path.exists(path):
        return

    quarantine_dir = os.path.join(DATA_DIR, REJECTED_DOWNLOAD_DIR_NAME)
    os.makedirs(quarantine_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    safe_reason = "".join(ch if ch.isalnum() else "_" for ch in reason)[:60]
    target = os.path.join(quarantine_dir, f"{timestamp}_{safe_reason}_{os.path.basename(path)}")
    os.replace(path, target)
    print(f"  Auffällige Datei verschoben: {target}")


def validate_energy_csv_file(path, expected_filename):
    """Prüft eine SunnyPortal-CSV, bevor sie als finale Datei behalten wird."""
    actual_filename = os.path.basename(path)
    if actual_filename != expected_filename:
        return False, f"Dateiname passt nicht: {actual_filename} != {expected_filename}"

    if not os.path.exists(path):
        return False, "Datei fehlt"

    size = os.path.getsize(path)
    if size == 0:
        return False, "Datei ist leer"

    with open(path, "rb") as file:
        raw = file.read()

    head = raw[:300].decode("utf-8", errors="ignore").lower()
    if "<html" in head or "<!doctype" in head:
        return False, "Datei sieht wie HTML statt CSV aus"

    text = raw.decode("utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < MIN_EXPECTED_CSV_ROWS + 1:
        return False, f"Zu wenige CSV-Zeilen: {len(lines) - 1}"
    if len(lines) > MAX_EXPECTED_CSV_ROWS + 1:
        return False, f"Ungewöhnlich viele CSV-Zeilen: {len(lines) - 1}"

    header = lines[0]
    if "PV power generation" not in header or "Total consumption" not in header:
        return False, "CSV-Header sieht nicht nach Energy Balance aus"

    first_data_row = lines[1].split(";")
    if len(first_data_row) < 9:
        return False, "CSV-Datenzeile hat zu wenige Spalten"

    current_hash = hashlib.sha256(raw).hexdigest()
    for existing_path in energy_csv_paths():
        if existing_path.name == expected_filename:
            continue
        if file_sha256(existing_path) == current_hash:
            return False, f"Doppelter Inhalt wie {existing_path.name}"

    return True, "OK"


def preflight_validate_existing_downloads(start_date, end_date):
    """Entfernt auffällige vorhandene Dateien vor dem Browserlauf."""
    print("\nPreflight-Prüfung vorhandener CSV-Dateien...")
    checked = 0
    quarantined = 0

    for date in iter_dates(start_date, end_date):
        filename = expected_download_filename(date)
        filepath = os.path.join(DATA_DIR, filename)
        if not os.path.exists(filepath):
            continue

        checked += 1
        is_valid, validation_message = validate_energy_csv_file(filepath, filename)
        if is_valid:
            print(f"  OK: {filename}")
            continue

        print(f"  AUFFÄLLIG: {filename}: {validation_message}")
        quarantine_file(filepath, validation_message)
        quarantined += 1

    print(f"Preflight fertig: {checked} geprüft, {quarantined} quarantänisiert.")


def close_cookie_consent(page):
    """Schließt den Cookie-Consent-Banner."""
    print("Prüfe Cookie-Consent...")
    selectors = [
        'button:has-text("Accept all")',
        '[role="button"]:has-text("Accept all")',
        'text=Accept all',
        'button:has-text("Accept")',
        'text=Accept',
        'button:has-text("Alle akzeptieren")',
        'text=Alle akzeptieren',
        'button:has-text("Zustimmen")',
        'text=Zustimmen',
        'button#cmpboxbtnyes'
    ]

    deadline = time.monotonic() + COOKIE_CONSENT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        for frame in page.frames:
            for selector in selectors:
                try:
                    btn = frame.locator(selector).first
                    if btn.count() > 0 and btn.is_visible(timeout=1000):
                        print(f"Cookie-Consent gefunden: {selector}")
                        btn.click(force=True)
                        page.wait_for_timeout(LOAD_SETTLE_MS)
                        hide_cookie_overlay(page)
                        print("Cookie-Consent akzeptiert.")
                        return True
                except:
                    pass
        page.wait_for_timeout(500)

    hide_cookie_overlay(page)
    print("Kein Cookie-Button gefunden - Overlay wird ausgeblendet.")
    return False


def hide_cookie_overlay(page):
    """Entfernt blockierende Consent-Overlays, falls der Button nicht sauber greift."""
    page.evaluate("""
        const styleId = 'codex-hide-cookie-overlay';
        if (!document.getElementById(styleId)) {
            const style = document.createElement('style');
            style.id = styleId;
            style.textContent = `
                #cmpwrapper, .cmpwrapper, #cmpbox, [id*="cmp"] {
                    display: none !important;
                    pointer-events: none !important;
                    visibility: hidden !important;
                }
            `;
            document.head.appendChild(style);
        }
        document
            .querySelectorAll('#cmpwrapper, .cmpwrapper, #cmpbox, [id*="cmp"]')
            .forEach(el => {
                el.style.display = 'none';
                el.style.pointerEvents = 'none';
                el.style.visibility = 'hidden';
            });
    """)


def hide_general_message(page):
    """Versteckt das GeneralMessageDiv Overlay."""
    page.evaluate("""
        const div = document.getElementById('GeneralMessageDiv');
        if (div) {
            div.style.display = 'none';
        }
    """)


def hide_blocking_overlays(page):
    """Versteckt Overlays, die Klicks auf Datepicker/Download abfangen."""
    hide_general_message(page)
    hide_cookie_overlay(page)


def wait_for_chart_loaded(page):
    """Wartet, bis SunnyPortal keine sichtbare Chart-Ladeanzeige mehr zeigt."""
    page.wait_for_function(
        """
        () => {
            const isVisible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && style.opacity !== '0'
                    && rect.width > 0
                    && rect.height > 0;
            };

            return ![...document.querySelectorAll('body *')].some(el => {
                if (!isVisible(el)) return false;
                const marker = [
                    el.id,
                    el.className,
                    el.getAttribute('src'),
                    el.getAttribute('alt'),
                    el.getAttribute('title'),
                    el.innerText
                ].join(' ');
                return /(^|\\s)Loading(\\s|$)|ChartLoadingImage|loading/i.test(marker);
            });
        }
        """,
        timeout=CHART_LOADING_TIMEOUT_MS,
    )
    page.wait_for_timeout(AFTER_CHART_LOADED_SETTLE_MS)


def chart_has_error(page):
    """Erkennt SunnyPortal-Chartfehler, bei denen kein valider Download erfolgen soll."""
    try:
        body_text = page.locator("body").inner_text(timeout=DATEPICKER_TIMEOUT_MS)
        return CHART_ERROR_TEXT in body_text
    except:
        return True


def validate_chart_for_download(page):
    """Stellt sicher, dass der Chart fertig und nicht im Fehlerzustand ist."""
    print("Warte, bis der Chart vollständig geladen ist...")
    wait_for_chart_loaded(page)
    if chart_has_error(page):
        raise RuntimeError(CHART_ERROR_TEXT)
    print("Chart ist geladen und ohne sichtbaren Fehler.")


def is_logged_in(page):
    """Prüft ohne lange Wartezeit, ob SunnyPortal noch eine aktive Session hat."""
    try:
        return page.locator('span[id*="lblUserName"]').count() > 0
    except:
        return False


def is_login_screen(page):
    """Erkennt SunnyPortal/SMA-ID Login-Ansichten nach Session-Timeout."""
    try:
        return (
            page.locator('a[id*="SmaIdLoginButton"]').count() > 0
            or page.locator('input#username').count() > 0
            or page.locator('input#password').count() > 0
        )
    except:
        return False


def login(page):
    """Meldet sich mit den Anmeldedaten an."""
    if not EMAIL or not PASSWORD:
        raise RuntimeError(
            "SunnyPortal-Zugangsdaten fehlen. Bitte SUNNYPORTAL_EMAIL und "
            "SUNNYPORTAL_PASSWORD in .env setzen."
        )

    print("Navigiere zur Login-Seite...")
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(LOAD_SETTLE_MS)

    close_cookie_consent(page)

    if page.locator('span[id*="lblUserName"]').count() > 0:
        username = page.locator('span[id*="lblUserName"]').inner_text()
        print(f"Already logged in as: {username}")
        return True

    if page.locator('input#username').count() == 0:
        print("Klicke auf SMA ID Login Button...")
        login_button = page.locator('a[id*="SmaIdLoginButton"]').first
        if login_button.count() == 0:
            print("SMA ID Login Button nicht gefunden.")
            return False
        login_button.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(LOAD_SETTLE_MS)

    close_cookie_consent(page)

    email_field = page.locator('input#username')
    if email_field.count() > 0:
        email_field.fill(EMAIL)
        print("Email eingegeben.")
    else:
        print("Email-Feld nicht gefunden.")
        return False

    password_field = page.locator('input#password')
    if password_field.count() > 0:
        password_field.fill(PASSWORD)
        password_field.press("Enter")
    else:
        print("Passwort-Feld nicht gefunden.")
        return False

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(LOGIN_SETTLE_MS)

    # Prüfe ob Login erfolgreich
    if page.locator('span[id*="lblUserName"]').count() > 0:
        username = page.locator('span[id*="lblUserName"]').inner_text()
        print(f"Login erfolgreich als: {username}")
        return True

    print("Login fehlgeschlagen!")
    return False


def ensure_logged_in(page):
    """Stellt sicher, dass die Browser-Session eingeloggt ist."""
    page.wait_for_timeout(SESSION_CHECK_TIMEOUT_MS)
    close_cookie_consent(page)
    hide_blocking_overlays(page)

    if is_logged_in(page):
        return True

    if is_login_screen(page):
        print("Session ist abgelaufen oder Login-Seite sichtbar - melde erneut an...")
    else:
        print("Keine aktive Session erkannt - melde erneut an...")

    return login(page)


def navigate_to_energy_balance(page):
    """Navigiert zur Energy-Balance Seite."""
    hide_blocking_overlays(page)
    page.wait_for_timeout(LOAD_SETTLE_MS)

    energy_link = page.locator('a[id*="NavigationLeftMenuControl_0_3"]')
    if energy_link.count() > 0:
        energy_link.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(NAVIGATION_SETTLE_MS)
        return True

    return False


def select_day_in_datepicker(page, date):
    """Wählt ein Tagesdatum über den echten jQuery-UI-Datepicker aus."""
    print(f"Öffne Datepicker für {date.strftime('%d.%m.%Y')}...")
    date_input = page.locator('input[id*="ChartDatePicker_PC_DatePickerFrom"]').first
    date_input.wait_for(state="visible", timeout=DATEPICKER_TIMEOUT_MS)
    expected_anchor_time = int(datetime(date.year, date.month, date.day, tzinfo=timezone.utc).timestamp())

    hide_blocking_overlays(page)
    date_input.scroll_into_view_if_needed()
    date_input.click(force=True)
    page.wait_for_selector("#ui-datepicker-div", state="visible", timeout=DATEPICKER_TIMEOUT_MS)
    hide_blocking_overlays(page)
    page.wait_for_timeout(LOAD_SETTLE_MS)

    page.locator("#ui-datepicker-div select.ui-datepicker-year").select_option(str(date.year))
    page.locator("#ui-datepicker-div select.ui-datepicker-month").select_option(str(date.month - 1))
    print("Datum wird im Kalender ausgewählt; warte auf Chart- und Legenden-Requests...")
    with page.expect_response(
        lambda response: (
            "PortalChartsAPI.aspx" in response.url
            and "id=mainChart" in response.url
            and "xf=" in response.url
            and "xt=" in response.url
        ),
        timeout=CHART_RESPONSE_TIMEOUT_MS,
    ):
        with page.expect_response(
            lambda response: (
                "GetLegendWithValues" in response.url
                and f'"anchorTime":{expected_anchor_time}' in (response.request.post_data or "")
            ),
            timeout=CHART_RESPONSE_TIMEOUT_MS,
        ):
            page.locator(
                f'#ui-datepicker-div td:not(.ui-datepicker-other-month) a:text-is("{date.day}")'
            ).click()
    print("SunnyPortal hat Chart- und Legenden-Daten für das Datum geliefert.")

    expected = date.strftime("%m/%d/%Y")
    page.wait_for_function(
        """([selector, expected]) => {
            const el = document.querySelector(selector);
            return el && el.value === expected;
        }""",
        arg=['input[id*="ChartDatePicker_PC_DatePickerFrom"]', expected],
        timeout=DATEPICKER_TIMEOUT_MS,
    )
    validate_chart_for_download(page)
    return expected


def open_energy_balance_page(page):
    """Öffnet Energy Balance und loggt bei Session-Timeout automatisch neu ein."""
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(LOAD_SETTLE_MS)

    if not ensure_logged_in(page):
        raise RuntimeError("Re-Login fehlgeschlagen")

    close_cookie_consent(page)
    hide_blocking_overlays(page)

    if not navigate_to_energy_balance(page):
        if not ensure_logged_in(page):
            raise RuntimeError("Re-Login fehlgeschlagen")
        if not navigate_to_energy_balance(page):
            raise RuntimeError("Energy-Balance Navigation nicht gefunden")

    date_input = page.locator('input[id*="ChartDatePicker_PC_DatePickerFrom"]').first
    try:
        date_input.wait_for(state="visible", timeout=DATEPICKER_TIMEOUT_MS)
    except Exception:
        if is_login_screen(page) or not is_logged_in(page):
            print("Session lief während der Navigation ab - erneuter Login...")
            if not login(page):
                raise RuntimeError("Re-Login fehlgeschlagen")
            if not navigate_to_energy_balance(page):
                raise RuntimeError("Energy-Balance Navigation nach Re-Login nicht gefunden")
            date_input.wait_for(state="visible", timeout=DATEPICKER_TIMEOUT_MS)
        else:
            raise


def export_day(page, date) -> bool:
    """
    Exportiert die Daten für einen bestimmten Tag.
    Gibt True zurück wenn erfolgreich, False sonst.

    Wählt das Datum über den echten Datepicker aus, damit SunnyPortal den
    Chart-Zustand vor dem Download aktualisiert.
    """
    import re
    from urllib.parse import urljoin

    date_str = date.strftime("%m/%d/%Y")
    expected_filename = expected_download_filename(date)
    expected_filepath = os.path.join(DATA_DIR, expected_filename)

    # Prüfe ob die Original-Datei für dieses Datum bereits existiert.
    if os.path.exists(expected_filepath):
        is_valid, validation_message = validate_energy_csv_file(expected_filepath, expected_filename)
        if is_valid:
            print(f"  Datei existiert bereits und ist plausibel - überspringe: {expected_filepath}")
            return True

        print(f"  Vorhandene Datei ist auffällig: {validation_message}")
        quarantine_file(expected_filepath, validation_message)

    for attempt in range(1, MAX_EXPORT_ATTEMPTS + 1):
        try:
            print(f"  Versuch {attempt}/{MAX_EXPORT_ATTEMPTS}")
            open_energy_balance_page(page)

            # Echte Kalenderauswahl statt Value-Manipulation: nur so wird der
            # SunnyPortal-Chart-Zustand für den Download aktualisiert.
            current_value = select_day_in_datepicker(page, date)
            print(f"  Datums-Wert: {current_value}")
            validate_chart_for_download(page)

            # Hole den Download Button per JavaScript und klicke ihn
            download_button = page.locator('input[id*="ChartMenu_DownloadButton_ImageButton"]')
            if download_button.count() == 0:
                raise RuntimeError("Download-Button nicht gefunden")

            btn = download_button.first
            onclick_code = btn.get_attribute('onclick')
            if not onclick_code or 'window.location' not in onclick_code:
                raise RuntimeError("Download-Button hat keine erwartete Download-URL")

            match = re.search(r"window\.location\s*=\s*'([^']+)", onclick_code)
            if not match:
                raise RuntimeError("Download-URL konnte nicht aus onclick gelesen werden")

            relative_url = match.group(1)
            full_url = urljoin(page.url, relative_url)

            print(f"  Download URL: {full_url}")

            # Direkt vor dem Download nochmal prüfen, damit Fehlerzustände wie
            # "The diagram could not be completely created" nicht gespeichert werden.
            validate_chart_for_download(page)

            # Klicke den Button per JavaScript (auch wenn visible=False)
            with page.expect_download(timeout=CHART_RESPONSE_TIMEOUT_MS) as download_info:
                btn.evaluate("el => el.click()")

            download = download_info.value
            downloaded_filename = download.suggested_filename
            filepath = os.path.join(DATA_DIR, downloaded_filename)
            tmp_dir = os.path.join(DATA_DIR, TMP_DOWNLOAD_DIR_NAME)
            os.makedirs(tmp_dir, exist_ok=True)
            tmp_filepath = os.path.join(
                tmp_dir,
                f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}_{downloaded_filename}",
            )
            print(f"  Download filename: {downloaded_filename}")

            if downloaded_filename != expected_filename:
                print(f"  WARNUNG: Erwartet war {expected_filename}, Portal liefert {downloaded_filename}")

            if os.path.exists(filepath):
                is_valid, validation_message = validate_energy_csv_file(filepath, expected_filename)
                if is_valid:
                    print(f"  Datei existiert bereits und ist plausibel - nicht überschrieben: {filepath}")
                    return downloaded_filename == expected_filename
                print(f"  Bestehende Zieldatei ist auffällig: {validation_message}")
                quarantine_file(filepath, validation_message)

            os.makedirs(DATA_DIR, exist_ok=True)
            download.save_as(tmp_filepath)
            print(f"  Download temporär gespeichert: {tmp_filepath}")

            validation_tmp_path = os.path.join(tmp_dir, downloaded_filename)
            os.replace(tmp_filepath, validation_tmp_path)
            is_valid, validation_message = validate_energy_csv_file(validation_tmp_path, expected_filename)
            if not is_valid:
                print(f"  Download verworfen: {validation_message}")
                quarantine_file(validation_tmp_path, validation_message)
                raise RuntimeError(f"Download-Validierung fehlgeschlagen: {validation_message}")

            os.replace(validation_tmp_path, filepath)
            print(f"  Datei gespeichert: {filepath}")
            return True

        except Exception as e:
            print(f"  -> Fehler beim Export von {date_str} (Versuch {attempt}): {e}")
            if attempt < MAX_EXPORT_ATTEMPTS:
                print("  Seite wird neu geladen, Session geprüft und der Tag wird erneut versucht...")
                page.wait_for_timeout(RETRY_SETTLE_MS)
                try:
                    page.reload(wait_until="networkidle", timeout=CHART_RESPONSE_TIMEOUT_MS)
                    if not ensure_logged_in(page):
                        print("  Re-Login nach Reload fehlgeschlagen.")
                except Exception as reload_error:
                    print(f"  Reload-Fehler ignoriert: {reload_error}")
                page.wait_for_timeout(RETRY_SETTLE_MS)

    return False


def summarize_downloads(start_date, end_date):
    """Prüft nach dem Lauf, ob alle erwarteten CSVs eindeutig vorhanden sind."""
    expected_dates = list(iter_dates(start_date, end_date))
    records = []
    missing = []
    empty = []
    unreadable = []

    for date in expected_dates:
        filename = expected_download_filename(date)
        filepath = os.path.join(DATA_DIR, filename)

        if not os.path.exists(filepath):
            missing.append(filename)
            continue

        try:
            with open(filepath, "rb") as file:
                content = file.read()
        except OSError as exc:
            unreadable.append((filename, str(exc)))
            continue

        digest = hashlib.sha256(content).hexdigest()
        size = len(content)
        if size == 0:
            empty.append(filename)

        records.append({
            "date": date,
            "filename": filename,
            "size": size,
            "sha256": digest,
        })

    by_hash = {}
    for record in records:
        by_hash.setdefault(record["sha256"], []).append(record)

    duplicates = [
        same_hash_records
        for same_hash_records in by_hash.values()
        if len(same_hash_records) > 1
    ]

    print("\n" + "=" * 60)
    print("Download-Prüfung")
    print(f"Erwartete Tage: {len(expected_dates)}")
    print(f"Gefundene passende Dateien: {len(records)}")
    print(f"Fehlende Dateien: {len(missing)}")
    print(f"Leere Dateien: {len(empty)}")
    print(f"Unlesbare Dateien: {len(unreadable)}")
    print(f"Unterschiedliche Inhalte (SHA256): {len(by_hash)}")
    print(f"Doppelte Inhalte: {len(duplicates)}")

    if records:
        print("\nGefundene Dateien:")
        for record in records:
            print(
                f"  {record['filename']}  "
                f"{record['size']} bytes  "
                f"{record['sha256'][:16]}"
            )

    if missing:
        print("\nFEHLT:")
        for filename in missing[:20]:
            print(f"  {filename}")
        if len(missing) > 20:
            print(f"  ... weitere {len(missing) - 20}")

    if unreadable:
        print("\nUNLESBAR:")
        for filename, error in unreadable[:20]:
            print(f"  {filename}: {error}")
        if len(unreadable) > 20:
            print(f"  ... weitere {len(unreadable) - 20}")

    if empty:
        print("\nLEER:")
        for filename in empty[:20]:
            print(f"  {filename}")
        if len(empty) > 20:
            print(f"  ... weitere {len(empty) - 20}")

    if duplicates:
        print("\nDUPLIKATE INHALTE:")
        for same_hash_records in duplicates[:20]:
            names = ", ".join(record["filename"] for record in same_hash_records)
            print(f"  {same_hash_records[0]['sha256'][:16]}: {names}")
        if len(duplicates) > 20:
            print(f"  ... weitere {len(duplicates) - 20}")

    is_ok = not missing and not empty and not unreadable and not duplicates
    print("\nPlausibilitätsstatus: " + ("OK" if is_ok else "AUFFÄLLIG"))
    print("=" * 60)
    return is_ok


def export_range(start_date, end_date):
    """Exportiert alle Tage im Bereich"""
    setup_run_log()

    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                accept_downloads=True,
            )
            page = context.new_page()

            print(f"Login...")
            if not login(page):
                print("\nLogin fehlgeschlagen - beende Script")
                return

            preflight_validate_existing_downloads(start_date, end_date)

            print("\nLogin erfolgreich. Starte automatisierten Export...")

            total_days = (end_date - start_date).days + 1
            successful = 0
            failed = 0

            for current_date in iter_dates(start_date, end_date):
                date_str = current_date.strftime("%d.%m.%Y")
                print(f"\n=== Verarbeite {date_str} ({successful + failed + 1}/{total_days}) ===")

                if export_day(page, current_date):
                    successful += 1
                else:
                    failed += 1

                # Status ausgeben alle 50 Tage
                if (successful + failed) % 50 == 0:
                    print(f"\n--- Fortschritt: {successful + failed}/{total_days} ({successful} erfolgreich, {failed} fehlgeschlagen) ---\n")

                page.wait_for_timeout(BETWEEN_DAYS_SETTLE_MS)

            print("\n" + "=" * 60)
            print("Export abgeschlossen!")
            print(f"Erfolgreich: {successful}")
            print(f"Fehlgeschlagen: {failed}")
            print("=" * 60)

            summarize_downloads(start_date, end_date)

            try:
                from ml.build_dataset import build_dataset
                from config.settings import (
                    ML_DATASET_OUTPUT,
                    WEATHER_FORECAST_OUTPUT,
                    WEATHER_SECONDARY_FORECAST_OUTPUT,
                )

                print("\nErstelle ML-Datensatz aus PV- und Forecast-Daten...")
                build_dataset(
                    Path(DATA_DIR),
                    WEATHER_FORECAST_OUTPUT,
                    WEATHER_SECONDARY_FORECAST_OUTPUT,
                    ML_DATASET_OUTPUT,
                    start_date,
                    end_date,
                )
            except Exception as exc:
                print(f"\nML-Datensatz konnte nicht erstellt werden: {exc}")

        finally:
            if browser:
                browser.close()
            close_run_log()


if __name__ == "__main__":
    start = START_DATE
    end = END_DATE

    print(f"Exportiere Daten von {start.strftime('%d.%m.%Y')} bis {end.strftime('%d.%m.%Y')}")
    export_range(start, end)
