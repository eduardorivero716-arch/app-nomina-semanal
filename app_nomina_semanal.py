"""
Cálculo de horas y nómina semanal · estilo liquidación corporativa
Ejecutar:  streamlit run app_nomina_semanal.py
"""
import io
from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

# ───────────────────────── Configuración y estilo ─────────────────────────
st.set_page_config(page_title="Nómina semanal", page_icon="🧾", layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Inter', sans-serif; }
.stApp { background: #F6F7FB; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 2rem; max-width: 1280px; }
h1, h2, h3 { color: #1B2559; letter-spacing: -0.01em; }
.page-title { font-size: 1.6rem; font-weight: 700; color: #1B2559; margin: 0; }
.page-sub { color: #6B7280; margin: 0 0 1.2rem 0; font-size: .92rem; }
.kpi { background: #fff; border: 1px solid #E6E8F0; border-radius: 12px; padding: 16px 18px; height: 100%; }
.kpi .lbl { color: #6B7280; font-size: .78rem; font-weight: 500; }
.kpi .val { color: #1B2559; font-size: 1.45rem; font-weight: 700; margin-top: 4px; }
.kpi .sub { color: #9CA3AF; font-size: .75rem; margin-top: 2px; }
.kpi.accent { background: #2750E8; border-color: #2750E8; }
.kpi.accent .lbl, .kpi.accent .sub { color: #D6DEFF; }
.kpi.accent .val { color: #fff; }
.card { background: #fff; border: 1px solid #E6E8F0; border-radius: 12px; padding: 16px 18px; margin-bottom: 12px; }
.chip { display:inline-block; background:#EEF2FF; color:#2750E8; border-radius:999px;
        padding: 2px 10px; font-size:.75rem; font-weight:600; margin-right:6px; }
.chip.warn { background:#FFF4E5; color:#B45309; }
[data-testid="stExpander"] { background:#fff; border:1px solid #E6E8F0; border-radius:12px; margin-bottom:10px; }
[data-testid="stSidebar"] { background:#fff; border-right:1px solid #E6E8F0; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid #E6E8F0; }
.stTabs [aria-selected="true"] { color:#2750E8; }
</style>
""",
    unsafe_allow_html=True,
)

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
JORNADA = 42.0


def clp(x):
    return "$" + f"{x:,.0f}".replace(",", ".")


def kpi(label, value, sub="", accent=False):
    return (f'<div class="kpi{" accent" if accent else ""}"><div class="lbl">{label}</div>'
            f'<div class="val">{value}</div><div class="sub">{sub}</div></div>')


# ───────────────────────── Carga del archivo de marcas ─────────────────────────
def demo_data():
    rng = np.random.default_rng(7)
    hoy = date.today().replace(day=1)
    emps = [("Camila Rojas", "Temuco", "Ventas"), ("Diego Soto", "Temuco", "Bodega"),
            ("Valentina Pérez", "Temuco", "Caja"), ("Matías Fuentes", "Padre Las Casas", "Ventas"),
            ("Javiera Muñoz", "Padre Las Casas", "Caja"), ("Felipe Araya", "Padre Las Casas", "Bodega")]
    rows = []
    for d in pd.date_range(hoy, hoy + pd.offsets.MonthEnd(0)):
        for n, s, a in emps:
            if d.weekday() == 6 and rng.random() > 0.25:
                continue
            ent = 8 + rng.integers(0, 2)
            dur = rng.choice([8, 9, 9, 10])
            rows.append([n, s, a, d, f"{ent:02d}:00", f"{(ent + dur) % 24:02d}:{rng.integers(0, 30):02d}", 60])
    return pd.DataFrame(rows, columns=["Colaborador", "Sucursal", "Área", "Fecha", "Entrada", "Salida", "Colación (min)"])


def guess(cols, keys):
    for i, c in enumerate(cols):
        if any(k in c.lower() for k in keys):
            return i
    return 0


def prepare_marks(raw):
    cols = list(raw.columns)
    none = "— ninguna —"
    with st.sidebar.expander("Mapeo de columnas", expanded=False):
        modo = st.radio("Formato del archivo", ["Entrada y salida por fila", "Marcas individuales (fecha-hora)"])
        c_col = st.selectbox("Colaborador", cols, guess(cols, ["colab", "nombre", "emplead", "trabaj"]))
        c_suc = st.selectbox("Sucursal", [none] + cols, 0 if not any("sucur" in c.lower() for c in cols) else 1 + guess(cols, ["sucur"]))
        c_area = st.selectbox("Área", [none] + cols, 0 if not any("area" in c.lower() or "área" in c.lower() for c in cols) else 1 + guess(cols, ["area", "área"]))
        if modo.startswith("Entrada"):
            c_fec = st.selectbox("Fecha", cols, guess(cols, ["fecha", "dia", "día"]))
            c_ent = st.selectbox("Entrada", cols, guess(cols, ["entrada", "ingreso", "in"]))
            c_sal = st.selectbox("Salida", cols, guess(cols, ["salida", "egreso", "out"]))
        else:
            c_dt = st.selectbox("Fecha-hora de la marca", cols, guess(cols, ["fecha", "hora", "marca"]))
        c_col_min = st.selectbox("Colación (min)", [none] + cols, 0)
        colacion_def = st.number_input("Colación por defecto (min)", 0, 180, 60, 15,
                                       help="Se usa si no hay columna de colación.")

    df = pd.DataFrame({"Colaborador": raw[c_col].astype(str).str.strip()})
    df["Sucursal"] = raw[c_suc].astype(str) if c_suc != none else "General"
    df["Área"] = raw[c_area].astype(str) if c_area != none else "General"
    col_min = pd.to_numeric(raw[c_col_min], errors="coerce").fillna(colacion_def) if c_col_min != none else colacion_def

    if modo.startswith("Entrada"):
        fecha = pd.to_datetime(raw[c_fec], errors="coerce", dayfirst=True).dt.normalize()
        te, ts = pd.to_datetime(raw[c_ent].astype(str), errors="coerce"), pd.to_datetime(raw[c_sal].astype(str), errors="coerce")
        ent = fecha + (te - te.dt.normalize())
        sal = fecha + (ts - ts.dt.normalize())
        sal = sal.where(sal >= ent, sal + pd.Timedelta(days=1))
        df["Fecha"], df["ent"], df["sal"], df["col"] = fecha, ent, sal, col_min
    else:
        dt = pd.to_datetime(raw[c_dt], errors="coerce", dayfirst=True)
        tmp = df.assign(dt=dt, Fecha=dt.dt.normalize(), col=col_min).dropna(subset=["dt"])
        df = (tmp.groupby(["Colaborador", "Sucursal", "Área", "Fecha"], as_index=False)
                 .agg(ent=("dt", "min"), sal=("dt", "max"), col=("col", "first")))

    df = df.dropna(subset=["Fecha", "ent", "sal"])
    df["Horas"] = ((df["sal"] - df["ent"]).dt.total_seconds() / 3600 - df["col"] / 60).clip(lower=0).round(2)
    return df[["Colaborador", "Sucursal", "Área", "Fecha", "ent", "sal", "Horas"]]


# ───────────────────────── Sidebar: archivo y filtros ─────────────────────────
st.sidebar.markdown("### Archivo de marcas")
up = st.sidebar.file_uploader("Reloj control (CSV o Excel)", type=["csv", "xlsx", "xls"])
if up is None:
    st.sidebar.info("Sin archivo: se muestran datos de demostración.")
    raw = demo_data()
else:
    raw = pd.read_csv(up, sep=None, engine="python") if up.name.lower().endswith(".csv") else pd.read_excel(up)

marks = prepare_marks(raw)
if marks.empty:
    st.error("No se pudieron leer marcas válidas. Revisa el mapeo de columnas en la barra lateral.")
    st.stop()

st.sidebar.markdown("### Filtros")
periodos = sorted(marks["Fecha"].dt.to_period("M").unique())
periodo = st.sidebar.selectbox("Mes", periodos, index=len(periodos) - 1,
                               format_func=lambda p: f"{MESES[p.month - 1]} {p.year}")
marks = marks[marks["Fecha"].dt.to_period("M") == periodo]
sucs = st.sidebar.multiselect("Sucursal", sorted(marks["Sucursal"].unique()))
if sucs:
    marks = marks[marks["Sucursal"].isin(sucs)]
areas = st.sidebar.multiselect("Área", sorted(marks["Área"].unique()))
if areas:
    marks = marks[marks["Área"].isin(areas)]
colabs = st.sidebar.multiselect("Colaborador", sorted(marks["Colaborador"].unique()))
if colabs:
    marks = marks[marks["Colaborador"].isin(colabs)]
if marks.empty:
    st.warning("Los filtros no devuelven marcas.")
    st.stop()
emps = sorted(marks["Colaborador"].unique())

st.sidebar.markdown("### Reglas de cálculo")
f_extra = st.sidebar.number_input("Factor hora extra", 1.0, 3.0, 1.5, 0.05)
rec_dom = st.sidebar.number_input("Recargo dominical", 0.0, 1.0, 0.30, 0.05, format="%.2f")
f_fer = st.sidebar.number_input("Factor feriado trabajado", 1.0, 3.0, 1.5, 0.05)
st.sidebar.markdown("### Descuentos estimados")
d_prev = st.sidebar.number_input("Previsión (%)", 0.0, 30.0, 11.0, 0.1)
d_salud = st.sidebar.number_input("Salud (%)", 0.0, 30.0, 7.0, 0.1)

# ───────────────────────── Encabezado ─────────────────────────
st.markdown('<p class="page-title">Horas y nómina semanal</p>'
            f'<p class="page-sub">{MESES[periodo.month - 1]} {periodo.year} · {len(emps)} colaboradores · '
            f'jornada base {JORNADA:g} h semanales</p>', unsafe_allow_html=True)
kpi_box = st.container()
t_res, t_sem, t_fer, t_par, t_aud, t_dia = st.tabs(
    ["Resumen", "Semana a semana", "Feriados", "Sueldos y parámetros", "Auditoría", "Detalle diario"])

# ───────────────────────── Parámetros de sueldo ─────────────────────────
with t_par:
    st.markdown("Ingresa el sueldo base mensual. El valor hora se calcula como **sueldo ÷ 180** "
                "(jornada de 42 h); escribe un valor distinto de 0 para reemplazarlo.")
    sueldo_def = st.number_input("Sueldo base por defecto", 0, 20_000_000, 600_000, 10_000)
    prev = st.session_state.get("params", pd.DataFrame(columns=["Colaborador", "Sueldo base", "Valor hora (manual)"]))
    par = pd.DataFrame({"Colaborador": emps}).merge(prev, how="left", on="Colaborador")
    par["Sueldo base"] = par["Sueldo base"].fillna(sueldo_def)
    par["Valor hora (manual)"] = par["Valor hora (manual)"].fillna(0)
    par = st.data_editor(par, hide_index=True, use_container_width=True, disabled=["Colaborador"],
                         column_config={"Sueldo base": st.column_config.NumberColumn(format="$ %d", min_value=0),
                                        "Valor hora (manual)": st.column_config.NumberColumn(format="$ %d", min_value=0)})
    st.session_state["params"] = par
par["Valor hora"] = np.where(par["Valor hora (manual)"] > 0, par["Valor hora (manual)"], par["Sueldo base"] / 180)
P = par.set_index("Colaborador")

# ───────────────────────── Feriados ─────────────────────────
with t_fer:
    ini, fin = periodo.start_time.date(), periodo.end_time.date()
    dias_mes = [ini + timedelta(days=i) for i in range((fin - ini).days + 1)]
    feriados = st.multiselect("Días feriados legales del mes", dias_mes,
                              format_func=lambda d: f"{DIAS[d.weekday()]} {d.day:02d}/{d.month:02d}")
    feriados_ts = {pd.Timestamp(d) for d in feriados}
    st.caption("Las horas en feriado no suman a las 42 h semanales ni llevan recargo dominical: "
               "se pagan solo según la opción elegida.")
    if feriados:
        hechos = (marks[marks["Fecha"].isin(feriados_ts)].groupby(["Colaborador", "Fecha"], as_index=False)["Horas"].sum())
        base = pd.DataFrame({"Colaborador": hechos["Colaborador"], "Fecha": hechos["Fecha"].dt.date,
                             "Horas": hechos["Horas"], "Compensación": "Pago extra (1.5x)"})
        sig = (str(periodo), tuple(feriados), tuple(emps))
        if st.session_state.get("fer_sig") != sig:
            st.session_state["fer_sig"], st.session_state["fer_df"] = sig, base
        st.markdown("**Quiénes trabajaron** · agrega filas para registrar a alguien sin marca.")
        fer_df = st.data_editor(
            st.session_state["fer_df"], num_rows="dynamic", hide_index=True, use_container_width=True,
            column_config={
                "Colaborador": st.column_config.SelectboxColumn(options=emps, required=True),
                "Fecha": st.column_config.SelectboxColumn(options=feriados, required=True),
                "Horas": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.2f"),
                "Compensación": st.column_config.SelectboxColumn(
                    options=["Pago extra (1.5x)", "Día libre compensatorio"], required=True)})
        st.session_state["fer_df"] = fer_df
    else:
        fer_df = pd.DataFrame(columns=["Colaborador", "Fecha", "Horas", "Compensación"])
        st.info("Selecciona los feriados del mes para registrar a quienes trabajaron.")
fer_df = fer_df.dropna(subset=["Colaborador", "Fecha"]).copy()
fer_df["Horas"] = pd.to_numeric(fer_df["Horas"], errors="coerce").fillna(0)
fer_df["Fecha"] = pd.to_datetime(fer_df["Fecha"])

# ───────────────────────── Motor de cálculo ─────────────────────────
m = marks.copy()
m["Feriado"] = m["Fecha"].isin(feriados_ts)
m["Domingo"] = (m["Fecha"].dt.weekday == 6) & ~m["Feriado"]
m["Sem_ini"] = m["Fecha"] - pd.to_timedelta(m["Fecha"].dt.weekday, unit="D")
ordin = m[~m["Feriado"]]

sem = (ordin.groupby(["Sem_ini", "Colaborador"])
       .agg(Dias=("Fecha", "nunique"), Total=("Horas", "sum"),
            Dom=("Horas", lambda s: s[ordin.loc[s.index, "Domingo"]].sum())).reset_index())
sem["Base"] = sem["Total"].clip(upper=JORNADA)
sem["Extras"] = (sem["Total"] - JORNADA).clip(lower=0)

fer_df["Sem_ini"] = fer_df["Fecha"] - pd.to_timedelta(fer_df["Fecha"].dt.weekday, unit="D")
fer_w = (fer_df.assign(Fer_pago=np.where(fer_df["Compensación"].str.startswith("Pago"), fer_df["Horas"], 0),
                       Fer_libre=np.where(fer_df["Compensación"].str.startswith("Pago"), 0, 1))
         .groupby(["Sem_ini", "Colaborador"], as_index=False)
         .agg(Fer_h=("Horas", "sum"), Fer_pago=("Fer_pago", "sum"), Fer_libre=("Fer_libre", "sum")))
sem = sem.merge(fer_w, how="outer", on=["Sem_ini", "Colaborador"]).fillna(0)
sem = sem[sem["Colaborador"].isin(emps)].sort_values(["Sem_ini", "Colaborador"])

sem["VH"] = sem["Colaborador"].map(P["Valor hora"])
sem["$ Extras"] = sem["Extras"] * sem["VH"] * f_extra
sem["$ Dominical"] = sem["Dom"] * sem["VH"] * rec_dom
sem["$ Feriado"] = sem["Fer_pago"] * sem["VH"] * f_fer

emp = sem.groupby("Colaborador", as_index=False).agg(
    Dias=("Dias", "sum"), Base=("Base", "sum"), Extras=("Extras", "sum"), Dom=("Dom", "sum"),
    Fer_h=("Fer_h", "sum"), Libres=("Fer_libre", "sum"),
    **{"$ Extras": ("$ Extras", "sum"), "$ Dominical": ("$ Dominical", "sum"), "$ Feriado": ("$ Feriado", "sum")})
emp["Sueldo base"] = emp["Colaborador"].map(P["Sueldo base"])
emp["Haberes"] = emp[["Sueldo base", "$ Extras", "$ Dominical", "$ Feriado"]].sum(axis=1)
emp["Descuentos"] = emp["Haberes"] * (d_prev + d_salud) / 100
emp["Líquido"] = emp["Haberes"] - emp["Descuentos"]

# ───────────────────────── KPIs ─────────────────────────
with kpi_box:
    c = st.columns(5)
    c[0].markdown(kpi("Sueldo base", clp(emp["Sueldo base"].sum()), f"{len(emp)} colaboradores"), unsafe_allow_html=True)
    c[1].markdown(kpi("Horas extras", clp(emp["$ Extras"].sum()), f'{emp["Extras"].sum():.1f} h sobre {JORNADA:g} semanales'), unsafe_allow_html=True)
    c[2].markdown(kpi("Recargo dominical", clp(emp["$ Dominical"].sum()), f'{emp["Dom"].sum():.1f} h · {rec_dom:.0%}'), unsafe_allow_html=True)
    c[3].markdown(kpi("Feriados", clp(emp["$ Feriado"].sum()), f'{emp["Libres"].sum():.0f} días libres compensatorios'), unsafe_allow_html=True)
    c[4].markdown(kpi("Líquido proyectado", clp(emp["Líquido"].sum()), "estimado tras descuentos", accent=True), unsafe_allow_html=True)
    st.write("")

# ───────────────────────── Resumen ─────────────────────────
with t_res:
    v = emp[["Colaborador", "Dias", "Base", "Extras", "Dom", "Fer_h", "Libres", "Haberes", "Líquido"]].copy()
    st.dataframe(v, hide_index=True, use_container_width=True, column_config={
        "Dias": "Días trab.", "Base": st.column_config.NumberColumn("Horas base", format="%.1f"),
        "Extras": st.column_config.NumberColumn("Horas extras", format="%.1f"),
        "Dom": st.column_config.NumberColumn("Horas dom.", format="%.1f"),
        "Fer_h": st.column_config.NumberColumn("Horas feriado", format="%.1f"),
        "Libres": "Días libres comp.",
        "Haberes": st.column_config.NumberColumn(format="$ %d"),
        "Líquido": st.column_config.NumberColumn("Líquido estimado", format="$ %d")})

# ───────────────────────── Semana a semana ─────────────────────────
with t_sem:
    semanas = sorted(sem["Sem_ini"].unique())
    for i, s0 in enumerate(semanas, 1):
        s1 = s0 + pd.Timedelta(days=6)
        w = sem[sem["Sem_ini"] == s0]
        titulo = (f"Semana {i} · {s0:%d/%m} al {s1:%d/%m} · {w['Base'].sum() + w['Extras'].sum():.1f} h "
                  f"· extras {w['Extras'].sum():.1f} h")
        with st.expander(titulo, expanded=(i == 1)):
            k = st.columns(5)
            k[0].markdown(kpi("Días trabajados", f"{w['Dias'].sum():.0f}"), unsafe_allow_html=True)
            k[1].markdown(kpi("Horas base", f"{w['Base'].sum():.1f}"), unsafe_allow_html=True)
            k[2].markdown(kpi("Horas extras", f"{w['Extras'].sum():.1f}", clp(w['$ Extras'].sum())), unsafe_allow_html=True)
            k[3].markdown(kpi("Horas dominicales", f"{w['Dom'].sum():.1f}", clp(w['$ Dominical'].sum())), unsafe_allow_html=True)
            k[4].markdown(kpi("Feriados", f"{w['Fer_h'].sum():.1f} h", clp(w['$ Feriado'].sum())), unsafe_allow_html=True)
            st.write("")
            st.dataframe(w[["Colaborador", "Dias", "Base", "Extras", "Dom", "Fer_h", "$ Extras", "$ Dominical", "$ Feriado"]],
                         hide_index=True, use_container_width=True, column_config={
                "Dias": "Días", "Base": st.column_config.NumberColumn("H. base", format="%.1f"),
                "Extras": st.column_config.NumberColumn("H. extras", format="%.1f"),
                "Dom": st.column_config.NumberColumn("H. dom.", format="%.1f"),
                "Fer_h": st.column_config.NumberColumn("H. feriado", format="%.1f"),
                "$ Extras": st.column_config.NumberColumn(format="$ %d"),
                "$ Dominical": st.column_config.NumberColumn(format="$ %d"),
                "$ Feriado": st.column_config.NumberColumn(format="$ %d")})
            if w["Extras"].sum() > 0:
                st.markdown('<span class="chip warn">Superó 42 h</span>', unsafe_allow_html=True)

# ───────────────────────── Auditoría ─────────────────────────
with t_aud:
    st.markdown("Compara el consolidado de esta app con el total haberes de la liquidación oficial.")
    aud = emp[["Colaborador", "Sueldo base", "$ Extras", "$ Dominical", "$ Feriado", "Haberes", "Descuentos", "Líquido"]].copy()
    prev_o = st.session_state.get("oficial", pd.DataFrame(columns=["Colaborador", "Haberes oficial"]))
    aud = aud.merge(prev_o, how="left", on="Colaborador")
    aud["Haberes oficial"] = aud["Haberes oficial"].fillna(0)
    money = st.column_config.NumberColumn(format="$ %d")
    aud = st.data_editor(aud, hide_index=True, use_container_width=True,
                         disabled=[c for c in aud.columns if c != "Haberes oficial"],
                         column_config={c: money for c in aud.columns if c != "Colaborador"})
    st.session_state["oficial"] = aud[["Colaborador", "Haberes oficial"]]
    aud["Diferencia"] = np.where(aud["Haberes oficial"] > 0, aud["Haberes"] - aud["Haberes oficial"], np.nan)
    tot = aud[["Sueldo base", "$ Extras", "$ Dominical", "$ Feriado", "Haberes", "Descuentos", "Líquido"]].sum()
    st.markdown('<div class="card"><b>Consolidado por categoría</b></div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame({"Categoría": tot.index, "Monto": tot.values}).assign(Monto=lambda d: d["Monto"].map(clp)),
                 hide_index=True, use_container_width=True)
    chk = aud.dropna(subset=["Diferencia"])
    if len(chk):
        st.dataframe(chk[["Colaborador", "Haberes", "Haberes oficial", "Diferencia"]], hide_index=True,
                     use_container_width=True, column_config={c: money for c in ["Haberes", "Haberes oficial", "Diferencia"]})
    st.caption("No incluye gratificación, tope imponible, impuesto único ni otros haberes o descuentos de la liquidación.")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        aud.to_excel(xw, "Auditoría", index=False)
        sem.drop(columns=["VH"]).to_excel(xw, "Semanas", index=False)
        fer_df.to_excel(xw, "Feriados", index=False)
    st.download_button("Descargar auditoría (Excel)", buf.getvalue(), f"auditoria_{periodo}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ───────────────────────── Detalle diario ─────────────────────────
with t_dia:
    dsel = st.multiselect("Día", sorted(m["Fecha"].dt.date.unique()), format_func=lambda d: f"{DIAS[d.weekday()]} {d:%d/%m}")
    dd = m[m["Fecha"].dt.date.isin(dsel)] if dsel else m
    dd = dd.assign(Día=dd["Fecha"].dt.weekday.map(lambda i: DIAS[i]),
                   Tipo=np.select([dd["Feriado"], dd["Domingo"]], ["Feriado", "Domingo"], "Ordinario"))
    st.dataframe(dd[["Fecha", "Día", "Colaborador", "Sucursal", "Área", "ent", "sal", "Horas", "Tipo"]]
                 .sort_values(["Fecha", "Colaborador"]), hide_index=True, use_container_width=True,
                 column_config={"Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                "ent": st.column_config.DatetimeColumn("Entrada", format="HH:mm"),
                                "sal": st.column_config.DatetimeColumn("Salida", format="HH:mm")})
