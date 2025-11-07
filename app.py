import io, os, tempfile, json
from pathlib import Path

import streamlit as st
from st_audiorec import st_audiorec

import speech_recognition as sr
from pydub import AudioSegment
from pydub.utils import which


AudioSegment.converter = which("ffmpeg")
AudioSegment.ffprobe   = which("ffprobe")


def concat_segments_wav(wav_bytes_list: list[bytes]) -> bytes:
    """Concatene plusieurs segments WAV (retour de st_audiorec) en un seul WAV mono 16k."""
    if not wav_bytes_list:
        return b""
    mixed = None
    for b in wav_bytes_list:
        seg = AudioSegment.from_file(io.BytesIO(b), format="wav")
        seg = seg.set_frame_rate(16000).set_channels(1)
        mixed = seg if mixed is None else mixed + seg
    out = io.BytesIO()
    mixed.export(out, format="wav")
    return out.getvalue()

def ensure_wav_bytes(audio_bytes: bytes) -> bytes:
    """Convertit mp3/m4a/whatever WAV mono 16k."""
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
        seg = seg.set_frame_rate(16000).set_channels(1)
        out = io.BytesIO()
        seg.export(out, format="wav")
        return out.getvalue()
    except Exception as e:
        raise RuntimeError(f"Impossible de lire/convertir le fichier audio: {e}")

def save_bytes_to_tmp_wav(wav_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(wav_bytes)
        return tmp.name

def transcribe_with_google(wav_path: str, language: str) -> tuple[str|None, str|None]:
    r = sr.Recognizer()
    try:
        with sr.AudioFile(wav_path) as src:
            audio = r.record(src)
        text = r.recognize_google(audio, language=language)
        return text, None
    except sr.UnknownValueError:
        return None, "Audio incompréhensible pour Google Speech."
    except sr.RequestError as e:
        return None, f"Erreur API Google: {e}"

def transcribe_with_sphinx(wav_path: str, language: str) -> tuple[str|None, str|None]:
    """
    Offline. Necessite `pip install pocketsphinx`.
    Le parametre 'language' est peut etre pas supporté (principalement en-US).
    """
    try:
        import pocketsphinx  
    except Exception:
        return None, "Pocketsphinx non installé. Fais `pip install pocketsphinx`."

    r = sr.Recognizer()
    try:
        with sr.AudioFile(wav_path) as src:
            audio = r.record(src)
        text = r.recognize_sphinx(audio) 
        return text, None
    except sr.UnknownValueError:
        return None, "Audio incompréhensible pour Sphinx."
    except Exception as e:
        return None, f"Erreur Pocketsphinx: {e}"

def transcribe_audio_bytes(audio_bytes: bytes, backend: str, language: str) -> tuple[str|None, str|None]:
    if not audio_bytes:
        return None, "Aucun audio fourni."
    try:
        wav_bytes = ensure_wav_bytes(audio_bytes)
    except RuntimeError as e:
        return None, str(e)

    wav_path = save_bytes_to_tmp_wav(wav_bytes)
    try:
        if backend == "Google (online)":
            return transcribe_with_google(wav_path, language)
        elif backend == "Sphinx (offline)":
            return transcribe_with_sphinx(wav_path, language)
        else:
            return None, f"Backend inconnu: {backend}"
    finally:
        try:
            os.remove(wav_path)
        except:
            pass

st.set_page_config(page_title="Speech Recognition — Checkpoint", layout="centered")
st.title("Speech Recognition — Checkpoint")

with st.expander("Instruct", expanded=True):
    st.markdown(
        """
        **Ce que tu peux faire ici :**
        1. **Choisir un backend** : Google (online) ou Sphinx (offline optionnel).  
        2. **Choisir la langue** (pour Google, FR/EN/ES…).  
        3. **Enregistrer** depuis le **micro** (navigateur) via *Record* *Stop*.  
        4. **Uploader** un fichier audio (WAV/MP3/M4A), transcrire.  
        5. **Pause/Reprendre** : enregistre en **plusieurs segments** puis **concatene** avant transcription.  
        6. **Sauvegarder** le texte transcrit en `.txt`.  

        **Notes rapides :**
        - *FFmpeg* doit être installé pour lire MP3/M4A.  
        - Sphinx (offline) = `pip install pocketsphinx` (support surtout en-US).  
        """
    )

ss = st.session_state
ss.setdefault("segments", []) 
ss.setdefault("last_transcript", "") 

colA, colB = st.columns(2)
with colA:
    backend = st.selectbox(
        "Backend de reconnaissance",
        ["Google (online)", "Sphinx (offline)"],
        index=0
    )
with colB:
    language = st.selectbox(
        "Langue (Google seulement)",
        ["fr-FR", "en-US", "es-ES", "de-DE", "it-IT"],
        index=0
    )

st.markdown("### Enregistrement (web)")
st.caption("Clique **Record** pour capturer. Tu peux faire **plusieurs segments** (pause/reprise), puis **Concatener + Transcrire**.")
wav_audio = st_audiorec()

col1, col2, col3 = st.columns(3)
with col1:
    if st.button(" + Ajouter ce segment"):
        if wav_audio:
            ss.segments.append(wav_audio)
            st.success(f"Segment ajouté. Total: {len(ss.segments)}")
        else:
            st.warning("Rien a ajouter. Enregistre d abord un segment")
with col2:
    if st.button("Supprimer les segments"):
        ss.segments.clear()
        st.info("Segments effacés")
with col3:
    if st.button("Concatener + Transcrire"):
        if not ss.segments:
            st.warning("Aucun segment. Enregistre au moins un segment.")
        else:
            joined = concat_segments_wav(ss.segments)
            text, err = transcribe_audio_bytes(joined, backend, language)
            if err:
                st.error(err)
            else:
                ss.last_transcript = text or ""
                st.success("Transcription terminée (segments)")

st.markdown("---")
st.markdown("### Uploader un fichier audio")
up = st.file_uploader("Choisis un fichier (WAV/MP3/M4A)", type=["wav", "mp3", "m4a"])
if st.button("Transcrire le fichier uploadé"):
    if up is None:
        st.warning("Ajoute un fichier d abord.")
    else:
        audio_bytes = up.read()
        text, err = transcribe_audio_bytes(audio_bytes, backend, language)
        if err:
            st.error(err)
        else:
            ss.last_transcript = text or ""
            st.success("Transcription terminée (upload).")

st.markdown("---")
st.markdown("### Resultat")
if ss.last_transcript:
    st.text_area("Texte transcrit", ss.last_transcript, height=200)
    st.download_button(
        "Télécharger .txt",
        data=ss.last_transcript.encode("utf-8"),
        file_name="transcription.txt",
        mime="text/plain"
    )
else:
    st.info("Aucune transcription encore. Enregistre des segments, ou upload un fichier, puis transcris.")
