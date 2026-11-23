import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import altair as alt
import time
import os
import json
import re
import base64
import hashlib
import requests
from datetime import datetime

# Import protetto di ReportLab (se non installato, l'app non va in crash)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# =====================================================================
# CONFIGURAZIONE PAGINA STREAMLIT
# =====================================================================
st.set_page_config(
    page_title="ScoutAI - Match Analysis & Formations",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================================
# COSTANTI RUOLI, AREE DI GIOCO, PARAMETRI SNELLI & UTENTI HOME
# =====================================================================
RUOLI_DIFENSORI = ["TS", "DC", "TD"]
RUOLI_CENTROCAMPISTI = ["CDC", "CC", "TQ"]
RUOLI_ATTACCANTI = ["AS", "AT", "AD"]
TUTTI_RUOLI_MOVIMENTO = RUOLI_DIFENSORI + RUOLI_CENTROCAMPISTI + RUOLI_ATTACCANTI

OPZIONI_IMPATTO_PARTITA = ["Decisivo", "Positivo", "Ordinato", "Sottotono", "In difficoltà"]
DELTA_IMPATTO_PARTITA = {
    "Decisivo": 0.9,
    "Positivo": 0.5,
    "Ordinato": 0.1,
    "Sottotono": -0.4,
    "In difficoltà": -0.8,
}
SCALA_IMPATTO_PARTITA = {
    "Decisivo": 2.0,
    "Positivo": 1.0,
    "Ordinato": 0.0,
    "Sottotono": -1.0,
    "In difficoltà": -2.0,
}

OPZIONI_GESTIONE_PALLA = ["Dominante", "Pulita", "Altalenante", "Imprecisa"]
DELTA_GESTIONE_PALLA = {
    "Dominante": 0.6,
    "Pulita": 0.3,
    "Altalenante": -0.1,
    "Imprecisa": -0.5,
}
SCALA_GESTIONE_PALLA = {
    "Dominante": 2.0,
    "Pulita": 1.0,
    "Altalenante": -0.5,
    "Imprecisa": -2.0,
}

OPZIONI_SICUREZZA_PORTIERE = ["Dominante", "Affidabile", "Altalenante", "Insicuro"]
DELTA_SICUREZZA_PORTIERE = {
    "Dominante": 0.7,
    "Affidabile": 0.3,
    "Altalenante": -0.2,
    "Insicuro": -0.7,
}
SCALA_SICUREZZA_PORTIERE = {
    "Dominante": 2.0,
    "Affidabile": 1.0,
    "Altalenante": -0.5,
    "Insicuro": -2.0,
}

# Pesi per area di gioco (Difesa, Centrocampo, Attacco)
PESI_AREA_GIOCO = {
    "DIFENSORE": {
        "etichetta": "Difesa",
        "impatto": 1.4,
        "gestione": 1.5,
        "assist": 0.8,
        "errori": 1.4,
    },
    "CENTROCAMPISTA": {
        "etichetta": "Centrocampo",
        "impatto": 1.3,
        "gestione": 1.4,
        "assist": 1.1,
        "errori": 1.2,
    },
    "ATTACCANTE": {
        "etichetta": "Attacco",
        "impatto": 1.4,
        "gestione": 0.8,
        "assist": 1.3,
        "errori": 0.8,
    },
}

TUTTE_LE_SCHEDE_APP = [
    "📋 Setup Partite & Formazioni",
    "⚡ Inserimento Parametri & Voti",
    "🎥 Video Analisi",
    "📈 Riepilogo Squadra",
    "📊 Grafici & Analisi Visiva",
    "🟨 Fair Play",
    "👤 Gestione Rosa",
    "🎨 Editor Grafica",
]

UTENTI_EXTRA_HOME = ["Mr Fabio", "Mirko", "Mr. Alessandro"]

def ottieni_opzioni_accesso_home(db_giocatori):
    """Restituisce la lista utenti per la Home includendo Mr Fabio, Mirko, Mr. Alessandro e tutta la rosa."""
    nomi_rosa = list((db_giocatori or {}).keys())
    opzioni = []
    for u in UTENTI_EXTRA_HOME + nomi_rosa:
        u_clean = str(u).strip()
        if u_clean and u_clean not in opzioni:
            opzioni.append(u_clean)
    return opzioni if opzioni else UTENTI_EXTRA_HOME.copy()

def ottieni_profilo_home_attivo():
    """Restituisce il profilo selezionato all'accesso nella Home se disponibile."""
    return (
        st.session_state.get("utente_attivo")
        or st.session_state.get("ultimo_utente_home")
        or st.query_params.get("utente", "")
    )

def sincronizza_client_localstorage(utente_da_salvare=None):
    """Salva su localStorage del client l'utente scelto oppure lo legge e aggiorna ?utente= al primo caricamento."""
    if utente_da_salvare:
        utente_json = json.dumps(utente_da_salvare)
        components.html(
            f"""
            <script>
            try {{
                window.localStorage.setItem("scoutai_uso_nuvolento_utente", {utente_json});
            }} catch (e) {{}}
            </script>
            """,
            height=0,
            width=0,
        )
    else:
        components.html(
            """
            <script>
            try {
                const saved = window.localStorage.getItem("scoutai_uso_nuvolento_utente");
                if (saved) {
                    const url = new URL(window.parent.location.href);
                    if (!url.searchParams.get("utente")) {
                        url.searchParams.set("utente", saved);
                        window.parent.location.replace(url.toString());
                    }
                }
            } catch (e) {}
            </script>
            """,
            height=0,
            width=0,
        )

def normalizza_impatto_partita(valore):
    val = str(valore or "").strip()
    if val in DELTA_IMPATTO_PARTITA:
        return val
    mappa_vecchia = {
        "Ottima": "Decisivo",
        "Buona": "Positivo",
        "Sufficiente": "Ordinato",
        "Insufficiente": "Sottotono",
        "Pessima": "In difficoltà",
    }
    return mappa_vecchia.get(val, "Ordinato")

def normalizza_gestione_palla(valore):
    val = str(valore or "").strip()
    if val in DELTA_GESTIONE_PALLA:
        return val
    mappa_vecchia = {
        "Ottima": "Dominante",
        "Buona": "Pulita",
        "Sufficiente": "Altalenante",
        "Insufficiente": "Imprecisa",
        "Pessima": "Imprecisa",
    }
    return mappa_vecchia.get(val, "Pulita")

def normalizza_sicurezza_portiere(valore):
    val = str(valore or "").strip()
    if val in DELTA_SICUREZZA_PORTIERE:
        return val
    return "Affidabile"

def calcola_media_giudizio(valori, opzioni, scala):
    """Restituisce l'etichetta media su scala ordinata."""
    if not valori:
        return "N.D."
    valori_validi = [scala[v] for v in valori if v in scala]
    if not valori_validi:
        return "N.D."
    media_val = sum(valori_validi) / len(valori_validi)
    return min(opzioni, key=lambda k: abs(scala[k] - media_val))

def estrai_fairplay_compat(d_p):
    """Estrae i flag booleani ammonito ed espulso da una prestazione giocatore."""
    if not isinstance(d_p, dict):
        return {"ammonito": False, "espulso": False}
    amm = bool(d_p.get("ammonito", d_p.get("ammonizione", False)))
    esp = bool(d_p.get("espulso", d_p.get("espulsione", False)))
    return {"ammonito": amm, "espulso": esp}

def render_indicatori_fairplay_html(ammonito, espulso):
    """Restituisce il markup HTML dei puntini gialli/rossi per ammonizioni ed espulsioni."""
    badges = []
    if ammonito:
        badges.append(
            "<span title='Ammonito' style='display:inline-flex;align-items:center;gap:5px;"
            "margin-left:8px;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;"
            "background:rgba(234,179,8,0.16);border:1px solid rgba(234,179,8,0.65);color:#facc15;'>"
            "<span style='width:8px;height:8px;border-radius:50%;background:#eab308;"
            "box-shadow:0 0 6px #eab308;display:inline-block;'></span>AMM</span>"
        )
    if espulso:
        badges.append(
            "<span title='Espulso (-1 voto)' style='display:inline-flex;align-items:center;gap:5px;"
            "margin-left:6px;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;"
            "background:rgba(239,68,68,0.18);border:1px solid rgba(239,68,68,0.75);color:#f87171;'>"
            "<span style='width:8px;height:8px;border-radius:50%;background:#ef4444;"
            "box-shadow:0 0 7px #ef4444;display:inline-block;'></span>ESP -1</span>"
        )
    return "".join(badges)

def get_macro_ruolo(ruolo_specifico):
    if ruolo_specifico in RUOLI_DIFENSORI:
        return "DIFENSORE"
    elif ruolo_specifico in RUOLI_CENTROCAMPISTI:
        return "CENTROCAMPISTA"
    elif ruolo_specifico in RUOLI_ATTACCANTI:
        return "ATTACCANTE"
    return "CENTROCAMPISTA"

def get_etichetta_area(ruolo_specifico):
    return PESI_AREA_GIOCO[get_macro_ruolo(ruolo_specifico)]["etichetta"]

def ruolo_default_da_rosa(ruolo_rosa_str):
    r = (ruolo_rosa_str or "").upper()
    if "TERZINO" in r or "TS" in r or "TD" in r:
        return "TD" if "TD" in r else "TS"
    if "DIFENSORE" in r or "DC" in r:
        return "DC"
    if "ATTACCANTE" in r or "EST" in r or "AT" in r:
        return "AT"
    if "CDC" in r:
        return "CDC"
    if "TQ" in r:
        return "TQ"
    return "CC"

def estrai_dati_movimento_compat(d_p):
    """Legge i parametri snelli mantenendo retrocompatibilità con eventuali dati storici."""
    impatto = normalizza_impatto_partita(
        d_p.get("impatto_partita") or d_p.get("efficacia_passaggi") or d_p.get("passaggi") or "Ordinato"
    )
    gestione = normalizza_gestione_palla(
        d_p.get("gestione_palla") or d_p.get("efficacia_passaggi") or "Pulita"
    )
    gol = int(d_p.get("gol_fatti", 0))
    assist = int(d_p.get("assist", 0))
    errori = int(d_p.get("errori_gravi", d_p.get("perse", 0)))
    fp = estrai_fairplay_compat(d_p)
    return {
        "impatto_partita": impatto,
        "gestione_palla": gestione,
        "gol_fatti": gol,
        "assist": assist,
        "errori_gravi": errori,
        "ammonito": fp["ammonito"],
        "espulso": fp["espulso"],
    }

def estrai_dati_portiere_compat(d_p):
    """Legge i parametri snelli del portiere mantenendo retrocompatibilità con dati storici."""
    sicurezza = normalizza_sicurezza_portiere(d_p.get("sicurezza_portiere", "Affidabile"))
    parate = int(d_p.get("parate_decisive", d_p.get("parate", 0)))
    if "gol_subiti" in d_p or "errori_gravi" in d_p:
        gol_sub = int(d_p.get("gol_subiti", 0))
        errori_p = int(d_p.get("errori_gravi", 0))
    else:
        gol_sub, errori_p = parse_frazione(d_p.get("gol_subiti_resp", "0/0"))
    fp = estrai_fairplay_compat(d_p)
    return {
        "sicurezza_portiere": sicurezza,
        "parate_decisive": parate,
        "gol_subiti": gol_sub,
        "errori_gravi": errori_p,
        "ammonito": fp["ammonito"],
        "espulso": fp["espulso"],
    }

def valori_base_giocatore(nome_g, is_portiere, is_riserva, db_giocatori):
    """Restituisce i valori iniziali/azzerati per un giocatore nel modello snello e visivo."""
    min_default = 0 if is_riserva else 80
    if is_portiere:
        return {
            "minuti": min_default,
            "sicurezza_portiere": "Affidabile",
            "parate_decisive": 0,
            "gol_subiti": 0,
            "errori_gravi": 0,
            "ammonito": False,
            "espulso": False,
        }
    return {
        "ruolo_campo": ruolo_default_da_rosa(db_giocatori.get(nome_g, {}).get("ruolo", "")),
        "minuti": min_default,
        "impatto_partita": "Ordinato",
        "gestione_palla": "Pulita",
        "gol_fatti": 0,
        "assist": 0,
        "errori_gravi": 0,
        "ammonito": False,
        "espulso": False,
    }

def ripristina_parametri_partita(partita_sel, p_dati, db_giocatori):
    """Riporta ai valori base i parametri della partita senza modificare il ruolo già impostato."""
    dati_attuali = p_dati.get("dati_prestazione", {})
    nuovi_dati = {}
    formazione = p_dati.get("formazione", {})

    for k_str, nome_g in formazione.items():
        if not nome_g:
            continue

        num_int = int(k_str) if str(k_str).isdigit() else 0
        is_portiere = str(k_str) in ["1", "12"]
        is_riserva = num_int >= 12

        prev_vals = dati_attuali.get(nome_g, {})
        base = valori_base_giocatore(
            nome_g, is_portiere=is_portiere, is_riserva=is_riserva, db_giocatori=db_giocatori
        )

        if not is_portiere:
            chiave_ruolo_widget = f"ruolo_res_{partita_sel}_{num_int}" if is_riserva else f"ruolo_{partita_sel}_{num_int}"
            ruolo_da_mantenere = (
                prev_vals.get("ruolo_campo")
                or st.session_state.get(chiave_ruolo_widget)
                or base["ruolo_campo"]
            )
            base["ruolo_campo"] = ruolo_da_mantenere

        nuovi_dati[nome_g] = base.copy()

        if not is_riserva:
            st.session_state[f"amm_{partita_sel}_{num_int}"] = False
            st.session_state[f"esp_{partita_sel}_{num_int}"] = False
            if is_portiere:
                st.session_state[f"min_{partita_sel}_{num_int}"] = int(base["minuti"])
                st.session_state[f"sic_{partita_sel}_{num_int}"] = str(base["sicurezza_portiere"])
                st.session_state[f"par_{partita_sel}_{num_int}"] = int(base["parate_decisive"])
                st.session_state[f"gsub_{partita_sel}_{num_int}"] = int(base["gol_subiti"])
                st.session_state[f"errp_{partita_sel}_{num_int}"] = int(base["errori_gravi"])
            else:
                st.session_state[f"min_{partita_sel}_{num_int}"] = int(base["minuti"])
                st.session_state[f"imp_{partita_sel}_{num_int}"] = str(base["impatto_partita"])
                st.session_state[f"ges_{partita_sel}_{num_int}"] = str(base["gestione_palla"])
                st.session_state[f"gol_{partita_sel}_{num_int}"] = int(base["gol_fatti"])
                st.session_state[f"ass_{partita_sel}_{num_int}"] = int(base["assist"])
                st.session_state[f"err_{partita_sel}_{num_int}"] = int(base["errori_gravi"])
        else:
            st.session_state[f"amm_res_{partita_sel}_{num_int}"] = False
            st.session_state[f"esp_res_{partita_sel}_{num_int}"] = False
            if is_portiere:
                st.session_state[f"min_res_{partita_sel}_{num_int}"] = int(base["minuti"])
                st.session_state[f"sic_res_{partita_sel}_{num_int}"] = str(base["sicurezza_portiere"])
                st.session_state[f"par_res_{partita_sel}_{num_int}"] = int(base["parate_decisive"])
                st.session_state[f"gsub_res_{partita_sel}_{num_int}"] = int(base["gol_subiti"])
                st.session_state[f"errp_res_{partita_sel}_{num_int}"] = int(base["errori_gravi"])
            else:
                st.session_state[f"min_res_{partita_sel}_{num_int}"] = int(base["minuti"])
                st.session_state[f"imp_res_{partita_sel}_{num_int}"] = str(base["impatto_partita"])
                st.session_state[f"ges_res_{partita_sel}_{num_int}"] = str(base["gestione_palla"])
                st.session_state[f"gol_res_{partita_sel}_{num_int}"] = int(base["gol_fatti"])
                st.session_state[f"ass_res_{partita_sel}_{num_int}"] = int(base["assist"])
                st.session_state[f"err_res_{partita_sel}_{num_int}"] = int(base["errori_gravi"])

    p_dati["dati_prestazione"] = nuovi_dati
    st.session_state["partita_attiva"] = partita_sel
    salva_dati_su_disco()

def parse_frazione(val_str):
    """Restituisce (numeratore, denominatore) da stringhe tipo '5/5' o '0/1'."""
    try:
        parti = str(val_str).strip().split("/")
        if len(parti) == 2:
            return int(parti[0].strip()), int(parti[1].strip())
    except Exception:
        pass
    return 0, 0

def hex_to_rgba(hex_color, alpha):
    """Converte un colore HEX (#rrggbb) in stringa rgba(r, g, b, alpha)."""
    h = (hex_color or "#10b981").lstrip("#")
    if len(h) != 6:
        return f"rgba(16, 185, 129, {alpha:.2f})"
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    alpha_clamped = max(0.0, min(1.0, float(alpha)))
    return f"rgba({r}, {g}, {b}, {alpha_clamped:.2f})"

# =====================================================================
# GESTIONE LOGO, IMMAGINE HOME, FOTO GIOCATORI, SICUREZZA & SYNC GITHUB
# =====================================================================
LOGO_PATH = "Channel logo.jpg" if os.path.exists("Channel logo.jpg") else ("logo.png" if os.path.exists("logo.png") else None)
HOME_IMAGE_PATH = "eagle.jpg" if os.path.exists("eagle.jpg") else ("eagle.png" if os.path.exists("eagle.png") else None)
DB_FILE = "scoutai_database.json"
PLAYER_PHOTOS_DIR = "player_photos"

def _hash_pin(pin_str):
    return hashlib.sha256((pin_str or "").encode("utf-8")).hexdigest()

def salva_foto_giocatore(nome_giocatore, uploaded_file):
    """Salva l'immagine caricata in player_photos/ e restituisce il percorso relativo."""
    if not uploaded_file or not nome_giocatore:
        return None
    os.makedirs(PLAYER_PHOTOS_DIR, exist_ok=True)
    ext = os.path.splitext(uploaded_file.name or "")[1].lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        ext = ".png"
    safe_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", nome_giocatore.strip()).strip("_") or "giocatore"
    file_path = os.path.join(PLAYER_PHOTOS_DIR, f"{safe_slug}{ext}")
    uploaded_file.seek(0)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def ottieni_foto_valida(nome_giocatore, db_giocatori):
    """Restituisce il percorso della foto se esiste davvero su disco, altrimenti None."""
    foto_path = db_giocatori.get(nome_giocatore, {}).get("foto_path")
    if foto_path and os.path.exists(foto_path):
        return foto_path
    return None

def costruisci_payload_database():
    """Restituisce il dizionario completo dello stato/database salvabile su disco o in backup JSON."""
    return {
        "giocatori": st.session_state.get("database_giocatori", {}),
        "partite": st.session_state.get("database_partite", {}),
        "partita_attiva": st.session_state.get("partita_attiva"),
        "ui_theme": st.session_state.get("ui_theme", {}),
        "fullscreen_mode": st.session_state.get("fullscreen_mode", False),
        "auth_config": st.session_state.get("auth_config", {}),
        "statistiche_accessi": st.session_state.get("statistiche_accessi", {}),
        "ultimo_utente_home": st.session_state.get("ultimo_utente_home", ""),
    }

def applica_payload_database(payload):
    """Applica un dizionario di backup/database validato allo session_state e lo salva su disco."""
    if not isinstance(payload, dict):
        return False, "Il file JSON non contiene un oggetto valido."

    giocatori_imp = payload.get("giocatori")
    partite_imp = payload.get("partite")
    if not isinstance(giocatori_imp, dict) or not isinstance(partite_imp, dict):
        return False, "Il JSON deve contenere almeno i campi 'giocatori' e 'partite' (oggetti)."

    st.session_state["database_giocatori"] = giocatori_imp
    st.session_state["database_partite"] = partite_imp
    st.session_state["partita_attiva"] = payload.get("partita_attiva")

    if isinstance(payload.get("ui_theme"), dict) and payload["ui_theme"]:
        merged_theme = PRESET_TEMI["Emerald Dark (Default)"].copy()
        merged_theme.update(payload["ui_theme"])
        st.session_state["ui_theme"] = merged_theme

    if "fullscreen_mode" in payload:
        st.session_state["fullscreen_mode"] = bool(payload.get("fullscreen_mode", False))

    if isinstance(payload.get("auth_config"), dict) and payload["auth_config"]:
        cfg_imp = payload["auth_config"].copy()
        cfg_imp.setdefault("admin_pin_hash", _hash_pin("1234"))
        cfg_imp.setdefault("read_only_boys", True)
        cfg_imp.setdefault("sezioni_ragazzi", [
            "🎥 Video Analisi",
            "📈 Riepilogo Squadra",
            "📊 Grafici & Analisi Visiva",
            "🟨 Fair Play",
        ])
        cfg_imp.setdefault("schede_attive", TUTTE_LE_SCHEDE_APP.copy())
        cfg_imp.setdefault("applica_nascoste_ad_admin", False)
        st.session_state["auth_config"] = cfg_imp

    if isinstance(payload.get("statistiche_accessi"), dict):
        st.session_state["statistiche_accessi"] = payload["statistiche_accessi"]

    if "ultimo_utente_home" in payload:
        st.session_state["ultimo_utente_home"] = str(payload.get("ultimo_utente_home") or "")

    salva_dati_su_disco()
    return True, f"Backup importato: {len(giocatori_imp)} giocatori e {len(partite_imp)} partite ripristinati."

def _get_github_sync_cfg():
    """Legge la configurazione [github_sync] da st.secrets se presente e completa."""
    try:
        cfg = st.secrets.get("github_sync", {})
    except Exception:
        return None
    if not cfg:
        return None
    token = str(cfg.get("token", "")).strip()
    owner = str(cfg.get("owner", "")).strip()
    repo = str(cfg.get("repo", "")).strip()
    path = str(cfg.get("path", "scoutai_state.json")).strip().lstrip("/")
    branch = str(cfg.get("branch", "main")).strip()
    if not (token and owner and repo and path):
        return None
    return {
        "token": token,
        "owner": owner,
        "repo": repo,
        "path": path,
        "branch": branch,
    }

def _github_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def _leggi_json_github(cfg):
    """Restituisce (payload_dict, sha_str) oppure (None, None) se il file non esiste ancora."""
    url = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/contents/{cfg['path']}"
    resp = requests.get(
        url,
        headers=_github_headers(cfg["token"]),
        params={"ref": cfg["branch"]},
        timeout=15,
    )
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()

    body = resp.json()
    sha = body.get("sha")
    raw_b64 = (body.get("content") or "").replace("\n", "")
    if not raw_b64:
        return None, sha
    decoded_text = base64.b64decode(raw_b64).decode("utf-8")
    return json.loads(decoded_text), sha

def _scrivi_json_github(cfg, payload_dict, commit_message="Aggiorna stato ScoutAI"):
    """Crea o aggiorna il file JSON su GitHub; in caso di 409/422 rilegge lo SHA più recente e ritenta."""
    url = f"https://api.github.com/repos/{cfg['owner']}/{cfg['repo']}/contents/{cfg['path']}"
    json_bytes = json.dumps(payload_dict, ensure_ascii=False, indent=2).encode("utf-8")
    encoded_content = base64.b64encode(json_bytes).decode("ascii")

    _, sha = _leggi_json_github(cfg)
    data = {
        "message": commit_message,
        "content": encoded_content,
        "branch": cfg["branch"],
    }
    if sha:
        data["sha"] = sha

    resp = requests.put(url, headers=_github_headers(cfg["token"]), json=data, timeout=15)
    if resp.status_code in (409, 422):
        _, sha_aggiornato = _leggi_json_github(cfg)
        if sha_aggiornato:
            data["sha"] = sha_aggiornato
        else:
            data.pop("sha", None)
        resp = requests.put(url, headers=_github_headers(cfg["token"]), json=data, timeout=15)

    resp.raise_for_status()

def salva_dati_su_disco():
    """Salva lo stato in locale (se possibile) e lo sincronizza su GitHub se configurato in st.secrets."""
    data_to_save = costruisci_payload_database()
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Errore durante il salvataggio locale: {e}")

    gh_cfg = _get_github_sync_cfg()
    if gh_cfg:
        try:
            _scrivi_json_github(
                gh_cfg,
                data_to_save,
                commit_message=f"Sync stato ScoutAI ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
            )
        except Exception as e:
            print(f"Errore sincronizzazione GitHub: {e}")

def carica_dati_da_disco():
    """Carica il JSON di stato da GitHub se configurato in st.secrets, con fallback al file locale."""
    gh_cfg = _get_github_sync_cfg()
    if gh_cfg:
        try:
            payload_gh, _ = _leggi_json_github(gh_cfg)
            if isinstance(payload_gh, dict):
                return payload_gh
        except Exception as e:
            print(f"Errore lettura GitHub: {e}")

    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def inizializza_sicurezza_ruoli(dati_salvati):
    if "auth_config" not in st.session_state:
        cfg_salvata = (dati_salvati or {}).get("auth_config", {})
        st.session_state["auth_config"] = {
            "admin_pin_hash": cfg_salvata.get("admin_pin_hash") or _hash_pin("1234"),
            "read_only_boys": bool(cfg_salvata.get("read_only_boys", True)),
            "sezioni_ragazzi": cfg_salvata.get("sezioni_ragazzi") or [
                "🎥 Video Analisi",
                "📈 Riepilogo Squadra",
                "📊 Grafici & Analisi Visiva",
                "🟨 Fair Play",
            ],
            "schede_attive": [
                s for s in (cfg_salvata.get("schede_attive") or TUTTE_LE_SCHEDE_APP)
                if s in TUTTE_LE_SCHEDE_APP
            ] or TUTTE_LE_SCHEDE_APP.copy(),
            "applica_nascoste_ad_admin": bool(cfg_salvata.get("applica_nascoste_ad_admin", False)),
        }
    else:
        cfg = st.session_state["auth_config"]
        cfg.setdefault("schede_attive", TUTTE_LE_SCHEDE_APP.copy())
        cfg.setdefault("applica_nascoste_ad_admin", False)
    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False

def is_sola_lettura():
    """Restituisce True se l'utente corrente è in modalità lettura limitata (ragazzi)."""
    return (not st.session_state.get("is_admin", False)) and bool(
        st.session_state.get("auth_config", {}).get("read_only_boys", True)
    )

def render_controllo_schede_ui(key_prefix="admin"):
    """Controllo condiviso per attivare/nascondere le schede da Pannello Admin o Editor Grafica."""
    cfg = st.session_state["auth_config"]
    schede_correnti = [
        s for s in cfg.get("schede_attive", TUTTE_LE_SCHEDE_APP)
        if s in TUTTE_LE_SCHEDE_APP
    ] or TUTTE_LE_SCHEDE_APP.copy()

    st.markdown("#### 🗂️ Attiva o Nascondi Schede")
    st.caption("Seleziona le schede da mantenere attive nel menu laterale. Le deselezionate vengono nascoste.")

    nuove_attive = []
    cols_s = st.columns(2)
    for idx, nome_scheda in enumerate(TUTTE_LE_SCHEDE_APP):
        with cols_s[idx % 2]:
            attiva = st.checkbox(
                nome_scheda,
                value=(nome_scheda in schede_correnti),
                key=f"chk_scheda_{key_prefix}_{idx}"
            )
            if attiva:
                nuove_attive.append(nome_scheda)

    applica_admin = st.toggle(
        "Nascondi schede deselezionate anche quando sono in modalità Admin",
        value=bool(cfg.get("applica_nascoste_ad_admin", False)),
        key=f"tgl_nascoste_admin_{key_prefix}"
    )

    if not nuove_attive:
        st.warning("⚠️ Devi lasciare attiva almeno una scheda: se le deselezioni tutte verrà mantenuta '📈 Riepilogo Squadra'.")

    return nuove_attive if nuove_attive else ["📈 Riepilogo Squadra"], bool(applica_admin)

def estrai_youtube_id(url):
    if not url:
        return None
    patterns = [
        r'(?:v=|\/v\/|embed\/|e\/|watch\?v=|watch\?.+&v=)([\w-]{11})',
        r'(?:youtu\.be\/)([\w-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    if len(url) == 11:
        return url
    return None

def parse_data_partita(data_str):
    """Converte una stringa data in oggetto datetime per ordinamento sicuro."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(data_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.min

# =====================================================================
# INIZIALIZZAZIONE STATO TEMA & DATABASE
# =====================================================================
PRESET_TEMI = {
    "Emerald Dark (Default)": {
        "bg_main": "#090a0f", "bg_card": "#141721", "bg_sidebar": "#12141c",
        "accent": "#10b981", "text_color": "#f3f4f6", "border_color": "#1e2230",
        "border_radius": 12, "font_size": 16, "shadow_intensity": 25,
        "glow_intensity": 25, "glow_width": 14, "custom_css": ""
    },
    "Tactical Blue": {
        "bg_main": "#070d19", "bg_card": "#0f172a", "bg_sidebar": "#0b1120",
        "accent": "#3b82f6", "text_color": "#f8fafc", "border_color": "#1e293b",
        "border_radius": 10, "font_size": 16, "shadow_intensity": 30,
        "glow_intensity": 30, "glow_width": 16, "custom_css": ""
    },
    "Matchday Crimson": {
        "bg_main": "#12090b", "bg_card": "#1f1014", "bg_sidebar": "#180c0f",
        "accent": "#ef4444", "text_color": "#fef2f2", "border_color": "#381a21",
        "border_radius": 8, "font_size": 16, "shadow_intensity": 20,
        "glow_intensity": 25, "glow_width": 14, "custom_css": ""
    }
}

dati_salvati = carica_dati_da_disco()
inizializza_sicurezza_ruoli(dati_salvati)

if "home_entered" not in st.session_state:
    st.session_state["home_entered"] = False

if "statistiche_accessi" not in st.session_state:
    st.session_state["statistiche_accessi"] = (
        dati_salvati.get("statistiche_accessi", {}) if isinstance(dati_salvati, dict) else {}
    )

if "ultimo_utente_home" not in st.session_state:
    st.session_state["ultimo_utente_home"] = (
        dati_salvati.get("ultimo_utente_home", "") if isinstance(dati_salvati, dict) else ""
    )

if "utente_attivo" not in st.session_state:
    st.session_state["utente_attivo"] = ""

if "ui_theme" not in st.session_state:
    base_theme = PRESET_TEMI["Emerald Dark (Default)"].copy()
    if dati_salvati and isinstance(dati_salvati.get("ui_theme"), dict) and dati_salvati["ui_theme"]:
        base_theme.update(dati_salvati["ui_theme"])
    base_theme.setdefault("glow_intensity", 25)
    base_theme.setdefault("glow_width", 14)
    base_theme.setdefault("shadow_intensity", 25)
    base_theme.setdefault("font_size", 16)
    st.session_state["ui_theme"] = base_theme

if "fullscreen_mode" not in st.session_state:
    st.session_state["fullscreen_mode"] = bool(dati_salvati.get("fullscreen_mode", False)) if dati_salvati else False

if "last_auto_save" not in st.session_state:
    st.session_state["last_auto_save"] = time.time()

if "ui_notice" not in st.session_state:
    st.session_state["ui_notice"] = None

if dati_salvati:
    if "database_giocatori" not in st.session_state:
        st.session_state["database_giocatori"] = dati_salvati.get("giocatori", {})
    if "database_partite" not in st.session_state:
        st.session_state["database_partite"] = dati_salvati.get("partite", {})
    if "partita_attiva" not in st.session_state:
        st.session_state["partita_attiva"] = dati_salvati.get("partita_attiva")
else:
    if "database_giocatori" not in st.session_state:
        st.session_state["database_giocatori"] = {
            "Lorenzo": {"ruolo": "Portiere (POR)", "partite": {}, "foto_path": None},
            "Mattia": {"ruolo": "Difensore Centrale (DC)", "partite": {}, "foto_path": None},
            "Filippo": {"ruolo": "Centrocampista (CC)", "partite": {}, "foto_path": None},
            "Davide": {"ruolo": "Attaccante (ATT)", "partite": {}, "foto_path": None},
            "Simone": {"ruolo": "Terzino (TS/TD)", "partite": {}, "foto_path": None},
            "Federico": {"ruolo": "Centrocampista (CC)", "partite": {}, "foto_path": None},
            "Alessandro": {"ruolo": "Attaccante (ATT)", "partite": {}, "foto_path": None},
            "Luca": {"ruolo": "Difensore Centrale (DC)", "partite": {}, "foto_path": None},
            "Marco": {"ruolo": "Esterno (EST)", "partite": {}, "foto_path": None},
            "Giovanni": {"ruolo": "Centrocampista (CC)", "partite": {}, "foto_path": None},
            "Tommaso": {"ruolo": "Attaccante (ATT)", "partite": {}, "foto_path": None},
            "Pietro": {"ruolo": "Portiere (POR)", "partite": {}, "foto_path": None},
            "Riccardo": {"ruolo": "Riserva / Jolly", "partite": {}, "foto_path": None},
            "Edoardo": {"ruolo": "Riserva / Jolly", "partite": {}, "foto_path": None}
        }
    if "database_partite" not in st.session_state:
        st.session_state["database_partite"] = {
            "Virtus (15/03/2026)": {
                "avversario": "Virtus", "data": "15/03/2026", "modulo": "4-4-2",
                "risultato": "N.D.", "casa_trasferta": "Casa", "youtube_link": "",
                "formazione": {str(i): (list(st.session_state["database_giocatori"].keys())[i-1] if i <= len(st.session_state["database_giocatori"]) else "") for i in range(1, 21)},
                "dati_prestazione": {}
            }
        }
    if "partita_attiva" not in st.session_state:
        st.session_state["partita_attiva"] = "Virtus (15/03/2026)"
    salva_dati_su_disco()

tema = st.session_state["ui_theme"]
is_fullscreen = st.session_state["fullscreen_mode"]

# =====================================================================
# APPLICAZIONE CSS & UI (GLOW + OMBREGGIATURA ESTERNA SU TUTTI I BOX)
# =====================================================================
ombra_alfa = tema.get("shadow_intensity", 25) / 100.0
accent_hex = tema.get("accent", "#10b981")
glow_intensita_alfa = tema.get("glow_intensity", 25) / 100.0
glow_larghezza_px = int(tema.get("glow_width", 14))
font_size_px = int(tema.get("font_size", 16))
radius_px = int(tema.get("border_radius", 12))

glow_rgba = hex_to_rgba(accent_hex, glow_intensita_alfa)
glow_soft_rgba = hex_to_rgba(accent_hex, glow_intensita_alfa * 0.55)
glow_border_rgba = hex_to_rgba(accent_hex, min(0.85, max(0.22, glow_intensita_alfa * 1.4)))

box_shadow_glow = f"0 8px 20px rgba(0, 0, 0, {ombra_alfa:.2f}), 0 0 {glow_larghezza_px}px {glow_rgba}"
box_shadow_soft = f"0 4px 12px rgba(0, 0, 0, {max(0.15, ombra_alfa * 0.75):.2f}), 0 0 {max(4, (glow_larghezza_px * 2) // 3)}px {glow_soft_rgba}"
fullscreen_css = "[data-testid=\"stSidebar\"] {display: none !important;} header {visibility: hidden !important;}" if is_fullscreen else ""

st.markdown(f"""
<style>
    .stApp {{ background-color: {tema['bg_main']}; color: {tema['text_color']}; font-size: {font_size_px}px; }}
    .block-container {{ max-width: 100% !important; padding: 2rem 3rem !important; }}
    h1, h2, h3, h4, h5, h6, p, label, .stMarkdown, span {{ color: {tema['text_color']} !important; }}

    [data-testid="stSidebar"] {{
        background-color: {tema['bg_sidebar']};
        border-right: 1px solid {glow_border_rgba};
        box-shadow: 4px 0 18px rgba(0, 0, 0, {max(0.2, ombra_alfa):.2f}), 0 0 {max(6, glow_larghezza_px)}px {glow_soft_rgba};
    }}

    [data-testid="stForm"] {{
        background-color: {tema['bg_card']} !important;
        border: 1px solid {glow_border_rgba} !important;
        border-radius: {radius_px}px !important;
        padding: 20px !important;
        box-shadow: {box_shadow_glow};
    }}

    [data-testid="stMetric"], div[data-baseweb="notification"], .stAlert, [data-testid="stFileUploader"] > section {{
        background-color: {tema['bg_card']} !important;
        border: 1px solid {glow_border_rgba} !important;
        color: {tema['text_color']} !important;
        padding: 18px;
        border-radius: {radius_px}px;
        box-shadow: {box_shadow_glow};
    }}
    [data-testid="stMetricValue"] {{ color: {accent_hex} !important; }}

    .stButton > button, .stDownloadButton > button {{
        background-color: #1a1d29 !important; color: #ffffff !important;
        border-radius: {radius_px}px !important; border: 1px solid {glow_border_rgba} !important; font-weight: 600 !important;
        padding: 0.6rem 1.2rem !important; width: 100% !important;
        box-shadow: {box_shadow_soft};
        transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        background-color: #ef4444 !important; border-color: #ef4444 !important; color: #ffffff !important;
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35), 0 0 {glow_larghezza_px}px rgba(239, 68, 68, 0.45);
    }}

    [data-testid="stExpander"] {{
        background-color: {tema['bg_card']} !important;
        border: 1px solid {glow_border_rgba} !important;
        border-radius: {radius_px}px !important;
        box-shadow: {box_shadow_glow};
    }}
    [data-testid="stExpander"] summary {{
        font-size: 20px !important;
        font-weight: bold !important;
        text-align: center !important;
        justify-content: center !important;
        padding: 4px !important;
    }}
    [data-testid="stExpander"] summary p {{
        text-align: center !important;
        width: 100% !important;
    }}

    input, textarea, select, div[data-baseweb="input"] > div, div[data-baseweb="select"] > div {{
        background-color: {tema['bg_card']} !important;
        color: {tema['text_color']} !important;
        border-color: {glow_border_rgba} !important;
        border-radius: {max(4, radius_px - 4)}px !important;
        box-shadow: {box_shadow_soft};
    }}

    table {{
        background-color: {tema['bg_card']};
        border-radius: {radius_px}px;
        overflow: hidden;
        border: 1px solid {glow_border_rgba};
        width: 100% !important;
        box-shadow: {box_shadow_glow};
    }}
    th {{ background-color: {accent_hex} !important; color: #ffffff !important; text-align: center !important; }}
    td {{ color: {tema['text_color']} !important; border-color: {tema['border_color']} !important; }}

    .scoutai-box {{
        background-color: {tema['bg_card']};
        border: 1px solid {glow_border_rgba};
        border-radius: {radius_px}px;
        padding: 20px;
        box-shadow: {box_shadow_glow};
    }}

    .scoutai-voto-box {{
        background-color: #1e2230;
        border: 1px solid {accent_hex};
        box-shadow: {box_shadow_glow};
        padding: 8px;
        border-radius: {max(6, radius_px - 4)}px;
        text-align: center;
        margin-top: 24px;
    }}

    .scoutai-area-badge {{
        display: inline-block;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.6px;
        text-transform: uppercase;
        padding: 2px 8px;
        border-radius: 999px;
        background-color: {hex_to_rgba(accent_hex, 0.16)};
        border: 1px solid {glow_border_rgba};
        color: {accent_hex} !important;
        margin-left: 8px;
    }}

    .scoutai-fp-dot {{
        width: 12px;
        height: 12px;
        border-radius: 50%;
        display: inline-block;
        vertical-align: middle;
        margin-top: 8px;
    }}

    .scoutai-video-empty {{
        background-color: {tema['bg_card']};
        border: 2px dashed {glow_border_rgba};
        border-radius: {radius_px}px;
        height: 260px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        padding: 20px;
        box-shadow: {box_shadow_glow};
    }}

    .scoutai-theme-toast {{
        background-color: {tema['bg_card']};
        border: 1px solid {accent_hex};
        border-left: 5px solid {accent_hex};
        border-radius: {radius_px}px;
        padding: 14px 18px;
        margin: 10px 0 18px 0;
        box-shadow: 0 10px 24px rgba(0, 0, 0, {max(0.25, ombra_alfa):.2f}), 0 0 {max(10, glow_larghezza_px + 4)}px {glow_rgba};
        display: flex;
        align-items: center;
        gap: 12px;
    }}

    @media (max-width: 768px) {{
        .block-container {{
            padding: 1rem 0.9rem !important;
        }}
        .scoutai-box {{
            padding: 14px !important;
        }}
        [data-testid="stMetric"] {{
            padding: 12px !important;
        }}
        .stButton > button, .stDownloadButton > button {{
            min-height: 44px !important;
            padding: 0.65rem 1rem !important;
        }}
    }}
    {fullscreen_css}
</style>
""", unsafe_allow_html=True)

def mostra_notifica_tema(messaggio, icona="✅"):
    st.markdown(f"""
    <div class="scoutai-theme-toast">
        <span style="font-size: 20px; line-height: 1;">{icona}</span>
        <div style="font-weight: 600; color: {tema['text_color']};">{messaggio}</div>
    </div>
    """, unsafe_allow_html=True)

# =====================================================================
# SCHERMATA HOME DI ACCESSO
# =====================================================================
if not st.session_state["home_entered"]:
    sincronizza_client_localstorage(utente_da_salvare=None)

    st.markdown(f"""
    <style>
        [data-testid="stSidebar"] {{ display: none !important; }}
        header {{ visibility: hidden !important; }}
        .scoutai-home-banner {{
            max-width: 860px;
            margin: 0.5rem auto 0.75rem auto;
            padding: 14px 18px;
            text-align: center;
            background-color: {tema['bg_card']};
            border: 1px solid {accent_hex};
            border-radius: {radius_px}px;
            box-shadow: {box_shadow_glow};
        }}
        .scoutai-home-kicker {{
            margin: 0 0 4px 0;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1.8px;
            color: {accent_hex} !important;
        }}
        .scoutai-home-title {{
            margin: 0;
            font-size: clamp(17px, 2.2vw, 24px);
            font-weight: 800;
            line-height: 1.2;
            color: {tema['text_color']} !important;
        }}
    </style>
    """, unsafe_allow_html=True)

    _, col_home, _ = st.columns([0.16, 0.68, 0.16])
    with col_home:
        st.markdown(
            "<div class='scoutai-home-banner'>"
            "<div class='scoutai-home-kicker'>ScoutAI · Match Analysis</div>"
            "<h1 class='scoutai-home-title'>Benvenuti nella fortezza dei dati dell'USO NUVOLENTO - 2011</h1>"
            "</div>",
            unsafe_allow_html=True,
        )

        opzioni_home = ottieni_opzioni_accesso_home(st.session_state.get("database_giocatori", {}))
        qp_utente = st.query_params.get("utente", "")
        if qp_utente in opzioni_home:
            default_utente = qp_utente
        elif st.session_state.get("utente_attivo") in opzioni_home:
            default_utente = st.session_state["utente_attivo"]
        elif st.session_state.get("ultimo_utente_home") in opzioni_home:
            default_utente = st.session_state["ultimo_utente_home"]
        else:
            default_utente = opzioni_home[0]

        col_sel_u, col_btn_u = st.columns([1.4, 1.0])
        with col_sel_u:
            utente_scelto = st.selectbox(
                "Chi sta accedendo",
                options=opzioni_home,
                index=opzioni_home.index(default_utente),
                key="sel_utente_home",
                label_visibility="collapsed"
            )
        with col_btn_u:
            clic_inizia = st.button("Inizia l'analisi", use_container_width=True, key="btn_inizia_analisi")

        stat_u = st.session_state.get("statistiche_accessi", {}).get(
            utente_scelto, {"count": 0, "ultimo_accesso": "Mai"}
        )
        st.caption(
            f"👤 Utente selezionato: **{utente_scelto}** · Accessi totali: **{stat_u.get('count', 0)}** "
            f"(Ultimo: {stat_u.get('ultimo_accesso', 'Mai')})"
        )

        if clic_inizia:
            stats = st.session_state.setdefault("statistiche_accessi", {})
            rec = stats.get(utente_scelto, {"count": 0, "ultimo_accesso": ""})
            rec["count"] = int(rec.get("count", 0)) + 1
            rec["ultimo_accesso"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            stats[utente_scelto] = rec

            st.session_state["ultimo_utente_home"] = utente_scelto
            st.session_state["utente_attivo"] = utente_scelto
            st.session_state["salva_utente_su_client"] = utente_scelto
            st.session_state["home_entered"] = True
            st.query_params["utente"] = utente_scelto
            salva_dati_su_disco()
            st.rerun()

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        if HOME_IMAGE_PATH and os.path.exists(HOME_IMAGE_PATH):
            st.image(HOME_IMAGE_PATH, use_container_width=True)
        else:
            st.info("Salva l'immagine come `eagle.jpg` nella cartella dell'app per mostrarla nella schermata Home.")

    st.stop()

# =====================================================================
# PERSISTENZA CLIENT (SALVA UTENTE IN LOCALSTORAGE DOPO IL PRIMO ACCESSO)
# =====================================================================
if st.session_state.get("salva_utente_su_client"):
    sincronizza_client_localstorage(utente_da_salvare=st.session_state["salva_utente_su_client"])
    st.session_state["salva_utente_su_client"] = None

# =====================================================================
# HEADER CON LOGO IN ALTO A SINISTRA
# =====================================================================
col_logo_h, col_title_h = [st.columns([0.08, 0.92])[i] for i in range(2)]
with col_logo_h:
    if LOGO_PATH and os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=65)
    else:
        st.markdown("⚽")
with col_title_h:
    st.markdown("<h2 style='margin-bottom:0; padding-top:8px;'>USO Nuvolento - ScoutAI Match Analysis</h2>", unsafe_allow_html=True)

st.divider()

# =====================================================================
# MOTORE DI CALCOLO VOTO SNELLO & VISIVO (PESATO PER AREA DI GIOCO + ESPULSIONE -1)
# =====================================================================
def calcola_voto(p, is_portiere=False):
    try:
        minuti_giocati = int(p.get("minuti", 80))
        if minuti_giocati <= 0:
            return None

        fattore_tempo = min(1.0, max(0.35, minuti_giocati / 60.0))
        rating = 6.0

        if is_portiere:
            dati_p = estrai_dati_portiere_compat(p)
            delta_sic = DELTA_SICUREZZA_PORTIERE.get(dati_p["sicurezza_portiere"], 0.0)
            parate_dec = dati_p["parate_decisive"]
            gol_sub = dati_p["gol_subiti"]
            errori_g = dati_p["errori_gravi"]

            rating += delta_sic * fattore_tempo
            rating += parate_dec * 0.5
            rating -= gol_sub * 0.3
            rating -= errori_g * 1.0
            if dati_p["espulso"]:
                rating -= 1.0
        else:
            ruolo_campo = p.get("ruolo_campo", "CC")
            macro_ruolo = get_macro_ruolo(ruolo_campo)
            pesi = PESI_AREA_GIOCO[macro_ruolo]

            dati_m = estrai_dati_movimento_compat(p)
            delta_imp = DELTA_IMPATTO_PARTITA.get(dati_m["impatto_partita"], 0.0)
            delta_ges = DELTA_GESTIONE_PALLA.get(dati_m["gestione_palla"], 0.0)
            gol_fatti = dati_m["gol_fatti"]
            assist = dati_m["assist"]
            errori_gravi = dati_m["errori_gravi"]

            rating += (delta_imp * pesi["impatto"]) * fattore_tempo
            rating += (delta_ges * pesi["gestione"]) * fattore_tempo
            rating += gol_fatti * 1.0
            rating += assist * (0.5 * pesi["assist"])
            rating -= errori_gravi * (0.6 * pesi["errori"])
            if dati_m["espulso"]:
                rating -= 1.0

        return round(max(1.0, min(10.0, rating)), 1)
    except Exception:
        return 6.0

def calcola_trend_giocatore(storico_voti):
    if len(storico_voti) < 2:
        return "Stabile (↔️)"
    diff = round(storico_voti[-1] - (sum(storico_voti[:-1]) / len(storico_voti[:-1])), 1)
    if diff > 0:
        return f"In Crescita 📈 (+{diff})"
    elif diff < 0:
        return f"In Decrescita 📉 ({diff})"
    return "Stabile (↔️)"

# =====================================================================
# GENERATORE PDF (OPZIONALE SE REPORTLAB È DISPONIBILE)
# =====================================================================
def _crea_immagine_pdf_adattata(img_path, max_w=34, max_h=34):
    """Crea un RLImage proporzionato entro max_w x max_h senza distorcere la foto."""
    if not img_path or not os.path.exists(img_path):
        return None
    try:
        if PIL_AVAILABLE:
            with PILImage.open(img_path) as im:
                w, h = im.size
                if w > 0 and h > 0:
                    scala = min(max_w / float(w), max_h / float(h))
                    return RLImage(img_path, width=max(12.0, w * scala), height=max(12.0, h * scala))
        return RLImage(img_path, width=max_w, height=max_h)
    except Exception:
        return None

def genera_pdf_partita(match_name, match_data, db_giocatori, accent_hex):
    if not REPORTLAB_AVAILABLE:
        return None
    filename = f"Report_Partita_{match_name.replace(' ', '_')}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold',
        fontSize=15, textColor=colors.HexColor(accent_hex), alignment=1, spaceAfter=8
    )
    sub_style = ParagraphStyle(
        'SubStyle', parent=styles['Normal'], fontName='Helvetica',
        fontSize=10, textColor=colors.HexColor("#cccccc"), alignment=1, spaceAfter=15
    )
    cell_style = ParagraphStyle(
        'CellStyle', parent=styles['Normal'], fontName='Helvetica',
        fontSize=8.5, textColor=colors.whitesmoke, alignment=1, leading=10
    )

    if LOGO_PATH and os.path.exists(LOGO_PATH):
        logo_pdf = _crea_immagine_pdf_adattata(LOGO_PATH, max_w=50, max_h=50)
        if logo_pdf:
            elements.append(logo_pdf)

    elements.append(Paragraph(f"<b>USO Nuvolento - Report Partita: {match_name}</b>", title_style))
    elements.append(Paragraph(
        f"<b>Avversario:</b> {match_data.get('avversario', '')} | "
        f"<b>Risultato:</b> {match_data.get('risultato', 'N.D.')} | "
        f"<b>{match_data.get('casa_trasferta', 'Casa')}</b>",
        sub_style
    ))
    elements.append(Paragraph(
        f"<b>Modulo:</b> {match_data['modulo']} | <b>Data:</b> {match_data['data']}",
        sub_style
    ))
    elements.append(Spacer(1, 10))

    t_data = [["N°", "Foto", "Giocatore", "Ruolo / Area", "Min.", "Valutazione Rapida", "Voto"]]
    for num, nome in match_data["formazione"].items():
        if not nome:
            continue
        p_dati = match_data.get("dati_prestazione", {}).get(nome, {})
        is_portiere = (str(num) in ["1", "12"])
        voto_calcolato = calcola_voto(p_dati, is_portiere) if p_dati else None
        voto = str(voto_calcolato) if voto_calcolato is not None else "N.D."
        fp = estrai_fairplay_compat(p_dati)
        fp_txt = []
        if fp["ammonito"]:
            fp_txt.append("Amm.")
        if fp["espulso"]:
            fp_txt.append("Esp.")
        fp_suffix = f" | FP: {','.join(fp_txt)}" if fp_txt else ""

        if is_portiere:
            ruolo_label = "POR (Porta)"
            dp = estrai_dati_portiere_compat(p_dati)
            stats = (
                f"Sicurezza: {dp['sicurezza_portiere']} | "
                f"Parate dec.: {dp['parate_decisive']} | "
                f"Gol sub.: {dp['gol_subiti']} | "
                f"Errori: {dp['errori_gravi']}{fp_suffix}"
            )
        else:
            ruolo_c = p_dati.get("ruolo_campo") or ruolo_default_da_rosa(
                db_giocatori.get(nome, {}).get("ruolo", "")
            )
            ruolo_label = f"{ruolo_c} ({get_etichetta_area(ruolo_c)})"
            dm = estrai_dati_movimento_compat(p_dati)
            stats = (
                f"Impatto: {dm['impatto_partita']} | "
                f"Palla: {dm['gestione_palla']} | "
                f"Gol: {dm['gol_fatti']} | "
                f"Assist: {dm['assist']} | "
                f"Errori: {dm['errori_gravi']}{fp_suffix}"
            )

        foto_path = ottieni_foto_valida(nome, db_giocatori)
        foto_cell = _crea_immagine_pdf_adattata(foto_path, max_w=28, max_h=28) if foto_path else Paragraph("-", cell_style)

        t_data.append([
            str(num),
            foto_cell,
            Paragraph(nome, cell_style),
            Paragraph(ruolo_label, cell_style),
            f"{p_dati.get('minuti', 80)}'",
            Paragraph(stats, cell_style),
            str(voto)
        ])

    t = Table(t_data, colWidths=[28, 36, 85, 82, 40, 214, 40], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(accent_hex)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#333333")),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#141721")),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
    ]))
    elements.append(t)
    doc.build(elements)
    return filename

# =====================================================================
# SIDEBAR, LOGIN ADMIN, PERSISTENZA SELEZIONE PARTITA & NAVIGAZIONE
# =====================================================================
db_giocatori = st.session_state["database_giocatori"]
db_partite = st.session_state["database_partite"]
auth_cfg = st.session_state["auth_config"]

if time.time() - st.session_state["last_auto_save"] > 30:
    st.session_state["last_auto_save"] = time.time()
    salva_dati_su_disco()

partite_ordinate_chiavi = [
    item[0] for item in sorted(
        db_partite.items(),
        key=lambda x: parse_data_partita(x[1].get("data", "01/01/2026"))
    )
]

if partite_ordinate_chiavi:
    if st.session_state.get("partita_attiva") not in partite_ordinate_chiavi:
        st.session_state["partita_attiva"] = partite_ordinate_chiavi[0]
else:
    st.session_state["partita_attiva"] = None

def get_partita_attiva_corrente():
    if not partite_ordinate_chiavi:
        return None
    curr = st.session_state.get("partita_attiva")
    if curr in partite_ordinate_chiavi:
        return curr
    st.session_state["partita_attiva"] = partite_ordinate_chiavi[0]
    return partite_ordinate_chiavi[0]

def selettore_partita_persistente(label, widget_key):
    """Renderizza un selectbox sincronizzato con partita_attiva e salvato su disco al cambio."""
    if not partite_ordinate_chiavi:
        return st.selectbox(label, ["Nessuna Partita"], key=widget_key)

    corrente = get_partita_attiva_corrente()
    idx = partite_ordinate_chiavi.index(corrente) if corrente in partite_ordinate_chiavi else 0

    def _on_change_partita():
        scelta = st.session_state.get(widget_key)
        if scelta in db_partite:
            st.session_state["partita_attiva"] = scelta
            salva_dati_su_disco()

    return st.selectbox(
        label,
        partite_ordinate_chiavi,
        index=idx,
        key=widget_key,
        on_change=_on_change_partita
    )

with st.sidebar:
    utente_corrente_sb = st.session_state.get("utente_attivo") or st.session_state.get("ultimo_utente_home")
    if utente_corrente_sb:
        tot_u_sb = st.session_state.get("statistiche_accessi", {}).get(utente_corrente_sb, {}).get("count", 0)
        st.caption(f"👤 Connesso come: **{utente_corrente_sb}** ({tot_u_sb} accessi)")

    if st.button("🏠 Schermata Home", use_container_width=True, key="btn_torna_home"):
        st.session_state["home_entered"] = False
        st.rerun()

    st.markdown("### 🔐 Accesso & Ruoli")
    if st.session_state["is_admin"]:
        st.success("Modalità attiva: **Admin**")
        if st.button("🔒 Blocca (Passa a Ragazzi)", use_container_width=True, key="btn_lock_admin"):
            st.session_state["is_admin"] = False
            st.rerun()
    else:
        st.info(
            "Modalità attiva: **Ragazzi (Sola Lettura)**"
            if auth_cfg.get("read_only_boys", True)
            else "Modalità attiva: **Lettura Aperta**"
        )
        with st.popover("🔑 Login Admin", use_container_width=True):
            pin_input = st.text_input("Inserisci PIN Admin", type="password", key="admin_pin_input")
            if st.button("Sblocca Admin", use_container_width=True, key="btn_unlock_admin"):
                if _hash_pin(pin_input.strip()) == auth_cfg["admin_pin_hash"]:
                    st.session_state["is_admin"] = True
                    st.rerun()
                else:
                    st.error("PIN non valido.")

    st.divider()

    schede_attive_cfg = [
        s for s in auth_cfg.get("schede_attive", TUTTE_LE_SCHEDE_APP)
        if s in TUTTE_LE_SCHEDE_APP
    ] or ["📈 Riepilogo Squadra"]
    applica_nascoste_ad_admin = bool(auth_cfg.get("applica_nascoste_ad_admin", False))

    if st.session_state["is_admin"]:
        base_admin = schede_attive_cfg if applica_nascoste_ad_admin else TUTTE_LE_SCHEDE_APP
        sezioni_disponibili = list(base_admin) + ["🛡️ Pannello Admin"]
    else:
        ammesse_ragazzi = [
            s for s in auth_cfg.get("sezioni_ragazzi", [])
            if s in TUTTE_LE_SCHEDE_APP and s in schede_attive_cfg
        ]
        if not ammesse_ragazzi:
            ammesse_ragazzi = [
                s for s in schede_attive_cfg
                if s in ["🎥 Video Analisi", "📈 Riepilogo Squadra", "📊 Grafici & Analisi Visiva", "🟨 Fair Play"]
            ] or [schede_attive_cfg[0]]
        sezioni_disponibili = ammesse_ragazzi

    menu = st.radio("Navigazione", sezioni_disponibili)

if is_sola_lettura():
    st.info("👀 **Modalità Sola Lettura (Ragazzi):** puoi consultare i dati condivisi senza modificare formazioni, voti, video o impostazioni.")

# =====================================================================
# 1. SETUP PARTITE & FORMAZIONI
# =====================================================================
if menu == "📋 Setup Partite & Formazioni":
    st.title("📋 Setup Partite & Formazioni Titolari / Riserve")
    lettura_only = is_sola_lettura()

    col_sel_p, col_new_p, col_del_p = st.columns([3, 0.4, 0.4])
    with col_sel_p:
        partita_selezionata = selettore_partita_persistente("Seleziona Partita", "sel_partita_setup")
    with col_new_p:
        if not lettura_only:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            with st.expander("➕"):
                with st.form("form_nuova_partita"):
                    n_avv = st.text_input("Squadra Avversaria")
                    n_data = st.text_input("Data (es. 29/03/2026)")
                    n_mod = st.selectbox("Modulo Titolari", ["4-4-2", "4-3-3", "3-5-2", "4-2-3-1"])
                    n_ris = st.text_input("Risultato (es. 2-1)", value="N.D.")
                    n_ct = st.selectbox("Casa / Trasferta", ["Casa", "Trasferta"])
                    if st.form_submit_button("💾") and n_avv:
                        nome_p = f"{n_avv} ({n_data})"
                        if nome_p not in db_partite:
                            db_partite[nome_p] = {
                                "avversario": n_avv, "data": n_data, "modulo": n_mod,
                                "risultato": n_ris, "casa_trasferta": n_ct, "youtube_link": "",
                                "formazione": {str(i): "" for i in range(1, 21)},
                                "dati_prestazione": {}
                            }
                            st.session_state["partita_attiva"] = nome_p
                            salva_dati_su_disco()
                            st.success(f"Partita {nome_p} creata!")
                            st.rerun()
    with col_del_p:
        if not lettura_only:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            with st.expander("➖"):
                if db_partite and partita_selezionata in db_partite:
                    st.warning(f"Eliminare '{partita_selezionata}'?")
                    if st.button("🗑️ Conferma"):
                        del db_partite[partita_selezionata]
                        rimanenti = sorted(
                            db_partite.keys(),
                            key=lambda k: parse_data_partita(db_partite[k].get("data", "01/01/2026"))
                        )
                        st.session_state["partita_attiva"] = rimanenti[0] if rimanenti else None
                        salva_dati_su_disco()
                        st.success("Partita eliminata!")
                        st.rerun()
                else:
                    st.info("Nessuna partita.")

    if db_partite and partita_selezionata in db_partite:
        p_info = db_partite[partita_selezionata]

        if "risultato" not in p_info:
            p_info["risultato"] = "N.D."
        if "casa_trasferta" not in p_info:
            p_info["casa_trasferta"] = "Casa"
        if "youtube_link" not in p_info:
            p_info["youtube_link"] = ""
        if "dati_prestazione" not in p_info:
            p_info["dati_prestazione"] = {}

        st.divider()
        st.subheader(f"⚙️ Configurazione Partita & Formazione: {partita_selezionata}")

        formazione_corrente = p_info.get("formazione", {})

        if lettura_only:
            st.markdown(
                f"**Avversario:** {p_info.get('avversario', '')} · "
                f"**Risultato:** {p_info.get('risultato', 'N.D.')} · "
                f"**{p_info.get('casa_trasferta', 'Casa')}** · "
                f"**Modulo:** {p_info.get('modulo', 'N.D.')}"
            )
            righe_formazione = []
            for i in range(1, 21):
                gioc_slot = formazione_corrente.get(str(i), formazione_corrente.get(i, ""))
                if gioc_slot:
                    righe_formazione.append({
                        "Maglia": f"N° {i}",
                        "Tipo": "Titolare" if i <= 11 else "Riserva",
                        "Giocatore": gioc_slot,
                        "Ruolo Rosa": db_giocatori.get(gioc_slot, {}).get("ruolo", "-")
                    })
            if righe_formazione:
                st.table(pd.DataFrame(righe_formazione))
            else:
                st.info("Formazione non ancora impostata per questa partita.")
        else:
            with st.form(f"config_partita_{partita_selezionata}"):
                c_avv, c_res, c_ct, c_mod = st.columns(4)
                with c_avv:
                    nuovo_avv = st.text_input("Squadra Avversaria", value=p_info.get("avversario", ""))
                with c_res:
                    nuovo_risultato = st.text_input("Risultato (es. 3-1)", value=p_info.get("risultato", "N.D."))
                with c_ct:
                    ct_opts = ["Casa", "Trasferta"]
                    idx_ct = ct_opts.index(p_info.get("casa_trasferta", "Casa")) if p_info.get("casa_trasferta", "Casa") in ct_opts else 0
                    nuovo_ct = st.selectbox("Casa / Trasferta", ct_opts, index=idx_ct)
                with c_mod:
                    moduli_disponibili = ["4-4-2", "4-3-3", "3-5-2", "4-2-3-1"]
                    idx_mod = moduli_disponibili.index(p_info["modulo"]) if p_info["modulo"] in moduli_disponibili else 0
                    nuovo_modulo = st.selectbox("Modulo di Gioco", moduli_disponibili, index=idx_mod)

                st.info("ℹ️ I numeri **1** e **12** sono assegnati ai Portieri. I giocatori già inseriti in formazione vengono automaticamente esclusi dalle tendine per evitare duplicati.")

                tutta_rosa = list(db_giocatori.keys())

                st.markdown("### 🔴 Titolari (Maglie 1 - 11)")
                cols_tit = st.columns(4)
                for i in range(1, 12):
                    with cols_tit[(i-1) % 4]:
                        curr_val = formazione_corrente.get(str(i), formazione_corrente.get(i, ""))
                        selezionati_altrove = [
                            val for k, val in formazione_corrente.items()
                            if str(k) != str(i) and val != ""
                        ]
                        opzioni_slot = [""] + [g for g in tutta_rosa if g not in selezionati_altrove or g == curr_val]
                        idx_val = opzioni_slot.index(curr_val) if curr_val in opzioni_slot else 0
                        label_ruolo = "PORTIERE" if i == 1 else "Titolare"
                        p_info["formazione"][str(i)] = st.selectbox(f"N° {i} ({label_ruolo})", opzioni_slot, index=idx_val, key=f"tit_{i}_{partita_selezionata}")

                st.markdown("### 🔵 Riserve / Panchina (Maglie 12 - 20)")
                cols_res = st.columns(3)
                for i in range(12, 21):
                    with cols_res[(i-12) % 3]:
                        curr_val = formazione_corrente.get(str(i), formazione_corrente.get(i, ""))
                        selezionati_altrove = [
                            val for k, val in formazione_corrente.items()
                            if str(k) != str(i) and val != ""
                        ]
                        opzioni_slot = [""] + [g for g in tutta_rosa if g not in selezionati_altrove or g == curr_val]
                        idx_val = opzioni_slot.index(curr_val) if curr_val in opzioni_slot else 0
                        label_ruolo = "PORTIERE RIS." if i == 12 else "Riserva"
                        p_info["formazione"][str(i)] = st.selectbox(f"N° {i} ({label_ruolo})", opzioni_slot, index=idx_val, key=f"res_{i}_{partita_selezionata}")

                if st.form_submit_button("Conferma e Salva Dati Partita"):
                    p_info["avversario"] = nuovo_avv
                    p_info["risultato"] = nuovo_risultato
                    p_info["casa_trasferta"] = nuovo_ct
                    p_info["modulo"] = nuovo_modulo
                    st.session_state["partita_attiva"] = partita_selezionata
                    salva_dati_su_disco()
                    st.success("Dati partita e formazione salvati con successo!")
                    st.rerun()

# =====================================================================
# 2. INSERIMENTO PARAMETRI & VOTI (MODELLO SNELLO & VISIVO + FAIR PLAY)
# =====================================================================
elif menu == "⚡ Inserimento Parametri & Voti":
    st.title("⚡ Valutazione Snella Post-Partita & Voti")
    lettura_only = is_sola_lettura()

    if not db_partite:
        st.warning("⚠️ Crea prima una partita nella sezione 'Setup Partite & Formazioni'.")
        st.stop()

    partita_sel = selettore_partita_persistente("Seleziona Partita da Analizzare", "analizza_partita")
    p_dati = db_partite[partita_sel]

    if "dati_prestazione" not in p_dati:
        p_dati["dati_prestazione"] = {}

    col_tit_sez, col_btn_reset = st.columns([3.5, 1])
    with col_tit_sez:
        st.subheader(f"Analisi Match: {partita_sel} (Risultato: {p_dati.get('risultato', 'N.D.')} | {p_dati.get('casa_trasferta', 'Casa')})")
    with col_btn_reset:
        if not lettura_only:
            st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
            if st.button("🔄 Ripristina valori", use_container_width=True, key=f"btn_ripristina_valori_{partita_sel}"):
                ripristina_parametri_partita(partita_sel, p_dati, db_giocatori)
                st.success("Valori ripristinati ai dati base (ruoli mantenuti)!")
                st.rerun()

    st.caption(
        "Modello Snello & Visivo: scegli **Impatto partita** e **Gestione palla / duelli** (pesati su **Difesa**, **Centrocampo** o **Attacco**), "
        "segna **Gol**, **Assist**, **Errori gravi** e le spunte **Amm** / **Esp** accanto al nome. "
        "**Solo le espulsioni** applicano un **-1.0** sul voto; l'ammonizione accende il punto **giallo** e l'espulsione quello **rosso**."
    )

    if lettura_only:
        righe_lettura = []
        for n, nome in p_dati.get("formazione", {}).items():
            if not nome:
                continue
            is_portiere = (str(n) in ["1", "12"])
            p_g = p_dati.get("dati_prestazione", {}).get(nome, {})
            min_g = int(p_g.get("minuti", 0)) if p_g else 0
            voto_g = calcola_voto(p_g, is_portiere) if (p_g and min_g > 0) else None
            fp = estrai_fairplay_compat(p_g)
            fp_label = []
            if fp["ammonito"]:
                fp_label.append("🟡 Amm.")
            if fp["espulso"]:
                fp_label.append("🔴 Esp. (-1)")

            if is_portiere:
                dp = estrai_dati_portiere_compat(p_g)
                ruolo_str = "POR (Porta)"
                righe_lettura.append({
                    "N°": str(n),
                    "Giocatore": nome,
                    "Fair Play": " · ".join(fp_label) if fp_label else "-",
                    "Ruolo / Area": ruolo_str,
                    "Minuti": f"{min_g}'",
                    "Sicurezza / Impatto": dp["sicurezza_portiere"],
                    "Parate / Palla": f"{dp['parate_decisive']} parate dec.",
                    "Gol / Gol Sub.": f"{dp['gol_subiti']} subiti",
                    "Assist": "-",
                    "Errori Gravi": dp["errori_gravi"],
                    "Voto": f"{voto_g} / 10" if voto_g is not None else "N.D."
                })
            else:
                ruolo_c = p_g.get("ruolo_campo") or ruolo_default_da_rosa(db_giocatori.get(nome, {}).get("ruolo", ""))
                ruolo_str = f"{ruolo_c} ({get_etichetta_area(ruolo_c)})"
                dm = estrai_dati_movimento_compat(p_g)
                righe_lettura.append({
                    "N°": str(n),
                    "Giocatore": nome,
                    "Fair Play": " · ".join(fp_label) if fp_label else "-",
                    "Ruolo / Area": ruolo_str,
                    "Minuti": f"{min_g}'",
                    "Sicurezza / Impatto": dm["impatto_partita"],
                    "Parate / Palla": dm["gestione_palla"],
                    "Gol / Gol Sub.": dm["gol_fatti"],
                    "Assist": dm["assist"],
                    "Errori Gravi": dm["errori_gravi"],
                    "Voto": f"{voto_g} / 10" if voto_g is not None else "N.D."
                })
        if righe_lettura:
            st.table(pd.DataFrame(righe_lettura))
        else:
            st.info("Nessun parametro disponibile per questa partita.")
    else:
        with st.form("form_inserimento_parametri"):
            st.markdown("### 🔴 TITOLARI (Maglie 1 - 11)")
            for i in range(1, 12):
                nome_g = p_dati["formazione"].get(str(i), p_dati["formazione"].get(i, ""))
                if not nome_g:
                    continue

                is_portiere = (i == 1)
                default_ruolo_g = ruolo_default_da_rosa(db_giocatori.get(nome_g, {}).get("ruolo", ""))
                current_vals = p_dati["dati_prestazione"].get(nome_g, {})
                fp_curr = estrai_fairplay_compat(current_vals)

                if is_portiere:
                    dp_curr = estrai_dati_portiere_compat(current_vals)
                    c_gioc, c_amm_chk, c_amm_dot, c_esp_chk, c_esp_dot = st.columns([2.2, 0.8, 0.25, 0.8, 0.25])
                    with c_gioc:
                        st.markdown(
                            f"<div style='padding-top:6px;'><strong>N° {i} — {nome_g}</strong>"
                            f"<span class='scoutai-area-badge'>Porta</span></div>",
                            unsafe_allow_html=True
                        )
                    with c_amm_chk:
                        amm_val = st.checkbox("Amm.", value=fp_curr["ammonito"], key=f"amm_{partita_sel}_{i}")
                    with c_amm_dot:
                        col_dot_a = "#eab308" if amm_val else "rgba(148,163,184,0.22)"
                        glow_dot_a = "box-shadow:0 0 8px #eab308;" if amm_val else ""
                        st.markdown(f"<span class='scoutai-fp-dot' style='background:{col_dot_a};{glow_dot_a}' title='Stato Ammonizione'></span>", unsafe_allow_html=True)
                    with c_esp_chk:
                        esp_val = st.checkbox("Esp.", value=fp_curr["espulso"], key=f"esp_{partita_sel}_{i}")
                    with c_esp_dot:
                        col_dot_e = "#ef4444" if esp_val else "rgba(148,163,184,0.22)"
                        glow_dot_e = "box-shadow:0 0 8px #ef4444;" if esp_val else ""
                        st.markdown(f"<span class='scoutai-fp-dot' style='background:{col_dot_e};{glow_dot_e}' title='Stato Espulsione (-1 voto)'></span>", unsafe_allow_html=True)

                    c1, c2, c3, c4, c5, c_voto = st.columns([0.9, 1.4, 1.0, 1.0, 1.0, 1.0])
                    with c1:
                        minuti = st.number_input("Minuti", 0, 80, int(current_vals.get("minuti", 80)), key=f"min_{partita_sel}_{i}")
                    with c2:
                        idx_sic = OPZIONI_SICUREZZA_PORTIERE.index(dp_curr["sicurezza_portiere"])
                        sicurezza_p = st.selectbox("Sicurezza & Uscite", OPZIONI_SICUREZZA_PORTIERE, index=idx_sic, key=f"sic_{partita_sel}_{i}")
                    with c3:
                        parate_dec = st.number_input("Parate dec.", 0, 15, int(dp_curr["parate_decisive"]), key=f"par_{partita_sel}_{i}")
                    with c4:
                        gol_sub = st.number_input("Gol subiti", 0, 15, int(dp_curr["gol_subiti"]), key=f"gsub_{partita_sel}_{i}")
                    with c5:
                        errori_p = st.number_input("Errori gravi", 0, 10, int(dp_curr["errori_gravi"]), key=f"errp_{partita_sel}_{i}")

                    temp_dict = {
                        "minuti": minuti,
                        "sicurezza_portiere": sicurezza_p,
                        "parate_decisive": parate_dec,
                        "gol_subiti": gol_sub,
                        "errori_gravi": errori_p,
                        "ammonito": bool(amm_val),
                        "espulso": bool(esp_val),
                    }
                    voto_live = calcola_voto(temp_dict, is_portiere=True)
                    voto_live_txt = str(voto_live) if voto_live is not None else "N.D."

                    with c_voto:
                        st.markdown(f"<div class='scoutai-voto-box'><span style='font-size: 11px; display: block; color: #a0aec0;'>VOTO LIVE</span><span style='font-size: 20px; font-weight: bold; color: {accent_hex};'>{voto_live_txt}</span></div>", unsafe_allow_html=True)

                    p_dati["dati_prestazione"][nome_g] = temp_dict
                else:
                    dm_curr = estrai_dati_movimento_compat(current_vals)
                    val_ruolo = current_vals.get("ruolo_campo", default_ruolo_g)
                    if val_ruolo not in TUTTI_RUOLI_MOVIMENTO:
                        val_ruolo = "CC"
                    area_gioco_label = get_etichetta_area(val_ruolo)

                    c_gioc, c_amm_chk, c_amm_dot, c_esp_chk, c_esp_dot, c_ruolo = st.columns([2.2, 0.75, 0.25, 0.75, 0.25, 1.0])
                    with c_gioc:
                        st.markdown(
                            f"<div style='padding-top: 6px;'><strong>N° {i} — {nome_g}</strong>"
                            f"<span class='scoutai-area-badge'>{area_gioco_label}</span></div>",
                            unsafe_allow_html=True
                        )
                    with c_amm_chk:
                        amm_val = st.checkbox("Amm.", value=fp_curr["ammonito"], key=f"amm_{partita_sel}_{i}")
                    with c_amm_dot:
                        col_dot_a = "#eab308" if amm_val else "rgba(148,163,184,0.22)"
                        glow_dot_a = "box-shadow:0 0 8px #eab308;" if amm_val else ""
                        st.markdown(f"<span class='scoutai-fp-dot' style='background:{col_dot_a};{glow_dot_a}' title='Stato Ammonizione'></span>", unsafe_allow_html=True)
                    with c_esp_chk:
                        esp_val = st.checkbox("Esp.", value=fp_curr["espulso"], key=f"esp_{partita_sel}_{i}")
                    with c_esp_dot:
                        col_dot_e = "#ef4444" if esp_val else "rgba(148,163,184,0.22)"
                        glow_dot_e = "box-shadow:0 0 8px #ef4444;" if esp_val else ""
                        st.markdown(f"<span class='scoutai-fp-dot' style='background:{col_dot_e};{glow_dot_e}' title='Stato Espulsione (-1 voto)'></span>", unsafe_allow_html=True)
                    with c_ruolo:
                        idx_ruolo = TUTTI_RUOLI_MOVIMENTO.index(val_ruolo)
                        ruolo_campo = st.selectbox("Ruolo", TUTTI_RUOLI_MOVIMENTO, index=idx_ruolo, key=f"ruolo_{partita_sel}_{i}", label_visibility="collapsed")

                    c1, c2, c3, c4, c5, c6, c_voto = st.columns([0.85, 1.35, 1.35, 0.8, 0.85, 0.9, 1.0])
                    with c1:
                        minuti = st.number_input("Minuti", 0, 80, int(current_vals.get("minuti", 80)), key=f"min_{partita_sel}_{i}")
                    with c2:
                        idx_imp = OPZIONI_IMPATTO_PARTITA.index(dm_curr["impatto_partita"])
                        impatto_partita = st.selectbox("Impatto partita", OPZIONI_IMPATTO_PARTITA, index=idx_imp, key=f"imp_{partita_sel}_{i}")
                    with c3:
                        idx_ges = OPZIONI_GESTIONE_PALLA.index(dm_curr["gestione_palla"])
                        gestione_palla = st.selectbox("Palla & duelli", OPZIONI_GESTIONE_PALLA, index=idx_ges, key=f"ges_{partita_sel}_{i}")
                    with c4:
                        gol_fatti = st.number_input("Gol", 0, 10, int(dm_curr["gol_fatti"]), key=f"gol_{partita_sel}_{i}")
                    with c5:
                        assist = st.number_input("Assist", 0, 10, int(dm_curr["assist"]), key=f"ass_{partita_sel}_{i}")
                    with c6:
                        errori_gravi = st.number_input("Errori gravi", 0, 10, int(dm_curr["errori_gravi"]), key=f"err_{partita_sel}_{i}")

                    temp_dict = {
                        "ruolo_campo": ruolo_campo,
                        "minuti": minuti,
                        "impatto_partita": impatto_partita,
                        "gestione_palla": gestione_palla,
                        "gol_fatti": gol_fatti,
                        "assist": assist,
                        "errori_gravi": errori_gravi,
                        "ammonito": bool(amm_val),
                        "espulso": bool(esp_val),
                    }
                    voto_live = calcola_voto(temp_dict, is_portiere=False)
                    voto_live_txt = str(voto_live) if voto_live is not None else "N.D."

                    with c_voto:
                        st.markdown(f"<div class='scoutai-voto-box'><span style='font-size: 11px; display: block; color: #a0aec0;'>VOTO LIVE</span><span style='font-size: 20px; font-weight: bold; color: {accent_hex};'>{voto_live_txt}</span></div>", unsafe_allow_html=True)

                    p_dati["dati_prestazione"][nome_g] = temp_dict

                st.markdown("---")

            st.markdown(f"<br><hr style='border: 2px dashed {accent_hex};'><br>", unsafe_allow_html=True)

            st.markdown("### 🔵 RISERVE / PANCHINA (Maglie 12 - 20)")
            for i in range(12, 21):
                nome_g = p_dati["formazione"].get(str(i), p_dati["formazione"].get(i, ""))
                if not nome_g:
                    continue

                is_portiere = (i == 12)
                default_ruolo_g = ruolo_default_da_rosa(db_giocatori.get(nome_g, {}).get("ruolo", ""))
                current_vals = p_dati["dati_prestazione"].get(nome_g, {})
                fp_curr = estrai_fairplay_compat(current_vals)

                if is_portiere:
                    dp_curr = estrai_dati_portiere_compat(current_vals)
                    c_gioc, c_amm_chk, c_amm_dot, c_esp_chk, c_esp_dot = st.columns([2.2, 0.8, 0.25, 0.8, 0.25])
                    with c_gioc:
                        st.markdown(
                            f"<div style='padding-top:6px;'><strong>N° {i} — {nome_g} (Riserva)</strong>"
                            f"<span class='scoutai-area-badge'>Porta</span></div>",
                            unsafe_allow_html=True
                        )
                    with c_amm_chk:
                        amm_val = st.checkbox("Amm.", value=fp_curr["ammonito"], key=f"amm_res_{partita_sel}_{i}")
                    with c_amm_dot:
                        col_dot_a = "#eab308" if amm_val else "rgba(148,163,184,0.22)"
                        glow_dot_a = "box-shadow:0 0 8px #eab308;" if amm_val else ""
                        st.markdown(f"<span class='scoutai-fp-dot' style='background:{col_dot_a};{glow_dot_a}' title='Stato Ammonizione'></span>", unsafe_allow_html=True)
                    with c_esp_chk:
                        esp_val = st.checkbox("Esp.", value=fp_curr["espulso"], key=f"esp_res_{partita_sel}_{i}")
                    with c_esp_dot:
                        col_dot_e = "#ef4444" if esp_val else "rgba(148,163,184,0.22)"
                        glow_dot_e = "box-shadow:0 0 8px #ef4444;" if esp_val else ""
                        st.markdown(f"<span class='scoutai-fp-dot' style='background:{col_dot_e};{glow_dot_e}' title='Stato Espulsione (-1 voto)'></span>", unsafe_allow_html=True)

                    c1, c2, c3, c4, c5, c_voto = st.columns([0.9, 1.4, 1.0, 1.0, 1.0, 1.0])
                    with c1:
                        minuti = st.number_input("Min sub", 0, 80, int(current_vals.get("minuti", 0)), key=f"min_res_{partita_sel}_{i}")
                    with c2:
                        idx_sic = OPZIONI_SICUREZZA_PORTIERE.index(dp_curr["sicurezza_portiere"])
                        sicurezza_p = st.selectbox("Sicurezza & Uscite", OPZIONI_SICUREZZA_PORTIERE, index=idx_sic, key=f"sic_res_{partita_sel}_{i}")
                    with c3:
                        parate_dec = st.number_input("Parate dec.", 0, 15, int(dp_curr["parate_decisive"]), key=f"par_res_{partita_sel}_{i}")
                    with c4:
                        gol_sub = st.number_input("Gol subiti", 0, 15, int(dp_curr["gol_subiti"]), key=f"gsub_res_{partita_sel}_{i}")
                    with c5:
                        errori_p = st.number_input("Errori gravi", 0, 10, int(dp_curr["errori_gravi"]), key=f"errp_res_{partita_sel}_{i}")

                    temp_dict_res = {
                        "minuti": minuti,
                        "sicurezza_portiere": sicurezza_p,
                        "parate_decisive": parate_dec,
                        "gol_subiti": gol_sub,
                        "errori_gravi": errori_p,
                        "ammonito": bool(amm_val),
                        "espulso": bool(esp_val),
                    }
                    voto_live_res = calcola_voto(temp_dict_res, is_portiere=True)
                    voto_live_res_txt = str(voto_live_res) if voto_live_res is not None else "N.D."

                    with c_voto:
                        st.markdown(f"<div class='scoutai-voto-box'><span style='font-size: 11px; display: block; color: #a0aec0;'>VOTO LIVE</span><span style='font-size: 20px; font-weight: bold; color: {accent_hex};'>{voto_live_res_txt}</span></div>", unsafe_allow_html=True)

                    p_dati["dati_prestazione"][nome_g] = temp_dict_res
                else:
                    dm_curr = estrai_dati_movimento_compat(current_vals)
                    val_ruolo = current_vals.get("ruolo_campo", default_ruolo_g)
                    if val_ruolo not in TUTTI_RUOLI_MOVIMENTO:
                        val_ruolo = "CC"
                    area_gioco_label = get_etichetta_area(val_ruolo)

                    c_gioc, c_amm_chk, c_amm_dot, c_esp_chk, c_esp_dot, c_ruolo = st.columns([2.2, 0.75, 0.25, 0.75, 0.25, 1.0])
                    with c_gioc:
                        st.markdown(
                            f"<div style='padding-top: 6px;'><strong>N° {i} — {nome_g} (Riserva)</strong>"
                            f"<span class='scoutai-area-badge'>{area_gioco_label}</span></div>",
                            unsafe_allow_html=True
                        )
                    with c_amm_chk:
                        amm_val = st.checkbox("Amm.", value=fp_curr["ammonito"], key=f"amm_res_{partita_sel}_{i}")
                    with c_amm_dot:
                        col_dot_a = "#eab308" if amm_val else "rgba(148,163,184,0.22)"
                        glow_dot_a = "box-shadow:0 0 8px #eab308;" if amm_val else ""
                        st.markdown(f"<span class='scoutai-fp-dot' style='background:{col_dot_a};{glow_dot_a}' title='Stato Ammonizione'></span>", unsafe_allow_html=True)
                    with c_esp_chk:
                        esp_val = st.checkbox("Esp.", value=fp_curr["espulso"], key=f"esp_res_{partita_sel}_{i}")
                    with c_esp_dot:
                        col_dot_e = "#ef4444" if esp_val else "rgba(148,163,184,0.22)"
                        glow_dot_e = "box-shadow:0 0 8px #ef4444;" if esp_val else ""
                        st.markdown(f"<span class='scoutai-fp-dot' style='background:{col_dot_e};{glow_dot_e}' title='Stato Espulsione (-1 voto)'></span>", unsafe_allow_html=True)
                    with c_ruolo:
                        idx_ruolo = TUTTI_RUOLI_MOVIMENTO.index(val_ruolo)
                        ruolo_campo = st.selectbox("Ruolo", TUTTI_RUOLI_MOVIMENTO, index=idx_ruolo, key=f"ruolo_res_{partita_sel}_{i}", label_visibility="collapsed")

                    c1, c2, c3, c4, c5, c6, c_voto = st.columns([0.85, 1.35, 1.35, 0.8, 0.85, 0.9, 1.0])
                    with c1:
                        minuti = st.number_input("Min sub", 0, 80, int(current_vals.get("minuti", 0)), key=f"min_res_{partita_sel}_{i}")
                    with c2:
                        idx_imp = OPZIONI_IMPATTO_PARTITA.index(dm_curr["impatto_partita"])
                        impatto_partita = st.selectbox("Impatto partita", OPZIONI_IMPATTO_PARTITA, index=idx_imp, key=f"imp_res_{partita_sel}_{i}")
                    with c3:
                        idx_ges = OPZIONI_GESTIONE_PALLA.index(dm_curr["gestione_palla"])
                        gestione_palla = st.selectbox("Palla & duelli", OPZIONI_GESTIONE_PALLA, index=idx_ges, key=f"ges_res_{partita_sel}_{i}")
                    with c4:
                        gol_fatti = st.number_input("Gol", 0, 10, int(dm_curr["gol_fatti"]), key=f"gol_res_{partita_sel}_{i}")
                    with c5:
                        assist = st.number_input("Assist", 0, 10, int(dm_curr["assist"]), key=f"ass_res_{partita_sel}_{i}")
                    with c6:
                        errori_gravi = st.number_input("Errori gravi", 0, 10, int(dm_curr["errori_gravi"]), key=f"err_res_{partita_sel}_{i}")

                    temp_dict_res = {
                        "ruolo_campo": ruolo_campo,
                        "minuti": minuti,
                        "impatto_partita": impatto_partita,
                        "gestione_palla": gestione_palla,
                        "gol_fatti": gol_fatti,
                        "assist": assist,
                        "errori_gravi": errori_gravi,
                        "ammonito": bool(amm_val),
                        "espulso": bool(esp_val),
                    }
                    voto_live_res = calcola_voto(temp_dict_res, is_portiere=False)
                    voto_live_res_txt = str(voto_live_res) if voto_live_res is not None else "N.D."

                    with c_voto:
                        st.markdown(f"<div class='scoutai-voto-box'><span style='font-size: 11px; display: block; color: #a0aec0;'>VOTO LIVE</span><span style='font-size: 20px; font-weight: bold; color: {accent_hex};'>{voto_live_res_txt}</span></div>", unsafe_allow_html=True)

                    p_dati["dati_prestazione"][nome_g] = temp_dict_res

                st.markdown("---")

            if st.form_submit_button("💾 Salva Valutazioni e Calcola Voti"):
                st.session_state["partita_attiva"] = partita_sel
                salva_dati_su_disco()
                st.success("Valutazioni salvate automaticamente e voti aggiornati!")
                st.rerun()

        st.divider()
        st.subheader("📄 Esportazione Report")
        col_pdf, col_csv = st.columns(2)
        with col_pdf:
            if REPORTLAB_AVAILABLE:
                if st.button("📄 Genera Report PDF Partita"):
                    pdf_path = genera_pdf_partita(partita_sel, p_dati, db_giocatori, accent_hex)
                    if pdf_path and os.path.exists(pdf_path):
                        with open(pdf_path, "rb") as f:
                            st.download_button("Scarica PDF Ufficiale", f, file_name=pdf_path, mime="application/pdf")
            else:
                st.info("ℹ️ Modulo PDF disabilitato (ReportLab non installato nell'ambiente). Puoi usare l'export CSV.")
        with col_csv:
            righe_csv = []
            for n, nome in p_dati["formazione"].items():
                if not nome:
                    continue
                is_portiere = (str(n) in ["1", "12"])
                p_dati_g = p_dati["dati_prestazione"].get(nome, {})
                voto = calcola_voto(p_dati_g, is_portiere)
                fp = estrai_fairplay_compat(p_dati_g)
                if is_portiere:
                    dp = estrai_dati_portiere_compat(p_dati_g)
                    righe_csv.append({
                        "Numero": n,
                        "Giocatore": nome,
                        "Area": "Porta",
                        "Minuti": p_dati_g.get("minuti", 0),
                        "Sicurezza": dp["sicurezza_portiere"],
                        "Parate Decisive": dp["parate_decisive"],
                        "Gol Subiti": dp["gol_subiti"],
                        "Errori Gravi": dp["errori_gravi"],
                        "Ammonito": "Si" if fp["ammonito"] else "No",
                        "Espulso": "Si" if fp["espulso"] else "No",
                        "Voto": voto if voto is not None else "N.D."
                    })
                else:
                    ruolo_c = p_dati_g.get("ruolo_campo") or ruolo_default_da_rosa(db_giocatori.get(nome, {}).get("ruolo", ""))
                    dm = estrai_dati_movimento_compat(p_dati_g)
                    righe_csv.append({
                        "Numero": n,
                        "Giocatore": nome,
                        "Ruolo": ruolo_c,
                        "Area": get_etichetta_area(ruolo_c),
                        "Minuti": p_dati_g.get("minuti", 0),
                        "Impatto Partita": dm["impatto_partita"],
                        "Palla & Duelli": dm["gestione_palla"],
                        "Gol": dm["gol_fatti"],
                        "Assist": dm["assist"],
                        "Errori Gravi": dm["errori_gravi"],
                        "Ammonito": "Si" if fp["ammonito"] else "No",
                        "Espulso": "Si" if fp["espulso"] else "No",
                        "Voto": voto if voto is not None else "N.D."
                    })

            df_match = pd.DataFrame(righe_csv)
            if not df_match.empty:
                csv_data = df_match.to_csv(index=False).encode('utf-8')
                st.download_button("📊 Esporta CSV Match", csv_data, file_name=f"Match_{partita_sel}.csv", mime="text/csv")

# =====================================================================
# 3. VIDEO ANALISI
# =====================================================================
elif menu == "🎥 Video Analisi":
    st.title("🎥 Video Analisi & Streaming Partita")
    lettura_only = is_sola_lettura()

    if not db_partite:
        st.warning("⚠️ Crea prima una partita nella sezione 'Setup Partite & Formazioni'.")
        st.stop()

    partita_sel = selettore_partita_persistente("Seleziona Partita per la Video Analisi", "video_partita")
    p_info = db_partite[partita_sel]

    if "youtube_link" not in p_info:
        p_info["youtube_link"] = ""

    data_p = p_info.get("data", "N.D.")
    ris_p = p_info.get("risultato", "N.D.")
    luogo_p = p_info.get("casa_trasferta", "Casa")
    mod_p = p_info.get("modulo", "N.D.")

    st.markdown(f"""
    <div style="
        background-color: {tema['bg_card']};
        border: 1px solid {glow_border_rgba};
        border-radius: {max(8, radius_px - 2)}px;
        padding: 10px 16px;
        margin: 10px 0 14px 0;
        box-shadow: {box_shadow_soft};
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
    ">
        <div style="font-weight: 700; font-size: 14px; color: {accent_hex};">
            📌 {partita_sel}
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 12px; font-size: 13px; color: {tema['text_color']};">
            <span>📅 <strong>Data:</strong> {data_p}</span>
            <span>⚽ <strong>Risultato:</strong> {ris_p}</span>
            <span>🏟️ <strong>Luogo:</strong> {luogo_p}</span>
            <span>📐 <strong>Modulo:</strong> {mod_p}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not lettura_only:
        col_link, col_btn = st.columns([3.5, 1.2])
        with col_link:
            link_inserito = st.text_input(
                "Link YouTube Partita",
                value=p_info.get("youtube_link", ""),
                placeholder="https://www.youtube.com/watch?v=...",
                label_visibility="collapsed",
                key=f"yt_input_{partita_sel}"
            )
        with col_btn:
            if st.button("📥 Carica Video", use_container_width=True, key=f"btn_carica_video_{partita_sel}"):
                p_info["youtube_link"] = link_inserito.strip()
                st.session_state["partita_attiva"] = partita_sel
                salva_dati_su_disco()
                st.success("Video caricato e link salvato!")
                st.rerun()

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    link_corrente = p_info.get("youtube_link", "")
    yt_id = estrai_youtube_id(link_corrente)

    if yt_id:
        embed_url = f"https://www.youtube.com/embed/{yt_id}"
        st.markdown(f"""
            <div style="
                width: 100%;
                max-width: 100%;
                margin: 0 auto;
                border-radius: {radius_px}px;
                overflow: hidden;
                border: 1px solid {glow_border_rgba};
                box-shadow: {box_shadow_glow};
                background-color: {tema['bg_card']};
            ">
                <div style="position: relative; width: 100%; padding-bottom: 56.25%; height: 0;">
                    <iframe
                        src="{embed_url}"
                        title="Video Analisi - {partita_sel}"
                        style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: 0;"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                        allowfullscreen>
                    </iframe>
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
            <div class="scoutai-video-empty" style="width: 100%; max-width: 100%; height: 260px;">
                <span style="font-size: 36px; margin-bottom: 8px;">📺</span>
                <p style="color: #a0aec0; margin: 0; font-size: 15px;">Nessun video caricato o link YouTube non valido.</p>
                <p style="color: #718096; margin-top: 6px; font-size: 13px;">{"Incolla un link YouTube qui sopra e clicca su <strong>Carica Video</strong>." if not lettura_only else "Il video per questa partita non è ancora stato caricato."}</p>
            </div>
        """, unsafe_allow_html=True)

# =====================================================================
# 4. RIEPILOGO SQUADRA & GIOCATORI (ADATTATO AL MODELLO SNELLO)
# =====================================================================
elif menu == "📈 Riepilogo Squadra":
    st.title("📈 Riepilogo Squadra & Statistiche Stagionali")

    def render_metric_box(titolo, valore_testo):
        st.markdown(f"""
        <div style="
            background-color: {tema['bg_card']};
            border: 1px solid {glow_border_rgba};
            border-radius: {radius_px}px;
            padding: 18px;
            box-shadow: {box_shadow_glow};
        ">
            <div style="font-size: 14px; color: #a0aec0; margin-bottom: 6px;">{titolo}</div>
            <div style="font-size: 28px; font-weight: 700; color: {accent_hex}; line-height: 1.15;">{valore_testo}</div>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("🏆 Elenco Partite & Rendimento per Reparto")

    partite_ordinate = sorted(
        db_partite.items(),
        key=lambda item: parse_data_partita(item[1].get("data", "01/01/2026"))
    )

    partite_riepilogo = []
    voti_reparti_stagione = {"Difesa": [], "Centrocampo": [], "Attacco": []}
    serie_globale_match = []

    for p_nome, p_val in partite_ordinate:
        voti_match = []
        voti_rep_match = {"Difesa": [], "Centrocampo": [], "Attacco": []}
        gol_match = 0
        assist_match = 0
        errori_match = 0

        for n, nome in p_val.get("formazione", {}).items():
            if not nome:
                continue
            is_portiere = (str(n) in ["1", "12"])
            d_p = p_val.get("dati_prestazione", {}).get(nome, {})
            if d_p and int(d_p.get("minuti", 0)) > 0:
                v_g = calcola_voto(d_p, is_portiere)
                if v_g is not None:
                    voti_match.append(v_g)
                    if is_portiere:
                        dp = estrai_dati_portiere_compat(d_p)
                        errori_match += dp["errori_gravi"]
                    else:
                        ruolo_c = d_p.get("ruolo_campo") or ruolo_default_da_rosa(
                            db_giocatori.get(nome, {}).get("ruolo", "")
                        )
                        area_g = get_etichetta_area(ruolo_c)
                        voti_rep_match[area_g].append(v_g)
                        voti_reparti_stagione[area_g].append(v_g)

                        dm = estrai_dati_movimento_compat(d_p)
                        gol_match += dm["gol_fatti"]
                        assist_match += dm["assist"]
                        errori_match += dm["errori_gravi"]

        voto_medio = round(sum(voti_match) / len(voti_match), 1) if voti_match else None
        media_dif = round(sum(voti_rep_match["Difesa"]) / len(voti_rep_match["Difesa"]), 1) if voti_rep_match["Difesa"] else None
        media_cen = round(sum(voti_rep_match["Centrocampo"]) / len(voti_rep_match["Centrocampo"]), 1) if voti_rep_match["Centrocampo"] else None
        media_att = round(sum(voti_rep_match["Attacco"]) / len(voti_rep_match["Attacco"]), 1) if voti_rep_match["Attacco"] else None

        if voto_medio is not None:
            serie_globale_match.append(voto_medio)

        partite_riepilogo.append({
            "Partita": p_nome,
            "Data": p_val["data"],
            "Risultato": p_val.get("risultato", "N.D."),
            "Luogo": p_val.get("casa_trasferta", "Casa"),
            "Gol / Ass / Err": f"{gol_match} / {assist_match} / {errori_match}",
            "Difesa": f"{media_dif}" if media_dif is not None else "-",
            "Centrocampo": f"{media_cen}" if media_cen is not None else "-",
            "Attacco": f"{media_att}" if media_att is not None else "-",
            "Media Squadra": f"{voto_medio} / 10" if voto_medio is not None else "N.D."
        })

    m_sq_stag = round(sum(serie_globale_match) / len(serie_globale_match), 1) if serie_globale_match else None
    m_stag_dif = round(sum(voti_reparti_stagione["Difesa"]) / len(voti_reparti_stagione["Difesa"]), 1) if voti_reparti_stagione["Difesa"] else None
    m_stag_cen = round(sum(voti_reparti_stagione["Centrocampo"]) / len(voti_reparti_stagione["Centrocampo"]), 1) if voti_reparti_stagione["Centrocampo"] else None
    m_stag_att = round(sum(voti_reparti_stagione["Attacco"]) / len(voti_reparti_stagione["Attacco"]), 1) if voti_reparti_stagione["Attacco"] else None

    col_sq_stag, col_rep1, col_rep2, col_rep3 = st.columns(4)
    with col_sq_stag:
        render_metric_box(
            "🏅 Voto Medio Squadra Stagionale",
            f"{m_sq_stag} / 10" if m_sq_stag is not None else "N.D."
        )
    with col_rep1:
        render_metric_box(
            "🛡️ Media Reparto Difesa",
            f"{m_stag_dif} / 10" if m_stag_dif is not None else "N.D."
        )
    with col_rep2:
        render_metric_box(
            "⚙️ Media Reparto Centrocampo",
            f"{m_stag_cen} / 10" if m_stag_cen is not None else "N.D."
        )
    with col_rep3:
        render_metric_box(
            "⚡ Media Reparto Attacco",
            f"{m_stag_att} / 10" if m_stag_att is not None else "N.D."
        )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    if partite_riepilogo:
        st.table(pd.DataFrame(partite_riepilogo))

    st.divider()
    st.subheader("📊 Riepilogo Stagionale Giocatore")
    nomi_rosa_riepilogo = list(db_giocatori.keys()) if db_giocatori else ["Nessun Giocatore"]
    profilo_home = ottieni_profilo_home_attivo()
    idx_gioc_default = nomi_rosa_riepilogo.index(profilo_home) if profilo_home in nomi_rosa_riepilogo else 0

    giocatore_sel = st.selectbox(
        "Seleziona Giocatore",
        nomi_rosa_riepilogo,
        index=idx_gioc_default,
        key="sel_giocatore_riepilogo"
    )

    foto_giocatore_sel = ottieni_foto_valida(giocatore_sel, db_giocatori)
    ruolo_giocatore_sel = db_giocatori.get(giocatore_sel, {}).get("ruolo", "")

    col_foto_scheda, col_info_scheda = st.columns([0.14, 0.86])
    with col_foto_scheda:
        if foto_giocatore_sel:
            st.image(foto_giocatore_sel, width=76)
        else:
            st.markdown(
                "<div style='width:76px;height:76px;border-radius:12px;display:flex;align-items:center;"
                "justify-content:center;background:#1e2230;font-size:32px;'>🧑🏻</div>",
                unsafe_allow_html=True
            )
    with col_info_scheda:
        st.markdown(f"<h3 style='margin:4px 0 2px 0;'>{giocatore_sel}</h3>", unsafe_allow_html=True)
        if ruolo_giocatore_sel:
            st.caption(f"Ruolo in rosa: {ruolo_giocatore_sel}")

    storico_voti = []
    tot_minuti = 0
    presenze_titolare = 0
    presenze_subentro = 0

    lista_impatti = []
    lista_gestione = []
    tot_gol = 0
    tot_assist = 0
    tot_errori_mov = 0

    lista_sicurezza_p = []
    tot_parate_dec = 0
    tot_gol_sub = 0
    tot_errori_p = 0

    ha_dati_portiere = False
    ha_dati_movimento = False
    righe_match_giocatore = []

    for p_nome, p_val in partite_ordinate:
        formazione = p_val.get("formazione", {})
        for n, nome in formazione.items():
            if nome == giocatore_sel:
                d_p = p_val.get("dati_prestazione", {}).get(giocatore_sel, {})
                if d_p:
                    min_giocati = int(d_p.get("minuti", 0))
                    num_maglia = int(n) if str(n).isdigit() else 0
                    is_portiere = (str(n) in ["1", "12"])
                    ha_minuti = min_giocati > 0
                    voto_match = calcola_voto(d_p, is_portiere) if ha_minuti else None
                    fp = estrai_fairplay_compat(d_p)
                    fp_txt = []
                    if fp["ammonito"]:
                        fp_txt.append("🟡 Amm.")
                    if fp["espulso"]:
                        fp_txt.append("🔴 Esp.")
                    fp_suffix = f" | {' · '.join(fp_txt)}" if fp_txt else ""

                    if ha_minuti and voto_match is not None:
                        storico_voti.append(voto_match)
                        tot_minuti += min_giocati

                        if 1 <= num_maglia <= 11:
                            presenze_titolare += 1
                        elif 12 <= num_maglia <= 20:
                            presenze_subentro += 1

                    if is_portiere or "sicurezza_portiere" in d_p or "parate_decisive" in d_p or "parate" in d_p:
                        ha_dati_portiere = True
                        dp = estrai_dati_portiere_compat(d_p)
                        if ha_minuti:
                            lista_sicurezza_p.append(dp["sicurezza_portiere"])
                        tot_parate_dec += dp["parate_decisive"]
                        tot_gol_sub += dp["gol_subiti"]
                        tot_errori_p += dp["errori_gravi"]

                        ruolo_match = "POR (Porta)"
                        parametri_str = (
                            f"Sicurezza: {dp['sicurezza_portiere']} | Parate dec.: {dp['parate_decisive']} | "
                            f"Gol sub.: {dp['gol_subiti']} | Errori: {dp['errori_gravi']}{fp_suffix}"
                        )
                    else:
                        ha_dati_movimento = True
                        dm = estrai_dati_movimento_compat(d_p)
                        if ha_minuti:
                            lista_impatti.append(dm["impatto_partita"])
                            lista_gestione.append(dm["gestione_palla"])
                        tot_gol += dm["gol_fatti"]
                        tot_assist += dm["assist"]
                        tot_errori_mov += dm["errori_gravi"]

                        ruolo_c = d_p.get("ruolo_campo") or ruolo_default_da_rosa(
                            db_giocatori.get(giocatore_sel, {}).get("ruolo", "")
                        )
                        ruolo_match = f"{ruolo_c} ({get_etichetta_area(ruolo_c)})"
                        parametri_str = (
                            f"Impatto: {dm['impatto_partita']} | Palla/Duelli: {dm['gestione_palla']} | "
                            f"Gol: {dm['gol_fatti']} | Assist: {dm['assist']} | Errori: {dm['errori_gravi']}{fp_suffix}"
                        )

                    tipo_presenza = "Titolare" if 1 <= num_maglia <= 11 else ("Subentro" if 12 <= num_maglia <= 20 else "Rosa")
                    righe_match_giocatore.append({
                        "Partita": p_nome,
                        "Data": p_val.get("data", "N.D."),
                        "Presenza": tipo_presenza,
                        "Ruolo / Area": ruolo_match,
                        "Minuti": f"{min_giocati}'",
                        "Valutazione": parametri_str,
                        "Voto": f"{voto_match} / 10" if voto_match is not None else "N.D. (0')"
                    })

    tot_presenze = presenze_titolare + presenze_subentro
    media_stagione = round(sum(storico_voti) / len(storico_voti), 1) if storico_voti else None
    trend = calcola_trend_giocatore(storico_voti)

    c1, c2, c3 = st.columns(3)
    c1.metric("Partite Votate", len(storico_voti))
    c2.metric("Media Voto Stagionale", f"{media_stagione} / 10" if media_stagione is not None else "N.D.")
    c3.metric("Trend di Rendimento", trend)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="scoutai-box" style="margin-bottom: 18px;">
        <h4 style="margin-top: 0; color: {accent_hex}; border-bottom: 1px solid {tema['border_color']}; padding-bottom: 10px;">🧮 Sintesi Stagionale Snella: {giocatore_sel}</h4>
    """, unsafe_allow_html=True)

    if ha_dati_movimento:
        impatto_medio = calcola_media_giudizio(lista_impatti, OPZIONI_IMPATTO_PARTITA, SCALA_IMPATTO_PARTITA)
        gestione_media = calcola_media_giudizio(lista_gestione, OPZIONI_GESTIONE_PALLA, SCALA_GESTIONE_PALLA)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Impatto Medio", impatto_medio)
        m2.metric("Palla & Duelli", gestione_media)
        m3.metric("Gol Segnati", tot_gol)
        m4.metric("Assist", tot_assist)
        m5.metric("Errori Gravi", tot_errori_mov)

    if ha_dati_portiere:
        sicurezza_media = calcola_media_giudizio(lista_sicurezza_p, OPZIONI_SICUREZZA_PORTIERE, SCALA_SICUREZZA_PORTIERE)
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Sicurezza Media", sicurezza_media)
        p2.metric("Parate Decisive", tot_parate_dec)
        p3.metric("Gol Subiti", tot_gol_sub)
        p4.metric("Errori Gravi", tot_errori_p)

    if not ha_dati_movimento and not ha_dati_portiere:
        st.info("Nessun parametro registrato per questo giocatore.")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="scoutai-box" style="margin-bottom: 18px;">
        <h4 style="margin-top: 0; color: {accent_hex}; border-bottom: 1px solid {tema['border_color']}; padding-bottom: 10px;">📋 Dettaglio Presenze & Minutaggio: {giocatore_sel}</h4>
        <div style="display: flex; justify-content: space-around; text-align: center; margin-top: 15px;">
            <div>
                <span style="font-size: 13px; color: #a0aec0; display: block;">PRESENZE TOTALI</span>
                <span style="font-size: 24px; font-weight: bold; color: {tema['text_color']};">{tot_presenze}</span>
            </div>
            <div>
                <span style="font-size: 13px; color: #a0aec0; display: block;">DA TITOLARE (1-11)</span>
                <span style="font-size: 24px; font-weight: bold; color: {accent_hex};">{presenze_titolare}</span>
            </div>
            <div>
                <span style="font-size: 13px; color: #a0aec0; display: block;">SUBENTRI (12-20)</span>
                <span style="font-size: 24px; font-weight: bold; color: #3b82f6;">{presenze_subentro}</span>
            </div>
            <div>
                <span style="font-size: 13px; color: #a0aec0; display: block;">MINUTI GIOCATI</span>
                <span style="font-size: 24px; font-weight: bold; color: {accent_hex};">{tot_minuti}'</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"#### 🗓️ Dettaglio Partita per Partita: {giocatore_sel}")
    if righe_match_giocatore:
        st.table(pd.DataFrame(righe_match_giocatore))
    else:
        st.info("Nessuna partita con dati registrati per questo giocatore.")

# =====================================================================
# 5. GRAFICI & ANALISI VISIVA (ADATTATI AL MODELLO SNELLO)
# =====================================================================
elif menu == "📊 Grafici & Analisi Visiva":
    st.title("📊 Grafici & Analisi Visiva")

    glow_chart_px = max(4, min(28, int(glow_larghezza_px * 0.75)))
    glow_chart_color = hex_to_rgba(accent_hex, max(0.28, min(0.75, glow_intensita_alfa * 1.35)))

    st.markdown(f"""
    <style>
        .scoutai-chart-glow {{
            background-color: {tema['bg_card']};
            border: 1px solid {glow_border_rgba};
            border-radius: {radius_px}px;
            padding: 14px 16px 8px 16px;
            box-shadow: {box_shadow_glow};
            margin-bottom: 12px;
        }}
        .scoutai-chart-glow [data-testid="stVegaLiteChart"] canvas,
        .scoutai-chart-glow [data-testid="stVegaLiteChart"] svg {{
            filter: drop-shadow(0 0 {glow_chart_px}px {glow_chart_color});
        }}
    </style>
    """, unsafe_allow_html=True)

    def stile_chart_scoutai(chart, altezza=280):
        return (
            chart.properties(height=altezza, background="transparent")
            .configure_view(stroke=None, fill="transparent")
            .configure_axis(
                labelColor=tema["text_color"],
                titleColor="#cbd5e1",
                gridColor=hex_to_rgba(tema["text_color"], 0.10),
                domainColor=hex_to_rgba(tema["text_color"], 0.25),
                tickColor=hex_to_rgba(tema["text_color"], 0.25),
            )
            .configure_legend(
                labelColor=tema["text_color"],
                titleColor="#cbd5e1",
                symbolSize=120,
                symbolStrokeWidth=1.5,
            )
        )

    if not db_partite:
        st.warning("⚠️ Nessuna partita disponibile per generare i grafici.")
        st.stop()

    partite_ordinate = sorted(
        db_partite.items(),
        key=lambda item: parse_data_partita(item[1].get("data", "01/01/2026"))
    )

    st.subheader("🏆 Voto Medio Squadra per Partita")
    filtro_luogo = st.radio(
        "Filtra partite",
        ["Tutte", "Casa", "Trasferta"],
        horizontal=True,
        key="filtro_luogo_grafici"
    )

    righe_squadra_graf = []
    for idx_ord, (p_nome, p_val) in enumerate(partite_ordinate, start=1):
        luogo_m = p_val.get("casa_trasferta", "Casa")
        if filtro_luogo != "Tutte" and luogo_m != filtro_luogo:
            continue

        voti_match = []
        for n, nome in p_val.get("formazione", {}).items():
            if not nome:
                continue
            is_portiere = (str(n) in ["1", "12"])
            d_p = p_val.get("dati_prestazione", {}).get(nome, {})
            if d_p and int(d_p.get("minuti", 0)) > 0:
                v_g = calcola_voto(d_p, is_portiere)
                if v_g is not None:
                    voti_match.append(v_g)

        if voti_match:
            righe_squadra_graf.append({
                "Ordine": idx_ord,
                "Partita": p_nome,
                "Data": p_val.get("data", "N.D."),
                "Luogo": luogo_m,
                "Voto Medio": round(sum(voti_match) / len(voti_match), 2)
            })

    if righe_squadra_graf:
        df_sq = pd.DataFrame(righe_squadra_graf)
        chart_sq = (
            alt.Chart(df_sq)
            .mark_bar(
                cornerRadiusTopLeft=6,
                cornerRadiusTopRight=6,
                color=accent_hex,
                stroke=tema["text_color"],
                strokeWidth=0.6,
                strokeOpacity=0.35
            )
            .encode(
                x=alt.X("Partita:N", sort=alt.EncodingSortField(field="Ordine", order="ascending"), title="Partita"),
                y=alt.Y("Voto Medio:Q", scale=alt.Scale(domain=[0, 10]), title="Voto Medio Squadra"),
                tooltip=["Partita", "Data", "Luogo", "Voto Medio"]
            )
        )
        st.markdown("<div class='scoutai-chart-glow'>", unsafe_allow_html=True)
        st.altair_chart(stile_chart_scoutai(chart_sq, altezza=300), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("Nessun voto disponibile per il filtro selezionato.")

    st.divider()

    st.subheader("📈 Andamento Voti & Eventi Chiave Giocatore")
    nomi_rosa = list(db_giocatori.keys()) if db_giocatori else []
    if not nomi_rosa:
        st.info("Aggiungi almeno un giocatore in Gestione Rosa per visualizzare i grafici individuali.")
        st.stop()

    profilo_home_graf = ottieni_profilo_home_attivo()
    idx_graf_default = nomi_rosa.index(profilo_home_graf) if profilo_home_graf in nomi_rosa else 0

    gioc_graf = st.selectbox(
        "Seleziona Giocatore",
        nomi_rosa,
        index=idx_graf_default,
        key="sel_giocatore_grafici"
    )

    righe_voti_gioc = []
    tot_gol_g = 0
    tot_assist_g = 0
    tot_errori_g = 0
    tot_parate_g = 0
    tot_gol_sub_g = 0
    is_portiere_graf = False

    for idx_ord, (p_nome, p_val) in enumerate(partite_ordinate, start=1):
        formazione = p_val.get("formazione", {})
        for n, nome in formazione.items():
            if nome == gioc_graf:
                d_p = p_val.get("dati_prestazione", {}).get(gioc_graf, {})
                if not d_p:
                    continue
                min_m = int(d_p.get("minuti", 0))
                is_portiere = (str(n) in ["1", "12"])

                if min_m > 0:
                    v_m = calcola_voto(d_p, is_portiere)
                    if v_m is not None:
                        righe_voti_gioc.append({
                            "Ordine": idx_ord,
                            "Partita": p_nome,
                            "Minuti": min_m,
                            "Voto": v_m
                        })

                if is_portiere or "sicurezza_portiere" in d_p or "parate_decisive" in d_p or "parate" in d_p:
                    is_portiere_graf = True
                    dp = estrai_dati_portiere_compat(d_p)
                    tot_parate_g += dp["parate_decisive"]
                    tot_gol_sub_g += dp["gol_subiti"]
                    tot_errori_g += dp["errori_gravi"]
                else:
                    dm = estrai_dati_movimento_compat(d_p)
                    tot_gol_g += dm["gol_fatti"]
                    tot_assist_g += dm["assist"]
                    tot_errori_g += dm["errori_gravi"]

    col_g_sx, col_g_dx = st.columns(2)

    with col_g_sx:
        st.markdown(f"**Voto partita per partita ({gioc_graf})**")
        if righe_voti_gioc:
            df_vg = pd.DataFrame(righe_voti_gioc)
            media_g = round(df_vg["Voto"].mean(), 2)
            df_vg["Media Stagionale"] = media_g

            area_voto = (
                alt.Chart(df_vg)
                .mark_area(
                    color=alt.Gradient(
                        gradient="linear",
                        stops=[
                            alt.GradientStop(color=hex_to_rgba(accent_hex, 0.32), offset=0),
                            alt.GradientStop(color=hex_to_rgba(accent_hex, 0.02), offset=1),
                        ],
                        x1=0, x2=0, y1=0, y2=1
                    )
                )
                .encode(
                    x=alt.X("Partita:N", sort=alt.EncodingSortField(field="Ordine", order="ascending"), title="Partita"),
                    y=alt.Y("Voto:Q", scale=alt.Scale(domain=[1, 10]), title="Voto")
                )
            )
            linea_voto = (
                alt.Chart(df_vg)
                .mark_line(point=alt.OverlayMarkDef(filled=True, size=75, color=accent_hex, stroke="#ffffff", strokeWidth=1.5), strokeWidth=3.5, color=accent_hex)
                .encode(
                    x=alt.X("Partita:N", sort=alt.EncodingSortField(field="Ordine", order="ascending"), title="Partita"),
                    y=alt.Y("Voto:Q", scale=alt.Scale(domain=[1, 10]), title="Voto"),
                    tooltip=["Partita", "Minuti", "Voto", "Media Stagionale"]
                )
            )
            linea_media = (
                alt.Chart(df_vg)
                .mark_rule(strokeDash=[5, 5], strokeWidth=1.8, color="#e2e8f0")
                .encode(y="Media Stagionale:Q")
            )
            st.markdown("<div class='scoutai-chart-glow'>", unsafe_allow_html=True)
            st.altair_chart(stile_chart_scoutai(area_voto + linea_voto + linea_media, altezza=280), use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Nessuna partita votata (con minuti > 0) per questo giocatore.")

    with col_g_dx:
        st.markdown(f"**Eventi chiave accumulati ({gioc_graf})**")
        if is_portiere_graf:
            if tot_parate_g > 0 or tot_gol_sub_g > 0 or tot_errori_g > 0:
                df_param = pd.DataFrame({
                    "Evento": ["Parate Decisive", "Gol Subiti", "Errori Gravi"],
                    "Totale": [tot_parate_g, tot_gol_sub_g, tot_errori_g]
                })
                chart_ev = (
                    alt.Chart(df_param)
                    .mark_bar(
                        cornerRadiusTopLeft=6,
                        cornerRadiusTopRight=6,
                        stroke="#ffffff",
                        strokeWidth=1.2,
                        strokeOpacity=0.65
                    )
                    .encode(
                        x=alt.X("Evento:N", sort=["Parate Decisive", "Gol Subiti", "Errori Gravi"], title="Evento"),
                        y=alt.Y("Totale:Q", title="Totale"),
                        color=alt.Color(
                            "Evento:N",
                            scale=alt.Scale(
                                domain=["Parate Decisive", "Gol Subiti", "Errori Gravi"],
                                range=[accent_hex, "#38bdf8", "#f97316"]
                            ),
                            legend=alt.Legend(title="Tipo Evento")
                        ),
                        tooltip=["Evento", "Totale"]
                    )
                )
                st.markdown("<div class='scoutai-chart-glow'>", unsafe_allow_html=True)
                st.altair_chart(stile_chart_scoutai(chart_ev, altezza=280), use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("Nessun evento registrato per questo portiere.")
        else:
            if tot_gol_g > 0 or tot_assist_g > 0 or tot_errori_g > 0:
                df_param = pd.DataFrame({
                    "Evento": ["Gol Segnati", "Assist", "Errori Gravi"],
                    "Totale": [tot_gol_g, tot_assist_g, tot_errori_g]
                })
                chart_ev = (
                    alt.Chart(df_param)
                    .mark_bar(
                        cornerRadiusTopLeft=6,
                        cornerRadiusTopRight=6,
                        stroke="#ffffff",
                        strokeWidth=1.2,
                        strokeOpacity=0.65
                    )
                    .encode(
                        x=alt.X("Evento:N", sort=["Gol Segnati", "Assist", "Errori Gravi"], title="Evento"),
                        y=alt.Y("Totale:Q", title="Totale"),
                        color=alt.Color(
                            "Evento:N",
                            scale=alt.Scale(
                                domain=["Gol Segnati", "Assist", "Errori Gravi"],
                                range=[accent_hex, "#38bdf8", "#f97316"]
                            ),
                            legend=alt.Legend(title="Tipo Evento")
                        ),
                        tooltip=["Evento", "Totale"]
                    )
                )
                st.markdown("<div class='scoutai-chart-glow'>", unsafe_allow_html=True)
                st.altair_chart(stile_chart_scoutai(chart_ev, altezza=280), use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("Nessun evento chiave (gol, assist o errori) registrato.")

    st.divider()

    st.subheader("👥 Confronto Rosa: Minuti Giocati & Gol + Assist")
    righe_rosa_graf = []
    for nome_r in nomi_rosa:
        min_r = 0
        gol_r = 0
        assist_r = 0
        for _, p_val in partite_ordinate:
            for _, g_in_form in p_val.get("formazione", {}).items():
                if g_in_form == nome_r:
                    d_p = p_val.get("dati_prestazione", {}).get(nome_r, {})
                    if d_p:
                        min_r += int(d_p.get("minuti", 0))
                        dm = estrai_dati_movimento_compat(d_p)
                        gol_r += dm["gol_fatti"]
                        assist_r += dm["assist"]
        righe_rosa_graf.append({
            "Giocatore": nome_r,
            "Minuti Giocati": min_r,
            "Gol": gol_r,
            "Assist": assist_r,
        })

    if righe_rosa_graf:
        df_rosa_g = pd.DataFrame(righe_rosa_graf).sort_values("Minuti Giocati", ascending=False)
        c_r1, c_r2 = st.columns(2)

        with c_r1:
            st.markdown("**Minuti giocati in stagione**")
            chart_min = (
                alt.Chart(df_rosa_g)
                .mark_bar(
                    cornerRadiusTopLeft=5,
                    cornerRadiusTopRight=5,
                    color=accent_hex,
                    stroke="#ffffff",
                    strokeWidth=0.9,
                    strokeOpacity=0.55
                )
                .encode(
                    x=alt.X("Giocatore:N", sort="-y", title="Giocatore"),
                    y=alt.Y("Minuti Giocati:Q", title="Minuti"),
                    tooltip=["Giocatore", "Minuti Giocati"]
                )
            )
            st.markdown("<div class='scoutai-chart-glow'>", unsafe_allow_html=True)
            st.altair_chart(stile_chart_scoutai(chart_min, altezza=280), use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with c_r2:
            st.markdown("**Gol e Assist in stagione**")
            ordine_ga = (
                df_rosa_g.assign(_tot_ga=df_rosa_g["Gol"] + df_rosa_g["Assist"])
                .sort_values(["_tot_ga", "Gol"], ascending=False)["Giocatore"]
                .tolist()
            )
            df_ga_long = df_rosa_g.melt(
                id_vars=["Giocatore"],
                value_vars=["Gol", "Assist"],
                var_name="Voce",
                value_name="Conteggio"
            )
            chart_ga = (
                alt.Chart(df_ga_long)
                .mark_bar(
                    cornerRadiusTopLeft=5,
                    cornerRadiusTopRight=5,
                    stroke="#ffffff",
                    strokeWidth=1.1,
                    strokeOpacity=0.65
                )
                .encode(
                    x=alt.X("Giocatore:N", sort=ordine_ga, title="Giocatore"),
                    y=alt.Y("Conteggio:Q", title="Totale"),
                    xOffset=alt.XOffset("Voce:N", sort=["Gol", "Assist"]),
                    color=alt.Color(
                        "Voce:N",
                        scale=alt.Scale(
                            domain=["Gol", "Assist"],
                            range=[accent_hex, "#38bdf8"]
                        ),
                        legend=alt.Legend(title="Voce")
                    ),
                    tooltip=["Giocatore", "Voce", "Conteggio"]
                )
            )
            st.markdown("<div class='scoutai-chart-glow'>", unsafe_allow_html=True)
            st.altair_chart(stile_chart_scoutai(chart_ga, altezza=280), use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

# =====================================================================
# 6. FAIR PLAY (AMMONIZIONI & ESPULSIONI)
# =====================================================================
elif menu == "🟨 Fair Play":
    st.title("🟨 Fair Play — Ammonizioni & Espulsioni")
    st.caption(
        "Riepilogo delle spunte **Ammonizione** ed **Espulsione** inserite nei parametri di gara. "
        "L'ammonizione è segnalata in **giallo**, l'espulsione in **rosso** e incide sul voto con un **-1.0**."
    )

    partite_ordinate_fp = sorted(
        db_partite.items(),
        key=lambda item: parse_data_partita(item[1].get("data", "01/01/2026"))
    )

    tot_amm_stag = 0
    tot_esp_stag = 0
    riepilogo_giocatori_fp = {
        nome_g: {"Giocatore": nome_g, "Ruolo": dati_g.get("ruolo", "-"), "Ammonizioni": 0, "Espulsioni": 0, "Penalità Voto": 0.0, "Partite Sanzionate": []}
        for nome_g, dati_g in db_giocatori.items()
    }
    dettaglio_match_fp = []

    for p_nome, p_val in partite_ordinate_fp:
        amm_match = 0
        esp_match = 0
        sanzionati_match = []

        for n, nome in p_val.get("formazione", {}).items():
            if not nome:
                continue
            d_p = p_val.get("dati_prestazione", {}).get(nome, {})
            if not d_p:
                continue
            fp = estrai_fairplay_compat(d_p)
            if not fp["ammonito"] and not fp["espulso"]:
                continue

            if nome not in riepilogo_giocatori_fp:
                riepilogo_giocatori_fp[nome] = {
                    "Giocatore": nome,
                    "Ruolo": db_giocatori.get(nome, {}).get("ruolo", "-"),
                    "Ammonizioni": 0,
                    "Espulsioni": 0,
                    "Penalità Voto": 0.0,
                    "Partite Sanzionate": []
                }

            etichette_g = []
            if fp["ammonito"]:
                amm_match += 1
                tot_amm_stag += 1
                riepilogo_giocatori_fp[nome]["Ammonizioni"] += 1
                etichette_g.append("🟡 Ammonito")
            if fp["espulso"]:
                esp_match += 1
                tot_esp_stag += 1
                riepilogo_giocatori_fp[nome]["Espulsioni"] += 1
                riepilogo_giocatori_fp[nome]["Penalità Voto"] = round(riepilogo_giocatori_fp[nome]["Penalità Voto"] - 1.0, 1)
                etichette_g.append("🔴 Espulso (-1)")

            riepilogo_giocatori_fp[nome]["Partite Sanzionate"].append(f"{p_nome} ({', '.join(etichette_g)})")
            sanzionati_match.append(f"{nome} [{' / '.join(etichette_g)}]")

        if amm_match > 0 or esp_match > 0:
            dettaglio_match_fp.append({
                "Partita": p_nome,
                "Data": p_val.get("data", "N.D."),
                "Ammonizioni": amm_match,
                "Espulsioni": esp_match,
                "Giocatori Sanzionati": ", ".join(sanzionati_match)
            })

    c_fp1, c_fp2, c_fp3 = st.columns(3)
    c_fp1.metric("🟡 Ammonizioni Totali", tot_amm_stag)
    c_fp2.metric("🔴 Espulsioni Totali", tot_esp_stag)
    c_fp3.metric("📉 Impatto Totale Espulsioni", f"{-1.0 * tot_esp_stag:.1f} pt" if tot_esp_stag > 0 else "0.0 pt")

    st.divider()
    st.subheader("👤 Riepilogo Giocatori")
    righe_g_fp = []
    for rec in riepilogo_giocatori_fp.values():
        if rec["Ammonizioni"] > 0 or rec["Espulsioni"] > 0:
            righe_g_fp.append({
                "Giocatore": rec["Giocatore"],
                "Ruolo": rec["Ruolo"],
                "🟡 Ammonizioni": rec["Ammonizioni"],
                "🔴 Espulsioni": rec["Espulsioni"],
                "Impatto Espulsioni": f"{rec['Penalità Voto']:.1f}" if rec["Penalità Voto"] < 0 else "0.0",
                "Dettaglio Gare": " ; ".join(rec["Partite Sanzionate"])
            })

    if righe_g_fp:
        df_g_fp = pd.DataFrame(righe_g_fp).sort_values(
            by=["🔴 Espulsioni", "🟡 Ammonizioni", "Giocatore"],
            ascending=[False, False, True]
        )
        st.table(df_g_fp)
    else:
        st.info("Nessuna ammonizione o espulsione spuntata finora nei parametri delle partite.")

    st.divider()
    st.subheader("🗓️ Dettaglio per Partita")
    if dettaglio_match_fp:
        st.table(pd.DataFrame(dettaglio_match_fp))
    else:
        st.info("Nessuna partita con cartellini registrati.")

# =====================================================================
# 7. GESTIONE ROSA
# =====================================================================
elif menu == "👤 Gestione Rosa":
    st.title("👤 Gestione Rosa Squadra")
    lettura_only = is_sola_lettura()

    if not lettura_only:
        st.subheader("📥 Template & Importazione CSV Rosa")
        col_dl, col_rs = st.columns(2)
        with col_dl:
            df_template = pd.DataFrame({
                "Nome": ["Mario Rossi", "Luigi Bianchi"],
                "Ruolo": ["Difensore Centrale (DC)", "Portiere (POR)"]
            })
            csv_template = df_template.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Scarica Template CSV Rosa",
                data=csv_template,
                file_name="template_rosa_scoutai.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col_rs:
            if st.button("🗑️ Resetta Tutta la Rosa", use_container_width=True, type="secondary"):
                st.session_state["database_giocatori"] = {}
                salva_dati_su_disco()
                st.success("Rosa resettata completamente!")
                st.rerun()

        uploaded_csv = st.file_uploader("📤 Carica file CSV compilato con la nuova rosa", type=["csv"])
        if uploaded_csv is not None:
            df_upload = None
            for enc in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    uploaded_csv.seek(0)
                    df_upload = pd.read_csv(uploaded_csv, encoding=enc)
                    break
                except Exception:
                    continue

            if df_upload is not None:
                if "Nome" in df_upload.columns and "Ruolo" in df_upload.columns:
                    st.success(f"File CSV letto con successo! Trovati {len(df_upload)} record.")
                    if st.button("✅ Conferma e Sostituisci Rosa con il File Caricato", type="primary"):
                        nuova_rosa = {}
                        for _, row in df_upload.iterrows():
                            nome = str(row["Nome"]).strip()
                            ruolo = str(row["Ruolo"]).strip()
                            if nome and nome.lower() != 'nan':
                                vecchia_foto = ottieni_foto_valida(nome, db_giocatori)
                                nuova_rosa[nome] = {"ruolo": ruolo, "partite": {}, "foto_path": vecchia_foto}
                        st.session_state["database_giocatori"] = nuova_rosa
                        salva_dati_su_disco()
                        st.success(f"Rosa aggiornata con successo! Caricati {len(nuova_rosa)} giocatori.")
                        st.rerun()
                else:
                    st.error("Il file CSV deve contenere esattamente le colonne 'Nome' e 'Ruolo'.")
            else:
                st.error("Errore nella lettura del file CSV: impossibile decodificare il file.")

        st.divider()

        with st.form("aggiungi_giocatore_form"):
            st.subheader("Aggiungi Singolo Giocatore Manualmente")
            n_nome = st.text_input("Nome e Cognome")
            n_ruolo = st.selectbox("Ruolo", ["Portiere (POR)", "Difensore Centrale (DC)", "Terzino (TS/TD)", "Centrocampista (CC)", "Esterno (EST)", "Attaccante (ATT)"])
            if st.form_submit_button("Aggiungi alla Rosa") and n_nome:
                if n_nome not in db_giocatori:
                    db_giocatori[n_nome] = {"ruolo": n_ruolo, "partite": {}, "foto_path": None}
                    salva_dati_su_disco()
                    st.success(f"Giocatore {n_nome} aggiunto e salvato con successo!")
                    st.rerun()

        st.divider()

    st.subheader("Rosa Attuale")
    if not db_giocatori:
        st.info("La rosa è attualmente vuota.")
    else:
        for nome, dati in list(db_giocatori.items()):
            foto_att = ottieni_foto_valida(nome, db_giocatori)
            chiave_box_foto = f"mostra_box_foto_{nome}"
            if chiave_box_foto not in st.session_state:
                st.session_state[chiave_box_foto] = False

            if lettura_only:
                c_img, c1 = st.columns([0.55, 4.35])
            else:
                c_img, c1, c_btn_foto, c_btn_del = st.columns([0.55, 2.55, 0.9, 0.9])

            with c_img:
                if foto_att:
                    st.image(foto_att, width=46)
                else:
                    st.markdown(
                        "<div style='width:46px;height:46px;border-radius:50%;display:flex;align-items:center;"
                        "justify-content:center;background:#1e2230;font-size:20px;'>🧑🏻</div>",
                        unsafe_allow_html=True
                    )
            with c1:
                stato_foto = " · 🖼️ Foto caricata" if foto_att else ""
                st.markdown(
                    f"<div class='scoutai-box' style='padding: 10px 14px; margin-bottom: 8px;'>"
                    f"📌 <strong>{nome}</strong> — <em>Ruolo:</em> {dati['ruolo']}{stato_foto}</div>",
                    unsafe_allow_html=True
                )

            if not lettura_only:
                with c_btn_foto:
                    if st.button("📷 Foto", key=f"btn_foto_{nome}", use_container_width=True):
                        st.session_state[chiave_box_foto] = not st.session_state[chiave_box_foto]
                        st.rerun()
                with c_btn_del:
                    if st.button("🗑️ Elimina", key=f"del_g_{nome}", use_container_width=True):
                        if foto_att and os.path.exists(foto_att):
                            try:
                                os.remove(foto_att)
                            except OSError:
                                pass
                        del db_giocatori[nome]
                        salva_dati_su_disco()
                        st.success(f"Rimosso {nome} e salvato.")
                        st.rerun()

                if st.session_state.get(chiave_box_foto):
                    with st.container():
                        f_up, f_save, f_rem = st.columns([2.6, 1.0, 1.0])
                        with f_up:
                            file_foto = st.file_uploader(
                                f"Carica foto di {nome}",
                                type=["png", "jpg", "jpeg", "webp"],
                                key=f"up_foto_{nome}",
                                label_visibility="collapsed"
                            )
                        with f_save:
                            if st.button("💾 Salva Foto", key=f"save_foto_{nome}", use_container_width=True):
                                if file_foto is not None:
                                    nuovo_path = salva_foto_giocatore(nome, file_foto)
                                    db_giocatori[nome]["foto_path"] = nuovo_path
                                    st.session_state[chiave_box_foto] = False
                                    salva_dati_su_disco()
                                    st.success(f"Foto salvata per {nome}!")
                                    st.rerun()
                                else:
                                    st.warning("Seleziona prima un'immagine.")
                        with f_rem:
                            if st.button("❌ Rimuovi Foto", key=f"rem_foto_{nome}", use_container_width=True):
                                if foto_att and os.path.exists(foto_att):
                                    try:
                                        os.remove(foto_att)
                                    except OSError:
                                        pass
                                db_giocatori[nome]["foto_path"] = None
                                st.session_state[chiave_box_foto] = False
                                salva_dati_su_disco()
                                st.info(f"Foto rimossa per {nome}.")
                                st.rerun()

# =====================================================================
# 8. EDITOR GRAFICA & SETTINGS
# =====================================================================
elif menu == "🎨 Editor Grafica":
    st.title("🎨 Editor Grafica & Impostazioni UI")

    if st.session_state.get("ui_notice"):
        mostra_notifica_tema(st.session_state["ui_notice"], icona="✨")
        st.session_state["ui_notice"] = None

    st.subheader("🎭 Preset Tema")
    cols_preset = st.columns(len(PRESET_TEMI))
    for idx, (n_preset, v_preset) in enumerate(PRESET_TEMI.items()):
        with cols_preset[idx]:
            if st.button(n_preset, use_container_width=True, key=f"preset_{idx}"):
                st.session_state["ui_theme"] = v_preset.copy()
                salva_dati_su_disco()
                st.session_state["ui_notice"] = f"Preset '{n_preset}' applicato e salvato con successo."
                st.rerun()

    st.divider()
    st.subheader("🎛️ Personalizzazione Font, Glow dei Box & Schermo")

    attiva_fs = st.toggle(
        "Abilita Modalità Fullscreen (Tutto Schermo)",
        value=st.session_state["fullscreen_mode"],
        key="toggle_fs_editor"
    )

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        nuovo_font_size = st.slider(
            "Dimensione Font (px)",
            min_value=13,
            max_value=22,
            value=int(tema.get("font_size", 16)),
            step=1,
            key="slider_font_size"
        )
    with col_f2:
        nuova_ombra = st.slider(
            "Ombreggiatura Esterna Box (%)",
            min_value=0,
            max_value=80,
            value=int(tema.get("shadow_intensity", 25)),
            step=5,
            key="slider_shadow_intensity"
        )

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        nuova_glow_intensita = st.slider(
            "Intensità Glow Box (%)",
            min_value=0,
            max_value=85,
            value=int(tema.get("glow_intensity", 25)),
            step=5,
            key="slider_glow_intensity"
        )
    with col_g2:
        nuova_glow_larghezza = st.slider(
            "Larghezza Glow Box (px)",
            min_value=0,
            max_value=40,
            value=int(tema.get("glow_width", 14)),
            step=2,
            key="slider_glow_width"
        )

    st.divider()
    nuove_schede_graf, nascondi_admin_graf = render_controllo_schede_ui(key_prefix="grafica")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 Salva Impostazioni Grafiche", use_container_width=True, key="btn_salva_grafica"):
        st.session_state["ui_theme"]["font_size"] = int(nuovo_font_size)
        st.session_state["ui_theme"]["shadow_intensity"] = int(nuova_ombra)
        st.session_state["ui_theme"]["glow_intensity"] = int(nuova_glow_intensita)
        st.session_state["ui_theme"]["glow_width"] = int(nuova_glow_larghezza)
        st.session_state["fullscreen_mode"] = bool(attiva_fs)
        st.session_state["auth_config"]["schede_attive"] = nuove_schede_graf
        st.session_state["auth_config"]["applica_nascoste_ad_admin"] = nascondi_admin_graf
        salva_dati_su_disco()
        st.session_state["ui_notice"] = (
            f"Modifiche salvate e applicate! Font: {nuovo_font_size}px · "
            f"Glow: {nuova_glow_intensita}% / {nuova_glow_larghezza}px · "
            f"Schede attive: {len(nuove_schede_graf)}."
        )
        st.rerun()

# =====================================================================
# 9. PANNELLO ADMIN
# =====================================================================
elif menu == "🛡️ Pannello Admin":
    if not st.session_state.get("is_admin", False):
        st.warning("Accesso riservato all'Admin. Effettua il login dalla sidebar.")
        st.stop()

    st.title("🛡️ Pannello Admin — Controllo Accessi, Schede & Backup")

    if st.session_state.get("admin_notice"):
        st.success(st.session_state["admin_notice"])
        st.session_state["admin_notice"] = None

    with st.form("form_admin_accessi"):
        st.subheader("1. Regole Accesso Ragazzi")
        sola_lettura_attiva = st.toggle(
            "Limita accesso in sola lettura per i ragazzi (blocca modifiche, salvataggi, eliminazioni e upload)",
            value=bool(auth_cfg.get("read_only_boys", True)),
        )

        opzioni_sez_ragazzi = [s for s in TUTTE_LE_SCHEDE_APP if s != "🎨 Editor Grafica"]
        sezioni_scelte = st.multiselect(
            "Sezioni visibili ai ragazzi",
            options=opzioni_sez_ragazzi,
            default=[s for s in auth_cfg.get("sezioni_ragazzi", []) if s in opzioni_sez_ragazzi],
        )

        st.divider()
        st.subheader("2. Cambia PIN Admin")
        nuovo_pin = st.text_input("Nuovo PIN (lascia vuoto per mantenere l'attuale)", type="password")
        conferma_pin = st.text_input("Conferma Nuovo PIN", type="password")

        if st.form_submit_button("💾 Salva Accessi & PIN", use_container_width=True):
            if nuovo_pin or conferma_pin:
                if nuovo_pin != conferma_pin:
                    st.error("I due PIN non coincidono.")
                    st.stop()
                if len(nuovo_pin.strip()) < 4:
                    st.error("Usa un PIN di almeno 4 caratteri.")
                    st.stop()
                auth_cfg["admin_pin_hash"] = _hash_pin(nuovo_pin.strip())

            auth_cfg["read_only_boys"] = bool(sola_lettura_attiva)
            auth_cfg["sezioni_ragazzi"] = sezioni_scelte if sezioni_scelte else ["🎥 Video Analisi", "📈 Riepilogo Squadra"]
            st.session_state["auth_config"] = auth_cfg
            salva_dati_su_disco()
            st.success("Impostazioni di accesso salvate!")
            st.rerun()

    st.divider()
    nuove_schede_adm, nascondi_admin_adm = render_controllo_schede_ui(key_prefix="admin_tab")
    if st.button("💾 Salva Visibilità Schede", use_container_width=True, key="btn_salva_schede_admin"):
        auth_cfg["schede_attive"] = nuove_schede_adm
        auth_cfg["applica_nascoste_ad_admin"] = nascondi_admin_adm
        st.session_state["auth_config"] = auth_cfg
        salva_dati_su_disco()
        st.success("Visibilità delle schede salvata!")
        st.rerun()

    st.divider()
    st.subheader("💾 Backup & Ripristino Completo (JSON)")
    st.caption(
        "Esporta un file `.json` con tutta la rosa, le partite, le valutazioni, i link video, il tema e gli accessi. "
        "Puoi importarlo in qualsiasi momento per ripristinare i dati."
    )

    col_exp_json, col_imp_json = st.columns(2)
    with col_exp_json:
        json_backup_str = json.dumps(costruisci_payload_database(), ensure_ascii=False, indent=4).encode("utf-8")
        nome_file_backup = f"scoutai_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        st.download_button(
            "📤 Esporta Backup Completo JSON",
            data=json_backup_str,
            file_name=nome_file_backup,
            mime="application/json",
            use_container_width=True,
            key="btn_export_backup_json"
        )

    with col_imp_json:
        uploaded_backup_json = st.file_uploader(
            "Seleziona file di backup JSON",
            type=["json"],
            key="uploader_backup_json",
            label_visibility="collapsed"
        )
        if st.button("📥 Importa Backup JSON", use_container_width=True, key="btn_import_backup_json"):
            if uploaded_backup_json is None:
                st.warning("Seleziona prima un file `.json` di backup.")
            else:
                try:
                    uploaded_backup_json.seek(0)
                    raw_bytes = uploaded_backup_json.read()
                    parsed_payload = json.loads(raw_bytes.decode("utf-8"))
                    ok, msg = applica_payload_database(parsed_payload)
                    if ok:
                        st.session_state["admin_notice"] = msg
                        st.rerun()
                    else:
                        st.error(msg)
                except json.JSONDecodeError:
                    st.error("File JSON non valido o danneggiato.")
                except Exception as e:
                    st.error(f"Errore durante l'importazione: {e}")

    st.divider()
    st.subheader("📊 Registro Accessi dalla Home")
    opzioni_reg = ottieni_opzioni_accesso_home(db_giocatori)
    stats_reg = st.session_state.get("statistiche_accessi", {})
    righe_accessi = []
    for u_nome in opzioni_reg:
        info_u = stats_reg.get(u_nome, {})
        righe_accessi.append({
            "Utente / Giocatore": u_nome,
            "Accessi": int(info_u.get("count", 0)),
            "Ultimo Accesso": info_u.get("ultimo_accesso") or "Mai",
        })
    df_accessi = pd.DataFrame(righe_accessi).sort_values(
        by=["Accessi", "Utente / Giocatore"], ascending=[False, True]
    )
    st.table(df_accessi)

    col_rst_singolo, col_rst_tutti = st.columns([2, 1.3])
    with col_rst_singolo:
        utente_reset = st.selectbox(
            "Seleziona utente da azzerare",
            options=opzioni_reg,
            key="sel_utente_reset_accessi",
            label_visibility="collapsed"
        )
        if st.button("🔄 Reset Contatore Accessi", use_container_width=True, key="btn_reset_singolo_accesso"):
            st.session_state.setdefault("statistiche_accessi", {})[utente_reset] = {
                "count": 0,
                "ultimo_accesso": "Mai",
            }
            salva_dati_su_disco()
            st.success(f"Contatore accessi resettato per {utente_reset}!")
            st.rerun()

    with col_rst_tutti:
        st.markdown("<div style='height: 38px;'></div>", unsafe_allow_html=True)
        if st.button("🗑️ Reset Tutti gli Accessi", use_container_width=True, key="btn_reset_accessi"):
            st.session_state["statistiche_accessi"] = {}
            salva_dati_su_disco()
            st.success("Tutti i contatori accessi sono stati resettati!")
            st.rerun()
