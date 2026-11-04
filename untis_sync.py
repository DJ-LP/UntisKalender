import datetime
import os
from webuntis import Session
from ics import Calendar, Event

# Zugangsdaten aus den geheimen GitHub-Einstellungen laden
SERVER = 'http://mariannhiller-gym.webuntis.com'
SCHULE = 'mariannhiller-gym'
USER = os.environ.get('UNTIS_USER')
PASSWORD = os.environ.get('UNTIS_PASSWORD')

if not USER or not PASSWORD:
    print("Fehler: Zugangsdaten nicht in den Secrets gefunden!")
    exit(1)

# Verbindung aufbauen
s = Session(server=SERVER, username=USER, password=PASSWORD, school=SCHULE, useragent='KalenderSync')
s.login()

# Zeitraum festlegen: Heute bis in 30 Tagen
heute = datetime.date.today()
ende = heute + datetime.timedelta(days=30)
stundenplan = s.my_timetable(start=heute, end=ende)

cal = Calendar()

for stunde in stundenplan:
    # Nur reguläre oder verschobene Stunden (keine komplett ausgefallenen)
    if stunde.code == 'cancelled':
        continue
        
    fach = stunde.su.long_name if stunde.su else "Freistunde/Unbekannt"
    raum = stunde.ro.name if stunde.ro else "Kein Raum"
    lehrer = stunde.te.long_name if stunde.te else ""
    
    event = Event()
    event.name = fach
    event.location = raum
    event.begin = stunde.start
    event.end = stunde.end
    if lehrer:
        event.description = f"Lehrer: {lehrer}"
        
    cal.events.add(event)

# In Datei schreiben
with open('stundenplan.ics', 'w', encoding='utf-8') as f:
    f.writelines(cal.serialize_iter())

s.logout()
print("Kalender-Datei erfolgreich aktualisiert!")
