# =============================================================================
# 01_build_piemonte_bilanci.py
# Piedmont municipalities: budget outturn (rendiconto) 2024 -> cleaned extract
# + one-row-per-comune indicators + GeoJSON for the Data Viz map.
#
# Sources (see README.md in this folder):
#   - OpenBDAP (RGS/MEF), "Bilanci armonizzati - Rendiconto - Schemi di bilancio",
#     2024, Piemonte                                       (CC-BY 4.0)
#   - ISTAT, resident population by comune at 1 January 2024 (POSAS)  (CC-BY 3.0 IT)
#   - ISTAT, generalised administrative boundaries at 1 January 2024  (CC-BY 3.0 IT)
#
# Rules: start from the raw total; flags, not drops;
# cross-tables at every step; every group sum must equal the total;
# a reconciliation table with one row per step; the same total by two routes.
#
# Run from any folder:  python 01_build_piemonte_bilanci.py
# Each block prints its checks. A line "deve essere 0" must print 0.
# =============================================================================


# %% Block 0 - Setup ----------------------------------------------------------
import os
import zipfile
import urllib.request
import urllib.parse

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")          # not in git (see .gitignore)
OUT = os.path.join(HERE, "output")
POST = os.path.join(HERE, "..", "..", "data", "piemonte-fiscal-map")
os.makedirs(RAW, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

YEAR = 2024
PIEMONTE_PROV = {   # ISTAT province code -> (name, abbreviation)
    "001": ("Torino", "TO"), "002": ("Vercelli", "VC"), "003": ("Novara", "NO"),
    "004": ("Cuneo", "CN"), "005": ("Asti", "AT"), "006": ("Alessandria", "AL"),
    "096": ("Biella", "BI"), "103": ("Verbano-Cusio-Ossola", "VB"),
}

URL_BDAP = ("https://openbdap.rgs.mef.gov.it/Datasets_FET/Rendiconto/2024/"
            + urllib.parse.quote("2024_Rendiconto - Schemi di bilancio_PIEMONTE.zip"))
URL_POP = "https://demo.istat.it/data/posas/POSAS_2024_it_Comuni.zip"
URL_GEO = ("https://www.istat.it/storage/cartografia/confini_amministrativi/"
           "generalizzati/2024/Limiti01012024_g.zip")

ZIP_BDAP = os.path.join(RAW, "2024_Rendiconto_SDB_PIEMONTE.zip")
ZIP_POP = os.path.join(RAW, "POSAS_2024_it_Comuni.zip")
ZIP_GEO = os.path.join(RAW, "Limiti01012024_g.zip")
# Dipartimento delle Finanze: addizionale comunale IRPEF rates 2024 (by codice catastale)
URL_ADD = ("https://www1.finanze.gov.it/finanze2/dipartimentopolitichefiscali/fiscalitalocale/"
           "nuova_addcomirpef/download/download.php?anno=2024")
CSV_ADD = os.path.join(RAW, "add_irpef_2024.csv")
# ISTAT list of comuni (ISTAT code <-> codice catastale)
URL_ELENCO = "https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv"
CSV_ELENCO = os.path.join(RAW, "elenco_comuni_istat.csv")

F_ENT = "2024_Rendiconto SDB Entrate_PIEMONTE.csv"                       # titolo x tipologia
F_ENT_TIT = "2024_Rendiconto SDB Entrate Riepilogo Titoli_PIEMONTE.csv"  # titolo (check)
F_SPE_MIS = "2024_Rendiconto SDB Spese Riepilogo Missioni_PIEMONTE.csv"  # missione
F_SPE_TIT = "2024_Rendiconto SDB Spese Riepilogo Titoli_PIEMONTE.csv"    # titolo
F_QGR_ENT = "2024_Rendiconto SDB Quadro Generale Riassuntivo Entrate_PIEMONTE.csv"
F_QGR_SPE = "2024_Rendiconto SDB Quadro Generale Riassuntivo Spese_PIEMONTE.csv"
F_CAT = "2024_Rendiconto SDB Allegato d Entrate per Categorie Enti Locali_PIEMONTE.csv"  # categoria

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
pd.set_option("display.float_format", lambda x: f"{x:,.2f}")

# reconciliation table: one row per step, filled block by block
riconc = []


# %% Block 1 - Download (only if the raw files are not already there) ---------
for url, path in [(URL_BDAP, ZIP_BDAP), (URL_POP, ZIP_POP), (URL_GEO, ZIP_GEO),
                  (URL_ADD, CSV_ADD), (URL_ELENCO, CSV_ELENCO)]:
    if not os.path.exists(path):
        print("downloading", url)
        urllib.request.urlretrieve(url, path)
    print(f"{os.path.basename(path):45s} {os.path.getsize(path):>12,d} bytes")


# %% Block 2 - Import the BDAP files (all columns as text) --------------------
def read_bdap(name):
    """Read one CSV from the BDAP zip, all columns as text."""
    with zipfile.ZipFile(ZIP_BDAP) as z:
        with z.open(name) as f:
            n_lines = sum(1 for _ in f) - 1          # rows in the file minus header
        with z.open(name) as f:
            d = pd.read_csv(f, sep=";", dtype=str, encoding="latin-1",
                            keep_default_na=False)
    d = d.loc[:, ~d.columns.str.startswith("Unnamed")]   # trailing ";" -> empty column
    print(f"{name[:70]:70s} rows {len(d):>7,d}  (file lines - header = {n_lines:,d})"
          f"  -> difference, deve essere 0: {len(d) - n_lines}")
    return d

ent = read_bdap(F_ENT)
ent_tit = read_bdap(F_ENT_TIT)
spe_mis = read_bdap(F_SPE_MIS)
spe_tit = read_bdap(F_SPE_TIT)
qgr_ent = read_bdap(F_QGR_ENT)
qgr_spe = read_bdap(F_QGR_SPE)
cat = read_bdap(F_CAT)


# %% Block 3 - Values: check the text format, then convert --------------------
NUM_RE = r"^-?\d+(\.\d+)?$"          # e.g. 1234.56 or -100 ; no thousands separator

def to_num(d, cols, label):
    for c in cols:
        bad = (~d[c].str.match(NUM_RE)) & (d[c] != "")
        print(f"{label:10s} {c[:45]:45s} bad format, deve essere 0: {bad.sum()}"
              f"   empty: {(d[c] == '').sum()}")
        d[c] = pd.to_numeric(d[c].replace("", "0"))
    return d

ID_COLS = list(ent.columns[:15])      # the first 15 columns describe the ente
ent = to_num(ent, [c for c in ent.columns[19:]], "entrate")
ent_tit = to_num(ent_tit, [c for c in ent_tit.columns[17:]], "ent_tit")
spe_mis = to_num(spe_mis, [c for c in spe_mis.columns[17:]], "spe_mis")
spe_tit = to_num(spe_tit, [c for c in spe_tit.columns[17:]], "spe_tit")
qgr_ent = to_num(qgr_ent, ["Accertamenti", "Incassi"], "qgr_ent")
qgr_spe = to_num(qgr_spe, ["Impegni", "Pagamenti"], "qgr_spe")
cat = to_num(cat, ["Accertamenti", "Riscossioni in C/Residui",
                   "di cui entrate accertate non ricorrenti", "Riscossioni in C/Competenza"], "categorie")
# category code = titolo (2) + tipologia (4 digits in BDAP, e.g. 0101) + categoria (2)
cat["cod_cat"] = (cat["Codice Titolo Entrata Arconet"] + cat["Cod Tipologia Entrata Arconet"]
                  + cat["Cod Categoria Entrata Arconet"])

# short names for the measures we use
ent = ent.rename(columns={"Codice Titolo Entrata Arconet": "cod_titolo",
                          "Desc Titolo Entrata Arconet": "titolo",
                          "Cod Tipologia Entrata Arconet": "cod_tipologia",
                          "Desc Tipologia Entrata Arconet": "tipologia",
                          "Accert. in CC": "accertamenti"})
spe_mis = spe_mis.rename(columns={"Codice Missione": "cod_missione",
                                  "Descrizione Missione": "missione"})
spe_tit = spe_tit.rename(columns={"Codice Titolo": "cod_titolo",
                                  "Descrizione Titolo": "titolo"})
for d in (ent, ent_tit, spe_mis, spe_tit, qgr_ent, qgr_spe, cat):
    d["pro_com_t"] = d["Codice Provincia"] + d["Codice Comune"]   # ISTAT code, 6 digits
    d["tipo_ente"] = d["Codice Tipologia Soggetto"]

# raw totals (all entities: comuni, unions, consortia, province, region...)
print("\nRaw totals, all entities in the file")
print(f"  entrate accertamenti   {ent['accertamenti'].sum():>22,.2f}")
print(f"  spese impegni (missioni){spe_mis['Impegni'].sum():>21,.2f}")
print(f"  spese impegni (titoli)  {spe_tit['Impegni'].sum():>21,.2f}")

riconc.append(dict(step=0, passo="Raw file, all entities (comuni, unioni, consorzi, ...)",
                   n_righe_ent=len(ent), n_enti=ent["Codice BDAP"].nunique(),
                   entrate_acc=ent["accertamenti"].sum(),
                   spese_imp_missioni=spe_mis["Impegni"].sum(),
                   spese_imp_titoli=spe_tit["Impegni"].sum()))


# %% Block 4 - Structure: who is in the file? (rows first, then sums) ---------
print("\nRows and entities by type of entity (entrate file)")
print(ent.groupby(["tipo_ente", "Descrizione Tipologia Soggetto"])
         .agg(righe=("accertamenti", "size"), enti=("Codice BDAP", "nunique"),
              accertamenti=("accertamenti", "sum")))

# flag: the entity is a comune (we keep the other rows, but do not use them)
for d in (ent, ent_tit, spe_mis, spe_tit, qgr_ent, qgr_spe, cat):
    d["flag_comune"] = (d["tipo_ente"] == "ELCOMU").astype(int)

# the comuni must be in Piedmont and must have a valid ISTAT code
c = ent[ent.flag_comune == 1]
print("\ncomuni not in Piemonte, deve essere 0:", (c["Codice Regione"] != "01").sum())
print("comuni with an unknown province code, deve essere 0:",
      (~c["Codice Provincia"].isin(PIEMONTE_PROV)).sum())
print("comuni with a closing date (Data Cessazione), deve essere 0:",
      (c["Data Cessazione Soggetto"] != "").sum())
# one BDAP code <-> one ISTAT code
link = c.groupby("Codice BDAP")["pro_com_t"].nunique()
print("BDAP codes with more than one ISTAT code, deve essere 0:", (link > 1).sum())
link = c.groupby("pro_com_t")["Codice BDAP"].nunique()
print("ISTAT codes with more than one BDAP code, deve essere 0:", (link > 1).sum())

print("\nComuni by province (rows and entities)")
print(c.groupby("Descrizione Provincia").agg(righe=("accertamenti", "size"),
                                             comuni=("pro_com_t", "nunique"),
                                             accertamenti=("accertamenti", "sum")))

riconc.append(dict(step=1, passo="Only comuni (flag_comune == 1)",
                   n_righe_ent=int(ent.flag_comune.sum()),
                   n_enti=ent.loc[ent.flag_comune == 1, "Codice BDAP"].nunique(),
                   entrate_acc=ent.loc[ent.flag_comune == 1, "accertamenti"].sum(),
                   spese_imp_missioni=spe_mis.loc[spe_mis.flag_comune == 1, "Impegni"].sum(),
                   spese_imp_titoli=spe_tit.loc[spe_tit.flag_comune == 1, "Impegni"].sum()))


# %% Block 5 - Duplicates and key ---------------------------------------------
# exact duplicates first (before anything that tells the copies apart)
for name, d, key in [("entrate", ent, ["pro_com_t", "cod_titolo", "cod_tipologia"]),
                     ("spese missioni", spe_mis, ["pro_com_t", "cod_missione"]),
                     ("spese titoli", spe_tit, ["pro_com_t", "cod_titolo"])]:
    dc = d[d.flag_comune == 1]
    print(f"{name:15s} exact duplicate rows, deve essere 0: {dc.duplicated().sum()}"
          f"   duplicates on the key {key}, deve essere 0: {dc.duplicated(key).sum()}")


# %% Block 6 - Double checks: the same total by two routes --------------------
ec = ent[ent.flag_comune == 1]
# (a) entrate: sum of tipologie by titolo = "Riepilogo Titoli" file = Quadro Generale
a = ec.groupby("cod_titolo")["accertamenti"].sum()
b = ent_tit[ent_tit.flag_comune == 1].groupby("Codice Titolo")["Accertamenti"].sum()
q = (qgr_ent[qgr_ent.flag_comune == 1]
     .groupby("Codice Titolo Entrata Arconet")["Accertamenti"].sum())
chk = pd.DataFrame({"tipologie": a, "riepilogo_titoli": b, "quadro_generale": q})
chk["diff_tip_rt"] = chk.tipologie - chk.riepilogo_titoli
chk["diff_tip_qg"] = chk.tipologie - chk.quadro_generale
print("\nEntrate (accertamenti), comuni, by titolo - three routes")
print(chk)
print("max abs difference, deve essere 0 (cents):",
      round(chk[["diff_tip_rt", "diff_tip_qg"]].abs().max().max(), 2))

# (b) spese: sum over missioni = sum over titoli, comune by comune
sm = spe_mis[spe_mis.flag_comune == 1].groupby("pro_com_t")["Impegni"].sum()
st = spe_tit[spe_tit.flag_comune == 1].groupby("pro_com_t")["Impegni"].sum()
d = (sm - st).abs()
print("\nSpese impegni: missioni vs titoli, comuni with |diff| > 1 euro, deve essere 0:",
      (d > 1).sum(), "   total diff:", round(sm.sum() - st.sum(), 2))
qs = (qgr_spe[qgr_spe.flag_comune == 1]
      .groupby("Codice Titolo Spese Arconet")["Impegni"].sum())
ts = spe_tit[spe_tit.flag_comune == 1].groupby("cod_titolo")["Impegni"].sum()
chk2 = pd.DataFrame({"riepilogo_titoli": ts, "quadro_generale": qs})
chk2["diff"] = chk2.riepilogo_titoli - chk2.quadro_generale
print("\nSpese (impegni), comuni, by titolo - two routes")
print(chk2)

print("\nSpese impegni by missione, comuni (sum of groups = total)")
mt = (spe_mis[spe_mis.flag_comune == 1]
      .groupby(["cod_missione", "missione"])["Impegni"].sum())
print(mt)
print("sum of missioni - total, deve essere 0:", round(mt.sum() - sm.sum(), 2))


# %% Block 7 - Population (ISTAT, 1 January 2024) -----------------------------
with zipfile.ZipFile(ZIP_POP) as z:
    with z.open("POSAS_2024_it_Comuni.csv") as f:
        pop = pd.read_csv(f, sep=";", skiprows=1, dtype={"Codice comune": str},
                          encoding="utf-8-sig")
print("\nPOSAS rows:", len(pop), " ages:", pop["Età"].min(), "-", pop["Età"].max(),
      "(999 = total)")
pop["flag_piemonte"] = pop["Codice comune"].str[:3].isin(PIEMONTE_PROV).astype(int)
pop_tot = pop[(pop["Età"] == 999)][["Codice comune", "Comune", "Totale", "flag_piemonte"]]
pop_age = pop[(pop["Età"] != 999)].groupby("Codice comune")["Totale"].sum()
# the "999" total row must equal the sum over single ages
dd = pop_tot.set_index("Codice comune")["Totale"] - pop_age
print("comuni where total row != sum over ages, deve essere 0:", (dd != 0).sum())
pop_pie = (pop_tot[pop_tot.flag_piemonte == 1]
           .rename(columns={"Codice comune": "pro_com_t", "Totale": "pop_2024"}))
print("Piemonte comuni in POSAS:", len(pop_pie),
      "  population:", f"{pop_pie.pop_2024.sum():,d}")


# %% Block 8 - Boundaries (ISTAT, 1 January 2024) -----------------------------
geo = gpd.read_file(f"zip://{ZIP_GEO}!Limiti01012024_g/Com01012024_g/Com01012024_g_WGS84.shp")
geo = geo[geo.COD_REG == 1].copy()
geo["pro_com_t"] = geo["PRO_COM_T"]
# the comune of "None" (TO, 001168) is read as a missing name: take names from the
# ISTAT list, read as text with no missing-value conversion
names = pd.read_csv(CSV_ELENCO, sep=";", dtype=str, encoding="cp1252", keep_default_na=False)
names = dict(zip(names["Codice Comune formato alfanumerico"], names["Denominazione in italiano"]))
print("comuni with a missing name in the boundaries file (filled from ISTAT list):",
      geo["COMUNE"].isna().sum())
geo["COMUNE"] = geo["COMUNE"].fillna(geo["pro_com_t"].map(names))
print("comuni with a missing name after filling, deve essere 0:", geo["COMUNE"].isna().sum())
print("\nPiemonte comuni in the boundaries file:", len(geo))


# %% Block 9 - One row per comune: indicators ---------------------------------
# entrate, wide by titolo and by the tipologie we need
e = ec.copy()
e["voce"] = "ent_t" + e.cod_titolo
w_t = e.pivot_table(index="pro_com_t", columns="voce", values="accertamenti",
                    aggfunc="sum", fill_value=0)
e1 = e[e.cod_titolo == "01"].copy()
e1["voce"] = "ent_t01_tip" + e1.cod_tipologia
w_tip = e1.pivot_table(index="pro_com_t", columns="voce", values="accertamenti",
                       aggfunc="sum", fill_value=0)
s = spe_tit[spe_tit.flag_comune == 1].copy()
s["voce"] = "spe_t" + s.cod_titolo
w_s = s.pivot_table(index="pro_com_t", columns="voce", values="Impegni",
                    aggfunc="sum", fill_value=0)

# categories we need (Allegato 13/2): IMU, addizionale IRPEF, TARI (two labels)
CATS = {"01010106": "ent_cat_imu",        # Imposta municipale propria
        "01010116": "ent_cat_addirpef",   # Addizionale comunale IRPEF
        "01010151": "ent_cat_tari51",     # Tassa smaltimento rifiuti solidi urbani
        "01010161": "ent_cat_tari61"}     # Tributo comunale sui rifiuti e sui servizi
cc = cat[cat.flag_comune == 1].copy()
print("\ncomuni in the categories file:", cc["pro_com_t"].nunique(),
      "  (tipologie file:", ec["pro_com_t"].nunique(), ")")
print("comuni missing in the categories file (listed):")
print(ec.loc[~ec.pro_com_t.isin(cc.pro_com_t), ["pro_com_t", "Denominazione Soggetto"]]
        .drop_duplicates().to_string(index=False))
# check: sum of categories = tipologia total, comune by comune (comuni in both files)
k = ["pro_com_t", "cod_titolo", "cod_tipologia"]
cc["cod_titolo"] = cc["Codice Titolo Entrata Arconet"]
cc["cod_tipologia"] = cc["Cod Tipologia Entrata Arconet"]
chk3 = (cc.groupby(k)["Accertamenti"].sum().to_frame("categorie")
          .join(ec[ec.pro_com_t.isin(cc.pro_com_t)].groupby(k)["accertamenti"].sum()
                  .to_frame("tipologie"), how="outer").fillna(0))
print("comune x tipologia where categories != tipologia (|diff| > 1 euro), deve essere 0:",
      int(((chk3.categorie - chk3.tipologie).abs() > 1).sum()))
w_cat = (cc[cc.cod_cat.isin(CATS)].assign(voce=lambda d: d.cod_cat.map(CATS))
           .pivot_table(index="pro_com_t", columns="voce", values="Accertamenti",
                        aggfunc="sum", fill_value=0))
for col in CATS.values():
    if col not in w_cat:
        w_cat[col] = 0.0
w_cat["flag_categorie"] = 1
cc_list = set(cc.pro_com_t)

com = (ec.groupby("pro_com_t")
         .agg(comune_bdap=("Denominazione Soggetto", "first"),
              cod_prov=("Codice Provincia", "first"))
         .join(w_t).join(w_tip).join(w_s).join(w_cat).fillna(0).reset_index())
for col in ["ent_t01_tip0101", "ent_t01_tip0104", "ent_t01_tip0301", "ent_t01_tip0302"]:
    if col not in com:
        com[col] = 0.0
print("\ncomuni with budget data:", len(com))
print("sum of ent_t* - total entrate, deve essere 0:",
      round(com.filter(regex=r"^ent_t\d\d$").sum().sum() - ec.accertamenti.sum(), 2))

# merge 1: boundaries (master list of comuni) <- budget data
m = geo[["pro_com_t", "COMUNE", "COD_PROV", "geometry"]].merge(
    com, on="pro_com_t", how="outer", indicator=True)
print("\nmerge boundaries x budget:")
print(m["_merge"].value_counts())
print("budget comuni not on the map, deve essere 0:", (m._merge == "right_only").sum())
print("comuni on the map without budget data (listed):")
print(m.loc[m._merge == "left_only", ["pro_com_t", "COMUNE"]].to_string(index=False))
m["flag_bilancio"] = (m._merge == "both").astype(int)
m = m.drop(columns="_merge")

# merge 2: <- population
m = m.merge(pop_pie[["pro_com_t", "pop_2024"]], on="pro_com_t", how="left", indicator=True)
print("\nmerge with population:")
print(m["_merge"].value_counts())
print("comuni on the map without population, deve essere 0:", (m._merge == "left_only").sum())
m = m.drop(columns="_merge")
print("population of map comuni - POSAS Piemonte total, deve essere 0:",
      int(m.pop_2024.sum() - pop_pie.pop_2024.sum()))

# the map variables (missing when the comune has no budget data)
ok = m.flag_bilancio == 1
corr = m.ent_t01 + m.ent_t02 + m.ent_t03          # current revenue (titoli 1-3)
okc = ok & (m.flag_categorie == 1)                   # comune also has the categories schedule
m["v_tax_pc"] = np.where(okc, (m.ent_cat_imu + m.ent_cat_addirpef) / m.pop_2024, np.nan)
# not on the map, kept in the CSV: TARI (both labels) and the whole tipologia 101
m["tari_pc"] = np.where(okc, (m.ent_cat_tari51 + m.ent_cat_tari61) / m.pop_2024, np.nan)
m["flag_no_tari"] = np.where(okc, ((m.ent_cat_tari51 + m.ent_cat_tari61) <= 0).astype(float), np.nan)
m["tip101_pc"] = np.where(ok, m.ent_t01_tip0101 / m.pop_2024, np.nan)
print("\ncomuni with no TARI in Titolo 1 (tariffa corrispettiva):", int(np.nansum(m.flag_no_tari)))

# --- recording checks on the two categories of the map variable ---------------
# IMU applies in every comune (L. 160/2019 c. 739): IMU = 0 means it was booked
# under another category (e.g. "ICI" or "Altre imposte ... n.a.c.").
# Addizionale IRPEF = 0 is genuine only if the comune's 2024 rate is 0 (Finanze).
el = pd.read_csv(CSV_ELENCO, sep=";", dtype=str, encoding="cp1252")
el.columns = [c.replace("\n", " ") for c in el.columns]
el = el.rename(columns={"Codice Comune formato alfanumerico": "pro_com_t",
                        "Codice Catastale del comune": "cod_catastale"})[["pro_com_t", "cod_catastale"]]
ad = pd.read_csv(CSV_ADD, sep=";", dtype=str, encoding="utf-8", keep_default_na=False)
rate_cols = [c for c in ad.columns if c.startswith("ALIQUOTA")]
ad["add_rate_max"] = pd.concat(
    [pd.to_numeric(ad[c].str.replace("*", "", regex=False).str.replace(",", ".", regex=False),
                   errors="coerce") for c in rate_cols], axis=1).max(axis=1).fillna(0)
m = m.merge(el, on="pro_com_t", how="left", indicator="_m_el")
print("\nmerge with ISTAT codice catastale:")
print(m["_m_el"].value_counts())
m = m.merge(ad[["CODICE_CATASTALE", "add_rate_max"]], left_on="cod_catastale",
            right_on="CODICE_CATASTALE", how="left", indicator="_m_add")
print("merge with Finanze rates 2024:")
print(m["_m_add"].value_counts())
print("comuni on the map without a 2024 rate row, deve essere 0:", (m._m_add == "left_only").sum())
m = m.drop(columns=["_m_el", "_m_add", "CODICE_CATASTALE"])
m["flag_imu_miscoded"] = (okc & (m.ent_cat_imu <= 0)).astype(int)
m["flag_add_miscoded"] = (okc & (m.ent_cat_addirpef <= 0) & (m.add_rate_max > 0)).astype(int)
print("\nCross-table: BDAP addizionale = 0  x  Finanze rate > 0 (comuni with categories)")
print(pd.crosstab(m.loc[okc, "ent_cat_addirpef"] <= 0, m.loc[okc, "add_rate_max"] > 0,
                  rownames=["BDAP add = 0"], colnames=["rate > 0"]))
print("comuni with IMU not booked in its category:", m.flag_imu_miscoded.sum())
print("comuni with addizionale not booked in its category (rate > 0):", m.flag_add_miscoded.sum())
print(m.loc[(m.flag_imu_miscoded == 1) | (m.flag_add_miscoded == 1),
            ["pro_com_t", "COMUNE", "ent_cat_imu", "ent_cat_addirpef", "add_rate_max"]]
        .to_string(index=False))
# the map variable is missing where a category is wrongly booked (shown grey, explained)
bad = (m.flag_imu_miscoded == 1) | (m.flag_add_miscoded == 1)
m.loc[bad, "v_tax_pc"] = np.nan
m["note_tax"] = np.select(
    [~ok, ok & (m.flag_categorie != 1), bad],
    ["no 2024 budget data in OpenBDAP",
     "the revenue-by-category schedule is missing in OpenBDAP",
     "IMU or the IRPEF surcharge is booked under another category in OpenBDAP"], default="")
m["v_transfer_share"] = np.where(
    ok, 100 * (m.ent_t02 + m.ent_t01_tip0301 + m.ent_t01_tip0302) / corr, np.nan)
m["v_curr_spend_pc"] = np.where(ok, m.spe_t01 / m.pop_2024, np.nan)
m["v_cap_spend_pc"] = np.where(ok, m.spe_t02 / m.pop_2024, np.nan)
m["v_debt_repay_pc"] = np.where(ok, m.spe_t04 / m.pop_2024, np.nan)

VARS = ["v_tax_pc", "v_transfer_share", "v_curr_spend_pc", "v_cap_spend_pc",
        "v_debt_repay_pc"]
print("\nIndicators, comuni with budget data")
print(m.loc[ok, VARS + ["pop_2024"]].describe(percentiles=[.05, .25, .5, .75, .95]).T)
print("missing values among comuni with budget data (= comuni without categories, listed above):",
      int(m.loc[ok, VARS].isna().sum().sum()))
print("negative values (listed if any):", int((m.loc[ok, VARS] < 0).sum().sum()))

# regional benchmarks of the indicators (aggregate, not average of comuni)
r = m[ok]
print("\nPiemonte aggregate: tipologia 101 per capita    "
      f"{r.ent_t01_tip0101.sum() / r.pop_2024.sum():,.0f} euro")
rc = r[r.flag_categorie == 1]
print("Piemonte aggregate: IMU + addizionale IRPEF pc  "
      f"{(rc.ent_cat_imu + rc.ent_cat_addirpef).sum() / rc.pop_2024.sum():,.0f} euro")
print("Piemonte aggregate: TARI per capita             "
      f"{(rc.ent_cat_tari51 + rc.ent_cat_tari61).sum() / rc.pop_2024.sum():,.0f} euro")
print("Piemonte aggregate: transfers+equalisation share "
      f"{100 * (r.ent_t02 + r.ent_t01_tip0301 + r.ent_t01_tip0302).sum() / (r.ent_t01 + r.ent_t02 + r.ent_t03).sum():.1f} %")
print("Piemonte aggregate: current spending per capita  "
      f"{r.spe_t01.sum() / r.pop_2024.sum():,.0f} euro")
print("Piemonte aggregate: capital spending per capita  "
      f"{r.spe_t02.sum() / r.pop_2024.sum():,.0f} euro")

riconc.append(dict(step=2, passo="Comuni matched to ISTAT boundaries and population",
                   n_righe_ent=int(ent.flag_comune.sum()), n_enti=int(ok.sum()),
                   entrate_acc=r.filter(regex=r"^ent_t\d\d$").sum().sum(),
                   spese_imp_missioni=sm.sum(), spese_imp_titoli=r.filter(regex=r"^spe_t\d\d$").sum().sum()))


# %% Block 10 - Save the cleaned extract (full structure, comuni only) --------
keep_id = ["Esercizio Finanziario", "Codice BDAP", "Denominazione Soggetto", "pro_com_t",
           "Codice Provincia", "Descrizione Provincia"]
ent_out = ent[ent.flag_comune == 1][keep_id + ["cod_titolo", "titolo", "cod_tipologia",
                                               "tipologia"] + list(ent.columns[19:33])]
ent_out.to_csv(os.path.join(OUT, f"piemonte_comuni_{YEAR}_entrate_titolo_tipologia.csv"),
               index=False, encoding="utf-8")
spe_mis[spe_mis.flag_comune == 1][keep_id + ["cod_missione", "missione"]
                                  + list(spe_mis.columns[17:30])].to_csv(
    os.path.join(OUT, f"piemonte_comuni_{YEAR}_spese_missione.csv"), index=False, encoding="utf-8")
spe_tit[spe_tit.flag_comune == 1][keep_id + ["cod_titolo", "titolo"]
                                  + list(spe_tit.columns[17:30])].to_csv(
    os.path.join(OUT, f"piemonte_comuni_{YEAR}_spese_titolo.csv"), index=False, encoding="utf-8")

m["provincia"] = m.COD_PROV.map(lambda x: PIEMONTE_PROV[f"{x:03d}"][0])
m["sigla"] = m.COD_PROV.map(lambda x: PIEMONTE_PROV[f"{x:03d}"][1])
ind_cols = (["pro_com_t", "COMUNE", "provincia", "sigla", "flag_bilancio", "pop_2024"]
            + sorted(m.filter(regex=r"^(ent|spe)_").columns) + VARS
            + ["tari_pc", "flag_no_tari", "tip101_pc", "add_rate_max",
               "flag_imu_miscoded", "flag_add_miscoded", "note_tax"])
ind = m[ind_cols].rename(columns={"COMUNE": "comune"}).sort_values("pro_com_t")
ind.to_csv(os.path.join(OUT, f"piemonte_comuni_{YEAR}_indicators.csv"), index=False,
           encoding="utf-8", float_format="%.2f")
print("\nsaved cleaned files in", OUT)


# %% Block 11 - GeoJSON for the map (simplified, shared borders kept) ----------
g = gpd.GeoDataFrame(m[["pro_com_t", "COMUNE", "sigla", "provincia", "pop_2024",
                        "flag_bilancio", "note_tax"] + VARS], geometry=m.geometry, crs=geo.crs)
# simplify each polygon (40 metres): the ISTAT file is already generalised, and
# any gap between neighbours stays below one screen pixel at the map's zoom.
# (shapely.coverage_simplify would keep borders shared, but needs GEOS >= 3.12)
g["geometry"] = g.geometry.simplify(40, preserve_topology=True)
prov = g.dissolve(by="sigla", as_index=False)[["sigla", "provincia", "geometry"]]
g = g.to_crs(4326)
prov = prov.to_crs(4326)
g = g.rename(columns={"COMUNE": "name", "pop_2024": "pop", "flag_bilancio": "has_data"})
for v in VARS:
    g[v] = g[v].round(1)
g.to_file(os.path.join(POST, "piemonte_comuni_2024.geojson"), driver="GeoJSON",
          COORDINATE_PRECISION=4, RFC7946="YES")
prov.to_file(os.path.join(POST, "piemonte_province_2024.geojson"), driver="GeoJSON",
             COORDINATE_PRECISION=4, RFC7946="YES")
# a small CSV for visitors (the map variables only)
ind[["pro_com_t", "comune", "provincia", "pop_2024", "flag_bilancio"] + VARS
    + ["tari_pc", "flag_no_tari", "note_tax"]].to_csv(
    os.path.join(POST, "piemonte_comuni_2024_indicators.csv"), index=False,
    encoding="utf-8", float_format="%.2f")
for f in ["piemonte_comuni_2024.geojson", "piemonte_province_2024.geojson",
          "piemonte_comuni_2024_indicators.csv"]:
    print(f"{f:40s} {os.path.getsize(os.path.join(POST, f)):>10,d} bytes")


# %% Block 11-bis - External benchmark: addizionale IRPEF vs tax returns ------
# MEF - Dipartimento delle Finanze, "Redditi e principali variabili IRPEF su base
# comunale" (tax returns), column "Addizionale comunale dovuta". By principio 4/2
# par. 3.7.5 the 2024 accertamento is based on the year N-2, so we compare with the
# tax years 2022 and 2023.
bench = []
for y in ["2022", "2023"]:
    zf = os.path.join(RAW, f"irpef_comunale_{y}.zip")
    if not os.path.exists(zf):
        urllib.request.urlretrieve(
            "https://www1.finanze.gov.it/finanze/analisi_stat/public/v_4_0_0/contenuti/"
            f"Redditi_e_principali_variabili_IRPEF_su_base_comunale_CSV_{y}.zip", zf)
    with zipfile.ZipFile(zf) as z:
        with z.open(z.namelist()[0]) as fh:
            irp = pd.read_csv(fh, sep=";", dtype=str, encoding="latin-1",
                              keep_default_na=False, index_col=False)   # rows end with ";"
    irp = irp[irp["Codice Istat Regione"] == "01"].copy()
    irp["add_dovuta"] = pd.to_numeric(irp["Addizionale comunale dovuta - Ammontare in euro"]
                                      .replace("", "0"))
    x = m[okc].merge(irp[["Codice Istat Comune", "add_dovuta"]], left_on="pro_com_t",
                     right_on="Codice Istat Comune", how="left")
    print(f"\nTax year {y}: comuni matched {x.add_dovuta.notna().sum()} of {len(x)}")
    bench.append(dict(benchmark=f"Addizionale comunale dovuta, tax returns {y}",
                      bdap_2024=x.ent_cat_addirpef.sum(), benchmark_value=x.add_dovuta.sum(),
                      ratio=x.ent_cat_addirpef.sum() / x.add_dovuta.sum(),
                      corr_across_comuni=np.corrcoef(x.ent_cat_addirpef, x.add_dovuta.fillna(0))[0, 1]))
bench = pd.DataFrame(bench)
print("\nBenchmark (BDAP accertamenti 2024, cat. 1010116, comuni with categories)")
print(bench.to_string(index=False))
bench.to_csv(os.path.join(OUT, f"benchmark_{YEAR}.csv"), index=False, encoding="utf-8")


# %% Block 12 - Reconciliation table ------------------------------------------
rt = pd.DataFrame(riconc)
print("\nReconciliation table")
print(rt.to_string(index=False))
rt.to_csv(os.path.join(OUT, f"reconciliation_{YEAR}.csv"), index=False, encoding="utf-8")
