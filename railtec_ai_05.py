"""RailTecSol 0.5 – source-grounded assistant module.

Requires Streamlit, requests and openai; the host app provides an authenticated
Supabase request helper and a document listing function.
"""
import re
import streamlit as st

STOPWORDS = set('der die das den dem des ein eine einer einem und oder ist sind mit für von zur zum auf bei aus als nach über unter wie was wer wo warum welche welcher welches kann können soll sollte wird werden ich du wir im in am an zu es nicht auch diese dieser diesem einer noch'.split())


def _tokens(text):
    return {w for w in re.findall(r'[a-zäöüß0-9]{3,}', text.casefold()) if w not in STOPWORDS}


def _rank(question, chunks, docs, vehicle):
    terms = _tokens(question)
    docmap = {str(d['id']): d for d in docs}
    scored = []
    for c in chunks:
        doc = docmap.get(str(c.get('document_id')))
        if not doc:
            continue
        content = str(c.get('content') or '')
        lower = content.casefold()
        found = _tokens(content) & terms
        score = len(found) * 4 + sum(min(lower.count(t), 3) for t in found)
        if vehicle and vehicle != 'Alle Fahrzeuge':
            if vehicle.casefold() in str(doc.get('vehicle', '')).casefold():
                score += 4
            else:
                continue
        if score:
            scored.append((score, c, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:6]


def render_ai_assistant(authorized_request, documents):
    st.subheader('Technischer KI-Assistent')
    st.caption('Antworten mit Fundstellen aus deiner privaten Dokumentenbibliothek.')
    if 'railtec_ai_history' not in st.session_state:
        st.session_state.railtec_ai_history = []
    try:
        docs = documents()
    except Exception:
        st.error('Die Dokumentenliste ist derzeit nicht erreichbar.')
        return
    vehicles = sorted({str(d.get('vehicle') or 'Allgemein') for d in docs})
    vehicle = st.selectbox('Fahrzeugfilter', ['Alle Fahrzeuge'] + vehicles)
    use_ai = st.toggle('KI-Antwort erstellen (Textauszüge an OpenAI senden)', value=False)
    if st.button('Chatverlauf löschen'):
        st.session_state.railtec_ai_history = []
        st.rerun()
    for m in st.session_state.railtec_ai_history:
        with st.chat_message(m['role']):
            st.markdown(m['text'])
    question = st.chat_input('Frage zu Bremse, Türen, Klima, Elektrik …')
    if not question:
        return
    st.session_state.railtec_ai_history.append({'role': 'user', 'text': question})
    with st.chat_message('user'):
        st.write(question)
    with st.chat_message('assistant'):
        try:
            result = authorized_request('GET', '/rest/v1/rail_chunks?select=document_id,page_number,content')
            hits = _rank(question, result.json(), docs, vehicle)
            if not hits:
                answer = 'In den verfügbaren Manuals habe ich keine passende Fundstelle gefunden. Bitte Fahrzeugfilter oder Fragestellung prüfen.'
            else:
                sources = []
                for i, (_, chunk, doc) in enumerate(hits, 1):
                    name = str(doc.get('filename', 'Unbekanntes Dokument'))
                    page = chunk.get('page_number', '?')
                    sources.append(f'[{i}] {name} | Seite/Abschnitt {page}\n{chunk.get("content", "")}')
                if use_ai:
                    key = st.secrets.get('OPENAI_API_KEY', '')
                    if not key:
                        answer = 'OPENAI_API_KEY fehlt in den Streamlit-Secrets. Hier sind die passenden Fundstellen.'
                    else:
                        from openai import OpenAI
                        client = OpenAI(api_key=key, timeout=35.0, max_retries=1)
                        history = st.session_state.railtec_ai_history[-7:]
                        context = '\n'.join(f"{m['role']}: {m['text']}" for m in history)
                        response = client.responses.create(
                            model='gpt-4.1-mini',
                            instructions=('Du bist ein Assistent für die Instandhaltung von Schienenfahrzeugen. '
                                          'Beantworte technische Fragen ausschließlich anhand der bereitgestellten Quellen. '
                                          'Zitiere jede konkrete Aussage mit [Nummer] und nenne die Seite. '
                                          'Wenn etwas nicht belegt ist, sage es deutlich. '
                                          'Keine erfundenen Sollwerte, Freigaben oder sicherheitskritischen Arbeitsschritte. '
                                          'Bei sicherheitsrelevanten Arbeiten auf gültige freigegebene Unterlagen verweisen.'),
                            input=f'Bisheriger Gesprächsverlauf:\n{context[:2500]}\n\nQuellen:\n{chr(10).join(sources)[:14000]}',
                            max_output_tokens=950,
                        )
                        answer = response.output_text or 'Keine Antwort erhalten.'
                else:
                    answer = 'Passende Fundstellen gefunden. Aktiviere die KI-Antwort, um eine Antwort daraus erstellen zu lassen.'
                st.markdown(answer)
                st.markdown('**Quellen**')
                for i, (_, chunk, doc) in enumerate(hits, 1):
                    with st.expander(f'[{i}] {doc.get("filename", "Dokument")} – Seite/Abschnitt {chunk.get("page_number", "?")}'):
                        st.write(chunk.get('content', ''))
        except Exception:
            answer = 'Die Anfrage konnte nicht abgeschlossen werden. Bitte Streamlit-Logs prüfen.'
            st.error(answer)
        st.session_state.railtec_ai_history.append({'role': 'assistant', 'text': answer})
