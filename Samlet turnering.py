#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
samlet_turnering.py
===================

Slår sammen resultatfiler (tekstfil fra Ruter/NBF) fra to eller flere klubber
som har spilt de SAMME spillene, og regner ut en felles turnering.

Prinsipp
--------
* All scoring gjøres pa nytt fra RAADATA (kontrakt/resultat -> poeng for N-S).
* Handikap brukes IKKE. Ingen justering av noe slag - kun oppnadde poeng.
* For hvert spill sammenlignes alle resultater fra alle klubber mot hverandre
  (vanlig parturnering / matchpoint):
      MP = 2 poeng for hvert par du slar, 1 poeng for hvert par du deler med
      maks = 2 * (antall resultater - 1)
      prosent for spillet = MP / maks * 100
* Frirunde (sitteover mot blindpar) gir paret sin egen innspilte prosent pa
  det spillet, slik Ruter gjor det. Totalprosenten blir den samme som om
  spillet ble holdt utenfor, men paret star med alle spillene i turneringen.
* "Vridde" spill (markert >a / >b i Ruter, altsa spill som er delt i grupper)
  kan ikke sammenlignes pa tvers av klubber. Standard er a score dem innenfor
  hver gruppe for seg (--vridd klubbvis), alternativt utelate dem (--vridd utelat).

Bruk
----
    python3 samlet_turnering.py fil1.txt fil2.txt [flere.txt ...] \
        [--ut MAPPE] [--navn "Sommer 11 samlet"] [--vridd klubbvis|utelat]

Programmet lager:
    Samlet_turnering.pdf       - ferdig rapport: sluttstilling forst, sa spillene
    Samlet_resultat.txt        - sluttstilling for den samlede turneringen
    Samlet_spillfordeling.txt  - alle resultater spill for spill med prosent
    Samlet_resultat.csv        - samme sluttstilling som CSV (semikolon)
"""

import argparse
import os
import re
import sys
from collections import defaultdict

# ----------------------------------------------------------------------------
# Datastrukturer
# ----------------------------------------------------------------------------


class Par:
    def __init__(self, kode, nr, navn, klubb):
        self.kode = kode          # klubbkode, f.eks. "HBK"
        self.nr = nr              # parnummer i egen klubb
        self.navn = navn
        self.klubb = klubb
        self.egen_plass = None    # plassering i egen klubb
        self.egen_pst = None      # prosent i egen klubb (med ev. handikap)
        self.spill = {}           # spillnr -> prosent i samlet turnering
        self.frirunde = set()     # spillnr der paret satt over
        self.spilt = 0            # spill paret faktisk satt og spilte
        self.klubb_pst = None     # prosent mot egen klubb, uten handikap
        self.klubb_plass = None

    @property
    def id(self):
        return "%s-%s" % (self.kode, self.nr)

    @property
    def antall_spill(self):
        return len(self.spill)

    @property
    def prosent(self):
        if not self.spill:
            return 0.0
        return sum(self.spill.values()) / len(self.spill)


class Resultat:
    """Ett spilt resultat: ett spill, ett N-S-par mot ett Ø-V-par."""

    def __init__(self, spill, ns, ov, kontrakt, spillefoerer, utgang,
                 utspill, poeng, gruppe, kode):
        self.spill = spill
        self.ns = ns              # Par-objekt
        self.ov = ov              # Par-objekt
        self.kontrakt = kontrakt
        self.spillefoerer = spillefoerer
        self.utgang = utgang      # "=", "+1", "-2" ...
        self.utspill = utspill
        self.poeng = poeng        # poeng sett fra N-S (fortegn)
        self.gruppe = gruppe      # None, eller "a"/"b" for vridd spill
        self.kode = kode          # klubbkode

    @property
    def kontrakt_tekst(self):
        t = "%s %s %s" % (self.kontrakt, self.spillefoerer, self.utgang)
        return t.strip()


# ----------------------------------------------------------------------------
# Innlesing av Ruter-tekstfil
# ----------------------------------------------------------------------------

RESULTATLINJE = re.compile(
    r"^\s*(?P<ns>\d+|--)\s+(?P<ov>\d+|--)\s+(?P<rest>.*\S)\s*$"
)

SPILT = re.compile(
    r"^(?P<kontrakt>\d\s?[KRHSNkrhsn]x{0,2}|[Pp]ass\w*)\s+"
    r"(?P<sf>[NSØVEWnsøvew])\s+"
    r"(?P<utgang>=|[+-]\d+)\s+"
    r"(?P<hale>.*)$"
)

TALL = re.compile(r"^-?\d+$")


def les_bytes(data):
    """Ruter skriver bade UTF-8 og Windows-koding. Prov i tur og orden."""
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", "replace")


def les_fil(sti, kode=None):
    """Leser en Ruter-tekstfil fra disk."""
    with open(sti, "rb") as f:
        return les_tekst(les_bytes(f.read()), kode, os.path.basename(sti))


def les_tekst(tekst, kode=None, filnavn="(ukjent)"):
    """Leser innholdet i en Ruter-tekstfil.

    Returnerer (klubbnavn, tittel, par, resultater, kortfordeling).
    """
    tekst = tekst.replace("\r", "")
    linjer = tekst.split("\n")

    tittel = linjer[0].strip() if linjer else filnavn

    par = {}
    resultater = []
    kortfordeling = {}
    diagrammer = {}

    # --- 1) Startlisten / sluttstillingen i egen klubb ------------------------
    hdr_i = None
    for i, l in enumerate(linjer):
        if re.match(r"^\s*Plass\s+Par\s+Poeng", l):
            hdr_i = i
            break
    if hdr_i is None:
        raise ValueError("Fant ikke resultattabellen i %s" % filnavn)

    hdr = linjer[hdr_i]
    kol_navn = hdr.index("Navn")
    kol_klubb = hdr.index("Klubb")
    # kolonnen rett etter Navn (Hcp% eller MNR)
    etter = [m.start() for m in re.finditer(r"\S+", hdr) if m.start() > kol_navn]
    kol_slutt_navn = etter[0] if etter else kol_klubb

    klubber = defaultdict(int)
    for l in linjer[hdr_i + 1:]:
        if l.startswith("-----"):
            break
        m = re.match(r"^\s*(\d+)\s+(\d+)\s+(-?\d+,\d+)\s+\*?\s*(-?\d+,\d+)\s", l)
        if not m:
            continue
        plass, parnr = int(m.group(1)), m.group(2)
        pst = float(m.group(4).replace(",", "."))
        navn = re.sub(r"\s+[\d.,\- ]+$", "", l[kol_navn:kol_slutt_navn]).strip()
        klubb = l[kol_klubb:].strip()
        # "Vikersund BK - Konnerud BK" -> hjemmeklubben er den siste
        hovedklubb = klubb.split(" - ")[-1].strip()
        klubber[hovedklubb] += 1
        par[parnr] = Par(kode or "?", parnr, navn, klubb)
        par[parnr].egen_plass = plass
        par[parnr].egen_pst = pst

    klubbnavn = max(klubber, key=klubber.get) if klubber else tittel

    # --- 2) Spill-seksjoner ---------------------------------------------------
    seksjoner = []
    start = None
    for i, l in enumerate(linjer):
        if l.startswith("-----"):
            if start is not None:
                seksjoner.append(linjer[start:i])
            start = i + 1
    if start is not None:
        seksjoner.append(linjer[start:])

    spillteller = 0
    for seksjon in seksjoner:
        # finn tabelloverskriften og kolonnedelingen
        hdr_idx = None
        for j, l in enumerate(seksjon):
            if "Par" in l and "Kontr" in l:
                hdr_idx = j
                break
        if hdr_idx is None:
            continue
        pos = [m.start() for m in re.finditer(r"Par\b", seksjon[hdr_idx])]
        delekol = pos[1] - 1 if len(pos) > 1 else len(seksjon[hdr_idx])

        # spillnumre: forste ikke-tomme linje i seksjonen
        forste = next((l for l in seksjon if l.strip()), "")
        v_nr = re.match(r"^\s*(\d{1,2})\s", forste)
        h_nr = re.match(r"^\s*(\d{1,2})\s", forste[delekol:])
        venstre = int(v_nr.group(1)) if v_nr else spillteller + 1
        hoyre = int(h_nr.group(1)) if h_nr else venstre + 1

        # kortfordeling (til kontroll av at klubbene har spilt samme spill)
        diagram = seksjon[:min(hdr_idx, 12)]
        kortfordeling[venstre] = _kort(diagram, 0, delekol)
        kortfordeling[hoyre] = _kort(diagram, delekol, None)
        diagrammer[venstre] = [l[:delekol].rstrip() for l in diagram]
        diagrammer[hoyre] = [l[delekol:].rstrip() for l in diagram]

        for l in seksjon[hdr_idx + 1:]:
            if not l.strip():
                continue
            for spillnr, bit in ((venstre, l[:delekol]), (hoyre, l[delekol:])):
                fri = _les_frirunde(bit, par)
                if fri:
                    fri.frirunde.add(spillnr)
                    continue
                r = _les_resultatlinje(bit, spillnr, par, kode)
                if r:
                    resultater.append(r)
        spillteller = hoyre

    return klubbnavn, tittel, par, resultater, kortfordeling, diagrammer


def _kort(diagram, fra, til):
    """Plukker ut kortene i et handdiagram som en sammenlignbar streng."""
    ut = []
    for i, l in enumerate(diagram):
        bit = l[fra:til] if til else l[fra:]
        toks = bit.split()
        if i < 3 and toks:
            toks = toks[1:]          # spillnr / giver / sone
        for tok in toks:
            if re.fullmatch(r"[AKQJ0-9]+|---", tok):
                ut.append(tok)
    return "|".join(ut)


FRIRUNDE = re.compile(r"^\s*(\d+|--)\s+(\d+|--)\s+Frirunde\b", re.IGNORECASE)


def _les_frirunde(bit, par):
    """Finner paret som satt over pa dette spillet."""
    m = FRIRUNDE.match(bit)
    if not m:
        return None
    for tok in (m.group(1), m.group(2)):
        if tok != "--" and tok in par:
            return par[tok]
    return None


def _les_resultatlinje(bit, spillnr, par, kode):
    m = RESULTATLINJE.match(bit)
    if not m:
        return None
    ns, ov, rest = m.group("ns"), m.group("ov"), m.group("rest")
    if "Frirunde" in rest or "frirunde" in rest:
        return None
    if ns == "--" or ov == "--":
        return None
    if ns not in par or ov not in par:
        return None

    sm = SPILT.match(rest)
    if not sm:
        return None

    hale = sm.group("hale").split()
    # to siste er matchpoint fra opprinnelig turnering - dropp dem
    if len(hale) >= 2 and all("," in t or TALL.match(t) for t in hale[-2:]):
        hale = hale[:-2]
    if not hale:
        return None

    poengtok = hale[-1]
    utspill = " ".join(hale[:-1]).strip() or ""
    gruppe = None
    gm = re.match(r"^(-?\d+)>([a-z])$", poengtok)
    if gm:
        poeng, gruppe = int(gm.group(1)), gm.group(2)
    elif TALL.match(poengtok):
        poeng = int(poengtok)
    else:
        return None

    return Resultat(spillnr, par[ns], par[ov], sm.group("kontrakt").replace(" ", ""),
                    sm.group("sf").upper(), sm.group("utgang"), utspill,
                    poeng, gruppe, kode)


# ----------------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------------


def score(resultater, vridd="klubbvis"):
    """Regner matchpoint-prosent per spill. Returnerer liste av (Resultat, pst_ns)."""
    pr_spill = defaultdict(list)
    for r in resultater:
        pr_spill[r.spill].append(r)

    ut = []
    merknader = []
    for spillnr in sorted(pr_spill):
        alle = pr_spill[spillnr]
        vridde = [r for r in alle if r.gruppe]
        if not vridde:
            grupper = {None: alle}
        else:
            klubb = {r.kode for r in vridde}
            if vridd == "utelat":
                merknader.append(
                    "Spill %d: vridd spill i %s - spillet er utelatt for alle."
                    % (spillnr, ", ".join(sorted(klubb))))
                continue
            merknader.append(
                "Spill %d: vridd spill i %s - scoret gruppevis innenfor hver klubb, "
                "ikke pa tvers." % (spillnr, ", ".join(sorted(klubb))))
            grupper = defaultdict(list)
            for r in alle:
                grupper[(r.kode, r.gruppe)].append(r)

        for gr in grupper.values():
            n = len(gr)
            if n < 2:
                continue
            maks = 2.0 * (n - 1)
            for r in gr:
                mp = 0.0
                for a in gr:
                    if a is r:
                        continue
                    if r.poeng > a.poeng:
                        mp += 2
                    elif r.poeng == a.poeng:
                        mp += 1
                ut.append((r, mp / maks * 100.0))
    return ut, merknader


# ----------------------------------------------------------------------------
# Rapportering
# ----------------------------------------------------------------------------


def n2(x, d=2):
    return ("%." + str(d) + "f") % x if x is not None else ""


def nk(x, d=2):
    """Norsk desimaltegn."""
    return n2(x, d).replace(".", ",")


def fordel(par, scoret, med_frirunde=True):
    """Legger prosent per spill inn pa parene. Returnerer rangert liste.

    Frirunde gir paret sin egen innspilte prosent pa det spillet, slik Ruter
    gjor det. Totalprosenten blir den samme, men paret star med alle spillene.
    """
    for p in par.values():
        p.spill = {}
    for r, pst in scoret:
        r.ns.spill[r.spill] = pst
        r.ov.spill[r.spill] = 100.0 - pst

    spilte = sorted({r.spill for r, _ in scoret})
    for p in par.values():
        p.spilt = len(p.spill)
        if not p.spilt:
            continue
        if med_frirunde:
            innspilt = sum(p.spill.values()) / p.spilt
            for spillnr in p.frirunde:
                if spillnr in spilte and spillnr not in p.spill:
                    p.spill[spillnr] = innspilt
    return sorted([p for p in par.values() if p.spilt], key=lambda p: -p.prosent)


def plasser(rangert):
    ut, forrige, plass = {}, None, 0
    for i, p in enumerate(rangert, 1):
        pst = round(p.prosent, 2)
        if pst != forrige:
            plass, forrige = i, pst
        ut[p.id] = plass
    return ut


def lag_rapport(navn, alle_par, scoret, merknader, kilder, klubbtall, vridd):
    rangert = fordel(alle_par, scoret)
    plassering = plasser(rangert)
    spillsett = sorted({r.spill for r, _ in scoret})

    L = [navn, "=" * len(navn), ""]
    L.append("Samlet turnering satt sammen av %d resultatfiler." % len(kilder))
    L.append("Alle resultater er scoret pa nytt fra oppnadde poeng ved bordet.")
    L.append("HANDIKAP ER IKKE BRUKT - alle par males mot samme skala.")
    L.append("")
    for k in kilder:
        L.append("   %-5s %-22s %3d par   %3d resultater   %s"
                 % (k["kode"], k["klubb"], k["antall_par"], k["antall_res"],
                    os.path.basename(k["fil"])))
    L.append("")
    L.append("   Spill: %d      Par: %d      Resultater: %d      Snitt: %s %%"
             % (len(spillsett), len(rangert), len(scoret),
                nk(sum(p.prosent * p.antall_spill for p in rangert)
                   / sum(p.antall_spill for p in rangert))))
    L.append("")

    L.append("=" * 112)
    L.append("%-5s %-7s %-42s %8s %6s %4s  %-14s %8s"
             % ("Pl.", "Par", "Navn", "Samlet %", "Spilt", "Fri", "Egen klubb", "Publ. %"))
    L.append("%-5s %-7s %-42s %8s %6s %4s  %-14s %8s"
             % ("", "", "", "", "", "", "u/hcp", "i egen fil"))
    L.append("=" * 112)
    for i, p in enumerate(rangert, 1):
        egen = "%d. / %s" % (p.klubb_plass, nk(p.klubb_pst)) if p.klubb_plass else ""
        L.append("%-5d %-7s %-42s %8s %6d %4d  %-14s %8s"
                 % (plassering[p.id], p.id, p.navn[:42], nk(p.prosent),
                    p.spilt, p.antall_spill - p.spilt, egen,
                    nk(p.egen_pst) if p.egen_pst else ""))
        if i % 5 == 0:
            L.append("")
    L.append("=" * 112)
    L.append("")

    L.append("Klubbvis sammendrag")
    L.append("-" * 76)
    L.append("%-24s %5s %10s %10s %9s %9s"
             % ("Klubb", "Par", "N-S snitt", "Ø-V snitt", "Beste", "Svakeste"))
    for k in klubbtall:
        L.append("%-24s %5d %10s %10s %9s %9s"
                 % (k["klubb"], k["antall"], nk(k["ns"]), nk(k["ov"]),
                    nk(k["beste"]), nk(k["svakeste"])))
    L.append("")
    L.append("N-S snitt = hvordan klubbens nord-syd-par gjorde det malt mot HELE det")
    L.append("samlede feltet. Siden begge par ved et bord kommer fra samme klubb, blir")
    L.append("Ø-V snitt automatisk 100 minus N-S snitt for samme klubb. Sammenligningen")
    L.append("mellom klubbene ma derfor gjores retning mot retning: HBK N-S mot KB N-S.")
    L.append("Et samlet 'hvem er best'-tall lar seg ikke regne ut nar ingen av bordene")
    L.append("har par fra begge klubber - det er selve turneringstabellen over som viser")
    L.append("hvordan hvert enkelt par star mot alle de andre.")
    L.append("")
    L.append("Slik er det regnet")
    L.append("-" * 60)
    L.append("* For hvert spill sammenlignes alle resultatene fra alle klubbene mot")
    L.append("  hverandre: 2 poeng for hvert par du slar, 1 for hvert du deler med.")
    L.append("  Prosent for spillet = oppnadde poeng / maks mulige poeng.")
    L.append("* Alle spill er spilt i begge klubbene og sammenlignet pa tvers.")
    L.append("* Kolonnen 'Spilt' er spill paret satt og spilte, 'Fri' er frirunde mot")
    L.append("  blindparet. Frirunde gir paret sin egen innspilte prosent pa det")
    L.append("  spillet, slik Ruter gjor det, sa alle par star med alle 24 spillene.")
    L.append("  Totalprosenten blir den samme som om frirunden ble holdt utenfor.")
    L.append("* Kolonnen 'Egen klubb u/hcp' er samme regnestykke, men bare mot egne")
    L.append("  klubbkamerater - altsa turneringen slik den var, uten handikap.")
    L.append("* Kolonnen 'Publ. %' er tallet som sto i klubbens egen resultatfil.")
    L.append("  Der klubben bruker handikap er dette IKKE sammenlignbart pa tvers.")
    L.append("* Vridde spill (>a/>b): valgt handtering = %s." % vridd)
    if merknader:
        L.append("")
        L.append("Merknader")
        L.append("-" * 60)
        for m in merknader:
            L.append("* " + m)
    return "\n".join(L), rangert


def lag_spillfordeling(navn, scoret, alle_par):
    pr_spill = defaultdict(list)
    for r, pst in scoret:
        pr_spill[r.spill].append((r, pst))

    L = [navn + " - spillfordeling", "=" * (len(navn) + 18), "",
         "Alle resultater spill for spill, sortert etter poeng for N-S.", ""]
    for spillnr in sorted(pr_spill):
        rader = sorted(pr_spill[spillnr], key=lambda x: -x[0].poeng)
        L.append("Spill %-3d  (%d resultater)" % (spillnr, len(rader)))
        L.append("   %-8s %-8s %-9s %-6s %8s %7s %7s %s"
                 % ("N-S", "Ø-V", "Kontrakt", "Utsp.", "Poeng", "% N-S", "% Ø-V", "Gr."))
        for r, pst in rader:
            L.append("   %-8s %-8s %-9s %-6s %8d %7s %7s %s"
                     % (r.ns.id, r.ov.id, r.kontrakt_tekst, r.utspill or "-",
                        r.poeng, nk(pst, 1), nk(100.0 - pst, 1), r.gruppe or ""))
        for pp in sorted(alle_par.values(), key=lambda x: x.id):
            if spillnr in pp.frirunde and spillnr in pp.spill:
                L.append("   %-8s %-8s %-9s %-6s %8s %7s %7s"
                         % (pp.id, "-", "Frirunde", "-", "-",
                            nk(pp.spill[spillnr], 1), "-"))
        L.append("")
    return "\n".join(L)


def lag_csv(rangert, plassering):
    L = ["Plass;ParID;Klubbkode;Parnr;Navn;Klubb;SamletProsent;AntallSpilt;"
         "AntallFrirunde;EgenKlubbPlass;EgenKlubbProsentUtenHcp;PublisertProsent"]
    for p in rangert:
        L.append("%d;%s;%s;%s;%s;%s;%s;%d;%d;%s;%s;%s"
                 % (plassering[p.id], p.id, p.kode, p.nr, p.navn, p.klubb,
                    nk(p.prosent), p.spilt, p.antall_spill - p.spilt,
                    p.klubb_plass or "",
                    nk(p.klubb_pst) if p.klubb_pst is not None else "",
                    nk(p.egen_pst) if p.egen_pst else ""))
    return "\n".join(L)


# ----------------------------------------------------------------------------


def kjor(kilder_inn, navn=None, vridd="klubbvis"):
    """Kjorer en samlet turnering.

    kilder_inn: liste av dict med 'tekst', 'filnavn' og valgfri 'kode'.
    Returnerer dict med rapport, spillfordeling, csv, rader og merknader.
    """
    alle_par, alle_res, kilder = {}, [], []
    kort_ref, kort_advarsler, brukt = {}, [], set()
    diagrammer = {}

    for k_inn in kilder_inn:
        filnavn = k_inn.get("filnavn", "(ukjent)")
        kode = k_inn.get("kode") or kode_fra_filnavn(filnavn, brukt)
        brukt.add(kode)
        klubb, tittel, par, res, kort, diag = les_tekst(k_inn["tekst"], kode, filnavn)
        for nr, linjer in diag.items():
            diagrammer.setdefault(nr, linjer)
        for p in par.values():
            alle_par[p.id] = p
        alle_res.extend(res)
        kilder.append({"kode": kode, "klubb": klubb, "fil": filnavn, "tittel": tittel,
                       "antall_par": len(par), "antall_res": len(res)})
        for nr, kort_str in kort.items():
            if nr not in kort_ref:
                kort_ref[nr] = (kort_str, kode)
            elif kort_ref[nr][0] != kort_str and kort_str and kort_ref[nr][0]:
                kort_advarsler.append(
                    "Spill %d: kortfordelingen i %s er ikke lik %s."
                    % (nr, kode, kort_ref[nr][1]))

    if not alle_res:
        raise ValueError("Fant ingen resultater i filene.")

    scoret, merknader = score(alle_res, vridd)
    merknader = kort_advarsler + merknader
    navn = navn or ("Samlet turnering - " + kilder[0]["tittel"])

    for k in kilder:
        egne_res = [r for r in alle_res if r.kode == k["kode"]]
        egne_par = {pid: p for pid, p in alle_par.items() if p.kode == k["kode"]}
        egen_scoret, _ = score(egne_res, vridd)
        rangert_egen = fordel(egne_par, egen_scoret)
        pl = plasser(rangert_egen)
        for p in rangert_egen:
            p.klubb_pst = p.prosent
            p.klubb_plass = pl[p.id]

    rangert = fordel(alle_par, scoret)

    ns_sum, ns_ant = defaultdict(float), defaultdict(int)
    for r, pst in scoret:
        ns_sum[r.kode] += pst
        ns_ant[r.kode] += 1
    klubbtall = []
    for k in kilder:
        gr = [p for p in rangert if p.kode == k["kode"]]
        if not gr or not ns_ant[k["kode"]]:
            continue
        ns = ns_sum[k["kode"]] / ns_ant[k["kode"]]
        klubbtall.append({"klubb": k["klubb"], "antall": len(gr), "ns": ns,
                          "ov": 100.0 - ns,
                          "beste": max(x.prosent for x in gr),
                          "svakeste": min(x.prosent for x in gr)})

    rapport, rangert = lag_rapport(navn, alle_par, scoret, merknader, kilder,
                                   klubbtall, vridd)
    plassering = plasser(rangert)
    rader = [{"Plass": plassering[p.id], "Par": p.id, "Navn": p.navn,
              "Klubb": p.klubb.split(" - ")[-1], "Samlet %": round(p.prosent, 2),
              "Spilt": p.spilt, "Fri": p.antall_spill - p.spilt,
              "Egen klubb u/hcp": round(p.klubb_pst, 2) if p.klubb_pst else None,
              "Publisert %": p.egen_pst} for p in rangert]

    spilldata = {}
    for r, pst in scoret:
        d = spilldata.setdefault(r.spill, {"nr": r.spill,
                                           "diagram": diagrammer.get(r.spill, []),
                                           "resultater": [], "frirunder": []})
        d["resultater"].append({"ns": r.ns.id, "ov": r.ov.id,
                                "kontrakt": r.kontrakt_tekst, "utspill": r.utspill,
                                "poeng": r.poeng, "pst_ns": pst, "pst_ov": 100.0 - pst,
                                "gruppe": r.gruppe or ""})
    for d in spilldata.values():
        d["resultater"].sort(key=lambda x: -x["poeng"])
        for p in sorted(alle_par.values(), key=lambda x: x.id):
            if d["nr"] in p.frirunde and d["nr"] in p.spill:
                d["frirunder"].append({"par": p.id, "pst": p.spill[d["nr"]]})

    return {"navn": navn, "rapport": rapport, "spill": spilldata,
            "spillfordeling": lag_spillfordeling(navn, scoret, alle_par),
            "csv": lag_csv(rangert, plassering), "rader": rader,
            "merknader": merknader, "kilder": kilder, "klubbtall": klubbtall,
            "antall_spill": len({r.spill for r, _ in scoret})}


def kode_fra_filnavn(sti, brukt):
    base = os.path.splitext(os.path.basename(sti))[0]
    bit = re.split(r"[_\-. ]+", base)[-1]
    kode = bit.upper()[:4] if bit and not bit.isdigit() else base.upper()[:4]
    k, n = kode, 2
    while k in brukt:
        k = "%s%d" % (kode, n)
        n += 1
    return k


def main():
    ap = argparse.ArgumentParser(
        description="Slar sammen Ruter-resultatfiler til en felles turnering.")
    ap.add_argument("filer", nargs="+", help="resultatfiler (tekstfil fra Ruter)")
    ap.add_argument("--ut", default=".", help="mappe for resultatfilene")
    ap.add_argument("--navn", default=None, help="tittel pa den samlede turneringen")
    ap.add_argument("--koder", default=None,
                    help="komma-separerte klubbkoder, en per fil, f.eks. HBK,KB")
    ap.add_argument("--ingen-pdf", dest="ingen_pdf", action="store_true",
                    help="ikke lag PDF-rapport")
    ap.add_argument("--vridd", choices=["klubbvis", "utelat"], default="klubbvis",
                    help="handtering av vridde spill (>a/>b). Standard: klubbvis")
    args = ap.parse_args()

    koder = [k.strip() for k in args.koder.split(",")] if args.koder else []
    kilder_inn = []
    for i, sti in enumerate(args.filer):
        with open(sti, "rb") as f:
            kilder_inn.append({"tekst": les_bytes(f.read()),
                               "filnavn": sti,
                               "kode": koder[i] if i < len(koder) else None})

    res = kjor(kilder_inn, args.navn, args.vridd)
    rapport = res["rapport"]

    os.makedirs(args.ut, exist_ok=True)
    if not args.ingen_pdf:
        try:
            import rapport_pdf
            sti = os.path.join(args.ut, "Samlet_turnering.pdf")
            rapport_pdf.lag_pdf(res, sti)
            print("Skrev", sti)
        except ImportError:
            print("Hopper over PDF (reportlab er ikke installert).")

    for filnavn, innhold in (("Samlet_resultat.txt", rapport),
                             ("Samlet_spillfordeling.txt", res["spillfordeling"]),
                             ("Samlet_resultat.csv", res["csv"])):
        sti = os.path.join(args.ut, filnavn)
        with open(sti, "w", encoding="utf-8") as f:
            f.write(innhold + "\n")
        print("Skrev", sti)

    print()
    print(rapport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
