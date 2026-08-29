# -*- coding: utf-8 -*-
"""
PDF-rapport for samlet turnering.

Side 1: sluttstilling og klubbvis sammendrag.
Deretter: spillene med kortfordeling og alle resultater.
"""

import datetime as dt
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

MORK = colors.HexColor("#1c2b3a")
LYS = colors.HexColor("#eef2f6")
STREK = colors.HexColor("#b8c4d0")
GRA = colors.HexColor("#5b6b7b")


def nk(x, d=2):
    return (("%." + str(d) + "f") % x).replace(".", ",")


def _stiler():
    s = getSampleStyleSheet()
    return {
        "tittel": ParagraphStyle("tittel", parent=s["Title"], fontName="Helvetica-Bold",
                                 fontSize=16, leading=19, textColor=MORK, spaceAfter=2),
        "undertittel": ParagraphStyle("undertittel", parent=s["Normal"], fontSize=9,
                                      leading=12, textColor=GRA, alignment=TA_CENTER,
                                      spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=s["Normal"], fontName="Helvetica-Bold",
                             fontSize=10.5, leading=13, textColor=MORK,
                             spaceBefore=10, spaceAfter=4),
        "brod": ParagraphStyle("brod", parent=s["Normal"], fontSize=7.6, leading=10,
                               textColor=GRA),
        "spill": ParagraphStyle("spill", parent=s["Normal"], fontName="Helvetica-Bold",
                                fontSize=9.5, leading=11, textColor=MORK, spaceAfter=2),
        "kort": ParagraphStyle("kort", parent=s["Normal"], fontName="Courier",
                               fontSize=6.8, leading=7.7, textColor=MORK),
    }


def _topptekst(navn):
    def tegn(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRA)
        canvas.drawString(15 * mm, A4[1] - 10 * mm, navn[:95])
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, "Side %d" % doc.page)
        canvas.setStrokeColor(STREK)
        canvas.setLineWidth(0.4)
        canvas.line(15 * mm, A4[1] - 12 * mm, A4[0] - 15 * mm, A4[1] - 12 * mm)
        canvas.restoreState()
    return tegn


def _stilling(res, st):
    rader = [["Pl.", "Par", "Navn", "Klubb", "Samlet %", "Spilt", "Fri",
              "Egen klubb\nu/hcp", "Publisert %"]]
    for r in res["rader"]:
        rader.append([
            str(r["Plass"]), r["Par"], r["Navn"], r["Klubb"],
            nk(r["Samlet %"]), str(r["Spilt"]), str(r["Fri"]),
            nk(r["Egen klubb u/hcp"]) if r["Egen klubb u/hcp"] is not None else "",
            nk(r["Publisert %"]) if r["Publisert %"] else "",
        ])
    t = Table(rader, repeatRows=1,
              colWidths=[10 * mm, 15 * mm, 58 * mm, 27 * mm, 17 * mm, 11 * mm,
                         9 * mm, 18 * mm, 18 * mm])
    stil = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 7.6),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), MORK),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, STREK),
    ]
    for i in range(1, len(rader)):
        if i % 2 == 0:
            stil.append(("BACKGROUND", (0, i), (-1, i), LYS))
    stil.append(("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 7.6))
    t.setStyle(TableStyle(stil))
    return t


def _klubbtabell(res):
    rader = [["Klubb", "Par", "N-S snitt", "Ø-V snitt", "Beste", "Svakeste"]]
    for k in res["klubbtall"]:
        rader.append([k["klubb"], str(k["antall"]), nk(k["ns"]), nk(k["ov"]),
                      nk(k["beste"]), nk(k["svakeste"])])
    t = Table(rader, colWidths=[55 * mm, 15 * mm, 22 * mm, 22 * mm, 20 * mm, 22 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 7.6),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), MORK),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, STREK),
    ]))
    return t


def _spillblokk(d, st):
    """Ett spill: kortfordeling til venstre, resultater til hoyre."""
    diagram = "<br/>".join(
        (l or " ").replace("&", "&amp;").replace("<", "&lt;").replace(" ", "&nbsp;")
        for l in d["diagram"])
    venstre = Paragraph(diagram, st["kort"])

    rader = [["N-S", "Ø-V", "Kontrakt", "Utsp.", "Poeng", "% N-S", "% Ø-V"]]
    for r in d["resultater"]:
        rader.append([r["ns"], r["ov"],
                      r["kontrakt"] + (" (%s)" % r["gruppe"] if r["gruppe"] else ""),
                      r["utspill"] or "-", str(r["poeng"]),
                      nk(r["pst_ns"], 1), nk(r["pst_ov"], 1)])
    for f in d["frirunder"]:
        rader.append([f["par"], "-", "Frirunde", "-", "-", nk(f["pst"], 1), "-"])

    hoyre = Table(rader, repeatRows=1,
                  colWidths=[15 * mm, 15 * mm, 22 * mm, 12 * mm, 15 * mm,
                             13 * mm, 13 * mm])
    stil = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 6.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 7.0),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), MORK),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, STREK),
    ]
    for i in range(1, len(rader)):
        if i % 2 == 0:
            stil.append(("BACKGROUND", (0, i), (-1, i), LYS))
    for i, r in enumerate(rader[1:], 1):
        if r[2] == "Frirunde":
            stil.append(("TEXTCOLOR", (0, i), (-1, i), GRA))
    hoyre.setStyle(TableStyle(stil))

    ytre = Table([[venstre, hoyre]], colWidths=[73 * mm, 107 * mm])
    ytre.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (0, 0), 0),
                              ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    return KeepTogether([Paragraph("Spill %d" % d["nr"], st["spill"]), ytre,
                         Spacer(1, 3 * mm)])


def lag_pdf(res, sti=None):
    """Bygger PDF-en. Returnerer bytes, og skriver til fil hvis sti er gitt."""
    st = _stiler()
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4,
                          leftMargin=15 * mm, rightMargin=15 * mm,
                          topMargin=16 * mm, bottomMargin=14 * mm,
                          title=res["navn"], author="Samlet turnering")
    ramme = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="ramme")
    doc.addPageTemplates([PageTemplate(id="std", frames=[ramme],
                                       onPage=_topptekst(res["navn"]))])

    kilder = "   ".join("%s = %s (%d par)" % (k["kode"], k["klubb"], k["antall_par"])
                        for k in res["kilder"])
    h = [Paragraph(res["navn"], st["tittel"]),
         Paragraph("%s  ·  %d spill  ·  %d par  ·  scoret uten handikap  ·  laget %s"
                   % (kilder, res["antall_spill"], len(res["rader"]),
                      dt.date.today().strftime("%d.%m.%Y")), st["undertittel"]),
         _stilling(res, st),
         Paragraph("Klubbvis", st["h2"]),
         _klubbtabell(res),
         Paragraph(
             "N-S snitt viser hvordan klubbens nord-syd-par gjorde det mot hele det "
             "samlede feltet. Siden begge par ved et bord kommer fra samme klubb, blir "
             "Ø-V snitt alltid 100 minus N-S snitt for samme klubb - klubbene må derfor "
             "sammenlignes retning mot retning.", st["brod"]),
         Paragraph("Slik er det regnet", st["h2"]),
         Paragraph(
             "For hvert spill sammenlignes alle resultatene fra alle klubbene mot "
             "hverandre: 2 poeng for hvert par du slår, 1 for hvert du deler med. "
             "Prosent for spillet er oppnådde poeng delt på maks mulige. Totalen er "
             "gjennomsnittet av spillene, og frirunde gir paret sin egen innspilte "
             "prosent. Handikap er ikke brukt; kolonnen «Publisert %» er tallet fra "
             "klubbens egen resultatfil og er ikke sammenlignbart på tvers der "
             "handikap benyttes.", st["brod"])]

    if res["merknader"]:
        h.append(Paragraph("Merknader", st["h2"]))
        for m in res["merknader"][:12]:
            h.append(Paragraph("• " + m, st["brod"]))

    h.append(PageBreak())
    h.append(Paragraph("Spillene", st["h2"]))
    h.append(Spacer(1, 2 * mm))
    for nr in sorted(res["spill"]):
        h.append(_spillblokk(res["spill"][nr], st))

    doc.build(h)
    data = buf.getvalue()
    if sti:
        with open(sti, "wb") as f:
            f.write(data)
    return data
