import streamlit as st
import re

st.set_page_config(page_title='RailTech AI – Demo', page_icon='🚆', layout='centered')
st.title('🚆 RailTech AI')
st.caption('iPhone-Demo · Nur fiktive Beispieldaten · Keine Firmenunterlagen hochladen')

DATA = {
 'BCM61': [
  ('BMA – Ausgangsstörung', 'DEMO-BCM61-001', 'Rev. Demo', 2, 'Eine BMA-Ausgangsstörung kann bei der Demo auf einen unterbrochenen Ausgangskreis hinweisen. Dies ist ein fiktives Beispiel und keine Prüfanweisung.'),
  ('Bremse – Druckanzeige', 'DEMO-BCM61-002', 'Rev. Demo', 5, 'Die Demo zeigt beispielhaft eine Beschreibung von Hauptluftleitung und Bremszylinderdruck. Keine Sollwerte oder Freigaben ableiten.')],
 'Bvcmz 248.5': [('Türsteuerung – Störmeldung', 'DEMO-BVCMZ-001', 'Rev. Demo', 3, 'Eine Türstörung wird in diesem erfundenen Beispiel als Meldung der Türsteuerung dokumentiert. Für echte Diagnosen sind freigegebene Unterlagen nötig.')],
 'WLABmz': [('Klimaanlage – Fehlersuche', 'DEMO-WLABMZ-001', 'Rev. Demo', 4, 'Fiktiver Beispieltext zur Klimaanlagen-Störmeldung. Der genaue Fehler muss anhand gültiger Fahrzeugdokumentation ermittelt werden.')]
}
vehicle = st.selectbox('Fahrzeug auswählen', list(DATA))
tab1, tab2 = st.tabs(['Fragen & Suchen', 'Dokumentenübersicht'])
with tab1:
 question = st.text_input('Deine technische Frage', placeholder='z. B. Was bedeutet BMA-Ausgangsstörung?')
 if st.button('Dokumente durchsuchen', type='primary'):
  if not question.strip(): st.warning('Bitte eine Frage eingeben.')
  else:
   words = [w.lower() for w in re.findall(r'\w+', question) if len(w)>2]
   ranked = sorted(DATA[vehicle], key=lambda d: sum(w in (d[0]+' '+d[4]).lower() for w in words), reverse=True)
   found = [d for d in ranked if any(w in (d[0]+' '+d[4]).lower() for w in words)]
   if not found: st.info('Keine passende Textstelle in den Beispieldaten gefunden.')
   for title, doc, rev, page, body in found:
    st.subheader(title)
    st.write(body)
    st.caption(f'Quelle: {doc} · {rev} · Seite {page} (fiktiv)')
with tab2:
 for title, doc, rev, page, body in DATA[vehicle]:
  with st.expander(title):
   st.write(body)
   st.caption(f'{doc} · {rev} · Seite {page} (fiktiv)')
st.divider()
st.info('Diese Demo hat absichtlich keine Benutzerkonten, Uploads oder echte KI-Anbindung. Für den öffentlichen Test sind nur fest eingebaute, erfundene Texte enthalten.')
