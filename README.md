# RailTech AI v0.2 – iPhone Streamlit Demo

## Update im bestehenden GitHub-Repository

1. `app.py` durch die neue Datei ersetzen.
2. `requirements.txt` durch die neue Datei ersetzen (enthält `streamlit`, `pypdf`, `python-docx`, `openai`).
3. Beide Änderungen auf Branch `main` mit **Commit changes** speichern.
4. Die bestehende Streamlit-App öffnen. Sie aktualisiert sich normalerweise automatisch; sonst **Manage app → Reboot app**.

## Echte KI aktivieren

1. Einen **separaten OpenAI API-Schlüssel** im OpenAI-API-Konto erstellen. Die API-Nutzung wird separat von ChatGPT abgerechnet.
2. In `share.streamlit.io` die bestehende App verwalten → **Settings → Secrets**.
3. Folgendes eintragen (Platzhalter ersetzen):

```toml
OPENAI_API_KEY = "DEIN_API_SCHLUESSEL"
```

4. Speichern und App neu starten. **API-Schlüssel nie in GitHub, Chat, Screenshots oder hochgeladene Dokumente kopieren.**

## Funktionsumfang

- Fahrzeugauswahl
- PDF/DOCX/TXT-Upload (max. 8 MB/Datei, 80 PDF-Seiten)
- einfache lokale Stichwortsuche mit Quellenhinweisen
- optionale echte KI-Antwort mit OpenAI Responses API
- Störungserfassung mit JSON-Export
- künstliche Demo-Dokumente

## Grenzen und Sicherheit

- **Öffentliche Test-App ohne Benutzeranmeldung**. Keine vertraulichen Firmenunterlagen, personenbezogenen Daten oder echten Wartungsprotokolle hochladen.
- **Keine dauerhafte Speicherung**: Dokumente und Störungen bleiben nur im Sitzungsspeicher und gehen bei Neustart/Abbruch verloren. Für dauerhafte Datenhaltung ist eine geschützte Datenbank nötig.
- Stichwortsuche ist keine semantische Vektorsuche. Scans benötigen OCR; DOCX hat keine verlässlichen Original-Seitenzahlen.
- Antworten sind keine Arbeits-, Bremsprüf- oder Sicherheitsfreigaben.
- Die KI-Anfragen übertragen Frage und passende Textauszüge an den API-Anbieter.
- `gpt-4.1-mini` kann im Code gegen ein anderes für das API-Konto freigeschaltetes Modell ausgetauscht werden.
