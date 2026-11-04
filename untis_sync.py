import datetime
import os
import json
import requests

# Zugangsdaten aus den Secrets laden
SERVER = os.environ.get("UNTIS_SERVER", "")
SCHULE = os.environ.get("UNTIS_Schule", "")
USER = os.environ.get("UNTIS_USER", "")
PASSWORD = os.environ.get("UNTIS_PASSWORD", "")

if not USER or not PASSWORD or not SERVER or not SCHULE:
    print("Fehler: Mindestens eines der Secrets (USER, PASSWORD, SERVER, Schule) fehlt!")
    exit(1)

# Bereinigung des Servernamens
clean_server = SERVER.strip()
for prefix in ["https://", "http://"]:
    if clean_server.lower().startswith(prefix):
        clean_server = clean_server[len(prefix):]
clean_server = clean_server.split("/")[0]

# WebUntis benötigt zwingend diese Header
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "KalenderSync"
}

# Liste möglicher API-Pfade bei WebUntis
PFADE_ZUM_TESTEN = [
    f"https://{clean_server}/jsonrpc.do?school={SCHULE}",
    f"https://{clean_server}/WebUntis/jsonrpc.do?school={SCHULE}",
    f"https://{clean_server}/webuntis/jsonrpc.do?school={SCHULE}"
]

def json_rpc(url, method, params={}, session_id=None):
    payload = {
        "id": "1",
        "method": method,
        "params": params,
        "jsonrpc": "2.0"
    }
    current_headers = HEADERS.copy()
    if session_id:
        current_headers["Cookie"] = f"JSESSIONID={session_id}"
        
    res = requests.post(url, json=payload, headers=current_headers, timeout=10)
    return res

# 1. API-Endpunkt automatisch ermitteln via Login-Versuch
aktuelle_url = None
session_id = None
login_daten = None

print("Suche nach dem korrekten WebUntis API-Pfad...")
for test_url in PFADE_ZUM_TESTEN:
    try:
        print(f"Teste Pfad: {test_url}")
        antwort = json_rpc(test_url, "authenticate", {"user": USER, "password": PASSWORD, "client": "KalenderSync"})
        
        # Wenn der Server valides JSON antwortet, haben wir den Pfad!
        daten = antwort.json()
        if "result" in daten:
            aktuelle_url = test_url
            session_id = daten["result"]["sessionId"]
            login_daten = daten["result"]
            print(f"-> Erfolg! Korrekter API-Pfad gefunden: {aktuelle_url}")
            break
        elif "error" in daten:
            print(f"-> Pfad korrekt, aber Untis-Fehler: {daten['error']['message']}")
            aktuelle_url = test_url
            exit(1)
    except Exception:
        # Falls es kein JSON war (HTML-Rückgabe) oder Verbindung fehlschlug, teste nächsten Pfad
        continue

if not aktuelle_url or not session_id:
    print("SCHWERWIEGENDER FEHLER: Es konnte kein gültiger API-Endpunkt gefunden werden. Bitte Zugangsdaten prüfen.")
    exit(1)

try:
    # 2. Stundenplan abfragen (Nächste 30 Tage)
    heute = datetime.date.today()
    ende = heute + datetime.timedelta(days=30)
    
    start_int = int(heute.strftime("%Y%m%d"))
    end_int = int(ende.strftime("%Y%m%d"))
    
    elem_id = login_daten.get("personId", 0)
    elem_type = login_daten.get("personType", 5) # 5 = Schüler
    
    timetable_res = json_rpc(aktuelle_url, "getTimetable", {
        "options": {
            "startDate": start_int,
            "endDate": end_int,
            "element": {"id": elem_id, "type": elem_type}
        }
    }, session_id=session_id).json()
    
    stunden = timetable_res.get("result", [])
    print(f"{len(stunden)} Stundenplandaten erfolgreich empfangen.")
    
    # 3. iCalendar (.ics) manuell erstellen
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UntisKalenderSync//DE",
        "X-WR-CALNAME:Untis Stundenplan",
        "X-WR-TIMEZONE:Europe/Berlin"
    ]
    
    def parse_untis_date_time(u_date, u_time):
        t_str = f"{u_time:04d}"
        d_str = str(u_date)
        dt = datetime.datetime.strptime(f"{d_str}{t_str}", "%Y%m%d%H%M")
        return dt.strftime("%Y%m%dT%H%M%S")
    
    for s in stunden:
        if "cellState" in s and s["cellState"] == "CANCEL":
            continue
            
        faecher = [f.get("longName", f.get("name", "")) for f in s.get("su", [])]
        raeume = [r.get("name", "") for r in s.get("ro", [])]
        lehrer = [t.get("longName", t.get("name", "")) for t in s.get("te", [])]
        
        titel = faecher[0] if faecher else "Unterricht"
        ort = raeume[0] if raeume else "Kein Raum"
        beschreibung = f"Lehrer: {lehrer[0]}" if lehrer else ""
        
        start_ics = parse_untis_date_time(s["date"], s["startTime"])
        end_ics = parse_untis_date_time(s["date"], s["endTime"])
        
        ics_lines.extend([
            "BEGIN:VEVENT",
            f"SUMMARY:{titel}",
            f"LOCATION:{ort}",
            f"DESCRIPTION:{beschreibung}",
            f"DTSTART:{start_ics}",
            f"DTEND:{end_ics}",
            f"UID:{s['id']}@webuntis",
            "END:VEVENT"
        ])
        
    ics_lines.append("END:VCALENDAR")
    
    with open("stundenplan.ics", "w", encoding="utf-8") as f:
        f.write("\n".join(ics_lines))
        
    print("Kalender-Datei (.ics) erfolgreich generiert!")

    # Logout
    try:
        json_rpc(aktuelle_url, "logout", session_id=session_id)
    except Exception:
        pass

except Exception as e:
    print(f"Fehler während der Verarbeitung: {e}")
    exit(1)
