# Piedmont municipal budgets 2024 — build folder

Data behind the post `data/piemonte-fiscal-map/` (Data Viz section).
Quarto ignores this folder (its name starts with `_`): nothing here becomes a page.

## Sources (downloaded 2026-10-29)

| What | Where | Licence |
|---|---|---|
| Harmonised budgets, *Rendiconto 2024 – Schemi di bilancio*, Piemonte (all local entities) | OpenBDAP (RGS/MEF), FET → Analizza → "Lavora sui dati in formato elaborabile": `https://openbdap.rgs.mef.gov.it/Datasets_FET/Rendiconto/2024/2024_Rendiconto - Schemi di bilancio_PIEMONTE.zip` (data updated 20-10-2026) | CC BY 4.0 (as stated in the OpenBDAP open-data catalogue; the zip page itself shows no licence text — **to confirm**) |
| Resident population by comune at 1 Jan 2024 (POSAS) | `https://demo.istat.it/data/posas/POSAS_2024_it_Comuni.zip` | ISTAT, CC BY 4.0 |
| Generalised municipal boundaries at 1 Jan 2024 | `https://www.istat.it/storage/cartografia/confini_amministrativi/generalizzati/2024/Limiti01012024_g.zip` | ISTAT, CC BY 4.0 |
| List of comuni (ISTAT code, codice catastale, names) | `https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv` | ISTAT, CC BY 4.0 |
| Addizionale comunale IRPEF rates 2024 (check of zeros) | MEF – Dipartimento delle Finanze, `.../nuova_addcomirpef/download/download.php?anno=2024` | licence to confirm (used only for checks) |
| IRPEF tax-return statistics by comune, tax years 2022 and 2023 (benchmark) | MEF – Dipartimento delle Finanze, `.../Redditi_e_principali_variabili_IRPEF_su_base_comunale_CSV_<YYYY>.zip` | licence to confirm (used only for the benchmark) |

Other years: the same OpenBDAP page offers rendiconto 2016–2025, one zip per region
(`/fet/GetDocuments?type=Rendiconto&year=YYYY&country=Piemonte`). The old CKAN catalogue
(`bdap-opendata.rgs.mef.gov.it`) only has per-comune budgets up to 2015.

## How to rebuild

```
python 01_build_piemonte_bilanci.py
```

The script downloads the raw files into `raw/` if missing (not in git, ~130 MB), and writes:

- `output/piemonte_comuni_2024_entrate_titolo_tipologia.csv` — revenue, comune × titolo × tipologia, all measures
- `output/piemonte_comuni_2024_spese_missione.csv` — spending, comune × missione, all measures
- `output/piemonte_comuni_2024_spese_titolo.csv` — spending, comune × titolo, all measures
- `output/piemonte_comuni_2024_indicators.csv` — one row per comune (1,180): population, totals by titolo, the 5 map variables
- `output/reconciliation_2024.csv` — one row per step
- `output/benchmark_2024.csv` — addizionale IRPEF: BDAP vs tax returns
- `output/build_log.txt` — all checks ("deve essere 0")
- in the post folder: `piemonte_comuni_2024.geojson`, `piemonte_province_2024.geojson`, `piemonte_comuni_2024_indicators.csv`

## Steps and checks

| Step | Rows (entrate) | Entities | Entrate accertamenti (€) | Spese impegni (€) |
|---|---|---|---|---|
| 0. Raw file, all local entities | 23,057 | 1,332 | 27,198,892,540 | 26,746,697,962 |
| 1. Only comuni (`flag_comune`) | 21,144 | 1,179 | 7,328,840,292 | 7,163,772,360 |
| 2. Matched to ISTAT boundaries and population | 21,144 | 1,179 | 7,328,840,292 | 7,163,772,360 |

- Rows read = file lines − header, for all 6 files.
- No exact duplicates; the keys (comune × titolo × tipologia, comune × missione, comune × titolo) are unique.
- One BDAP code ↔ one ISTAT code; all comuni in the 8 Piedmont provinces; no closed entities.
- Revenue by titolo: same total by three routes (tipologie, Riepilogo Titoli, Quadro Generale Riassuntivo), difference 0.
- Spending: missioni = titoli for every comune.
- Population: 1,180 comuni, 4,251,623 residents; the total row of POSAS = sum over ages.

## Anomalies

1. **Cassinasco (AT, 005021)** has no 2024 rendiconto in OpenBDAP. It stays on the map as "no data" (`flag_bilancio = 0`).
2. **Arola (VB)**: current spending (titolo 1, impegni) differs by €352.71 between *Spese Riepilogo Titoli* and the *Quadro Generale Riassuntivo*. It is an inconsistency inside the comune's own submission; we use the Riepilogo Titoli (it matches the missioni).

3. **Schedules differ slightly** (2026-10-29): revenue by categoria (Allegato d) is 3.9 M€ below revenue by titolo, and spending by macroaggregato (Allegato e) 4.2 M€ below spending by titolo (both ~0.05%). The categoria file has 1,178 comuni (titoli: 1,179). We use the titolo files for the map.
4. **TARI** (now only in the data file, column `tari_pc`; `flag_no_tari`): most comuni record it in cat. 1010151 "Tassa smaltimento rifiuti solidi urbani", others in 1010161 "Tributo comunale sui rifiuti e sui servizi" (119 use both). **30 comuni** have no TARI in Titolo 1 (tariffa corrispettiva, L. 147/2013 c. 668): 29 in Alessandria province + Oulx.

5. **Mongrando (BI)** filed the rendiconto but not the revenue-by-category annex: this explains the whole 3.9 M€ gap in point 3 (for all other comuni categories = tipologie to the cent). Its IMU + addizionale is missing on the map.
6. **Categories booked wrongly** (`flag_imu_miscoded`, `flag_add_miscoded`): 26 comuni with IMU = 0 (IMU booked under "ICI" or "Altre imposte n.a.c.") and 5 comuni with addizionale = 0 although their 2024 rate is > 0. 30 comuni in total (19 in Alessandria province): grey on the IMU + addizionale map, with a note in the tooltip (`note_tax`). The other 87 zeros of addizionale are genuine (0% rate).
7. **The comune of "None"** (TO, 001168): its name was read as a missing value; names are now filled from the ISTAT list.

## Benchmark

| Benchmark | BDAP 2024 (cat. 1010116) | Benchmark | Ratio | Correlation across comuni |
|---|---|---|---|---|
| Addizionale comunale dovuta, tax returns 2022 | 508.6 M€ | 490.2 M€ | 1.04 | 0.9998 |
| Addizionale comunale dovuta, tax returns 2023 | 508.6 M€ | 528.8 M€ | 0.96 | 0.9999 |

The 2024 accertamento lies between the two tax years, as expected from principio 4/2 §3.7.5. No independent benchmark for IMU yet (F24 payments by comune not found in open data).

Background on the accounting items: see the note *How Italian municipalities are financed* on this website (`notes/local-public-finance-italy.qmd`).

## Open points

- Benchmark for IMU (F24 payments by comune) and for the regional totals (IFEL / Corte dei conti reports).
- Confirm the licence of the Dipartimento delle Finanze files (used only for checks, not shown).
- Confirm the OpenBDAP licence on the bulk-download page.

## Variables on the map

| Variable | Definition |
|---|---|
| `v_tax_pc` | Revenue categoria 1010106 «Imposta municipale propria» + 1010116 «Addizionale comunale IRPEF» ÷ population (missing for the 30 mis-booked comuni and Mongrando) |
| `v_transfer_share` | (Revenue titolo 2 + titolo 1 tipologie 0301, 0302) ÷ (titoli 1+2+3) × 100 |
| `v_curr_spend_pc` | Spending titolo 1 ÷ population |
| `v_cap_spend_pc` | Spending titolo 2 ÷ population |
| `v_debt_repay_pc` | Spending titolo 4 ÷ population |

Revenue = accertamenti in conto competenza; spending = impegni. Population = residents at 1 Jan 2024.
