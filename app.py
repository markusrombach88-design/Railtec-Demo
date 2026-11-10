
import io
import re
import uuid
from urllib.parse import quote

import requests
import streamlit as st
from docx import Document
from pypdf import PdfReader

st.set_page_config(
    page_title="RailTecSol",
    page_icon="🚆",
    layout="wide",
)

URL = st.secrets.get("SUPABASE_URL", "").rstrip("/")
KEY = st.secrets.get("SUPABASE_KEY", "")
BUCKET = "rail-manuals"

st.title("🚆 RailTecSol")
st.caption("Version 0.4.1 · Private technische Wissensdatenbank")

if not URL or not KEY:
    st.error("Supabase-Zugangsdaten fehlen in Streamlit Secrets.")
    st.stop()

if not URL.startswith("https://") or not URL.endswith(".supabase.co"):
    st.error("SUPABASE_URL muss direkt auf .supabase.co enden.")
    st.stop()


def headers(token=None, content_type="application/json"):
    h = {"apikey": KEY}
    if content_type:
        h["Content-Type"] = content_type
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def login(email, password):
    response = requests.post(
        URL + "/auth/v1/token?grant_type=password",
        headers=headers(),
        json={"email": email, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def clear_session():
    for key in ("access_token", "refresh_token", "user_id"):
        st.session_state.pop(key, None)


def refresh_session():
    refresh = st.session_state.get("refresh_token")
    if not refresh:
        return False

    try:
        response = requests.post(
            URL + "/auth/v1/token?grant_type=refresh_token",
            headers=headers(),
            json={"refresh_token": refresh},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        st.session_state.access_token = data["access_token"]
        st.session_state.refresh_token = data["refresh_token"]
        st.session_state.user_id = data["user"]["id"]
        return True
    except (requests.RequestException, KeyError, ValueError):
        clear_session()
        return False


def current_user():
    token = st.session_state.get("access_token")
    if not token:
        return None

    try:
        response = requests.get(
            URL + "/auth/v1/user",
            headers=headers(token),
            timeout=20,
        )
        if response.status_code == 401:
            if not refresh_session():
                return None
            response = requests.get(
                URL + "/auth/v1/user",
                headers=headers(st.session_state.access_token),
                timeout=20,
            )
        response.raise_for_status()
        user = response.json()
        st.session_state.user_id = user["id"]
        return user
    except (requests.RequestException, ValueError, KeyError):
        return None


def authorized_request(method, path, **kwargs):
    content_type = kwargs.pop("content_type", "application/json")

    for attempt in range(2):
        token = st.session_state.get("access_token")
        if not token:
            raise RuntimeError("Nicht angemeldet.")

        response = requests.request(
            method,
            URL + path,
            headers=headers(token, content_type),
            timeout=60,
            **kwargs,
        )

        if response.status_code == 401 and attempt == 0:
            if refresh_session():
                continue

        response.raise_for_status()
        return response

    raise RuntimeError("Sitzung abgelaufen.")


def extract_pages(filename, data):
    extension = filename.lower().rsplit(".", 1)[-1]

    if extension == "pdf":
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("Verschlüsselte PDF nicht unterstützt.")
        if len(reader.pages) > 80:
            raise ValueError("Maximal 80 Seiten.")
        pages = [(page.extract_text() or "").strip()
                 for page in reader.pages]

    elif extension == "docx":
        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                text += "\n" + " | ".join(c.text for c in row.cells)
        pages = [text.strip()]

    elif extension == "txt":
        pages = [data.decode("utf-8-sig", errors="replace")]

    else:
        raise ValueError("Nur PDF, DOCX und TXT erlaubt.")

    if not any(pages):
        raise ValueError("Kein lesbarer Text gefunden.")

    return pages


def create_chunks(pages):
    chunks = []
    for number, page in enumerate(pages, 1):
        for start in range(0, len(page), 1500):
            part = page[start:start + 1500].strip()
            if part:
                chunks.append({
                    "page_number": number,
                    "content": part,
                })
    return chunks


def documents():
    response = authorized_request(
        "GET",
        "/rest/v1/rail_documents?select=*&order=created_at.desc",
    )
    return response.json()


def search_chunks(question, docs):
    response = authorized_request(
        "GET",
        "/rest/v1/rail_chunks?select=document_id,page_number,content",
    )

    words = set(re.findall(r"[a-zäöüß0-9]{3,}", question.lower()))
    doc_map = {doc["id"]: doc for doc in docs}
    hits = []

    for chunk in response.json():
        content = chunk["content"].lower()
        score = sum(content.count(word) for word in words)
        doc = doc_map.get(chunk["document_id"])
        if score > 0 and doc:
            hits.append((score, chunk, doc))

    hits.sort(key=lambda item: item[0], reverse=True)
    return hits[:5]


# ==========================================
# ANMELDUNG
# ==========================================

user = current_user()

if user is None:
    clear_session()
    st.subheader("Anmelden")

    with st.form("login_form"):
        email = st.text_input("E-Mail-Adresse")
        password = st.text_input("Passwort", type="password")
        submit = st.form_submit_button("Anmelden")

    if submit:
        try:
            data = login(email.strip(), password)
            st.session_state.access_token = data["access_token"]
            st.session_state.refresh_token = data["refresh_token"]
            st.session_state.user_id = data["user"]["id"]
            st.rerun()

        except requests.HTTPError as exc:
            status = exc.response.status_code
            try:
                code = exc.response.json().get("error_code", "")
            except ValueError:
                code = ""

            st.error(f"Anmeldung fehlgeschlagen: HTTP {status}")
            if code:
                st.code(code)

        except requests.RequestException:
            st.error("Supabase ist momentan nicht erreichbar.")

    # Wichtig: Keine App-Inhalte ohne Anmeldung
    st.stop()


# ==========================================
# AB HIER NUR ANGEMELDETE BENUTZER
# ==========================================

with st.sidebar:
    st.success("Angemeldet")
    st.caption(user.get("email", ""))

    if st.button("Abmelden"):
        clear_session()
        st.rerun()

st.warning(
    "Nur freigegebene technische Unterlagen verwenden. "
    "KI-Antworten ersetzen keine gültigen Prüfanweisungen."
)

tab_docs, tab_ai, tab_info = st.tabs([
    "📚 Dokumente",
    "🤖 KI-Assistent",
    "ℹ️ Info",
])


# ==========================================
# DOKUMENTENBIBLIOTHEK
# ==========================================

with tab_docs:
    st.subheader("Technische Manuals")

    with st.form("upload_form"):
        file = st.file_uploader(
            "Dokument auswählen",
            type=["pdf", "docx", "txt"],
        )
        vehicle = st.text_input("Fahrzeug / Baureihe")
        revision = st.text_input("Revision", value="Unbekannt")
        upload = st.form_submit_button("Dauerhaft speichern")

    if upload:
        if file is None:
            st.warning("Bitte zuerst eine Datei auswählen.")
        else:
            try:
                data = file.getvalue()

                if len(data) > 8 * 1024 * 1024:
                    raise ValueError("Maximal 8 MB je Datei.")

                pages = extract_pages(file.name, data)
                chunks = create_chunks(pages)

                doc_id = str(uuid.uuid4())
                safe_name = re.sub(
                    r"[^a-zA-Z0-9._-]", "_", file.name
                )
                path = (
                    f"{st.session_state.user_id}/"
                    f"{doc_id}/{safe_name}"
                )

                mime = {
                    "pdf": "application/pdf",
                    "docx": (
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    "txt": "text/plain",
                }[file.name.lower().rsplit(".", 1)[-1]]

                authorized_request(
                    "POST",
                    f"/storage/v1/object/{BUCKET}/{quote(path, safe='/')}",
                    data=data,
                    content_type=mime,
                )

                metadata = {
                    "id": doc_id,
                    "filename": file.name,
                    "vehicle": vehicle or "Allgemein",
                    "revision": revision or "Unbekannt",
                    "storage_path": path,
                    "created_by": st.session_state.user_id,
                }

                authorized_request(
                    "POST",
                    "/rest/v1/rail_documents",
                    json=metadata,
                )

                if chunks:
                    rows = [
                        {"document_id": doc_id, **chunk}
                        for chunk in chunks
                    ]
                    authorized_request(
                        "POST",
                        "/rest/v1/rail_chunks",
                        json=rows,
                    )

                st.success("Dokument gespeichert.")
                st.rerun()

            except (requests.RequestException, ValueError) as exc:
                st.error(f"Upload fehlgeschlagen: {exc}")

    st.divider()
    st.subheader("Gespeicherte Dokumente")

    try:
        docs = documents()

        if not docs:
            st.info("Noch keine Dokumente vorhanden.")

        for doc in docs:
            with st.expander(doc["filename"]):
                st.write("Fahrzeug:", doc["vehicle"])
                st.write("Revision:", doc["revision"])

                if st.button(
                    "Datei zum Download vorbereiten",
                    key="get_" + doc["id"],
                ):
                    try:
                        response = authorized_request(
                            "GET",
                            "/storage/v1/object/authenticated/"
                            + BUCKET + "/"
                            + quote(doc["storage_path"], safe="/"),
                        )
                        st.session_state[
                            "file_" + doc["id"]
                        ] = response.content
                    except requests.RequestException:
                        st.error("Datei konnte nicht geladen werden.")

                prepared = st.session_state.get(
                    "file_" + doc["id"]
                )
                if prepared is not None:
                    st.download_button(
                        "Herunterladen",
                        data=prepared,
                        file_name=doc["filename"],
                        key="download_" + doc["id"],
                    )

                if doc["created_by"] == st.session_state.user_id:
                    if st.button(
                        "Dokument löschen",
                        key="del_" + doc["id"],
                    ):
                        try:
                            authorized_request(
                                "DELETE",
                                "/storage/v1/object/"
                                + BUCKET + "/"
                                + quote(doc["storage_path"], safe="/"),
                            )
                            authorized_request(
                                "DELETE",
                                "/rest/v1/rail_documents?id=eq."
                                + doc["id"],
                            )
                            st.session_state.pop(
                                "file_" + doc["id"], None
                            )
                            st.success("Dokument gelöscht.")
                            st.rerun()
                        except requests.RequestException:
                            st.error("Löschen fehlgeschlagen.")

    except requests.RequestException:
        st.error("Dokumentenliste konnte nicht geladen werden.")


# ==========================================
# KI-ASSISTENT
# ==========================================

with tab_ai:
    st.subheader("Technischer KI-Assistent")

    question = st.text_area("Deine technische Frage")

    use_ai = st.checkbox(
        "Dokumentenauszüge an OpenAI senden",
        value=False,
    )

    if st.button("Antwort suchen"):
        if not question.strip():
            st.warning("Bitte eine Frage eingeben.")
        else:
            try:
                docs = documents()
                hits = search_chunks(question, docs)

                if not hits:
                    st.info("Keine passenden Fundstellen gefunden.")
                else:
                    sources = []

                    for index, (_, chunk, doc) in enumerate(hits, 1):
                        label = (
                            f"[{index}] {doc['filename']} "
                            f"– Seite/Abschnitt {chunk['page_number']}"
                        )
                        sources.append(
                            label + "\n" + chunk["content"]
                        )
                        with st.expander(label):
                            st.write(chunk["content"])

                    if use_ai:
                        openai_key = st.secrets.get(
                            "OPENAI_API_KEY", ""
                        )

                        if not openai_key:
                            st.warning("OpenAI-Key fehlt.")
                        else:
                            from openai import OpenAI

                            client = OpenAI(api_key=openai_key)

                            answer = client.responses.create(
                                model="gpt-4.1-mini",
                                instructions=(
                                    "Du bist ein technischer Assistent "
                                    "für Schienenfahrzeuge. "
                                    "Verwende nur die Quellen. "
                                    "Nenne Dokument und Fundstelle. "
                                    "Erfinde keine Sollwerte oder Prüfschritte. "
                                    "Kennzeichne fehlende Informationen."
                                ),
                                input=(
                                    "Frage:\n" + question +
                                    "\n\nQuellen:\n" +
                                    "\n\n".join(sources)[:12000]
                                ),
                                max_output_tokens=800,
                            )

                            st.markdown(answer.output_text)

            except Exception:
                st.error(
                    "Die Suche konnte nicht abgeschlossen werden."
                )


# ==========================================
# INFORMATIONEN
# ==========================================

with tab_info:
    st.subheader("RailTecSol 0.4.1")
    st.write("Private Wissensdatenbank für Schienenfahrzeuge.")
    st.write("Anmeldung über Supabase Auth.")
    st.write("Dauerhafte Dokumentenspeicherung in Supabase.")
    st.write("Gemeinsamer Dokumentenzugriff für Teammitglieder.")
    st.write("KI-Auswertung nur nach ausdrücklicher Aktivierung.")
    st.info(
        "Die frühere Störungserfassung ist in dieser "
        "Version noch nicht enthalten."
    )
