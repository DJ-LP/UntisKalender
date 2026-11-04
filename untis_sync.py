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

URL = f"https://{clean_server}/WebUntis/jsonrpc.do?school={SCHULE}"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "KalenderSync"
}

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
    return res.json()

try:
    # 1. Login
    login_res = json_rpc(URL, "authenticate", {"user": USER, "password": PASSWORD, "client": "KalenderSync"})
    if "error" in login_res:
        print(f"Login fehlgeschlagen: {login_res['error']['message']}")
        exit(1)
        
    session_id = login_res["result"]["sessionId"]
    elem_id = login_res["result"].get("personId", 0)
    elem_type = login_res["result"].get("personType", 5)
    
    # 2. Stundenplan abfragen (Nächste 30 Tage)
    heute = datetime.date.today()
    ende = heute + datetime.timedelta(days=30)
    
    start_int = int(heute.strftime("%Y%m%d"))
    end_int = int(ende.strftime("%Y%m%d"))
    
    timetable_res = json_rpc(URL, "getTimetable", {
        "options": {
            "startDate": start_int,
            "endDate": end_int,
            "element": {"id": elem_id, "type": elem_type}
        }
    }, session_id=session_id)
    
    stunden = timetable_res.get("result", [])
    print(f"{len(stunden)} Stunden empfangen.")
    
    # 3. iCalendar (.ics) erstellen
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UntisKalenderSync//DE",
        "X-WR-CALNAME:Untis Stundenplan",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H"
    ]
    
    def parse_untis_date_time(u_date, u_time):
        t_str = f"{u_time:04d}"
        d_str = str(u_date)
        dt = datetime.datetime.strptime(f"{d_str}{t_str}", "%Y%m%d%H%M")
        # Umwandlung in UTC für reibungslosen Import ohne Zeitzonensprung (-1 Stunde im Winter)
        dt_utc = dt - datetime.timedelta(hours=1)
        return dt_utc.strftime("%Y%m%dT%H%M%SZ")
    
    for s in stunden:
        if s.get("cellState") == "CANCEL":
            continue
            
        # Namen sauber als Text extrahieren statt als Liste
        faecher = [f.get("longName", f.get("name", "")) for f in s.get("su", [])]
        raeume = [r.get("name", "") for r in s.get("ro", [])]
        lehrer = [t.get("longName", t.get("name", "")) for t in s.get("te", [])]
        
        titel = faecher[0] if faecher else "Unterricht"
        ort = raeume[0] if raeume else "Kein Raum"
        beschreibung = f"Lehrer: {lehrer[0]}" if lehrer else ""
        
        # Falls eine Vertretung stattfindet, fügen wir einen Hinweis hinzu
        if s.get("cellState") == "SUBST":
            titel = f"Vertretung: {titel}"
        
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
        
    print("Kalender-Datei erfolgreich aktualisiert!")
    
    # Logout
    try:
        json_rpc(URL, "logout", session_id=session_id)
    except Exception:
        pass

except Exception as e:
    print(f"Fehler während der Verarbeitung: {e}")
    exit(1)
