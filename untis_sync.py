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

# FEHLERSCHUTZ: Bereinigt den Server-String von allen Protokollen und Schrägstrichen
clean_server = SERVER.strip()
for prefix in ["https://", "http://"]:
    if clean_server.lower().startswith(prefix):
        clean_server = clean_server[len(prefix):]
clean_server = clean_server.split("/")[0] # Nimmt nur den reinen Hostnamen

# Finale URL zusammensetzen
URL = f"https://{clean_server}/webuntis/jsonrpc.do?school={SCHULE}"
print(f"Verbindung wird aufgebaut zu: https://{clean_server}...")

def json_rpc(method, params={}):
    payload = {"id": "1", "method": method, "params": params, "jsonrpc": "2.0"}
    res = requests.post(URL, json=payload)
    return res.json()

def parse_untis_date_time(u_date, u_time):
    t_str = f"{u_time:04d}"
    d_str = str(u_date)
    dt = datetime.datetime.strptime(f"{d_str}{t_str}", "%Y%m%d%H%M")
    return dt.strftime("%Y%m%dT%H%M%S")

try:
    # 1. Login
    login_res = json_rpc("authenticate", {"user": USER, "password": PASSWORD, "client": "KalenderSync"})
    if "error" in login_res:
        print(f"Login bei WebUntis fehlgeschlagen: {login_res['error']}")
        exit(1)
        
    session_id = login_res["result"]["sessionId"]
    
    # 2. Stundenplan abfragen (Nächste 30 Tage)
    heute = datetime.date.today()
    ende = heute + datetime.timedelta(days=30)
    
    start_int = int(heute.strftime("%Y%m%d"))
    end_int = int(ende.strftime("%Y%m%d"))
    
    elem_id = login_res["result"].get("personId", 0)
    elem_type = login_res["result"].get("personType", 5) # 5 = Schueler
    
    timetable_res = json_rpc("getTimetable", {
        "options": {
            "startDate": start_int,
            "endDate": end_int,
            "element": {"id": elem_id, "type": elem_type}
        }
    })
    
    stunden = timetable_res.get("result", [])
    
    # 3. iCalendar (.ics) manuell erstellen
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UntisKalenderSync//DE",
        "X-WR-CALNAME:Untis Stundenplan",
        "X-WR-TIMEZONE:Europe/Berlin"
    ]
    
    for s in stunden:
        if "cellState" in s and s["cellState"] == "CANCEL":
            continue
            
        faecher = [f["longName"] for f in s.get("su", []) if "longName" in f]
        raeume = [r["name"] for r in s.get("ro", []) if "name" in r]
        lehrer = [t["longName"] for t in s.get("te", []) if "longName" in t]
        
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
        
    print("Kalender-Datei erfolgreich generiert!")

except Exception as e:
    print(f"Fehler während der Ausführung: {e}")
    exit(1)
