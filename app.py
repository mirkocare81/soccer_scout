import streamlit as st
import pandas as pd
import io
import time
import os
import json
import re
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
# COSTANTI RUOLI IN CAMPO & EFFICACIA PASSAGGI
# =====================================================================
RUOLI_DIFENSORI = ["TS", "DC", "TD"]
RUOLI_CENTROCAMPISTI = ["CDC", "CC", "TQ"]
RUOLI_ATTACCANTI = ["AS", "AT", "AD"]
TUTTI_RUOLI_MOVIMENTO = RUOLI_DIFENSORI + RUOLI_CENTROCAMPISTI + RUOLI_ATTACCANTI

OPZIONI_EFFICACIA_PASSAGGI = ["Ottima", "Buona", "Sufficiente", "Insufficiente", "Pessima"]
DELTA_EFFICACIA_PASSAGGI = {
    "Ottima": 0.7,
    "Buona": 0.4,
    "Sufficiente": 0.1,
    "Insufficiente": -0.3,
    "Pessima": -0.5,
}
SCALA_MEDIA_EFFICACIA_PASSAGGI = {
    "Ottima": 2.0,
    "Buona": 1.0,
    "Sufficiente": 0.0,
    "Insufficiente": -1.0,
    "Pessima": -2.0,
}

def normalizza_efficacia_passaggi(valore):
    """Converte valori vecchi (es. percentuali o stringhe) in una categoria valida."""
    if isinstance(valore, str) and valore.strip() in DELTA_EFFICACIA_PASSAGGI:
        return valore.strip()
    try:
        pct = float(valore)
        if pct >= 85:
            return "Ottima"
        elif pct >= 75:
            return "Buona"
        elif pct >= 60:
            return "Sufficiente"
        elif pct >= 40:
            return "Insufficiente"
        else:
            return "Pessima"
    except Exception:
        return "Buona"

def calcola_efficacia_passaggi_media(valori):
    """Restituisce l'etichetta media finale su scala ordinata (con preferenza al livello superiore in caso di parità)."""
    if not valori:
        return "N.D."
    normalizzati = [normalizza_efficacia_passaggi(v) for v in valori]
    media_scala = sum(SCALA_MEDIA_EFFICACIA_PASSAGGI[e] for e in normalizzati) / len(normalizzati)
    return min(
        OPZIONI_EFFICACIA_PASSAGGI,
        key=lambda k: abs(SCALA_MEDIA_EFFICACIA_PASSAGGI[k] - media_scala)
    )

def get_macro_ruolo(ruolo_specifico):
    if ruolo_specifico in RUOLI_DIFENSORI:
        return "DIFENSORE"
    elif ruolo_specifico in RUOLI_CENTROCAMPISTI:
        return "CENTROCAMPISTA"
    elif ruolo_specifico in RUOLI_ATTACCANTI:
        return "ATTACCANTE"
    return "CENTROCAMPISTA"

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

def valori_base_giocatore(nome_g, is_portiere, is_riserva, db_giocatori):
    """Restituisce i valori iniziali/azzerati per un giocatore."""
    min_default = 0 if is_riserva else 80
    if is_portiere:
        return {
            "minuti": min_default,
            "parate": 0,
            "uscite": "0/0",
            "gol_subiti_resp": "0/0",
        }
    return {
        "ruolo_campo": ruolo_default_da_rosa(db_giocatori.get(nome_g, {}).get("ruolo", "")),
        "minuti": min_default,
        "duelli": "0/0",
        "efficacia_passaggi": "Buona",
        "perse": 0,
        "tiri": "0/0",
        "gol_fatti": 0,
        "salvataggi": 0,
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

        # Aggiorna subito i widget dei parametri (escludendo ruolo_... / ruolo_res_...)
        if not is_riserva:
            if is_portiere:
                st.session_state[f"min_{partita_sel}_{num_int}"] = int(base["minuti"])
                st.session_state[f"par_{partita_sel}_{num_int}"] = int(base["parate"])
                st.session_state[f"usc_{partita_sel}_{num_int}"] = str(base["uscite"])
                st.session_state[f"gol_sub_{partita_sel}_{num_int}"] = str(base["gol_subiti_resp"])
            else:
                st.session_state[f"min_{partita_sel}_{num_int}"] = int(base["minuti"])
                st.session_state[f"due_{partita_sel}_{num_int}"] = str(base["duelli"])
                st.session_state[f"pas_{partita_sel}_{num_int}"] = str(base["efficacia_passaggi"])
                st.session_state[f"per_{partita_sel}_{num_int}"] = int(base["perse"])
                st.session_state[f"tir_{partita_sel}_{num_int}"] = str(base["tiri"])
                st.session_state[f"gol_{partita_sel}_{num_int}"] = int(base["gol_fatti"])
        else:
            if is_portiere:
                st.session_state[f"min_res_{partita_sel}_{num_int}"] = int(base["minuti"])
                st.session_state[f"par_res_{partita_sel}_{num_int}"] = int(base["parate"])
                st.session_state[f"usc_res_{partita_sel}_{num_int}"] = str(base["uscite"])
                st.session_state[f"gol_sub_res_{partita_sel}_{num_int}"] = str(base["gol_subiti_resp"])
            else:
                st.session_state[f"min_res_{partita_sel}_{num_int}"] = int(base["minuti"])
                st.session_state[f"due_res_{partita_sel}_{num_int}"] = str(base["duelli"])
                st.session_state[f"pas_res_{partita_sel}_{num_int}"] = str(base["efficacia_passaggi"])
                st.session_state[f"per_res_{partita_sel}_{num_int}"] = int(base["perse"])
                st.session_state[f"tir_res_{partita_sel}_{num_int}"] = str(base["tiri"])
                st.session_state[f"gol_res_{partita_sel}_{num_int}"] = int(base["gol_fatti"])

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
# GESTIONE LOGO & FILE PERSISTENTI (JSON)
# =====================================================================
LOGO_PATH = "Channel logo.jpg" if os.path.exists("Channel logo.jpg") else ("logo.png" if os.path.exists("logo.png") else None)
DB_FILE = "scoutai_database.json"

def salva_dati_su_disco():
    """Salvataggio automatico istantaneo su file JSON"""
    try:
        data_to_save = {
            "giocatori": st.session_state.get("database_giocatori", {}),
            "partite": st.session_state.get("database_partite", {}),
            "partita_attiva": st.session_state.get("partita_attiva"),
            "ui_theme": st.session_state.get("ui_theme", {}),
            "fullscreen_mode": st.session_state.get("fullscreen_mode", False)
        }
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Errore durante il salvataggio automatico: {e}")

def carica_dati_da_disco():
    """Caricamento dati da file JSON se esiste"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return None

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
    """Converte una stringa data in oggetto datetime per ordinamento sicuro (fallback a data odierna se non parsabile)"""
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
            "Lorenzo": {"ruolo": "Portiere (POR)", "partite": {}},
            "Mattia": {"ruolo": "Difensore Centrale (DC)", "partite": {}},
            "Filippo": {"ruolo": "Centrocampista (CC)", "partite": {}},
            "Davide": {"ruolo": "Attaccante (ATT)", "partite": {}},
            "Simone": {"ruolo": "Terzino (TS/TD)", "partite": {}},
            "Federico": {"ruolo": "Centrocampista (CC)", "partite": {}},
            "Alessandro": {"ruolo": "Attaccante (ATT)", "partite": {}},
            "Luca": {"ruolo": "Difensore Centrale (DC)", "partite": {}},
            "Marco": {"ruolo": "Esterno (EST)", "partite": {}},
            "Giovanni": {"ruolo": "Centrocampista (CC)", "partite": {}},
            "Tommaso": {"ruolo": "Attaccante (ATT)", "partite": {}},
            "Pietro": {"ruolo": "Portiere (POR)", "partite": {}},
            "Riccardo": {"ruolo": "Riserva / Jolly", "partite": {}},
            "Edoardo": {"ruolo": "Riserva / Jolly", "partite": {}}
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

    .scoutai-video-empty {{
        background-color: {tema['bg_card']};
        border: 2px dashed {glow_border_rgba};
        border-radius: {radius_px}px;
        height: 320px;
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
# MOTORE DI CALCOLO VOTO & TREND (PESATO PER RUOLO)
# =====================================================================
def calcola_voto(p, is_portiere=False):
    try:
        minuti_giocati = int(p.get('minuti', 80))
        fattore_tempo = minuti_giocati / 80.0 if minuti_giocati > 0 else 1.0
        rating = 6.0

        if is_portiere:
            parate = int(p.get('parate', 0))
            uscite_v, uscite_t = map(int, p.get('uscite', '0/0').split("/"))
            gol_subiti, gol_resp = map(int, p.get('gol_subiti_resp', '0/0').split("/"))

            rating += (parate * 0.4) * fattore_tempo
            
            pct_uscite = (uscite_v / uscite_t) if uscite_t > 0 else 0
            if pct_uscite >= 0.75 and uscite_t >= 1:
                rating += 0.3 * fattore_tempo
            elif pct_uscite < 0.40 and uscite_t > 0:
                rating -= 0.3 * fattore_tempo

            rating -= (gol_subiti * 0.4) * fattore_tempo
            rating -= (gol_resp * 1.0) * fattore_tempo
        else:
            ruolo_campo = p.get("ruolo_campo", "CC")
            macro_ruolo = get_macro_ruolo(ruolo_campo)

            duelli_v, duelli_t = map(int, p.get('duelli', '0/0').split("/"))
            val_raw_pass = p.get('efficacia_passaggi', p.get('passaggi', 'Buona'))
            efficacia_pass = normalizza_efficacia_passaggi(val_raw_pass)
            delta_pass = DELTA_EFFICACIA_PASSAGGI.get(efficacia_pass, 0.0)
            perse = int(p.get('perse', 0))
            tiri_porta, tiri_specchio = map(int, p.get('tiri', '0/0').split("/"))
            gol_fatti = int(p.get('gol_fatti', 0))

            pct_duelli = (duelli_v / duelli_t) if duelli_t > 0 else 0

            if macro_ruolo == "DIFENSORE":
                peso_duelli = 1.8
                peso_passaggi = 0.5
                peso_perse = 0.5
                peso_tiri = 0.5
                soglia_duelli_min = 2
            elif macro_ruolo == "CENTROCAMPISTA":
                peso_duelli = 0.7
                peso_passaggi = 1.7
                peso_perse = 1.7
                peso_tiri = 0.6
                soglia_duelli_min = 3
            else:
                peso_duelli = 0.6
                peso_passaggi = 0.5
                peso_perse = 0.6
                peso_tiri = 1.9
                soglia_duelli_min = 2

            if pct_duelli >= 0.75 and duelli_t >= soglia_duelli_min:
                rating += (0.4 * peso_duelli) * min(1.0, fattore_tempo + 0.2)
            elif pct_duelli >= 0.55 and duelli_t >= soglia_duelli_min and macro_ruolo == "DIFENSORE":
                rating += (0.2 * peso_duelli) * fattore_tempo
            elif pct_duelli < 0.40 and duelli_t > 0:
                rating -= (0.4 * peso_duelli) * fattore_tempo

            if delta_pass >= 0:
                rating += (delta_pass * peso_passaggi) * min(1.0, fattore_tempo + 0.2)
            else:
                rating += (delta_pass * peso_passaggi) * fattore_tempo

            if perse > 0:
                rating -= (perse * 0.6 * peso_perse) * fattore_tempo

            if tiri_specchio > 0:
                efficacia = tiri_porta / tiri_specchio
                if efficacia >= 0.66:
                    rating += (0.4 * peso_tiri) * fattore_tempo
                elif tiri_specchio >= 2 and efficacia < 0.30:
                    rating -= (0.2 * peso_tiri) * fattore_tempo

            if gol_fatti > 0:
                rating += (gol_fatti * 1.0)

        return round(max(1.0, min(10.0, rating)), 1)
    except:
        return 6.0

def calcola_trend_giocatore(storico_voti):
    if len(storico_voti) < 2:
        return "Stabile (↔️)"
    diff = round(storico_voti[-1] - (sum(storico_voti[:-1])/len(storico_voti[:-1])), 1)
    if diff > 0: return f"In Crescita 📈 (+{diff})"
    elif diff < 0: return f"In Decrescita 📉 ({diff})"
    return "Stabile (↔️)"

# =====================================================================
# GENERATORE PDF (OPZIONALE SE REPORTLAB È DISPONIBILE)
# =====================================================================
def genera_pdf_partita(match_name, match_data, db_giocatori, accent_hex):
    if not REPORTLAB_AVAILABLE:
        return None
    filename = f"Report_Partita_{match_name.replace(' ', '_')}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=15, textColor=colors.HexColor(accent_hex), alignment=1, spaceAfter=8)
    sub_style = ParagraphStyle('SubStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, textColor=colors.HexColor("#cccccc"), alignment=1, spaceAfter=15)

    if LOGO_PATH and os.path.exists(LOGO_PATH):
        elements.append(RLImage(LOGO_PATH, width=50, height=50))
    elements.append(Paragraph(f"<b>USO Nuvolento - Report Partita: {match_name}</b>", title_style))
    elements.append(Paragraph(f"<b>Avversario:</b> {match_data.get('avversario', '')} | <b>Risultato:</b> {match_data.get('risultato', 'N.D.')} | <b>{match_data.get('casa_trasferta', 'Casa')}</b>", sub_style))
    elements.append(Paragraph(f"<b>Modulo:</b> {match_data['modulo']} | <b>Data:</b> {match_data['data']}", sub_style))
    elements.append(Spacer(1, 10))

    t_data = [["N°", "Giocatore", "Ruolo", "Min.", "Statistiche Chiave", "Voto"]]
    for num, nome in match_data["formazione"].items():
        if not nome: continue
        p_dati = match_data.get("dati_prestazione", {}).get(nome, {})
        is_portiere = (str(num) in ["1", "12"])
        voto = calcola_voto(p_dati, is_portiere) if p_dati else "N.D."
        ruolo = p_dati.get("ruolo_campo") or db_giocatori.get(nome, {}).get("ruolo", "Portiere" if is_portiere else "Movimento")
        
        if is_portiere:
            stats = f"Parate: {p_dati.get('parate', 0)} | Uscite: {p_dati.get('uscite', '0/0')} | Gol Sub./Resp.: {p_dati.get('gol_subiti_resp', '0/0')}"
        else:
            eff_pass = normalizza_efficacia_passaggi(p_dati.get('efficacia_passaggi', p_dati.get('passaggi', 'Buona')))
            stats = f"Duelli: {p_dati.get('duelli', '0/0')} | Efficacia Pass.: {eff_pass} | Perse: {p_dati.get('perse', 0)} | Tiri: {p_dati.get('tiri', '0/0')} | Gol: {p_dati.get('gol_fatti', 0)}"

        t_data.append([str(num), nome, ruolo, f"{p_dati.get('minuti', 80)}'", stats, str(voto)])

    t = Table(t_data, colWidths=[30, 100, 90, 45, 230, 45])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(accent_hex)),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#333333")),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#141721")),
    ]))
    elements.append(t)
    doc.build(elements)
    return filename

# =====================================================================
# SIDEBAR, PERSISTENZA SELEZIONE PARTITA & NAVIGAZIONE
# =====================================================================
db_giocatori = st.session_state["database_giocatori"]
db_partite = st.session_state["database_partite"]

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

menu = st.sidebar.radio("Navigazione", [
    "📋 Setup Partite & Formazioni", 
    "⚡ Inserimento Parametri & Voti", 
    "🎥 Video Analisi", 
    "📈 Riepilogo Squadra", 
    "👤 Gestione Rosa", 
    "🎨 Editor Grafica"
])

# =====================================================================
# 1. SETUP PARTITE & FORMAZIONI
# =====================================================================
if menu == "📋 Setup Partite & Formazioni":
    st.title("📋 Setup Partite & Formazioni Titolari / Riserve")

    col_sel_p, col_new_p, col_del_p = st.columns([3, 0.4, 0.4])
    with col_sel_p:
        partita_selezionata = selettore_partita_persistente("Seleziona Partita", "sel_partita_setup")
    with col_
