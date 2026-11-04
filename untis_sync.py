import datetime
import os
import json
import requests

# Schuldaten festlegen
SERVER = "://webuntis.com"
SCHULE = "Mariannhiller-Gym"
USER = os.environ.get("UNTIS_USER")
PASSWORD = os.environ.get("UNTIS_PASSWORD")

if not USER or not PASSWORD:
    print("Fehler: Zugangsdaten nicht in den Secrets gefunden!")
    exit(1)

URL = f"https://{SERVER}/webuntis/jsonrpc.do?school={SCHULE}"

def json_rpc(method, params={}):
    payload = {"id": "1", "method": method, "params": params, "jsonrpc": "2.0"}
    res = requests.post(URL, json=payload)
    return res.json()

def parse_untis_date_time(u_date, u_time):
    # Formate: Date: YYYYMMDD, Time: hhmm oder hmm
    t_str = f"{u_time:04d}"
    d_str = str(u_date)
    dt = datetime.datetime.strptime(f"{d_str}{t_str}", "%Y%m%d%H%M")
    return dt.strftime("%Y%m%dT%H%M%S")

try:
    # 1. Login
    login_res = json_rpc("authenticate", {"user": USER, "password": PASSWORD, "client": "KalenderSync"})
    if "error" in login_res:
        print(f"Login fehlgeschlagen: {login_res['error']}")
        exit(1)
        
    session_id = login_res["result"]["sessionId"]
    headers = {"Cookie": f"JSESSIONID={session_id}"}
    
    # 2. Stundenplan abfragen (Nächste 30 Tage)
    heute = datetime.date.today()
    ende = heute + datetime.timedelta(days=30)
    
    # Datumsformat für API konvertieren (YYYYMMDD)
    start_int = int(heute.strftime("%Y%m%d"))
    end_int = int(ende.strftime("%Y%m%d"))
    
    # Eigene Element-ID holen (ID des Schülers/Benutzers)
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
        # Ausgefallene Stunden überspringen
        if "cellState" in s and s["cellState"] == "CANCEL":
            continue
            
        # Fächernamen zusammenbauen
        faecher = [f["longName"] for f in s.get("su", []) if "longName" in f]
        raeume = [r["name"] for r in s.get("ro", []) if "name" in r]
        lehrer = [t["longName"] for t in s.get("te", []) if "longName" in t]
        
        titel = faecher[0] if faecher else "Unterricht"
        ort = raeume[0] if raeume else "Kein Raum"
        beschreibung = f"Lehrer: {lehrer[0]}" if lehrer else ""
        
        start_ics = parse_untis_date_time(s["date"], s["startTime"])
        end_ics = parse_untis_date_time(s["date"], s["endTime"])
        
        # Event-Eintrag hinzufügen
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
    
    # In Datei schreiben
    with open("stundenplan.ics", "w", encoding="utf-8") as f:
        f.write("\n".join(ics_lines))
        
    print("Kalender-Datei erfolgreich und unabhängig generiert!")

except Exception as e:
    print(f"Fehler während der Ausführung: {e}")
    exit(1)
