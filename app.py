import json
import os
from datetime import datetime
import streamlit as st

st.set_page_config(
    page_title="USO Nuvolento U16 - MVP & Statistiche",
    page_icon="🏅",
    layout="wide",
)

DB_PARTITE_FILE = "db_partite.json"
DB_GIOCATORI_FILE = "db_giocatori.json"

TEMI = {
    "Dark Pro": {
        "bg_main": "#0b1120",
        "bg_card": "#111827",
        "text_color": "#f8fafc",
        "border_color": "#1e293b",
        "accent": "#f59e0b",
    },
    "Notte": {
        "bg_main": "#090d16",
        "bg_card": "#131c31",
        "text_color": "#f1f5f9",
        "border_color": "#24324d",
        "accent": "#38bdf8",
    },
}


def carica_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else default
    except Exception:
        return default


def salva_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_data_partita(data_str):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(str(data_str).strip(), fmt)
        except Exception:
            continue
    return datetime(2026, 1, 1)


def ruolo_default_da_rosa(ruolo_raw):
    r = (ruolo_raw or "").strip().upper()
    if r in ("POR", "P", "PORTIERE", "GK"):
        return "POR"
    if r in ("DIF", "D", "DIFENSORE", "DC", "TS", "TD"):
        return "DIF"
    if r in ("CEN", "C", "CENTROCAMPISTA", "CC", "MED", "TRE"):
        return "CEN"
    if r in ("ATT", "A", "ATTACCANTE", "ALA", "PUNTA", "ST"):
        return "ATT"
    return r or "CEN"


def estrai_dati_portiere_compat(d_p):
    return {
        "gol_subiti": int(d_p.get("gol_subiti", 0) or 0),
        "parate_decisive": int(d_p.get("parate_decisive", d_p.get("parate", 0)) or 0),
        "errori_gravi": int(d_p.get("errori_gravi", d_p.get("errori", 0)) or 0),
        "sicurezza_portiere": d_p.get("sicurezza_portiere", None),
    }


def estrai_dati_movimento_compat(d_p):
    return {
        "gol_fatti": int(d_p.get("gol_fatti", d_p.get("gol", 0)) or 0),
        "assist": int(d_p.get("assist", 0) or 0),
        "errori_gravi": int(d_p.get("errori_gravi", d_p.get("errori", 0)) or 0),
    }


def calcola_voto(d_p, is_portiere=False):
    if not isinstance(d_p, dict):
        return None
    if d_p.get("voto") is not None and str(d_p.get("voto")).strip() != "":
        try:
            return round(float(d_p["voto"]), 2)
        except Exception:
            return None

    base = 6.0
    if is_portiere or "sicurezza_portiere" in d_p or "parate_decisive" in d_p:
        dp = estrai_dati_portiere_compat(d_p)
        voto = (
            base
            + (0.5 * dp["parate_decisive"])
            - (0.5 * dp["gol_subiti"])
            - (1.0 * dp["errori_gravi"])
        )
    else:
        dm = estrai_dati_movimento_compat(d_p)
        voto = (
            base
            + (1.0 * dm["gol_fatti"])
            + (0.5 * dm["assist"])
            - (1.0 * dm["errori_gravi"])
        )
    return round(max(1.0, min(10.0, voto)), 2)


def calcola_top3_partita(p_val, db_partite, db_giocatori):
    """
    Restituisce la TOP 3 dei migliori giocatori di una singola partita
    (includendo eventuali ex-aequo sull'ultimo posto utile).
    """
    minuti_stag_map = {}
    for _, p_item in db_partite.items():
        for _, g_nome in p_item.get("formazione", {}).items():
            if not g_nome:
                continue
            d_item = p_item.get("dati_prestazione", {}).get(g_nome, {})
            if d_item:
                minuti_stag_map[g_nome] = minuti_stag_map.get(g_nome, 0) + int(d_item.get("minuti", 0) or 0)

    candidati = []
    for n, nome in p_val.get("formazione", {}).items():
        if not nome:
            continue
        d_p = p_val.get("dati_prestazione", {}).get(nome, {})
        if not d_p:
            continue
        min_partita = int(d_p.get("minuti", 0) or 0)
        if min_partita <= 0:
            continue

        is_portiere = str(n) in ["1", "12"]
        voto = calcola_voto(d_p, is_portiere=is_portiere)
        if voto is None:
            continue

        if is_portiere or "sicurezza_portiere" in d_p or "parate_decisive" in d_p:
            dp = estrai_dati_portiere_compat(d_p)
            gol = 0
            assist = dp["parate_decisive"]
            gol_subiti = dp["gol_subiti"]
            errori = dp["errori_gravi"] + dp["gol_subiti"]
            ruolo_lbl = "POR"
        else:
            dm = estrai_dati_movimento_compat(d_p)
            gol = dm["gol_fatti"]
            assist = dm["assist"]
            gol_subiti = 0
            errori = dm["errori_gravi"]
            ruolo_lbl = d_p.get("ruolo_campo") or ruolo_default_da_rosa(
                db_giocatori.get(nome, {}).get("ruolo", "")
            )

        punteggio_contributo = round((gol + assist) - errori, 2)
        min_stag = int(minuti_stag_map.get(nome, min_partita))

        candidati.append({
            "nome": nome,
            "maglia": str(n),
            "ruolo": ruolo_lbl,
            "is_portiere": bool(is_portiere or ruolo_lbl == "POR"),
            "voto": float(voto),
            "punteggio_contributo": punteggio_contributo,
            "gol": int(gol),
            "assist": int(assist),
            "gol_subiti": int(gol_subiti),
            "errori": int(errori),
            "min_partita": int(min_partita),
            "min_stagione": min_stag,
        })

    if not candidati:
        return []

    def _chiave_partita(c):
        return (
            -c["voto"],
            -c["punteggio_contributo"],
            -c["gol"],
            -c["assist"],
            c["errori"],
            c["min_partita"],
            c["min_stagione"],
        )

    candidati_ord = sorted(candidati, key=_chiave_partita)
    if len(candidati_ord) <= 3:
        top3 = candidati_ord
    else:
        soglia_chiave = _chiave_partita(candidati_ord[2])
        top3 = [c for c in candidati_ord if _chiave_partita(c) <= soglia_chiave]

    for idx, item in enumerate(top3, start=1):
        item["posizione"] = idx

    return top3


def calcola_mvp_partita(p_val, db_partite, db_giocatori):
    """Restituisce la TOP 3 della partita (compatibilità con le chiamate esistenti)."""
    return calcola_top3_partita(p_val, db_partite, db_giocatori)


def calcola_mvp_stagione(db_partite, db_giocatori):
    """
    Calcola l'MVP stagionale SOLO tra i giocatori presenti almeno una volta nella TOP 3
    di almeno una partita, applicando in sequenza i criteri e fermandosi al primo
    che identifica un solo giocatore:
      1) Media voto stagionale più alta
      2) Gol + Assist (oppure -Gol Subiti se portiere) più alto
      3) Media voto più alta per minor numero di punti fatti (gol + assist)
    In caso di parità residua dopo il 3° criterio, restituisce i giocatori a pari merito.
    """
    top3_nomi = set()
    for _, p_val in db_partite.items():
        for item_t3 in calcola_top3_partita(p_val, db_partite, db_giocatori):
            nome_t3 = (item_t3.get("nome") or "").strip()
            if nome_t3:
                top3_nomi.add(nome_t3)

    if not top3_nomi:
        return []

    agg = {}
    for _, p_val in db_partite.items():
        for n, nome in p_val.get("formazione", {}).items():
            if not nome or nome not in top3_nomi:
                continue
            d_p = p_val.get("dati_prestazione", {}).get(nome, {})
            if not d_p:
                continue
            min_p = int(d_p.get("minuti", 0) or 0)
            if min_p <= 0:
                continue

            is_portiere = str(n) in ["1", "12"]
            voto = calcola_voto(d_p, is_portiere=is_portiere)
            if voto is None:
                continue

            if nome not in agg:
                ruolo_init = ruolo_default_da_rosa(db_giocatori.get(nome, {}).get("ruolo", ""))
                agg[nome] = {
                    "nome": nome,
                    "ruolo": ruolo_init,
                    "is_portiere": bool(is_portiere or ruolo_init == "POR"),
                    "voti": [],
                    "gol": 0,
                    "assist": 0,
                    "gol_subiti": 0,
                    "errori": 0,
                    "min_stagione": 0,
                }

            agg[nome]["voti"].append(float(voto))
            agg[nome]["min_stagione"] += min_p

            if is_portiere or "sicurezza_portiere" in d_p or "parate_decisive" in d_p:
                dp = estrai_dati_portiere_compat(d_p)
                agg[nome]["gol_subiti"] += int(dp["gol_subiti"])
                agg[nome]["errori"] += int(dp["errori_gravi"] + dp["gol_subiti"])
                agg[nome]["ruolo"] = "POR"
                agg[nome]["is_portiere"] = True
            else:
                dm = estrai_dati_movimento_compat(d_p)
                agg[nome]["gol"] += int(dm["gol_fatti"])
                agg[nome]["assist"] += int(dm["assist"])
                agg[nome]["errori"] += int(dm["errori_gravi"])
                rc = d_p.get("ruolo_campo")
                if rc:
                    agg[nome]["ruolo"] = rc
                    if rc == "POR":
                        agg[nome]["is_portiere"] = True

    if not agg:
        return []

    candidati = []
    for rec in agg.values():
        media_voto = round(sum(rec["voti"]) / len(rec["voti"]), 2)
        punti_fatti = int(rec["gol"] + rec["assist"])
        if rec["is_portiere"]:
            criterio_2 = -int(rec["gol_subiti"])
            criterio_2_label = f"Gol subiti: {rec['gol_subiti']}"
        else:
            criterio_2 = punti_fatti
            criterio_2_label = f"Gol+Assist: {punti_fatti}"

        candidati.append({
            "nome": rec["nome"],
            "ruolo": rec["ruolo"],
            "is_portiere": rec["is_portiere"],
            "media_voto": media_voto,
            "gol": rec["gol"],
            "assist": rec["assist"],
            "punti_fatti": punti_fatti,
            "gol_subiti": rec["gol_subiti"],
            "criterio_2": criterio_2,
            "criterio_2_label": criterio_2_label,
            "errori": rec["errori"],
            "min_stagione": rec["min_stagione"],
        })

    # 1) Media voto stagionale più alta
    max_media = max(c["media_voto"] for c in candidati)
    attuali = [c for c in candidati if c["media_voto"] == max_media]
    if len(attuali) == 1:
        attuali[0]["criterio_decisivo"] = "1) Media voto stagionale più alta"
        return attuali

    # 2) Gol+Assist (oppure -Gol subiti se portiere) più alto
    max_c2 = max(c["criterio_2"] for c in attuali)
    attuali = [c for c in attuali if c["criterio_2"] == max_c2]
    if len(attuali) == 1:
        attuali[0]["criterio_decisivo"] = "2) Gol+Assist (o meno gol subiti per portiere)"
        return attuali

    # 3) Media voto più alta per minor numero di punti fatti
    min_punti = min(c["punti_fatti"] for c in attuali)
    fascia_min_punti = [c for c in attuali if c["punti_fatti"] == min_punti]
    max_media_c3 = max(c["media_voto"] for c in fascia_min_punti)
    vincitori_c3 = [c for c in fascia_min_punti if c["media_voto"] == max_media_c3]
    for v in vincitori_c3:
        v["criterio_decisivo"] = "3) Media voto più alta per minor numero di punti fatti"
    return vincitori_c3


db_partite = carica_json(DB_PARTITE_FILE, {})
db_giocatori = carica_json(DB_GIOCATORI_FILE, {})

tema_nome = st.sidebar.selectbox("Tema interfaccia", list(TEMI.keys()), index=0)
tema = TEMI[tema_nome]
accent_hex = tema["accent"]
radius_px = 12
glow_larghezza_px = 12
glow_rgba = "rgba(245, 158, 11, 0.22)"
glow_border_rgba = tema["border_color"]
box_shadow_soft = "0 6px 18px rgba(0, 0, 0, 0.35)"

menu = st.sidebar.radio(
    "Sezioni",
    ["🏅 MVP", "⚽ Partite", "👥 Rosa"],
    index=0,
)

if menu == "🏅 MVP":
    st.title("🏅 MVP di Partita (TOP 3) & Stagione")
    st.caption(
        "Ogni partita mostra la **TOP 3**. L'**MVP della stagione** viene scelto solo tra chi è entrato "
        "almeno una volta in **TOP 3** di gara, applicando in sequenza finché resta un solo giocatore: "
        "**1) Media voto stagionale** · **2) Gol+Assist (o meno gol subiti se portiere)** · "
        "**3) Media voto più alta per minor numero di punti fatti**."
    )

    if not db_partite:
        st.warning("⚠️ Nessuna partita disponibile per calcolare gli MVP.")
        st.stop()

    if "mostra_popup_mvp_stagione" not in st.session_state:
        st.session_state["mostra_popup_mvp_stagione"] = False

    col_btn_mvp_s, _ = st.columns([1.4, 2.6])
    with col_btn_mvp_s:
        if st.button("🏆 Genera MVP della stagione", use_container_width=True, key="btn_genera_mvp_stagione"):
            st.session_state["mostra_popup_mvp_stagione"] = True
            st.rerun()

    if st.session_state.get("mostra_popup_mvp_stagione"):
        mvp_stag_list = calcola_mvp_stagione(db_partite, db_giocatori)
        if not mvp_stag_list:
            nomi_mvp_stag = "Nessun dato disponibile"
            dettagli_mvp_stag = "Inserisci almeno una prestazione con minuti > 0 per calcolare l'MVP stagionale."
            badge_stag_lbl = "MVP DELLA STAGIONE"
        else:
            badge_stag_lbl = (
                "MVP DELLA STAGIONE · PARI MERITO" if len(mvp_stag_list) > 1 else "MVP DELLA STAGIONE"
            )
            nomi_mvp_stag = " & ".join(m["nome"] for m in mvp_stag_list)
            dettagli_mvp_stag = " · ".join(
                f"{m['nome']}: Media <strong>{m['media_voto']:.2f}</strong> · "
                f"{m['criterio_2_label']} · Punti fatti <strong>{m['punti_fatti']}</strong> · "
                f"<em>{m.get('criterio_decisivo', '')}</em>"
                for m in mvp_stag_list
            )

        st.markdown(
            f"""
        <div style="
            background: linear-gradient(155deg, {tema['bg_card']} 0%, {tema['bg_main']} 100%);
            border: 2px solid {accent_hex};
            border-radius: {radius_px + 4}px;
            padding: 34px 24px 28px 24px;
            margin: 14px 0 14px 0;
            box-shadow: 0 20px 46px rgba(0, 0, 0, 0.72), 0 0 {max(18, glow_larghezza_px + 8)}px {glow_rgba};
            text-align: center;
        ">
            <div style="
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 2.2px;
                text-transform: uppercase;
                color: {accent_hex};
                margin-bottom: 10px;
            ">
                {badge_stag_lbl}
            </div>
            <div style="
                font-size: clamp(30px, 4.4vw, 48px);
                font-weight: 900;
                color: {tema['text_color']};
                line-height: 1.15;
                margin: 0 auto 14px auto;
            ">
                {nomi_mvp_stag}
            </div>
            <div style="
                font-size: 82px;
                line-height: 1.0;
                margin: 4px auto 16px auto;
                filter: drop-shadow(0 0 18px rgba(250, 204, 21, 0.55));
            " title="Pallone d'Oro">
                🟡
            </div>
            <div style="
                font-size: 58px;
                line-height: 1.0;
                margin-top: -68px;
                margin-bottom: 18px;
                pointer-events: none;
            ">
                ⚽
            </div>
            <div style="
                font-size: 13px;
                color: #cbd5e1;
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid {glow_border_rgba};
                border-radius: {max(8, radius_px - 2)}px;
                padding: 10px 14px;
                display: inline-block;
                max-width: 100%;
            ">
                {dettagli_mvp_stag}
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        col_c_pop, _ = st.columns([1.2, 2.8])
        with col_c_pop:
            if st.button("✖️ Chiudi popup MVP stagione", use_container_width=True, key="btn_chiudi_popup_mvp_stag"):
                st.session_state["mostra_popup_mvp_stagione"] = False
                st.rerun()

    st.divider()

    partite_ordinate_mvp = sorted(
        db_partite.items(),
        key=lambda item: parse_data_partita(item[1].get("data", "01/01/2026")),
    )

    medaglie_t3 = {1: "🥇", 2: "🥈", 3: "🥉"}

    for idx_m in range(0, len(partite_ordinate_mvp), 3):
        cols_mvp = st.columns(3)
        for j in range(3):
            if idx_m + j >= len(partite_ordinate_mvp):
                continue
            p_nome, p_val = partite_ordinate_mvp[idx_m + j]
            top3_partita = calcola_top3_partita(p_val, db_partite, db_giocatori)
            data_m = p_val.get("data", "N.D.")
            ris_m = p_val.get("risultato", "N.D.")

            with cols_mvp[j]:
                if not top3_partita:
                    st.markdown(
                        f"""
                    <div style="
                        background-color: {tema['bg_card']};
                        border: 1px solid {glow_border_rgba};
                        border-radius: {radius_px}px;
                        padding: 11px 13px;
                        margin-bottom: 10px;
                        box-shadow: {box_shadow_soft};
                    ">
                        <div style="font-weight:700; font-size:13px; color:{tema['text_color']};">⚽ {p_nome}</div>
                        <div style="font-size:11px; color:#94a3b8; margin-top:2px;">{data_m} · Ris. {ris_m}</div>
                        <div style="font-size:12px; color:#94a3b8; margin-top:6px;">TOP 3: <strong>N.D.</strong></div>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )
                    continue

                righe_mvp_html = []
                for m_item in top3_partita:
                    pos_num = int(m_item.get("posizione", 1))
                    icona_pos = medaglie_t3.get(pos_num, f"#{pos_num}")
                    bordo_item = accent_hex if pos_num == 1 else glow_border_rgba
                    txt_col = tema["text_color"]
                    g_val = m_item["gol"]
                    a_val = m_item["assist"]
                    e_val = m_item["errori"]
                    m_val = m_item["min_partita"]
                    v_val = m_item["voto"]
                    n_val = m_item["nome"]
                    righe_mvp_html.append(
                        f'<div style="margin-top:6px;padding:7px 9px;border-radius:{max(6, radius_px-6)}px;'
                        f'background:rgba(255,255,255,0.04);border:1px solid {bordo_item};">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">'
                        f'<span style="font-size:13px;font-weight:800;color:{txt_col} !important;line-height:1.25;">{icona_pos} {n_val}</span>'
                        f'<span style="font-size:12px;font-weight:800;color:{accent_hex} !important;white-space:nowrap;line-height:1.25;">{v_val:.1f}</span>'
                        f'</div>'
                        f'<div style="font-size:11px;color:#cbd5e1 !important;margin-top:3px;line-height:1.3;">'
                        f'Gol {g_val} · Ass {a_val} · Err {e_val} · Min {m_val}\''
                        f'</div>'
                        f'</div>'
                    )

                st.markdown(
                    f"""
                <div style="
                    background-color: {tema['bg_card']};
                    border: 1px solid {accent_hex};
                    border-radius: {radius_px}px;
                    padding: 11px 13px;
                    margin-bottom: 10px;
                    box-shadow: {box_shadow_soft};
                ">
                    <div style="display:flex; justify-content:space-between; align-items:center; gap:6px; border-bottom:1px solid {tema['border_color']}; padding-bottom:5px;">
                        <div style="font-weight:700; font-size:13px; color:{tema['text_color']};">⚽ {p_nome}</div>
                        <span style="font-size:10px; font-weight:800; color:{accent_hex}; text-transform:uppercase;">TOP 3</span>
                    </div>
                    <div style="font-size:11px; color:#94a3b8; margin-top:4px;">{data_m} · Ris. <strong>{ris_m}</strong></div>
                    {''.join(righe_mvp_html)}
                </div>
                """,
                    unsafe_allow_html=True,
                )

elif menu == "⚽ Partite":
    st.title("⚽ Gestione Partite")
    st.info("Sezione partite pronta per l'inserimento e la consultazione dei dati di gara.")
    if db_partite:
        for nome_p, dati_p in db_partite.items():
            st.write(f"**{nome_p}** — {dati_p.get('data', 'N.D.')} — Risultato: {dati_p.get('risultato', 'N.D.')}")
    else:
        st.caption("Nessuna partita salvata in `db_partite.json`.")

elif menu == "👥 Rosa":
    st.title("👥 Rosa Giocatori")
    st.info("Sezione rosa pronta per la gestione dell'organico.")
    if db_giocatori:
        for nome_g, dati_g in db_giocatori.items():
            st.write(f"**{nome_g}** — Ruolo: {dati_g.get('ruolo', 'N.D.')}")
    else:
        st.caption("Nessun giocatore salvato in `db_giocatori.json`.")
