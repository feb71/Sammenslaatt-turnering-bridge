# Samlet turnering

Slår sammen resultatfiler (tekstfil fra Ruter) fra to eller flere klubber som har
spilt de samme spillene, og regner ut én felles turnering. Alt scores på nytt fra
poengene ved bordet — **uten handikap** — slik at par fra ulike klubber kan
sammenlignes direkte.

## Filer

| Fil | Hva det er |
| --- | --- |
| `samlet_turnering.py` | Selve beregningen. Kan brukes som modul eller fra kommandolinja. |
| `app.py` | Streamlit-app: last opp filer, se tabellen, last ned resultatene. |
| `rapport_pdf.py` | PDF-rapporten: sluttstilling på side 1, spillene på sidene etter. |
| `requirements.txt` | Pakkene appen trenger. |

## Kjøre lokalt

```bash
pip install -r requirements.txt
streamlit run app.py
```

Uten Streamlit, rett fra kommandolinja:

```bash
python3 samlet_turnering.py HBK.txt KB.txt --ut resultat --navn "Sommer 11"
```

Valg: `--koder HBK,KB` setter klubbkodene, `--vridd utelat` holder vridde spill
helt utenfor i stedet for å score dem gruppevis, `--ingen-pdf` dropper PDF-en.

Ut kommer `Samlet_turnering.pdf` (sluttstilling først, deretter alle spillene med
kortfordeling og resultater), samt de samme dataene som tekst og CSV.

## Legge den ut på Streamlit Community Cloud

1. Lag et GitHub-repo med `app.py`, `samlet_turnering.py` og `requirements.txt`
   i rota.
2. Gå til share.streamlit.io, logg inn med GitHub og velg **New app**.
3. Pek på repoet og `app.py` som hovedfil. Appen får en fast adresse du kan
   dele med den andre klubben.
4. Hver klubbkveld: last opp de to tekstfilene fra Ruter og last ned resultatet.

Tjenesten er gratis for offentlige repoer. Filene lastes opp i nettleseren og
lagres ikke noe sted — appen regner og glemmer.

## Slik regnes det

* For hvert spill sammenlignes alle resultatene fra alle klubbene mot hverandre:
  2 poeng for hvert par du slår, 1 for hvert du deler med. Prosent for spillet =
  oppnådde poeng delt på maks mulige.
* Totalen er gjennomsnittet av spillene. Frirunde gir paret sin egen innspilte
  prosent på det spillet, slik Ruter gjør det.
* Programmet sammenligner kortfordelingen spill for spill og sier fra hvis
  klubbene ikke har spilt samme spill.
* Vridde spill (merket `>a` / `>b` i Ruter) kan ikke sammenlignes på tvers og
  scores gruppevis innenfor hver klubb.

## Merk om handikap

Klubber som bruker handikap får en `%`-kolonne i Ruter som er justert:
`publisert % = innspilt % + handikap × 100 / (antall spill × 12)`.
Det tallet er ikke sammenlignbart med en klubb som spiller uten handikap.
Rapporten viser derfor både innspilt prosent uten handikap og den publiserte,
side om side.
