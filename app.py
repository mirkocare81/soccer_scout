import streamlit as st
import pandas as pd
import io
import time
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# =====================================================================
# CONFIGURAZIONE PAGINA STREAMLIT
# =====================================================================
st.set_page_config(
    page_title="ScoutAI - Match Analysis",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================================
# INIZIALIZZAZIONE STATO TEMA & UI EDITOR
# =====================================================================
PRESET_TEMI = {
    "Emerald Dark (Default)": {
        "bg_main": "#090a0f",
        "bg_card": "#141721",
        "bg_sidebar": "#12141c",
        "accent": "#10b981",
        "text_color": "#f3f4f6",
        "border_color": "#1e2230",
        "border_radius": 12,
        "font_size": 16,
        "shadow_intensity": 25,
        "custom_css": ""
    },
    "Tactical Blue": {
        "bg_main": "#070d19",
        "bg_card": "#0f172a",
        "bg_sidebar": "#0b1120",
        "accent": "#3b82f6",
        "text_color": "#f8fafc",
        "border_color": "#1e293b",
        "border_radius": 10,
        "font_size": 16,
        "shadow_intensity": 30,
        "custom_css": ""
    },
    "Matchday Crimson": {
        "bg_main": "#12090b",
        "bg_card": "#1f1014",
        "bg_sidebar": "#180c0f",
        "accent": "#ef4444",
        "text_color": "#fef2f2",
        "border_color": "#381a21",
        "border_radius": 8,
        "font_size": 16,
        "shadow_intensity": 20,
        "custom_css": ""
    },
    "Clean Dark Tech": {
        "bg_main": "#0b0f19",
        "bg_card": "#111827",
        "bg_sidebar": "#0f172a",
        "accent": "#06b6d4",
        "text_color": "#f9fafb",
        "border_color": "#374151",
        "border_radius": 12,
        "font_size": 16,
        "shadow_intensity": 25,
        "custom_css": ""
    }
}

if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = PRESET_TEMI["Emerald Dark (Default)"].copy()

if "fullscreen_mode" not in st.session_state:
    st.session_state["fullscreen_mode"] = False

if "last_auto_save" not in st.session_state:
    st.session_state["last_auto_save"] = time.time()

tema = st.session_state["ui_theme"]
is_fullscreen = st.session_state["fullscreen_mode"]

# =====================================================================
# APPLICAZIONE DINAMICA DEL CSS (SFONDO SCURO UNIVERSALE & BOX ADATTIVI)
# =====================================================================
ombra_alfa = tema["shadow_intensity"] / 100.0

fullscreen_css = """
    [data-testid="stSidebar"] {display: none !important;}
    header {visibility: hidden !important;}
    footer {visibility: hidden !important;}
""" if is_fullscreen else ""

st.markdown(f"""
<style>
    .stApp {{
        background-color: {tema['bg_main']};
        color: {tema['text_color']};
        font-size: {tema['font_size']}px;
    }}
    
    .block-container {{
        max-width: 100% !important;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
        padding-top: 2rem !important;
        padding-bottom: 2rem !important;
    }}

    h1, h2, h3, h4, h5, h6, p, label, .stMarkdown, span {{
        color: {tema['text_color']} !important;
    }}

    [data-testid="stSidebar"] {{
        background-color: {tema['bg_sidebar']};
        border-right: 1px solid {tema['border_color']};
    }}

    [data-testid="stMetric"], div[data-baseweb="card"], .element-container {{
        width: 100% !important;
    }}

    [data-testid="stMetric"] {{
        background-color: {tema['bg_card']};
        border: 1px solid {tema['border_color']};
        padding: 18px;
        border-radius: {tema['border_radius']}px;
        box-shadow: 0 6px 14px rgba(0, 0, 0, {ombra_alfa});
    }}

    [data-testid="stMetricValue"] {{
        color: {tema['accent']} !important;
    }}

    .stButton > button, .stDownloadButton > button {{
        background-color: {tema['accent']} !important;
        color: #ffffff !important;
        border-radius: {tema['border_radius']}px !important;
        border: none !important;
        font-weight: 600 !important;
        padding: 0.6rem 1.2rem !important;
        width: 100% !important;
        transition: filter 0.2s ease, transform 0.1s ease;
    }}

    .stButton > button:hover, .stDownloadButton > button:hover {{
        filter: brightness(1.12);
        transform: translateY(-1px);
    }}

    input, textarea, select, div[data-baseweb="input"] div, div[data-baseweb="select"] div, div[data-baseweb="base-input"] {{
        background-color: {tema['bg_card']} !important;
        color: {tema['text_color']} !important;
        border-color: {tema['border_color']} !important;
        border-radius: {max(4, tema['border_radius'] - 4)}px !important;
    }}

    textarea, input[type="text"], input[type="number"] {{
        color: {tema['text_color']} !important;
        background-color: {tema['bg_card']} !important;
        height: auto !important;
        min-height: 42px !important;
        resize: vertical !important;
    }}

    .stTextArea textarea {{
        background-color: {tema['bg_card']} !important;
        color: {tema['text_color']} !important;
        height: 140px !important;
        overflow-y: auto !important;
    }}

    table {{
        background-color: {tema['bg_card']};
        border-radius: {tema['border_radius']}px;
        overflow: hidden;
        border: 1px solid {tema['border_color']};
        width: 100% !important;
    }}
    th {{
        background-color: {tema['accent']} !important;
        color: #ffffff !important;
        text-align: center !important;
    }}
    td {{
        color: {tema['text_color']} !important;
        border-color: {tema['border_color']} !important;
    }}

    @media (max-width: 768px) {{
        .block-container {{
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
        }}
        h1 {{
            font-size: 1.4rem !important;
        }}
        h2 {{
            font-size: 1.2rem !important;
        }}
        h3 {{
            font-size: 1.05rem !important;
        }}
        [data-testid="stMetric"] {{
            padding: 12px !important;
        }}
    }}

    {tema['custom_css']}
    {fullscreen_css}
</style>
""", unsafe_allow_html=True)

# =====================================================================
# HEADER SENZA LOGO
# =====================================================================
st.markdown("<h2>Match Analysis Dashboard</h2>", unsafe_allow_html=True)
st.divider()

# =====================================================================
# DATABASE IN-MEMORY DELLA SQUADRA
# =====================================================================
if "database_giocatori" not in st.session_state:
    st.session_state["database_giocatori"] = {
        "Mattia": {
            "ruolo": "Difensore Centrale (DC)",
            "partite": [
                {"avversario": "Virtus", "data": "15/03/2026", "minuti": 80, "duelli": "6/7", "salvataggi": "1", "passaggi": "91", "perse": "0", "tiri": "0/0", "youtube": "https://www.youtube.com/watch?v=esempio1"},
                {"avversario": "Aurora", "data": "22/03/2026", "minuti": 60, "duelli": "4/5", "salvataggi": "2", "passaggi": "88", "perse": "0", "tiri": "1/1", "youtube": ""}
            ]
        },
        "Filippo": {
            "ruolo": "Centrocampista (CC)",
            "partite": [
                {"avversario": "Virtus", "data": "15/03/2026", "minuti": 80, "duelli": "4/5", "salvataggi": "2", "passaggi": "88", "perse": "1", "tiri": "1/2", "youtube": ""}
            ]
        },
        "Davide": {
            "ruolo": "Attaccante (ATT)",
            "partite": [
                {"avversario": "Virtus", "data": "15/03/2026", "minuti": 40, "duelli": "5/8", "salvataggi": "0", "passaggi": "82", "perse": "2", "tiri": "2/3", "youtube": ""}
            ]
        }
    }

# =====================================================================
# MOTORE DI CALCOLO VOTO (Fase Difensiva + Tiri, Max 80 min)
# =====================================================================
def calcola_voto_da_partita(p):
    try:
        duelli_v, duelli_t = map(int, p['duelli'].split("/"))
        salvataggi = int(p['salvataggi'])
        pct_passaggi = float(p['passaggi']) / 100.0
        perse = int(p['perse'])
        minuti_giocati = int(p.get('minuti', 80))
        tiri_porta, tiri_specchio = map(int, p.get('tiri', '0/0').split("/"))
    except ValueError:
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
    elif pct_passaggi < 0.70:
        rating -= 0.3 * fattore_tempo

    if perse > 0:
        rating -= (perse * 0.6) * fattore_tempo

    if tiri_specchio > 0:
        efficacia_tiri = tiri_porta / tiri_specchio
        if efficacia_tiri >= 0.66:
            rating += 0.4 * fattore_tempo
        elif efficacia_tiri == 0 and tiri_specchio >= 2:
            rating -= 0.2 * fattore_tempo

    return round(max(1.0, min(10.0, rating)), 1)

# =====================================================================
# GENERATORI DI REPORT PDF (Senza Logo)
# =====================================================================
def genera_pdf_singolo(nome, dati, p, voto, accent_hex):
    filename = f"Report_{nome}_{p['avversario']}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor(accent_hex), spaceAfter=8)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=11, textColor=colors.HexColor("#333333"), spaceAfter=15)

    elements.append(Paragraph("<b>Match Analysis Report</b>", title_style))
    elements.append(Paragraph(f"<b>Giocatore:</b> {nome} ({dati['ruolo']}) | <b>Avversario:</b> {p['avversario']} | <b>Data:</b> {p['data']} | <b>Minuti:</b> {p['minuti']}'/80'", subtitle_style))

    table_data = [
        ["Parametro", "Valore Registrato"],
        ["Voto Finale (Parametrizzato 80')", f"{voto} / 10"],
        ["Minuti in Campo", f"{p['minuti']}' / 80'"],
        ["Duelli Difensivi Vinti/Tot", p['duelli']],
        ["Salvataggi Decisivi", p['salvataggi']],
        ["Precisione Passaggi", f"{p['passaggi']}%"],
        ["Palle Perse Pericolose", p['perse']],
        ["Tiri in Porta / Nello Specchio", p.get('tiri', '0/0')]
    ]

    t = Table(table_data, colWidths=[200, 200])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), colors.HexColor(accent_hex)),
        ('TEXTCOLOR', (0,0), (1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f3f4f6")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#d1d5db")),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('TOPPADDING', (0,1), (-1,-1), 6),
        ('BOTTOMPADDING', (0,1), (-1,-1), 6),
    ]))
    elements.append(t)
    
    if p.get('youtube'):
        elements.append(Spacer(1, 15))
        elements.append(Paragraph(f"<b>Video YouTube Match:</b> {p['youtube']}", styles['Normal']))

    doc.build(elements)
    return filename

def genera_pdf_stagione_giocatore(nome, dati, accent_hex):
    filename = f"Report_Stagionale_{nome}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor(accent_hex), spaceAfter=12)

    elements.append(Paragraph(f"<b>Report Stagionale: {nome} ({dati['ruolo']})</b>", title_style))
    elements.append(Spacer(1, 10))

    table_data = [["Data", "Avversario", "Min.", "Duelli", "Tiri (P/Sp)", "Voto"]]
    for p in dati["partite"]:
        v = calcola_voto_da_partita(p)
        table_data.append([p['data'], p['avversario'], f"{p['minuti']}'", p['duelli'], p.get('tiri', '0/0'), str(v)])

    t = Table(table_data, colWidths=[80, 110, 50, 75, 85, 50])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(accent_hex)),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#d1d5db")),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f3f4f6")),
    ]))
    elements.append(t)
    doc.build(elements)
    return filename

def genera_pdf_squadra(db, accent_hex):
    filename = "Report_Generale_Stagione_Squadra.pdf"
    doc = SimpleDocTemplate(filename, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, textColor=colors.HexColor(accent_hex), spaceAfter=12)

    elements.append(Paragraph("<b>Riepilogo Generale Stagionale Squadra</b>", title_style))
    elements.append(Spacer(1, 10))

    table_data = [["Giocatore", "Ruolo", "Partite", "Media Voto Stagione"]]
    for nome, dati in db.items():
        voti = [calcola_voto_da_partita(p) for p in dati["partite"]]
        media = round(sum(voti) / len(voti), 1) if voti else 6.0
        table_data.append([nome, dati['ruolo'], str(len(dati["partite"])), f"{media} / 10"])

    t = Table(table_data, colWidths=[120, 150, 80, 100])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(accent_hex)),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#d1d5db")),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#f3f4f6")),
    ]))
    elements.append(t)
    doc.build(elements)
    return filename

# =====================================================================
# INTERFACCIA STREAMLIT (SIDEBAR & NAVIGAZIONE)
# =====================================================================
st.sidebar.title("⚽ ScoutAI")
menu = st.sidebar.radio("Navigazione", ["📊 Match Dashboard", "📈 Dashboard Stagione", "👤 Gestione Rosa", "🎨 Editor Grafica & Settings"])

db = st.session_state["database_giocatori"]

# =====================================================================
# SALVATAGGIO AUTOMATICO SILENZIOSO (OGNI 30 SECONDI)
# =====================================================================
current_time = time.time()
if current_time - st.session_state["last_auto_save"] > 30:
    st.session_state["last_auto_save"] = current_time

# ---------------------------------------------------------------------
# 1. MATCH DASHBOARD
# ---------------------------------------------------------------------
if menu == "📊 Match Dashboard":
    st.title("📊 Match Analysis Dashboard (Fase Difensiva & Tiri)")

    if not db:
        st.warning("⚠️ Nessun giocatore in rosa. Aggiungi prima dei giocatori nella sezione 'Gestione Rosa'.")
        st.stop()

    giocatore_selezionato = st.selectbox("Seleziona Giocatore", list(db.keys()))
    dati_g = db[giocatore_selezionato]

    modalita_match = st.radio("Azione Partita", ["Modifica Ultima Partita", "Registra Nuova Partita"], horizontal=True)

    if modalita_match == "Registra Nuova Partita":
        st.subheader(f"➕ Aggiungi Nuovo Match per {giocatore_selezionato}")
        with st.form("nuova_partita_form"):
            n_avv = st.text_input("Squadra Avversaria")
            n_data = st.text_input("Data Partita (es. 29/03/2026)")
            n_minuti = st.number_input("Minuti Giocati (Max 80')", min_value=1, max_value=80, value=80)
            n_duelli = st.text_input("Duelli Difensivi Vinti / Totali (es. 6/7)")
            n_salv = st.text_input("Salvataggi Decisivi", value="0")
            n_pass = st.text_input("Precisione Passaggi (%)", value="85")
            n_perse = st.text_input("Palle Perse Pericolose", value="0")
            n_tiri = st.text_input("Tiri in Porta / Nello Specchio (es. 1/2)", value="0/0")
            n_youtube = st.text_input("🔗 Link Video YouTube del Match (Opzionale)", placeholder="https://www.youtube.com/watch?v=...")
            
            submit_match = st.form_submit_button("Salva Nuova Partita")
            if submit_match and n_avv:
                nuovo_match = {
                    "avversario": n_avv, "data": n_data, "minuti": int(n_minuti),
                    "duelli": n_duelli, "salvataggi": n_salv, "passaggi": n_pass, "perse": n_perse,
                    "tiri": n_tiri, "youtube": n_youtube
                }
                dati_g["partite"].append(nuovo_match)
                st.success(f"Partita contro {n_avv} aggiunta con successo allo storico di {giocatore_selezionato}!")
                st.rerun()
        st.stop()

    ultima_p = dati_g["partite"][-1] if dati_g["partite"] else {"avversario": "Esordio", "data": "Oggi", "minuti": 80, "duelli": "5/5", "salvataggi": "0", "passaggi": "80", "perse": "0", "tiri": "0/0", "youtube": ""}

    st.markdown(f"### Analisi Ultimo Match: {giocatore_selezionato} ({dati_g['ruolo']}) vs {ultima_p['avversario']}")

    col_input, col_score, col_report = st.columns([1.2, 1, 1.2])

    with col_input:
        st.markdown("#### Parametri Partita Corrente")
        avv = st.text_input("Squadra Avversaria", value=ultima_p['avversario'])
        data_p = st.text_input("Data Partita", value=ultima_p['data'])
        minuti = st.number_input("Minuti Giocati in Campo (Max 80')", min_value=1, max_value=80, value=int(ultima_p.get('minuti', 80)))
        duelli = st.text_input("Duelli Difensivi Vinti / Totali (es. 6/7)", value=ultima_p['duelli'])
        salvataggi = st.text_input("Salvataggi Decisivi", value=ultima_p['salvataggi'])
        passaggi = st.text_input("Precisione Passaggi (%)", value=ultima_p['passaggi'])
        perse = st.text_input("Palle Perse Pericolose", value=ultima_p['perse'])
        tiri = st.text_input("Tiri in Porta / Nello Specchio (es. 1/2)", value=ultima_p.get('tiri', '0/0'))
        link_yt = st.text_input("🔗 Link Video YouTube del Match", value=ultima_p.get('youtube', ''))

        if st.button("Aggiorna Voto Partita", use_container_width=True):
            ultima_p['avversario'] = avv
            ultima_p['data'] = data_p
            ultima_p['minuti'] = int(minuti)
            ultima_p['duelli'] = duelli
            ultima_p['salvataggi'] = salvataggi
            ultima_p['passaggi'] = passaggi
            ultima_p['perse'] = perse
            ultima_p['tiri'] = tiri
            ultima_p['youtube'] = link_yt
            st.success("Dati aggiornati con successo!")
            st.rerun()

    voto_fin = calcola_voto_da_partita(ultima_p)

    with col_score:
        st.markdown("#### Voto Finale")
        st.metric(label="Rating (Parametrizzato 80')", value=f"{voto_fin} / 10", delta=f"{minuti}' in campo")
        
        if minuti < 80:
            st.warning(f"⚠️ Subentrato/Sostituito ({minuti}/80 min): normalizzato sul minutaggio.")
        else:
            st.info("⏱️ Partita completa (80 min)")

        if ultima_p.get('youtube'):
            st.link_button("▶️ Guarda Video su YouTube", ultima_p['youtube'], use_container_width=True)

    with col_report:
        st.markdown("#### Dettaglio Valutazione & Export PDF")
        try:
            dv, dt = map(int, duelli.split("/"))
            p_duelli = (dv / dt) if dt > 0 else 0
        except:
            p_duelli = 0

        report_txt = f"• Minuti giocati: {minuti}' / 80'\n"
        report_txt += "• Punteggio base: 6.0\n"
        if p_duelli >= 0.75 and dt >= 3: report_txt += "• Ottimi duelli difensivi (>75%): Bonus\n"
        elif p_duelli < 0.40: report_txt += "• Duelli difensivi bassi (<40%): Malus\n"
        
        salv_int = int(salvataggi) if salvataggi.isdigit() else 0
        if salv_int > 0: report_txt += f"• Salvataggi Decisivi ({salv_int}): Bonus\n"
        
        report_txt += f"• Tiri (Porta/Specchio): {tiri}\n"
        
        st.text_area("Log Algoritmo", value=report_txt, height=140)

        pdf_file = genera_pdf_singolo(giocatore_selezionato, dati_g, ultima_p, voto_fin, tema["accent"])
        with open(pdf_file, "rb") as f:
            st.download_button("📄 Scarica PDF Singolo Match", f, file_name=pdf_file, mime="application/pdf", use_container_width=True)

# ---------------------------------------------------------------------
# 2. DASHBOARD STAGIONE
# ---------------------------------------------------------------------
elif menu == "📈 Dashboard Stagione":
    st.title("📈 Dashboard Stagione - Squadra & Trend Giocatori")

    if not db:
        st.warning("⚠️ Nessun giocatore in rosa. Aggiungi prima dei giocatori nella sezione 'Gestione Rosa'.")
        st.stop()

    tot_giocatori = len(db)
    tot_partite = sum(len(d["partite"]) for d in db.values())
    voti_generali = [calcola_voto_da_partita(p) for d in db.values() for p in d["partite"]]
    media_generale = round(sum(voti_generali) / len(voti_generali), 1) if voti_generali else 6.0

    col1, col2, col3 = st.columns(3)
    col1.metric("Giocatori in Rosa", tot_giocatori)
    col2.metric("Partite Monitorate (Totali)", tot_partite)
    col3.metric("Media Voto Generale Squadra", f"{media_generale} / 10")

    col_pdf_sq1, col_pdf_sq2 = st.columns([1, 3])
    with col_pdf_sq1:
        pdf_squadra = genera_pdf_squadra(db, tema["accent"])
        with open(pdf_squadra, "rb") as f:
            st.download_button("📄 PDF Intera Squadra", f, file_name=pdf_squadra, mime="application/pdf")

    st.divider()

    g_sel = st.selectbox("Seleziona Giocatore per Trend & Statistiche Stagionali", list(db.keys()))
    dati_giocatore = db[g_sel]
    partite_g = dati_giocatore["partite"]
    
    voti_g = [calcola_voto_da_partita(p) for p in partite_g]
    media_g = round(sum(voti_g) / len(voti_g), 1) if voti_g else 6.0

    trend_txt = "Stabile (↔️)"
    if len(voti_g) >= 2:
        ultimo_voto = voti_g[-1]
        media_precedente = sum(voti_g[:-1]) / len(voti_g[:-1])
        delta_val = round(ultimo_voto - media_precedente, 1)
        if delta_val > 0:
            trend_txt = f"In Crescita 📈 (+{delta_val} vs media prec.)"
        elif delta_val < 0:
            trend_txt = f"In Decrescita 📉 ({delta_val} vs media prec.)"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Partite Giocate", len(partite_g))
    c2.metric("Media Voto Stagione", f"{media_g} / 10")
    c3.metric("Miglior Prestazione", f"{max(voti_g)} / 10" if voti_g else "N/D")
    c4.metric("Trend di Rendimento", trend_txt)

    pdf_stag_singolo = genera_pdf_stagione_giocatore(g_sel, dati_giocatore, tema["accent"])
    with open(pdf_stag_singolo, "rb") as f:
        st.download_button(f"📄 Scarica PDF Stagionale di {g_sel}", f, file_name=pdf_stag_singolo, mime="application/pdf")

    st.markdown("#### Storico Partite del Giocatore")
    st.table([{"Partita N°": i+1, "Data": p['data'], "Avversario": p['avversario'], "Minuti in Campo": f"{p['minuti']}'/80'", "Duelli": p['duelli'], "Tiri (Porta/Specchio)": p.get('tiri', '0/0'), "Voto": calcola_voto_da_partita(p), "YouTube": p.get('youtube', 'Nessuno')} for i, p in enumerate(partite_g)])

# ---------------------------------------------------------------------
# 3. GESTIONE ROSA (Con Import/Export Excel e Cancellazione Giocatore)
# ---------------------------------------------------------------------
elif menu == "👤 Gestione Rosa":
    st.title("👤 Gestione Rosa Squadra")

    st.subheader("📥 Template Excel per Importazione Rosa")
    st.markdown("Scarica il template precompilato, inserisci i nomi e i ruoli dei giocatori e caricalo qui sotto.")

    df_template = pd.DataFrame({
        "Nome": ["Esempio Mario", "Esempio Luigi"],
        "Ruolo": ["Difensore Centrale (DC)", "Centrocampista (CC)"]
    })
    
    output_excel = io.BytesIO()
    with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
        df_template.to_excel(writer, index=False, sheet_name='Rosa')
    excel_data = output_excel.getvalue()

    st.download_button(
        label="📥 Scarica Template Excel Rosa (.xlsx)",
        data=excel_data,
        file_name="template_rosa_scoutai.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.divider()

    st.subheader("📤 Carica Rosa da File Excel o CSV")
    uploaded_file = st.file_uploader("Carica il file della rosa", type=["xlsx", "csv"])
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df_upload = pd.read_csv(uploaded_file)
            else:
                df_upload = pd.read_excel(uploaded_file)
            
            if "Nome" in df_upload.columns and "Ruolo" in df_upload.columns:
                st.success(f"File letto correttamente! Trovati {len(df_upload)} giocatori.")
                if st.button("Conferma e Aggiorna Rosa nel Database", type="primary"):
                    for _, row in df_upload.iterrows():
                        nome_giocatore = str(row["Nome"]).strip()
                        ruolo_giocatore = str(row["Ruolo"]).strip()
                        if nome_giocatore and nome_giocatore not in db:
                            db[nome_giocatore] = {
                                "ruolo": ruolo_giocatore,
                                "partite": [{"avversario": "Esordio", "data": "Oggi", "minuti": 80, "duelli": "5/5", "salvataggi": "0", "passaggi": "80", "perse": "0", "tiri": "0/0", "youtube": ""}]
                            }
                    st.success("Rosa aggiornata con successo dal file!")
                    st.rerun()
            else:
                st.error("Il file deve contenere esattamente le colonne 'Nome' e 'Ruolo'.")
        except Exception as e:
            st.error(f"Errore nella lettura del file: {e}")

    st.divider()

    with st.form("nuovo_giocatore_form"):
        st.subheader("Aggiungi Singolo Giocatore Manualmente")
        n_nome = st.text_input("Nome e Cognome")
        n_ruolo = st.text_input("Ruolo (es. Difensore, Centrocampista)")
        submit = st.form_submit_button("Crea Giocatore")
        
        if submit and n_nome and n_ruolo:
            if n_nome not in db:
                db[n_nome] = {
                    "ruolo": n_ruolo,
                    "partite": [{"avversario": "Esordio", "data": "Oggi", "minuti": 80, "duelli": "5/5", "salvataggi": "0", "passaggi": "80", "perse": "0", "tiri": "0/0", "youtube": ""}]
                }
                st.success(f"Giocatore {n_nome} aggiunto con successo!")
                st.rerun()
            else:
                st.warning("Giocatore già esistente.")

    st.divider()
    st.subheader("Elenco Rosa Attuale & Rimozione Giocatori")
    
    if not db:
        st.info("La rosa è attualmente vuota.")
    else:
        for nome in list(db.keys()):
            dati = db[nome]
            col_info, col_del = st.columns([3, 1])
            with col_info:
                st.write(f"📌 **{nome}** — *Ruolo:* {dati['ruolo']} — *Partite:* {len(dati['partite']) if 'partite' in dati else 0}")
            with col_del:
                if st.button(f"🗑️ Elimina", key=f"del_{nome}", use_container_width=True):
                    del db[nome]
                    st.success(f"Giocatore {nome} rimosso dalla rosa!")
                    st.rerun()

# ---------------------------------------------------------------------
# 4. EDITOR GRAFICA & SETTINGS
# ---------------------------------------------------------------------
elif menu == "🎨 Editor Grafica & Settings":
    st.title("🎨 Editor Grafica & Impostazioni UI")
    st.markdown("Personalizza colori, forme, stile e modalità di visualizzazione dell'applicazione.")

    st.subheader("🖥️ Modalità di Visualizzazione")
    attiva_fs = st.toggle("Abilita Modalità Fullscreen (Tutto Schermo / Nascondi Sidebar)", value=st.session_state["fullscreen_mode"])
    if attiva_fs != st.session_state["fullscreen_mode"]:
        st.session_state["fullscreen_mode"] = attiva_fs
        st.rerun()

    st.divider()

    st.subheader("1. Temi Preimpostati (Quick Presets)")
    cols_preset = st.columns(len(PRESET_TEMI))
    for idx, (nome_preset, valori_preset) in enumerate(PRESET_TEMI.items()):
        with cols_preset[idx]:
            if st.button(nome_preset, use_container_width=True):
                st.session_state["ui_theme"] = valori_preset.copy()
                st.rerun()

    st.divider()

    st.subheader("2. Personalizzazione Colori & Forme")
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        nuovo_accent = st.color_picker("Colore Primario / Accenti", tema["accent"])
        nuovo_bg_main = st.color_picker("Sfondo Principale App", tema["bg_main"])
        nuovo_bg_card = st.color_picker("Sfondo Card, Input e Tabelle", tema["bg_card"])
        nuovo_bg_sidebar = st.color_picker("Sfondo Sidebar", tema["bg_sidebar"])
        nuovo_text = st.color_picker("Colore Testo", tema["text_color"])
        nuovo_border = st.color_picker("Colore Bordi", tema["border_color"])

    with col_c2:
        nuovo_radius = st.slider("Arrotondamento Angoli (px)", min_value=0, max_value=24, value=tema["border_radius"])
        nuovo_font = st.slider("Dimensione Base Testo (px)", min_value=12, max_value=22, value=tema["font_size"])
        nuovo_shadow = st.slider("Intensità Ombre Card (%)", min_value=0, max_value=80, value=tema["shadow_intensity"])

    with st.expander("🛠️ CSS Avanzato Personalizzato (Opzionale)"):
        nuovo_css = st.text_area("Incolla qui eventuali regole CSS extra:", value=tema["custom_css"], height=120)

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("✅ Applica Modifiche Grafiche", use_container_width=True):
            st.session_state["ui_theme"] = {
                "bg_main": nuovo_bg_main, "bg_card": nuovo_bg_card, "bg_sidebar": nuovo_bg_sidebar,
                "accent": nuovo_accent, "text_color": nuovo_text, "border_color": nuevo_border,
                "border_radius": nuevo_radius, "font_size": nuevo_font, "shadow_intensity": nuevo_shadow, "custom_css": nuovo_css
            }
            st.success("Tema grafico aggiornato con successo!")
            st.rerun()

    with col_btn2:
        if st.button("🔄 Ripristina Tema Predefinito", use_container_width=True):
            st.session_state["ui_theme"] = PRESET_TEMI["Emerald Dark (Default)"].copy()
            st.session_state["fullscreen_mode"] = False
            st.rerun()
