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
# SIDEBAR & NAVIGAZIONE
# =====================================================================
db_giocatori = st.session_state["database_giocatori"]
db_partite = st.session_state["database_partite"]

if time.time() - st.session_state["last_auto_save"] > 30:
    st.session_state["last_auto_save"] = time.time()
    salva_dati_su_disco()

menu = st.sidebar.radio("Navigazione", [
    "📋 Setup Partite & Formazioni", 
    "⚡ Inserimento Parametri & Voti", 
    "🎥 Video Analisi", 
    "📈 Riepilogo Squadra", 
    "👤 Gestione Rosa", 
    "🎨 Editor Grafica"
])

partite_ordinate_chiavi = [
    item[0] for item in sorted(
        db_partite.items(),
        key=lambda x: parse_data_partita(x[1].get("data", "01/01/2026"))
    )
]

# =====================================================================
# 1. SETUP PARTITE & FORMAZIONI
# =====================================================================
if menu == "📋 Setup Partite & Formazioni":
    st.title("📋 Setup Partite & Formazioni Titolari / Riserve")

    col_sel_p, col_new_p, col_del_p = st.columns([3, 0.4, 0.4])
    with col_sel_p:
        partita_selezionata = st.selectbox("Seleziona Partita", partite_ordinate_chiavi if partite_ordinate_chiavi else ["Nessuna Partita"])
    with col_new_p:
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
                        salva_dati_su_disco()
                        st.success(f"Partita {nome_p} creata!")
                        st.rerun()
    with col_del_p:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        with st.expander("➖"):
            if db_partite and partita_selezionata in db_partite:
                st.warning(f"Eliminare '{partita_selezionata}'?")
                if st.button("🗑️ Conferma"):
                    del db_partite[partita_selezionata]
                    salva_dati_su_disco()
                    st.success("Partita eliminata!")
                    st.rerun()
            else:
                st.info("Nessuna partita.")

    if db_partite and partita_selezionata in db_partite:
        p_info = db_partite[partita_selezionata]
        
        if "risultato" not in p_info: p_info["risultato"] = "N.D."
        if "casa_trasferta" not in p_info: p_info["casa_trasferta"] = "Casa"
        if "youtube_link" not in p_info: p_info["youtube_link"] = ""
        if "dati_prestazione" not in p_info: p_info["dati_prestazione"] = {}

        st.divider()
        st.subheader(f"⚙️ Configurazione Partita & Formazione: {partita_selezionata}")

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
            formazione_corrente = p_info.get("formazione", {})

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
                salva_dati_su_disco()
                st.success("Dati partita e formazione salvati con successo!")
                st.rerun()

# =====================================================================
# 2. INSERIMENTO PARAMETRI & VOTI
# =====================================================================
elif menu == "⚡ Inserimento Parametri & Voti":
    st.title("⚡ Inserimento Parametri Post-Partita & Voti")

    if not db_partite:
        st.warning("⚠️ Crea prima una partita nella sezione 'Setup Partite & Formazioni'.")
        st.stop()

    partita_sel = st.selectbox("Seleziona Partita da Analizzare", partite_ordinate_chiavi, key="analizza_partita")
    p_dati = db_partite[partita_sel]

    if "dati_prestazione" not in p_dati:
        p_dati["dati_prestazione"] = {}

    st.subheader(f"Analisi Match: {partita_sel} (Risultato: {p_dati.get('risultato', 'N.D.')} | {p_dati.get('casa_trasferta', 'Casa')})")
    st.caption("Efficacia passaggi: Ottima (+0,7) · Buona (+0,4) · Sufficiente (+0,1) · Insufficiente (-0,3) · Pessima (-0,5), pesata sul ruolo. Gol = +1 per tutti.")

    with st.form("form_inserimento_parametri"):
        st.markdown("### 🔴 TITOLARI (Maglie 1 - 11)")
        for i in range(1, 12):
            nome_g = p_dati["formazione"].get(str(i), p_dati["formazione"].get(i, ""))
            if not nome_g: continue
            
            is_portiere = (i == 1)
            default_ruolo_g = ruolo_default_da_rosa(db_giocatori.get(nome_g, {}).get("ruolo", ""))
            current_vals = p_dati["dati_prestazione"].get(nome_g, {})

            if is_portiere:
                st.markdown(f"**N° {i} — {nome_g}** *(PORTIERE)*")
                c1, c2, c3, c4, c_voto = st.columns([1.5, 1.5, 1.5, 1.5, 1])
                with c1:
                    minuti = st.number_input("Minuti", 1, 80, int(current_vals.get("minuti", 80)), key=f"min_{partita_sel}_{i}")
                with c2:
                    parate = st.number_input("Parate", 0, 20, int(current_vals.get("parate", 0)), key=f"par_{partita_sel}_{i}")
                with c3:
                    uscite = st.text_input("Uscite tent./rius.", str(current_vals.get("uscite", "0/1")), key=f"usc_{partita_sel}_{i}")
                with c4:
                    gol_subiti_resp = st.text_input("Gol sub./resp.", str(current_vals.get("gol_subiti_resp", "0/0")), key=f"gol_sub_{partita_sel}_{i}")
                
                temp_dict = {"minuti": minuti, "parate": parate, "uscite": uscite, "gol_subiti_resp": gol_subiti_resp}
                voto_live = calcola_voto(temp_dict, is_portiere=True)
                
                with c_voto:
                    st.markdown(f"<div class='scoutai-voto-box'><span style='font-size: 11px; display: block; color: #a0aec0;'>VOTO LIVE</span><span style='font-size: 20px; font-weight: bold; color: {accent_hex};'>{voto_live}</span></div>", unsafe_allow_html=True)

                p_dati["dati_prestazione"][nome_g] = temp_dict
            else:
                c_gioc, c_ruolo = st.columns([2.2, 1.2])
                with c_gioc:
                    st.markdown(f"<div style='padding-top: 6px;'><strong>N° {i} — {nome_g}</strong></div>", unsafe_allow_html=True)
                with c_ruolo:
                    val_ruolo = current_vals.get("ruolo_campo", default_ruolo_g)
                    idx_ruolo = TUTTI_RUOLI_MOVIMENTO.index(val_ruolo) if val_ruolo in TUTTI_RUOLI_MOVIMENTO else TUTTI_RUOLI_MOVIMENTO.index("CC")
                    ruolo_campo = st.selectbox("Ruolo", TUTTI_RUOLI_MOVIMENTO, index=idx_ruolo, key=f"ruolo_{partita_sel}_{i}", label_visibility="collapsed")

                c1, c2, c3, c4, c5, c6, c_voto = st.columns([1, 1, 1.3, 0.8, 1, 0.8, 1])
                with c1:
                    minuti = st.number_input("Minuti", 1, 80, int(current_vals.get("minuti", 80)), key=f"min_{partita_sel}_{i}")
                with c2:
                    duelli = st.text_input("Duelli V/T", str(current_vals.get("duelli", "5/5")), key=f"due_{partita_sel}_{i}")
                with c3:
                    val_eff = normalizza_efficacia_passaggi(current_vals.get("efficacia_passaggi", current_vals.get("passaggi", "Buona")))
                    idx_eff = OPZIONI_EFFICACIA_PASSAGGI.index(val_eff) if val_eff in OPZIONI_EFFICACIA_PASSAGGI else 1
                    efficacia_passaggi = st.selectbox("Efficacia passaggi", OPZIONI_EFFICACIA_PASSAGGI, index=idx_eff, key=f"pas_{partita_sel}_{i}")
                with c4:
                    perse = st.number_input("Perse", 0, 10, int(current_vals.get("perse", 0)), key=f"per_{partita_sel}_{i}")
                with c5:
                    tiri = st.text_input("Tiri P/Sp", str(current_vals.get("tiri", "0/0")), key=f"tir_{partita_sel}_{i}")
                with c6:
                    gol_fatti = st.number_input("Gol", 0, 5, int(current_vals.get("gol_fatti", 0)), key=f"gol_{partita_sel}_{i}")
                
                temp_dict = {
                    "ruolo_campo": ruolo_campo,
                    "minuti": minuti, "duelli": duelli, "efficacia_passaggi": efficacia_passaggi,
                    "perse": perse, "tiri": tiri, "gol_fatti": gol_fatti, "salvataggi": 0
                }
                voto_live = calcola_voto(temp_dict, is_portiere=False)
                
                with c_voto:
                    st.markdown(f"<div class='scoutai-voto-box'><span style='font-size: 11px; display: block; color: #a0aec0;'>VOTO LIVE</span><span style='font-size: 20px; font-weight: bold; color: {accent_hex};'>{voto_live}</span></div>", unsafe_allow_html=True)

                p_dati["dati_prestazione"][nome_g] = temp_dict

            st.markdown("---")

        st.markdown(f"<br><hr style='border: 2px dashed {accent_hex};'><br>", unsafe_allow_html=True)

        st.markdown("### 🔵 RISERVE / PANCHINA (Maglie 12 - 20)")
        for i in range(12, 21):
            nome_g = p_dati["formazione"].get(str(i), p_dati["formazione"].get(i, ""))
            if not nome_g: continue
            
            is_portiere = (i == 12)
            default_ruolo_g = ruolo_default_da_rosa(db_giocatori.get(nome_g, {}).get("ruolo", ""))
            current_vals = p_dati["dati_prestazione"].get(nome_g, {})

            if is_portiere:
                st.markdown(f"**N° {i} — {nome_g} (Riserva)** *(PORTIERE)*")
                c1, c2, c3, c4, c_voto = st.columns([1.5, 1.5, 1.5, 1.5, 1])
                with c1:
                    minuti = st.number_input("Min sub", 0, 80, int(current_vals.get("minuti", 0)), key=f"min_res_{partita_sel}_{i}")
                with c2:
                    parate = st.number_input("Parate", 0, 20, int(current_vals.get("parate", 0)), key=f"par_res_{partita_sel}_{i}")
                with c3:
                    uscite = st.text_input("Uscite tent./rius.", str(current_vals.get("uscite", "0/0")), key=f"usc_res_{partita_sel}_{i}")
                with c4:
                    gol_subiti_resp = st.text_input("Gol sub./resp.", str(current_vals.get("gol_subiti_resp", "0/0")), key=f"gol_sub_res_{partita_sel}_{i}")
                
                temp_dict_res = {"minuti": minuti, "parate": parate, "uscite": uscite, "gol_subiti_resp": gol_subiti_resp}
                voto_live_res = calcola_voto(temp_dict_res, is_portiere=True)
                
                with c_voto:
                    st.markdown(f"<div class='scoutai-voto-box'><span style='font-size: 11px; display: block; color: #a0aec0;'>VOTO LIVE</span><span style='font-size: 20px; font-weight: bold; color: {accent_hex};'>{voto_live_res}</span></div>", unsafe_allow_html=True)

                p_dati["dati_prestazione"][nome_g] = temp_dict_res
            else:
                c_gioc, c_ruolo = st.columns([2.2, 1.2])
                with c_gioc:
                    st.markdown(f"<div style='padding-top: 6px;'><strong>N° {i} — {nome_g} (Riserva)</strong></div>", unsafe_allow_html=True)
                with c_ruolo:
                    val_ruolo = current_vals.get("ruolo_campo", default_ruolo_g)
                    idx_ruolo = TUTTI_RUOLI_MOVIMENTO.index(val_ruolo) if val_ruolo in TUTTI_RUOLI_MOVIMENTO else TUTTI_RUOLI_MOVIMENTO.index("CC")
                    ruolo_campo = st.selectbox("Ruolo", TUTTI_RUOLI_MOVIMENTO, index=idx_ruolo, key=f"ruolo_res_{partita_sel}_{i}", label_visibility="collapsed")

                c1, c2, c3, c4, c5, c6, c_voto = st.columns([1, 1, 1.3, 0.8, 1, 0.8, 1])
                with c1:
                    minuti = st.number_input("Min sub", 0, 80, int(current_vals.get("minuti", 0)), key=f"min_res_{partita_sel}_{i}")
                with c2:
                    duelli = st.text_input("Duelli V/T", str(current_vals.get("duelli", "0/0")), key=f"due_res_{partita_sel}_{i}")
                with c3:
                    val_eff_res = normalizza_efficacia_passaggi(current_vals.get("efficacia_passaggi", current_vals.get("passaggi", "Buona")))
                    idx_eff_res = OPZIONI_EFFICACIA_PASSAGGI.index(val_eff_res) if val_eff_res in OPZIONI_EFFICACIA_PASSAGGI else 1
                    efficacia_passaggi = st.selectbox("Efficacia passaggi", OPZIONI_EFFICACIA_PASSAGGI, index=idx_eff_res, key=f"pas_res_{partita_sel}_{i}")
                with c4:
                    perse = st.number_input("Perse", 0, 10, int(current_vals.get("perse", 0)), key=f"per_res_{partita_sel}_{i}")
                with c5:
                    tiri = st.text_input("Tiri P/Sp", str(current_vals.get("tiri", "0/0")), key=f"tir_res_{partita_sel}_{i}")
                with c6:
                    gol_fatti = st.number_input("Gol", 0, 5, int(current_vals.get("gol_fatti", 0)), key=f"gol_res_{partita_sel}_{i}")
                
                temp_dict_res = {
                    "ruolo_campo": ruolo_campo,
                    "minuti": minuti, "duelli": duelli, "efficacia_passaggi": efficacia_passaggi,
                    "perse": perse, "tiri": tiri, "gol_fatti": gol_fatti, "salvataggi": 0
                }
                voto_live_res = calcola_voto(temp_dict_res, is_portiere=False)
                
                with c_voto:
                    st.markdown(f"<div class='scoutai-voto-box'><span style='font-size: 11px; display: block; color: #a0aec0;'>VOTO LIVE</span><span style='font-size: 20px; font-weight: bold; color: {accent_hex};'>{voto_live_res}</span></div>", unsafe_allow_html=True)

                p_dati["dati_prestazione"][nome_g] = temp_dict_res

            st.markdown("---")

        if st.form_submit_button("💾 Salva Parametri e Calcola Voti"):
            salva_dati_su_disco()
            st.success("Parametri salvati automaticamente su disco e voti aggiornati per questa partita!")
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
            if not nome: continue
            is_portiere = (str(n) in ["1", "12"])
            p_dati_g = p_dati["dati_prestazione"].get(nome, {})
            voto = calcola_voto(p_dati_g, is_portiere)
            righe_csv.append({"Numero": n, "Giocatore": nome, **p_dati_g, "Voto": voto})
        
        df_match = pd.DataFrame(righe_csv)
        if not df_match.empty:
            csv_data = df_match.to_csv(index=False).encode('utf-8')
            st.download_button("📊 Esporta CSV Match", csv_data, file_name=f"Match_{partita_sel}.csv", mime="text/csv")

# =====================================================================
# 3. VIDEO ANALISI
# =====================================================================
elif menu == "🎥 Video Analisi":
    st.title("🎥 Video Analisi & Streaming Partita")

    if not db_partite:
        st.warning("⚠️ Crea prima una partita nella sezione 'Setup Partite & Formazioni'.")
        st.stop()

    partita_sel = st.selectbox("Seleziona Partita per la Video Analisi", partite_ordinate_chiavi, key="video_partita")
    p_info = db_partite[partita_sel]

    if "youtube_link" not in p_info:
        p_info["youtube_link"] = ""

    st.divider()

    col_info1, col_info2, col_info3, col_info4 = st.columns(4)
    col_info1.metric("Data Partita", p_info.get("data", "N.D."))
    col_info2.metric("Risultato", p_info.get("risultato", "N.D."))
    col_info3.metric("Luogo", p_info.get("casa_trasferta", "Casa"))
    col_info4.metric("Modulo", p_info.get("modulo", "N.D."))

    st.divider()

    col_input_l, col_video_r = st.columns([1.2, 1.8])

    with col_input_l:
        st.subheader("🔗 Configurazione Link")
        link_inserito = st.text_input("Inserisci Link YouTube", value=p_info.get("youtube_link", ""), placeholder="https://www.youtube.com/watch?v=...")
        
        if st.button("▶️ Play Video", use_container_width=True):
            p_info["youtube_link"] = link_inserito
            salva_dati_su_disco()
            st.success("Link aggiornato con successo!")
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        st.info("💡 **Istruzioni:** Incolla il link del video di YouTube e clicca su **Play Video** per caricarlo nel player a destra.")

    with col_video_r:
        st.subheader("📺 Main Frame Video")
        link_corrente = p_info.get("youtube_link", "")
        yt_id = estrai_youtube_id(link_corrente)

        if yt_id:
            embed_url = f"https://www.youtube.com/embed/{yt_id}"
            st.markdown(f"""
                <div style="position: relative; width: 100%; height: 0; padding-bottom: 56.25%;">
                    <iframe src="{embed_url}" 
                            style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: {radius_px}px; border: 1px solid {glow_border_rgba}; box-shadow: {box_shadow_glow};" 
                            allowfullscreen>
                    </iframe>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class="scoutai-video-empty">
                    <span style="font-size: 40px; margin-bottom: 10px;">📺</span>
                    <p style="color: #a0aec0; margin: 0; font-size: 16px;">Nessun video caricato o link YouTube non valido.</p>
                    <p style="color: #718096; margin-top: 5px; font-size: 13px;">Inserisci un link valido nel pannello a sinistra e premi Play.</p>
                </div>
            """, unsafe_allow_html=True)

# =====================================================================
# 4. RIEPILOGO SQUADRA & GIOCATORI
# =====================================================================
elif menu == "📈 Riepilogo Squadra":
    st.title("📈 Riepilogo Squadra & Statistiche Stagionali")

    st.subheader("🏆 Elenco Partite & Voti Medi Squadra (Dal più vecchio al più recente)")
    
    partite_ordinate = sorted(
        db_partite.items(),
        key=lambda item: parse_data_partita(item[1].get("data", "01/01/2026"))
    )

    partite_riepilogo = []
    for p_nome, p_val in partite_ordinate:
        voti_match = []
        for n, nome in p_val.get("formazione", {}).items():
            if not nome: continue
            is_portiere = (str(n) in ["1", "12"])
            d_p = p_val.get("dati_prestazione", {}).get(nome, {})
            if d_p:
                voti_match.append(calcola_voto(d_p, is_portiere))
        
        voto_medio = round(sum(voti_match)/len(voti_match), 1) if voti_match else 6.0
        partite_riepilogo.append({
            "Partita": p_nome, 
            "Data": p_val["data"], 
            "Risultato": p_val.get("risultato", "N.D."), 
            "Casa/Trasferta": p_val.get("casa_trasferta", "Casa"),
            "Modulo": p_val["modulo"], 
            "Voto Medio Squadra": f"{voto_medio} / 10"
        })
    
    if partite_riepilogo:
        st.table(pd.DataFrame(partite_riepilogo))

    st.divider()
    st.subheader("📊 Riepilogo Stagionale Giocatore")
    giocatore_sel = st.selectbox("Seleziona Giocatore", list(db_giocatori.keys()) if db_giocatori else ["Nessun Giocatore"])
    
    storico_voti = []
    tot_minuti = 0
    presenze_titolare = 0
    presenze_subentro = 0

    tot_duelli_v = 0
    tot_duelli_t = 0
    lista_efficacia_passaggi = []
    tot_perse = 0
    tot_tiri_p = 0
    tot_tiri_sp = 0
    tot_gol = 0

    tot_parate = 0
    tot_uscite_v = 0
    tot_uscite_t = 0
    tot_gol_sub = 0
    tot_gol_resp = 0
    ha_dati_portiere = False
    ha_dati_movimento = False

    for p_nome, p_val in partite_ordinate:
        formazione = p_val.get("formazione", {})
        for n, nome in formazione.items():
            if nome == giocatore_sel:
                d_p = p_val.get("dati_prestazione", {}).get(giocatore_sel, {})
                if d_p:
                    min_giocati = int(d_p.get("minuti", 0))
                    num_maglia = int(n) if str(n).isdigit() else 0
                    is_portiere = (str(n) in ["1", "12"])

                    if min_giocati > 0:
                        storico_voti.append(calcola_voto(d_p, is_portiere))
                        tot_minuti += min_giocati

                        if 1 <= num_maglia <= 11:
                            presenze_titolare += 1
                        elif 12 <= num_maglia <= 20:
                            presenze_subentro += 1

                    if "parate" in d_p or "uscite" in d_p or "gol_subiti_resp" in d_p:
                        ha_dati_portiere = True
                        tot_parate += int(d_p.get("parate", 0))
                        u_v, u_t = parse_frazione(d_p.get("uscite", "0/0"))
                        tot_uscite_v += u_v
                        tot_uscite_t += u_t
                        g_s, g_r = parse_frazione(d_p.get("gol_subiti_resp", "0/0"))
                        tot_gol_sub += g_s
                        tot_gol_resp += g_r
                    else:
                        ha_dati_movimento = True
                        d_v, d_t = parse_frazione(d_p.get("duelli", "0/0"))
                        tot_duelli_v += d_v
                        tot_duelli_t += d_t
                        lista_efficacia_passaggi.append(
                            normalizza_efficacia_passaggi(d_p.get("efficacia_passaggi", d_p.get("passaggi", "Buona")))
                        )
                        tot_perse += int(d_p.get("perse", 0))
                        t_p, t_sp = parse_frazione(d_p.get("tiri", "0/0"))
                        tot_tiri_p += t_p
                        tot_tiri_sp += t_sp
                        tot_gol += int(d_p.get("gol_fatti", 0))

    tot_presenze = presenze_titolare + presenze_subentro
    media_stagione = round(sum(storico_voti)/len(storico_voti), 1) if storico_voti else 6.0
    trend = calcola_trend_giocatore(storico_voti)

    c1, c2, c3 = st.columns(3)
    c1.metric("Partite Votate", len(storico_voti))
    c2.metric("Media Voto Stagionale", f"{media_stagione} / 10")
    c3.metric("Trend di Rendimento", trend)

    st.markdown("<br>", unsafe_allow_html=True)

    # 1. Conteggio totale parametri inseriti (PRIMA di presenze e minutaggio)
    st.markdown(f"""
    <div class="scoutai-box" style="margin-bottom: 18px;">
        <h4 style="margin-top: 0; color: {accent_hex}; border-bottom: 1px solid {tema['border_color']}; padding-bottom: 10px;">🧮 Conteggio Totale Parametri Inseriti: {giocatore_sel}</h4>
    """, unsafe_allow_html=True)

    if ha_dati_movimento:
        valore_pass_metric = calcola_efficacia_passaggi_media(lista_efficacia_passaggi)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Duelli (V/T)", f"{tot_duelli_v}/{tot_duelli_t}")
        m2.metric("Efficacia Passaggi", valore_pass_metric)
        m3.metric("Palle Perse", tot_perse)
        m4.metric("Tiri (P/Sp)", f"{tot_tiri_p}/{tot_tiri_sp}")
        m5.metric("Gol Segnati", tot_gol)

    if ha_dati_portiere:
        p1, p2, p3 = st.columns(3)
        p1.metric("Parate Totali", tot_parate)
        p2.metric("Uscite (Rius./Tent.)", f"{tot_uscite_v}/{tot_uscite_t}")
        p3.metric("Gol Subiti / Respinti", f"{tot_gol_sub}/{tot_gol_resp}")

    if not ha_dati_movimento and not ha_dati_portiere:
        st.info("Nessun parametro registrato per questo giocatore.")

    st.markdown("</div>", unsafe_allow_html=True)

    # 2. Dettaglio Presenze & Minutaggio (DOPO il conteggio parametri)
    st.markdown(f"""
    <div class="scoutai-box">
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

# =====================================================================
# 5. GESTIONE ROSA
# =====================================================================
elif menu == "👤 Gestione Rosa":
    st.title("👤 Gestione Rosa Squadra")

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
                            nuova_rosa[nome] = {"ruolo": ruolo, "partite": {}}
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
                db_giocatori[n_nome] = {"ruolo": n_ruolo, "partite": {}}
                salva_dati_su_disco()
                st.success(f"Giocatore {n_nome} aggiunto e salvato con successo!")
                st.rerun()

    st.divider()
    st.subheader("Rosa Attuale")
    if not db_giocatori:
        st.info("La rosa è attualmente vuota.")
    else:
        for nome, dati in list(db_giocatori.items()):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"<div class='scoutai-box' style='padding: 12px 16px; margin-bottom: 8px;'>📌 <strong>{nome}</strong> — <em>Ruolo:</em> {dati['ruolo']}</div>", unsafe_allow_html=True)
            with c2:
                if st.button("🗑️ Elimina", key=f"del_g_{nome}"):
                    del db_giocatori[nome]
                    salva_dati_su_disco()
                    st.success(f"Rimosso {nome} e salvato.")
                    st.rerun()

# =====================================================================
# 6. EDITOR GRAFICA & SETTINGS
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

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 Salva Impostazioni Grafiche", use_container_width=True, key="btn_salva_grafica"):
        st.session_state["ui_theme"]["font_size"] = int(nuovo_font_size)
        st.session_state["ui_theme"]["shadow_intensity"] = int(nuova_ombra)
        st.session_state["ui_theme"]["glow_intensity"] = int(nuova_glow_intensita)
        st.session_state["ui_theme"]["glow_width"] = int(nuova_glow_larghezza)
        st.session_state["fullscreen_mode"] = bool(attiva_fs)
        salva_dati_su_disco()
        st.session_state["ui_notice"] = (
            f"Modifiche salvate e applicate! Font: {nuovo_font_size}px · "
            f"Glow: {nuova_glow_intensita}% / {nuova_glow_larghezza}px."
        )
        st.rerun()
