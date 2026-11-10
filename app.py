"""RailTecSol 0.6 – Supabase login, private documents, AI research."""
import io
import re
import uuid
from urllib.parse import quote
import requests
import streamlit as st
from docx import Document
from pypdf import PdfReader
from railtec_ai_06 import render_ai_assistant

st.set_page_config(page_title='RailTecSol', page_icon='🚆', layout='wide')
URL = st.secrets.get('SUPABASE_URL', '').rstrip('/')
KEY = st.secrets.get('SUPABASE_KEY', '')
BUCKET = 'rail-manuals'
st.title('🚆 RailTecSol')
st.caption('Version 0.6 · Private technische Wissensdatenbank mit KI-Recherche')
if not URL.startswith('https://') or not URL.endswith('.supabase.co') or not KEY:
    st.error('Bitte SUPABASE_URL und SUPABASE_KEY in Streamlit Secrets prüfen.')
    st.stop()


def headers(token=None, content_type='application/json'):
    result = {'apikey': KEY}
    if content_type:
        result['Content-Type'] = content_type
    if token:
        result['Authorization'] = f'Bearer {token}'
    return result


def clear_session():
    for key in ('access_token', 'refresh_token', 'user_id', 'railtec_ai_history'):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith('file_'):
            st.session_state.pop(key, None)


def login(email, password):
    response = requests.post(URL + '/auth/v1/token?grant_type=password',
                             headers=headers(), json={'email': email, 'password': password}, timeout=30)
    response.raise_for_status()
    return response.json()


def refresh_session():
    refresh = st.session_state.get('refresh_token')
    if not refresh:
        return False
    try:
        response = requests.post(URL + '/auth/v1/token?grant_type=refresh_token',
                                 headers=headers(), json={'refresh_token': refresh}, timeout=30)
        response.raise_for_status()
        data = response.json()
        st.session_state.access_token = data['access_token']
        st.session_state.refresh_token = data['refresh_token']
        st.session_state.user_id = data['user']['id']
        return True
    except (requests.RequestException, KeyError, ValueError):
        clear_session()
        return False


def current_user():
    token = st.session_state.get('access_token')
    if not token:
        return None
    try:
        response = requests.get(URL + '/auth/v1/user', headers=headers(token), timeout=20)
        if response.status_code == 401:
            if not refresh_session():
                return None
            response = requests.get(URL + '/auth/v1/user',
                                    headers=headers(st.session_state.access_token), timeout=20)
        response.raise_for_status()
        user = response.json()
        st.session_state.user_id = user['id']
        return user
    except (requests.RequestException, ValueError, KeyError):
        return None


def authorized_request(method, path, **kwargs):
    content_type = kwargs.pop('content_type', 'application/json')
    for attempt in range(2):
        token = st.session_state.get('access_token')
        if not token:
            raise RuntimeError('Nicht angemeldet.')
        response = requests.request(method, URL + path,
                                    headers=headers(token, content_type), timeout=60, **kwargs)
        if response.status_code == 401 and attempt == 0 and refresh_session():
            continue
        response.raise_for_status()
        return response
    raise RuntimeError('Sitzung abgelaufen.')


def extract_pages(filename, data):
    extension = filename.lower().rsplit('.', 1)[-1]
    if extension == 'pdf':
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError('Verschlüsselte PDFs werden nicht unterstützt.')
        if len(reader.pages) > 80:
            raise ValueError('Maximal 80 Seiten je PDF.')
        pages = [(page.extract_text() or '').strip() for page in reader.pages]
    elif extension == 'docx':
        doc = Document(io.BytesIO(data))
        content = '\n'.join(p.text for p in doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                content += '\n' + ' | '.join(c.text for c in row.cells)
        pages = [content.strip()]
    elif extension == 'txt':
        pages = [data.decode('utf-8-sig', errors='replace').strip()]
    else:
        raise ValueError('Nur PDF, DOCX und TXT erlaubt.')
    if not any(pages):
        raise ValueError('Kein lesbarer Text gefunden (Scan-PDF benötigt OCR).')
    return pages


def create_chunks(pages):
    chunks = []
    for number, page in enumerate(pages, 1):
        for start in range(0, len(page), 1500):
            part = page[start:start + 1500].strip()
            if part:
                chunks.append({'page_number': number, 'content': part})
    return chunks


def documents():
    response = authorized_request('GET', '/rest/v1/rail_documents?select=*&order=created_at.desc')
    return response.json()


user = current_user()
if user is None:
    clear_session()
    st.subheader('Anmelden')
    with st.form('login_form'):
        email = st.text_input('E-Mail-Adresse')
        password = st.text_input('Passwort', type='password')
        submit = st.form_submit_button('Anmelden')
    if submit:
        try:
            data = login(email.strip(), password)
            st.session_state.access_token = data['access_token']
            st.session_state.refresh_token = data['refresh_token']
            st.session_state.user_id = data['user']['id']
            st.rerun()
        except requests.HTTPError as exc:
            status = exc.response.status_code
            try:
                code = exc.response.json().get('error_code', '')
            except ValueError:
                code = ''
            st.error(f'Anmeldung fehlgeschlagen: HTTP {status}')
            if code:
                st.code(code)
        except requests.RequestException:
            st.error('Supabase ist momentan nicht erreichbar.')
    st.stop()

with st.sidebar:
    st.success('Angemeldet')
    st.caption(user.get('email', ''))
    if st.button('Abmelden'):
        clear_session()
        st.rerun()

st.warning('Nur freigegebene technische Unterlagen verwenden. KI-Antworten ersetzen keine gültigen Prüfanweisungen.')
tab_docs, tab_ai, tab_info = st.tabs(['📚 Dokumente', '🤖 KI-Assistent', 'ℹ️ Info'])

with tab_docs:
    st.subheader('Technische Manuals')
    with st.form('upload_form'):
        file = st.file_uploader('Dokument auswählen', type=['pdf', 'docx', 'txt'])
        vehicle = st.text_input('Fahrzeug / Baureihe')
        revision = st.text_input('Revision', value='Unbekannt')
        upload = st.form_submit_button('Dauerhaft speichern')
    if upload:
        if file is None:
            st.warning('Bitte zuerst eine Datei auswählen.')
        else:
            try:
                data = file.getvalue()
                if len(data) > 8 * 1024 * 1024:
                    raise ValueError('Maximal 8 MB je Datei.')
                pages = extract_pages(file.name, data)
                chunks = create_chunks(pages)
                doc_id = str(uuid.uuid4())
                safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', file.name)
                path = f'{st.session_state.user_id}/{doc_id}/{safe_name}'
                extension = file.name.lower().rsplit('.', 1)[-1]
                mime = {'pdf': 'application/pdf',
                        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'txt': 'text/plain'}[extension]
                authorized_request('POST', f'/storage/v1/object/{BUCKET}/{quote(path, safe="/")}',
                                   data=data, content_type=mime)
                authorized_request('POST', '/rest/v1/rail_documents', json={
                    'id': doc_id, 'filename': file.name, 'vehicle': vehicle or 'Allgemein',
                    'revision': revision or 'Unbekannt', 'storage_path': path,
                    'created_by': st.session_state.user_id})
                authorized_request('POST', '/rest/v1/rail_chunks', json=[
                    {'document_id': doc_id, **chunk} for chunk in chunks])
                st.success('Dokument gespeichert.')
                st.rerun()
            except (requests.RequestException, ValueError) as exc:
                st.error(f'Upload fehlgeschlagen: {exc}')
    st.divider()
    st.subheader('Gespeicherte Dokumente')
    try:
        docs = documents()
        if not docs:
            st.info('Noch keine Dokumente vorhanden.')
        for doc in docs:
            with st.expander(doc['filename']):
                st.write('Fahrzeug:', doc['vehicle'])
                st.write('Revision:', doc['revision'])
                if st.button('Datei zum Download vorbereiten', key='get_' + doc['id']):
                    try:
                        response = authorized_request('GET', '/storage/v1/object/authenticated/'
                            + BUCKET + '/' + quote(doc['storage_path'], safe='/'))
                        st.session_state['file_' + doc['id']] = response.content
                    except requests.RequestException:
                        st.error('Datei konnte nicht geladen werden.')
                prepared = st.session_state.get('file_' + doc['id'])
                if prepared is not None:
                    st.download_button('Herunterladen', data=prepared,
                                       file_name=doc['filename'], key='download_' + doc['id'])
                if doc['created_by'] == st.session_state.user_id:
                    if st.button('Dokument löschen', key='del_' + doc['id']):
                        try:
                            authorized_request('DELETE', '/storage/v1/object/' + BUCKET + '/'
                                               + quote(doc['storage_path'], safe='/'))
                            authorized_request('DELETE', '/rest/v1/rail_documents?id=eq.' + doc['id'])
                            st.session_state.pop('file_' + doc['id'], None)
                            st.success('Dokument gelöscht.')
                            st.rerun()
                        except requests.RequestException:
                            st.error('Löschen fehlgeschlagen.')
    except requests.RequestException:
        st.error('Dokumentenliste konnte nicht geladen werden.')

with tab_ai:
    render_ai_assistant(authorized_request, documents)

with tab_info:
    st.subheader('RailTecSol 0.6')
    st.write('Private Wissensdatenbank für Schienenfahrzeuge.')
    st.write('Anmeldung über Supabase Auth und dauerhafte Dokumentenspeicherung.')
    st.write('KI-Chat mit Dokumentenrecherche, Fachwissen und optionaler Websuche.')
    st.info('Die frühere Störungserfassung ist in dieser Version noch nicht enthalten.')
