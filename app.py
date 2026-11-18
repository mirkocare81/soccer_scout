import streamlit as st
import pandas as pd
import io
import time
import os
import json

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
# GESTIONE LOGO & FILE PERSISTENTI (JSON)
# =====================================================================
LOGO_PATH = "Channel logo.jpg" if os.path.exists("Channel logo.jpg") else ("logo.png" if os.path.exists("logo.png") else None)
DB_FILE = "scoutai_database.json"

def salva_dati_su_disco():
    """Salvataggio automatico istantaneo su file JSON"""
    try:
        data_to_save = {
            "giocatori": st.session_state.get("database_giocatori", {}),
            "partite": st.session_state.get("database_partite", {})
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

# =====================================================================
# INIZIALIZZAZIONE STATO TEMA & DATABASE
# =====================================================================
PRESET_TEMI = {
    "Emerald Dark (Default)": {
        "bg_main": "#090a0f", "bg_card": "#141721", "bg_sidebar": "#12141c",
        "accent": "#10b981", "text_color": "#f3f4f6", "border_color": "#1e2230",
        "border_radius": 12, "font_size": 16, "shadow_intensity": 25, "custom_css": ""
    },
    "Tactical Blue": {
        "bg_main": "#070d19", "bg_card": "#0f172a", "bg_sidebar": "#0b1120",
        "accent": "#3b82f6", "text_color": "#f8fafc", "border_color": "#1e293b",
        "border_radius": 10, "font_size": 16, "shadow_intensity": 30, "custom_css": ""
    },
    "Matchday Crimson": {
        "bg_main": "#12090b", "bg_card": "#1f1014", "bg_sidebar": "#180c0f",
        "accent": "#ef4444", "text_color": "#fef2f2", "border_color": "#381a21",
        "border_radius": 8, "font_size": 16, "shadow_intensity": 20, "custom_css": ""
    }
}

if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = PRESET_TEMI["Emerald Dark (Default)"].copy()
if "fullscreen_mode" not in st.session_state:
    st.session_state["fullscreen_mode"] = False
if "last_auto_save" not in st.session_state:
    st.session_state["last_auto_save"] = time.time()

dati_salvati = carica_dati_da_disco()
if dati_salvati:
    if "database_giocatori" not in st.session_state:
        st.session_state["database_giocatori"] = dati_salvati.get("giocatori", {})
    if "database_partite" not in st.session_state:
        st.session_state["database_partite"] = dati_salvati.get("partite", {})
else:
    if "database_giocatori" not in st.session_state:
        st.session_state["database_giocatori"] = {
            "Mattia": {"ruolo": "Difensore Centrale (DC)", "partite": {}},
            "Filippo": {"ruolo": "Centrocampista (CC)", "partite": {}},
            "Davide": {"ruolo": "Attaccante (ATT)", "partite": {}},
            "Lorenzo": {"ruolo": "Portiere (POR)", "partite": {}},
            "Simone": {"ruolo": "Terzino (TS/TD)", "partite": {}},
            "Federico": {"ruolo": "Centrocampista (CC)", "partite": {}},
            "Alessandro": {"ruolo": "Attaccante (ATT)", "partite": {}},
            "Luca": {"ruolo": "Difensore Centrale (DC)", "partite": {}},
            "Marco": {"ruolo": "Esterno (EST)", "partite": {}},
            "Giovanni": {"ruolo": "Centrocampista (CC)", "partite": {}},
            "Tommaso": {"ruolo": "Attaccante (ATT)", "partite": {}},
            "Riccardo": {"ruolo": "Riserva / Jolly", "partite": {}},
            "Pietro": {"ruolo": "Riserva / Jolly", "partite": {}},
            "Edoardo": {"ruolo": "Riserva / Jolly", "partite": {}}
        }
    if "database_partite" not in st.session_state:
        st.session_state["database_partite"] = {
            "Virtus (15/03/2026)": {
                "avversario": "Virtus", "data": "15/03/2026", "modulo": "4-4-2",
                "risultato": "N.D.", "casa_trasferta": "Casa",
                "formazione": {str(i): (list(st.session_state["database_giocatori"].keys())[i-1] if i <= len(st.session_state["database_giocatori"]) else "") for i in range(1, 21)},
                "dati_prestazione": {}
            }
        }
    salva_dati_su_disco()

tema = st.session_state["ui_theme"]
is_fullscreen = st.session_state["fullscreen_mode"]

# =====================================================================
# APPLICAZIONE CSS & UI
# =====================================================================
ombra_alfa = tema["shadow_intensity"] / 100.0
fullscreen_css = "[data-testid=\"stSidebar\"] {display: none !important;} header {visibility: hidden !important;}" if is_fullscreen else ""

st.markdown(f"""
<style>
    .stApp {{ background-color: {tema['bg_main']}; color: {tema['text_color']}; font-size: {tema['font_size']}px; }}
    .block-container {{ max-width: 100% !important; padding: 2rem 3rem !important; }}
    h1, h2, h3, h4, h5, h6, p, label, .stMarkdown, span {{ color: {tema['text_color']} !important; }}
    [data-testid="stSidebar"] {{ background-color: {tema['bg_sidebar']}; border-right: 1px solid {tema['border_color']}; }}
    
    [data-testid="stMetric"], div[data-baseweb="notification"], .stAlert {{
        background-color: {tema['bg_card']} !important; border: 1px solid {tema['border_color']} !important;
        color: {tema['text_color']} !important; padding: 18px; border-radius: {tema['border_radius']}px; box-shadow: 0 6px 14px rgba(0,0,0,{ombra_alfa});
    }}
    [data-testid="stMetricValue"] {{ color: {tema['accent']} !important; }}

    .stButton > button, .stDownloadButton > button {{
        background-color: #1a1d29 !important; color: #ffffff !important;
        border-radius: {tema['border_radius']}px !important; border: 1px solid {tema['border_color']} !important; font-weight: 600 !important;
        padding: 0.6rem 1.2rem !important; width: 100% !important; transition: background-color 0.2s ease, border-color 0.2s ease;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover {{
        background-color: #ef4444 !important; border-color: #ef4444 !important; color: #ffffff !important;
    }}

    [data-testid="stExpander"] {{
        background-color: {tema['bg_card']} !important;
        border: 1px solid {tema['border_color']} !important;
        border-radius: {tema['border_radius']}px !important;
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

    input, textarea, select, div[data-baseweb="input"] div, div[data-baseweb="select"] div {{
        background-color: {tema['bg_card']} !important; color: {tema['text_color']} !important;
        border-color: {tema['border_color']} !important; border-radius: {max(4, tema['border_radius']-4)}px !important;
    }}
    table {{ background-color: {tema['bg_card']}; border-radius: {tema['border_radius']}px; overflow: hidden; border: 1px solid {tema['border_color']}; width: 100% !important; }}
    th {{ background-color: {tema['accent']} !important; color: #ffffff !important; text-align: center !important; }}
    td {{ color: {tema['text_color']} !important; border-color: {tema['border_color']} !important; }}
    {fullscreen_css}
</style>
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
# MOTORE DI CALCOLO VOTO & TREND
# =====================================================================
def calcola_voto(p):
    try:
        duelli_v, duelli_t = map(int, p.get('duelli', '0/0').split("/"))
        salvataggi = int(p.get('salvataggi', 0))
        pct_passaggi = float(p.get('passaggi', 75)) / 100.0
        perse = int(p.get('perse', 0))
        minuti_giocati = int(p.get('minuti', 80))
        tiri_porta, tiri_specchio = map(int, p.get('tiri', '0/0').split("/"))
    except:
        return 6.0

    fattore_tempo = minuti_giocati / 80.0 if minuti_giocati > 0 else 1.0
    rating = 6.0
    pct_duelli = (duelli_v / duelli_t) if duelli_t > 0 else 0

    if pct_duelli >= 0.75 and duelli_t >= 3:
        rating += 0.4 * min(1.0, fattore_tempo + 0.2)
    elif pct_duelli < 0.40:
        rating -= 0.4 * fattore_tempo

    if salvataggi > 0:
        rating += (salvataggi * 0.5) * fattore_tempo

    if pct_passaggi >= 0.85:
        rating += 0.3
    elif pct_passaggi < 0.50:
        rating -= 0.3 * fattore_tempo

    if perse > 0:
        rating -= (perse * 0.6) * fattore_tempo

    if tiri_specchio > 0:
        efficacia = tiri_porta / tiri_specchio
        if efficacia >= 0.66:
            rating += 0.4 * fattore_tempo

    return round(max(1.0, min(10.0, rating)), 1)

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

    t_data = [["N°", "Giocatore", "Ruolo", "Min.", "Duelli", "Pass.", "Tiri", "Voto"]]
    for num, nome in match_data["formazione"].items():
        if not nome: continue
        p_dati = db_giocatori.get(nome, {}).get("partite", {}).get(match_name, {})
        voto = calcola_voto(p_dati) if p_dati else "N.D."
        ruolo = db_giocatori.get(nome, {}).get("ruolo", "Titolare" if int(num) <= 11 else "Riserva")
        t_data.append([str(num), nome, ruolo, f"{p_dati.get('minuti', 80)}'", p_dati.get('duelli', '0/0'), f"{p_dati.get('passaggi', 75)}%", p_dati.get('tiri', '0/0'), str(voto)])

    t = Table(t_data, colWidths=[30, 110, 100, 45, 60, 50, 50, 45])
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

menu = st.sidebar.radio("Navigazione", ["📋 Setup Partite & Formazioni", "⚡ Inserimento Parametri & Voti", "📈 Riepilogo Squadra", "👤 Gestione Rosa", "🎨 Editor Grafica"])

# =====================================================================
# 1. SETUP PARTITE & FORMAZIONI
# =====================================================================
if menu == "📋 Setup Partite & Formazioni":
    st.title("📋 Setup Partite & Formazioni Titolari / Riserve")

    col_sel_p, col_new_p, col_del_p = st.columns([3, 0.4, 0.4])
    with col_sel_p:
        partita_selezionata = st.selectbox("Seleziona Partita", list(db_partite.keys()) if db_partite else ["Nessuna Partita"])
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
                            "risultato": n_ris, "casa_trasferta": n_ct,
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

            st.info("ℹ️ I numeri **1-11** rappresentano i titolari. I numeri **12-20** sono le riserve in panchina.")

            nodi_rosa = [""] + list(db_giocatori.keys())

            st.markdown("### 🔴 Titolari (Maglie 1 - 11)")
            cols_tit = st.columns(4)
            for i in range(1, 12):
                with cols_tit[(i-1) % 4]:
                    curr_val = p_info["formazione"].get(str(i), p_info["formazione"].get(i, ""))
                    idx_val = nodi_rosa.index(curr_val) if curr_val in nodi_rosa else 0
                    p_info["formazione"][str(i)] = st.selectbox(f"N° {i} (Titolare)", nodi_rosa, index=idx_val, key=f"tit_{i}_{partita_selezionata}")

            st.markdown("### 🔵 Riserve / Panchina (Maglie 12 - 20)")
            cols_res = st.columns(3)
            for i in range(12, 21):
                with cols_res[(i-12) % 3]:
                    curr_val = p_info["formazione"].get(str(i), p_info["formazione"].get(i, ""))
                    idx_val = nodi_rosa.index(curr_val) if curr_val in nodi_rosa else 0
                    p_info["formazione"][str(i)] = st.selectbox(f"N° {i} (Riserva)", nodi_rosa, index=idx_val, key=f"res_{i}_{partita_selezionata}")

            if st.form_submit_button("Conferma e Salva Dati Partita"):
                p_info["avversario"] = nuovo_avv
                p_info["risultato"] = nuovo_risultato
                p_info["casa_trasferta"] = nuovo_ct
                p_info["modulo"] = nuovo_modulo
                salva_dati_su_disco()
                st.success("Dati partita e formazione salvati con successo!")
                st.rerun()

# =====================================================================
# 2. INSERIMENTO PARAMETRI & VOTI (CON BOX VOTO IN TEMPO REALE A DESTRA)
# =====================================================================
elif menu == "⚡ Inserimento Parametri & Voti":
    st.title("⚡ Inserimento Parametri Post-Partita & Voti")

    if not db_partite:
        st.warning("⚠️ Crea prima una partita nella sezione 'Setup Partite & Formazioni'.")
        st.stop()

    partita_sel = st.selectbox("Seleziona Partita da Analizzare", list(db_partite.keys()), key="analizza_partita")
    p_dati = db_partite[partita_sel]

    st.subheader(f"Analisi Match: {partita_sel} (Risultato: {p_dati.get('risultato', 'N.D.')} | {p_dati.get('casa_trasferta', 'Casa')})")

    if partita_sel not in p_dati["dati_prestazione"]:
        p_dati["dati_prestazione"] = {}

    with st.form("form_inserimento_parametri"):
        passaggi_opt = [100, 75, 50, 25, 10]
        
        st.markdown("### 🔴 TITOLARI (Maglie 1 - 11)")
        for i in range(1, 12):
            nome_g = p_dati["formazione"].get(str(i), p_dati["formazione"].get(i, ""))
            if not nome_g: continue
            
            st.markdown(f"**N° {i} — {nome_g}**")
            current_vals = p_dati["dati_prestazione"].get(nome_g, {
                "minuti": 80, "duelli": "5/5", "passaggi": 75, "perse": 0, "tiri": "0/0", "salvataggi": 0
            })
            
            # Layout: 5 colonne per i parametri + 1 colonna a destra per il Voto in tempo reale
            c1, c2, c3, c4, c5, c_voto = st.columns([1.2, 1.2, 1.2, 1, 1.2, 1])
            with c1:
                minuti = st.number_input(f"Minuti ({nome_g})", 1, 80, int(current_vals.get("minuti", 80)), key=f"min_{i}")
            with c2:
                duelli = st.text_input(f"Duelli V/T ({nome_g})", str(current_vals.get("duelli", "5/5")), key=f"due_{i}")
            with c3:
                val_pass = int(current_vals.get("passaggi", 75))
                idx_pass = passaggi_opt.index(val_pass) if val_pass in passaggi_opt else 1
                passaggi = st.selectbox(f"Passaggi % ({nome_g})", passaggi_opt, index=idx_pass, key=f"pas_{i}")
            with c4:
                perse = st.number_input(f"Perse ({nome_g})", 0, 10, int(current_vals.get("perse", 0)), key=f"per_{i}")
            with c5:
                tiri = st.text_input(f"Tiri P/Sp ({nome_g})", str(current_vals.get("tiri", "0/0")), key=f"tir_{i}")
            
            # Calcolo istantaneo del voto con i valori correnti del form
            temp_dict = {"minuti": minuti, "duelli": duelli, "passaggi": passaggi, "perse": perse, "tiri": tiri, "salvataggi": 0}
            voto_live = calcola_voto(temp_dict)
            
            with c_voto:
                st.markdown(f"<div style='background-color: #1e2230; border: 1px solid {tema['accent']}; padding: 8px; border-radius: 8px; text-align: center; margin-top: 24px;'><span style='font-size: 11px; display: block; color: #a0aec0;'>VOTO LIVE</span><span style='font-size: 20px; font-weight: bold; color: {tema['accent']};'>{voto_live}</span></div>", unsafe_allow_html=True)

            p_dati["dati_prestazione"][nome_g] = temp_dict
            st.markdown("---")

        st.markdown("<br><hr style='border: 2px dashed #10b981;'><br>", unsafe_allow_html=True)

        st.markdown("### 🔵 RISERVE / PANCHINA (Maglie 12 - 20)")
        for i in range(12, 21):
            nome_g = p_dati["formazione"].get(str(i), p_dati["formazione"].get(i, ""))
            if not nome_g: continue
            
            st.markdown(f"**N° {i} — {nome_g} (Riserva)**")
            current_vals = p_dati["dati_prestazione"].get(nome_g, {
                "minuti": 0, "duelli": "0/0", "passaggi": 75, "perse": 0, "tiri": "0/0", "salvataggi": 0
            })
            
            c1, c2, c3, c4, c5, c_voto = st.columns([1.2, 1.2, 1.2, 1, 1.2, 1])
            with c1:
                minuti = st.number_input(f"Min sub ({nome_g})", 0, 80, int(current_vals.get("minuti", 0)), key=f"min_res_{i}")
            with c2:
                duelli = st.text_input(f"Duelli V/T ({nome_g})", str(current_vals.get("duelli", "0/0")), key=f"due_res_{i}")
            with c3:
                val_pass_res = int(current_vals.get("passaggi", 75))
                idx_pass_res = passaggi_opt.index(val_pass_res) if val_pass_res in passaggi_opt else 1
                passaggi = st.selectbox(f"Passaggi % ({nome_g})", passaggi_opt, index=idx_pass_res, key=f"pas_res_{i}")
            with c4:
                perse = st.number_input(f"Perse ({nome_g})", 0, 10, int(current_vals.get("perse", 0)), key=f"per_res_{i}")
            with c5:
                tiri = st.text_input(f"Tiri P/Sp ({nome_g})", str(current_vals.get("tiri", "0/0")), key=f"tir_res_{i}")
            
            # Calcolo istantaneo del voto per la riserva
            temp_dict_res = {"minuti": minuti, "duelli": duelli, "passaggi": passaggi, "perse": perse, "tiri": tiri, "salvataggi": 0}
            voto_live_res = calcola_voto(temp_dict_res)
            
            with c_voto:
                st.markdown(f"<div style='background-color: #1e2230; border: 1px solid {tema['accent']}; padding: 8px; border-radius: 8px; text-align: center; margin-top: 24px;'><span style='font-size: 11px; display: block; color: #a0aec0;'>VOTO LIVE</span><span style='font-size: 20px; font-weight: bold; color: {tema['accent']};'>{voto_live_res}</span></div>", unsafe_allow_html=True)

            p_dati["dati_prestazione"][nome_g] = temp_dict_res
            st.markdown("---")

        if st.form_submit_button("💾 Salva Parametri e Calcola Voti"):
            salva_dati_su_disco()
            st.success("Parametri salvati automaticamente su disco e voti aggiornati!")
            st.rerun()

    st.divider()
    st.subheader("📄 Esportazione Report")
    col_pdf, col_csv = st.columns(2)
    with col_pdf:
        if REPORTLAB_AVAILABLE:
            if st.button("📄 Genera Report PDF Partita"):
                pdf_path = genera_pdf_partita(partita_sel, p_dati, db_giocatori, tema["accent"])
                if pdf_path and os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        st.download_button("Scarica PDF Ufficiale", f, file_name=pdf_path, mime="application/pdf")
        else:
            st.info("ℹ️ Modulo PDF disabilitato (ReportLab non installato nell'ambiente). Puoi usare l'export CSV.")
    with col_csv:
        df_match = pd.DataFrame([
            {"Giocatore": n, **p_dati["dati_prestazione"][n], "Voto": calcola_voto(p_dati["dati_prestazione"][n])}
            for n in p_dati["dati_prestazione"]
        ])
        if not df_match.empty:
            csv_data = df_match.to_csv(index=False).encode('utf-8')
            st.download_button("📊 Esporta CSV Match", csv_data, file_name=f"Match_{partita_sel}.csv", mime="text/csv")

# =====================================================================
# 3. RIEPILOGO SQUADRA & GIOCATORI
# =====================================================================
elif menu == "📈 Riepilogo Squadra":
    st.title("📈 Riepilogo Squadra & Statistiche Stagionali")

    st.subheader("🏆 Elenco Partite & Voti Medi Squadra")
    partite_riepilogo = []
    for p_nome, p_val in db_partite.items():
        voti_match = [calcola_voto(d) for d in p_val.get("dati_prestazione", {}).values()]
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
    for p_nome, p_val in db_partite.items():
        if giocatore_sel in p_val.get("dati_prestazione", {}):
            storico_voti.append(calcola_voto(p_val["dati_prestazione"][giocatore_sel]))

    media_stagione = round(sum(storico_voti)/len(storico_voti), 1) if storico_voti else 6.0
    trend = calcola_trend_giocatore(storico_voti)

    c1, c2, c3 = st.columns(3)
    c1.metric("Partite Giocate", len(storico_voti))
    c2.metric("Media Voto Stagionale", f"{media_stagione} / 10")
    c3.metric("Trend di Rendimento", trend)

# =====================================================================
# 4. GESTIONE ROSA
# =====================================================================
elif menu == "👤 Gestione Rosa":
    st.title("👤 Gestione Rosa Squadra")

    st.subheader("📥 Template & Importazione CSV Rosa")
    col_dl, col_rs = st.columns(2)
    with col_dl:
        df_template = pd.DataFrame({
            "Nome": ["Mario Rossi", "Luigi Bianchi"],
            "Ruolo": ["Difensore Centrale (DC)", "Centrocampista (CC)"]
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
                st.write(f"📌 **{nome}** — *Ruolo:* {dati['ruolo']}")
            with c2:
                if st.button("🗑️ Elimina", key=f"del_g_{nome}"):
                    del db_giocatori[nome]
                    salva_dati_su_disco()
                    st.success(f"Rimosso {nome} e salvato.")
                    st.rerun()

# =====================================================================
# 5. EDITOR GRAFICA & SETTINGS
# =====================================================================
elif menu == "🎨 Editor Grafica":
    st.title("🎨 Editor Grafica & Impostazioni UI")
    
    attiva_fs = st.toggle("Abilita Modalità Fullscreen (Tutto Schermo)", value=st.session_state["fullscreen_mode"])
    if attiva_fs != st.session_state["fullscreen_mode"]:
        st.session_state["fullscreen_mode"] = attiva_fs
        salva_dati_su_disco()
        st.rerun()

    cols_preset = st.columns(len(PRESET_TEMI))
    for idx, (n_preset, v_preset) in enumerate(PRESET_TEMI.items()):
        with cols_preset[idx]:
            if st.button(n_preset, use_container_width=True):
                st.session_state["ui_theme"] = v_preset.copy()
                salva_dati_su_disco()
                st.rerun()
