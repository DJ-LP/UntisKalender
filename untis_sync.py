import datetime
import os
import json
import requests
from zoneinfo import ZoneInfo

# Zugangsdaten aus den Secrets laden
SERVER = os.environ.get("UNTIS_SERVER", "")
SCHULE = os.environ.get("UNTIS_Schule", "")
USER = os.environ.get("UNTIS_USER", "")
PASSWORD = os.environ.get("UNTIS_PASSWORD", "")

if not USER or not PASSWORD or not SERVER or not SCHULE:
    print("Fehler: Mindestens eines der Secrets fehlt!")
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
    
    print("Login erfolgreich! Rufe Stammdaten zur Übersetzung ab...")
    
    # 2. Stammdaten abrufen, um IDs in echte Namen zu übersetzen
    subjects_data = json_rpc(URL, "getSubjects", {}, session_id=session_id).get("result", [])
    rooms_data = json_rpc(URL, "getRooms", {}, session_id=session_id).get("result", [])
    teachers_data = json_rpc(URL, "getTeachers", {}, session_id=session_id).get("result", [])
    
    # ID-Mappings erstellen (Wichtig, da getTimetable nur IDs liefert)
    sub_map = {s["id"]: s.get("longName", s.get("name", "Unterricht")) for s in subjects_data}
    room_map = {r["id"]: r.get("name", "Kein Raum") for r in rooms_data}
    tea_map = {t["id"]: t.get("longName", t.get("name", "")) for t in teachers_data}
    
    # 3. Stundenplan abfragen (Nächste 30 Tage)
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
    print(f"{len(stunden)} Stunden empfangen. Verarbeite Kalender...")
    
    # 4. iCalendar (.ics) erstellen
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UntisKalenderSync//DE",
        "X-WR-CALNAME:Untis Stundenplan",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H"
    ]
    
    def to_utc_ics_string(u_date, u_time):
        t_str = f"{u_time:04d}"
        d_str = str(u_date)
        dt_local = datetime.datetime.strptime(f"{d_str}{t_str}", "%Y%m%d%H%M")
        dt_local = dt_local.replace(tzinfo=ZoneInfo("Europe/Berlin"))
        dt_utc = dt_local.astimezone(ZoneInfo("UTC"))
        return dt_utc.strftime("%Y%m%dT%H%M%SZ")
    
    for s in stunden:
        if s.get("cellState") == "CANCEL":
            continue
            
        # IDs über unsere Mappings in echten Text übersetzen
        faecher = [sub_map.get(f["id"], "Unterricht") for f in s.get("su", []) if "id" in f]
        raeume = [room_map.get(r["id"], "Kein Raum") for r in s.get("ro", []) if "id" in r]
        lehrer = [tea_map.get(t["id"], "") for t in s.get("te", []) if "id" in t]
        
        titel = ", ".join(faecher) if faecher else "Unterricht"
        ort = ", ".join(raeume) if raeume else "Kein Raum"
        
        lehrer_liste = [l for l in lehrer if l]
        beschreibung = f"Lehrer: {', '.join(lehrer_liste)}" if lehrer_liste else ""
        
        if s.get("cellState") == "SUBST":
            titel = f"Vertretung: {titel}"
        
        start_ics = to_utc_ics_string(s["date"], s["startTime"])
        end_ics = to_utc_ics_string(s["date"], s["endTime"])
        
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
        
    print("Universelle Kalender-Datei erfolgreich aktualisiert!")
    
    try:
        json_rpc(URL, "logout", session_id=session_id)
    except Exception:
        pass

except Exception as e:
    print(f"Fehler während der Verarbeitung: {e}")
    exit(1)
