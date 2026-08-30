# -*- coding: utf-8 -*-
"""
Streamlit-app for samlet turnering.

Kjor lokalt:      streamlit run app.py
Deploy:           legg app.py, samlet_turnering.py og requirements.txt i et
                  GitHub-repo og pek Streamlit Community Cloud pa app.py.
"""

import datetime as dt
import io
import zipfile

import pandas as pd
import streamlit as st

import samlet_turnering as st_kjerne

st.set_page_config(page_title="Samlet turnering", page_icon="♠", layout="wide")

st.title("♠ Samlet turnering")
st.caption(
    "Slar sammen resultatfiler fra flere klubber som har spilt de samme spillene. "
    "Alt scores pa nytt fra poengene ved bordet, uten handikap."
)

with st.sidebar:
    st.header("Innstillinger")
    navn = st.text_input(
        "Navn pa turneringen",
        value="Samlet turnering %s" % dt.date.today().strftime("%d.%m.%Y"),
    )
    vridd = st.radio(
        "Vridde spill (>a / >b)",
        options=["klubbvis", "utelat"],
        format_func=lambda v: {
            "klubbvis": "Score gruppevis innenfor hver klubb",
            "utelat": "Hold spillet utenfor for alle",
        }[v],
        help="Et vridd spill kan ikke sammenlignes pa tvers av klubbene.",
    )
    st.divider()
    st.markdown(
        "**Slik gjor du det hver klubbkveld**\n\n"
        "1. Hent tekstfila fra Ruter i hver klubb\n"
        "2. Last opp begge her\n"
        "3. Last ned resultatfilene og send dem rundt"
    )

opplastet = st.file_uploader(
    "Resultatfiler fra Ruter (tekstfil)",
    type=["txt"],
    accept_multiple_files=True,
    help="En fil per klubb. Filene ma vaere fra samme spillsett.",
)

if not opplastet:
    st.info("Last opp minst to tekstfiler for a komme i gang.")
    st.stop()

st.subheader("Klubbkoder")
st.caption("Kortkoden settes foran parnummeret, slik at par 5 i to klubber ikke blandes.")
kilder_inn, brukt = [], set()
kolonner = st.columns(min(len(opplastet), 4))
for i, fil in enumerate(opplastet):
    tekst = st_kjerne.les_bytes(fil.getvalue())
    forslag = st_kjerne.kode_fra_filnavn(fil.name, brukt)
    brukt.add(forslag)
    with kolonner[i % len(kolonner)]:
        kode = st.text_input(fil.name, value=forslag, key="kode_%d" % i, max_chars=6)
    kilder_inn.append({"tekst": tekst, "filnavn": fil.name, "kode": kode.strip() or forslag})

if len({k["kode"] for k in kilder_inn}) < len(kilder_inn):
    st.error("To klubber har fatt samme kode. Gi dem hver sin.")
    st.stop()

try:
    res = st_kjerne.kjor(kilder_inn, navn, vridd)
except Exception as feil:  # noqa: BLE001 - vises til brukeren
    st.error("Klarte ikke a lese filene: %s" % feil)
    st.stop()

kort_avvik = [m for m in res["merknader"] if "kortfordelingen" in m]
if kort_avvik:
    st.error(
        "Klubbene ser ikke ut til a ha spilt samme spill (%d avvik). "
        "Kontroller at filene er fra samme spillsett." % len(kort_avvik)
    )
    with st.expander("Vis avvik"):
        for m in kort_avvik[:30]:
            st.write("* " + m)
else:
    st.success("Kortfordelingen er identisk i alle filene - spillene er sammenlignbare.")

m1, m2, m3 = st.columns(3)
m1.metric("Spill", res["antall_spill"])
m2.metric("Par", len(res["rader"]))
m3.metric("Klubber", len(res["kilder"]))

st.subheader("Sluttstilling")
tabell = pd.DataFrame(res["rader"])
st.caption(
    "Poeng er matchpoeng pa samme skala som Ruter viser: +1 for hvert par du slar, "
    "-1 for hvert du taper mot, 0 for likt. Toppen pa et spill er antall bord minus "
    "1. Prosenten er 50 + poeng / topp * 50, sa regnestykket kan kontrolleres."
)
st.dataframe(tabell, use_container_width=True, hide_index=True)

st.subheader("Klubbvis")
st.dataframe(
    pd.DataFrame(
        [
            {
                "Klubb": k["klubb"],
                "Par": k["antall"],
                "N-S snitt %": round(k["ns"], 2),
                "Ø-V snitt %": round(k["ov"], 2),
                "Beste %": round(k["beste"], 2),
                "Svakeste %": round(k["svakeste"], 2),
            }
            for k in res["klubbtall"]
        ]
    ),
    hide_index=True,
)
st.caption(
    "Begge par ved et bord kommer fra samme klubb, sa Ø-V snitt blir alltid 100 minus "
    "N-S snitt for samme klubb. Klubbene ma derfor sammenlignes retning mot retning."
)

andre = [m for m in res["merknader"] if "kortfordelingen" not in m]
if andre:
    with st.expander("Merknader (%d)" % len(andre)):
        for m in andre:
            st.write("* " + m)

st.subheader("Utskrift")
try:
    import rapport_pdf
    pdf_data = rapport_pdf.lag_pdf(res)
except ImportError:
    pdf_data = None
    st.warning(
        "PDF-en krever pakken **reportlab**, som ikke er installert her.\n\n"
        "* Lokalt: kjor `pip install -r requirements.txt` og start appen pa nytt.\n"
        "* Streamlit Cloud: se etter linja `reportlab>=4.0` i `requirements.txt` "
        "i GitHub-repoet, og velg deretter *Manage app -> Reboot app*.\n\n"
        "Tekstfilene og CSV-en under virker som normalt."
    )
except Exception as feil:  # noqa: BLE001
    pdf_data = None
    st.warning("Klarte ikke a lage PDF: %s" % feil)

if pdf_data:
    st.caption(
        "Sluttstilling pa side 1, deretter spillene med kortfordeling og alle "
        "resultater. Bla gjennom her, eller last ned og skriv ut."
    )
    try:
        st.pdf(pdf_data, height=800)
    except Exception:  # noqa: BLE001 - visningen er en bonus, ikke et krav
        st.info(
            "PDF-visning i nettleseren krever tillegget **streamlit-pdf**. "
            "Legg linja `streamlit[pdf]>=1.50` i `requirements.txt` og velg "
            "*Manage app -> Reboot app*, eller kjor `pip install \"streamlit[pdf]\"` "
            "lokalt. Selve PDF-en er ferdig og kan lastes ned nedenfor."
        )

with st.expander("Resultatfil som tekst"):
    st.code(res["rapport"], language=None)
with st.expander("Spillfordeling"):
    st.code(res["spillfordeling"], language=None)

st.subheader("Last ned")

filer = {
    "Samlet_resultat.txt": res["rapport"],
    "Samlet_spillfordeling.txt": res["spillfordeling"],
    "Samlet_resultat.csv": res["csv"],
}
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for filnavn, innhold in filer.items():
        z.writestr(filnavn, innhold + "\n")
    if pdf_data:
        z.writestr("Samlet_turnering.pdf", pdf_data)

if pdf_data:
    st.download_button(
        "📄 Samlet_turnering.pdf  -  resultat forst, deretter spillene",
        pdf_data, file_name="Samlet_turnering.pdf", mime="application/pdf",
        type="primary", use_container_width=True,
    )

d1, d2, d3, d4 = st.columns(4)
for kol, (filnavn, innhold) in zip((d1, d2, d3), filer.items()):
    kol.download_button(
        filnavn, innhold.encode("utf-8"), file_name=filnavn, mime="text/plain",
        use_container_width=True,
    )
d4.download_button(
    "Alle som ZIP", buf.getvalue(),
    file_name="samlet_turnering_%s.zip" % dt.date.today().isoformat(),
    mime="application/zip", use_container_width=True,
)
