
import io
import re
import uuid

import requests
import streamlit as st
from docx import Document
from pypdf import PdfReader

st.set_page_config(
    page_title="RailTecSol",
    page_icon="🚆",
    layout="wide",
)

st.title("🚆 RailTecSol")
st.caption("Version 0.4 · Private technische Wissensdatenbank")

URL = st.secrets.get("SUPABASE_URL", "").rstrip("/")
KEY = st.secrets.get("SUPABASE_KEY", "")
BUCKET = "rail-manuals"

if not URL or not KEY:
    st.error("Supabase-Zugangsdaten fehlen in Streamlit Secrets.")
    st.stop()


def headers(token=None, content_type="application/json"):
    result = {
        "apikey": KEY,
        "Content-Type": content_type,
    }
    if token:
        result["Authorization"] = f"Bearer {token}"
    return result


def api(method, path, token=None, **kwargs):
    response = requests.request(
        method,
        URL + path,
        headers=headers(token),
        timeout=30,
        **kwargs,
    )
    response.raise_for_status()
    return response.json() if response.content else None


def login(email, password):
    response = requests.post(
        URL + "/auth/v1/token?grant_type=password",
        headers=headers(),
        json={"email": email, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


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
        return True
    except requests.RequestException:
        return False


def authorized_request(method, path, **kwargs):
    for attempt in range(2):
        token = st.session_state.get("access_token")
        response = requests.request(
            method,
            URL + path,
            headers=headers(token, kwargs.pop("content_type", "application/json")),
            timeout=60,
            **kwargs,
        )
        if response.status_code == 401 and attempt == 0:
            if refresh_session():
                continue
        response.raise_for_status()
        return response
    raise RuntimeError("Anmeldung abgelaufen.")


def extract_pages(filename, data):
    extension = filename.lower().rsplit(".", 1)[-1]

    if extension == "pdf":
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("Verschlüsselte PDFs werden nicht unterstützt.")
        if len(reader.pages) > 80:
            raise ValueError("Maximal 80 Seiten pro PDF.")
        pages = [
            (page.extract_text() or "").strip()
            for page in reader.pages
        ]
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
        raise ValueError("Dateityp nicht unterstützt.")

    if not any(pages):
        raise ValueError("Kein lesbarer Text gefunden.")

    return pages


def create_chunks(pages):
    chunks = []
    for page_number, page in enumerate(pages, 1):
        for start in range(0, len(page), 1500):
            part = page[start:start + 1700].strip()
            if part:
                chunks.append({
                    "page_number": page_number,
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
    chunks = response.json()
    words = set(re.findall(r"[a-zäöüß0-9]{3,}", question.lower()))
    doc_map = {doc["id"]: doc for doc in docs}
    results = []

    for chunk in chunks:
        text = chunk["content"].lower()
        score = sum(text.count(word) for word in words)
        if score > 0 and chunk["document_id"] in doc_map:
            results.append((score, chunk, doc_map[chunk["document_id"]]))

    results.sort(key=lambda item: item[0], reverse=True)
    return results[:5]


if "access_token" not in st.session_state:
    st.session_state.access_token = None

if "refresh_token" not in st.session_state:
    st.session_state.refresh_token = None

if "user_id" not in st.session_state:
    st.session_state.user_id = None


if not st.session_state.access_token:
    st.subheader("Anmelden")

    with st.form("login"):
        email = st.text_input("E-Mail-Adresse")
        password = st.text_input("Passwort", type="password")
        submit = st.form_submit_button("Anmelden")

    if submit:
        try:
            data = login(email, password)
            st.session_state.access_token = data["access_token"]
            st.session_state.refresh_token = data["refresh_token"]
            st.session_state.user_id = data["user"]["id"]
            st.rerun()
        except requests.RequestException:
            st.error("Anmeldung fehlgeschlagen. Zugangsdaten prüfen.")

    st.stop()


with st.sidebar:
    st.success("Angemeldet")
    if st.button("Abmelden"):
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        st.session_state.user_id = None
        st.rerun()

st.warning(
    "Nur freigegebene technische Unterlagen verwenden. "
    "Keine verbindlichen Prüfanweisungen durch KI ersetzen."
)

tab1, tab2, tab3 = st.tabs([
    "📚 Dokumente",
    "🤖 KI-Assistent",
    "ℹ️ Info",
])

with tab1:
    st.subheader("Technische Manuals")

    with st.form("upload"):
        file = st.file_uploader(
            "Dokument hochladen",
            type=["pdf", "docx", "txt"],
        )
        vehicle = st.text_input("Fahrzeug / Baureihe")
        revision = st.text_input("Revision", value="Unbekannt")
        upload = st.form_submit_button("Dauerhaft speichern")

    if upload and file:
        try:
            data = file.getvalue()

            if len(data) > 8 * 1024 * 1024:
                raise ValueError("Maximal 8 MB je Datei.")

            pages = extract_pages(file.name, data)
            chunks = create_chunks(pages)

            doc_id = str(uuid.uuid4())
            path = f"{st.session_state.user_id}/{doc_id}/{file.name}"

            storage_response = authorized_request(
                "POST",
                f"/storage/v1/object/{BUCKET}/{path}",
                data=data,
                content_type=file.type or "application/octet-stream",
            )

            metadata = {
                "id": doc_id,
                "filename": file.name,
                "vehicle": vehicle or "Allgemein",
                "revision": revision or "Unbekannt",
                "storage_path": path,
                "created_by": st.session_state.user_id,
            }

            try:
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
            except Exception:
                st.error(
                    "Datei gespeichert, aber Datenbankeintrag "
                    "nicht vollständig. Bitte Administrator informieren."
                )
                raise

            st.success("Dokument dauerhaft gespeichert.")
            st.rerun()

        except Exception as exc:
            st.error(f"Upload fehlgeschlagen: {exc}")

    try:
        docs = documents()

        if not docs:
            st.info("Noch keine Manuals vorhanden.")

        for doc in docs:
            with st.expander(doc["filename"]):
                st.write("Fahrzeug:", doc["vehicle"])
                st.write("Revision:", doc["revision"])

                if st.button("Datei herunterladen", key="get_" + doc["id"]):
                    try:
                        response = authorized_request(
                            "GET",
                            f"/storage/v1/object/authenticated/{BUCKET}/{doc['storage_path']}",
                        )
                        st.download_button(
                            "Download starten",
                            data=response.content,
                            file_name=doc["filename"],
                            key="download_" + doc["id"],
                        )
                    except Exception as exc:
                        st.error(str(exc))

                if doc["created_by"] == st.session_state.user_id:
                    if st.button("Dokument löschen", key="del_" + doc["id"]):
                        try:
                            authorized_request(
                                "DELETE",
                                f"/storage/v1/object/{BUCKET}/{doc['storage_path']}",
                            )
                            authorized_request(
                                "DELETE",
                                f"/rest/v1/rail_documents?id=eq.{doc['id']}",
                            )
                            st.success("Dokument gelöscht.")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

    except Exception as exc:
        st.error(f"Dokumente konnten nicht geladen werden: {exc}")


with tab2:
    st.subheader("Technischer KI-Assistent")

    question = st.text_area("Deine technische Frage")

    use_ai = st.checkbox(
        "Passende Dokumentenauszüge an OpenAI senden",
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
                    source_text = []

                    for index, (_, chunk, doc) in enumerate(hits, 1):
                        label = (
                            f"[{index}] {doc['filename']} "
                            f"– Seite {chunk['page_number']}"
                        )
                        source_text.append(
                            label + "\n" + chunk["content"]
                        )
                        with st.expander(label):
                            st.write(chunk["content"])

                    if use_ai:
                        openai_key = st.secrets.get("OPENAI_API_KEY", "")

                        if not openai_key:
                            st.warning("OpenAI-Key fehlt.")
                        else:
                            from openai import OpenAI

                            client = OpenAI(api_key=openai_key)

                            answer = client.responses.create(
                                model="gpt-4.1-mini",
                                instructions=(
                                    "Du bist ein technischer Assistent für "
                                    "Schienenfahrzeuge. Verwende ausschließlich "
                                    "die bereitgestellten Quellen. "
                                    "Nenne Dokument und Seitenzahl. "
                                    "Erfinde keine Sollwerte oder Prüfschritte. "
                                    "Bei fehlender Grundlage sage dies klar."
                                ),
                                input=(
                                    "Frage:\n" + question +
                                    "\n\nQuellen:\n" +
                                    "\n\n".join(source_text)[:12000]
                                ),
                                max_output_tokens=800,
                            )

                            st.markdown(answer.output_text)

            except Exception as exc:
                st.error(f"Suche fehlgeschlagen: {exc}")


with tab3:
    st.subheader("RailTecSol 0.4")
    st.write("Private Dokumentenbibliothek mit Supabase.")
    st.write("Benutzerkonten werden in Supabase verwaltet.")
    st.write("Dokumente sind für angemeldete Teammitglieder sichtbar.")
    st.write("Nur der jeweilige Uploader kann seine Dateien löschen.")
    st.info(
        "Die bisherige Störungserfassung aus Version 0.3 "
        "ist in dieser Version noch nicht enthalten."
    )
