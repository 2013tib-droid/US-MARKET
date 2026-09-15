"""Smart money: apa yang dilakukan orang yang tahu lebih banyak dari kita —
pengganti bandarmologi IDX (docs/01-metodologi.md §3, Pilar 3).

Tiga sinyal, tiga sumber, tiga kecepatan:

1. **Orang dalam (Form 4)** dari EDGAR, lag ≤ 2 hari kerja. Ini sinyal
   tercepat dan paling kuat, dan satu-satunya yang diambil langsung dari
   dokumen resmi. Yang dihitung hanya transaksi pasar terbuka (kode `P` beli,
   `S` jual); pemberian saham (`A`), eksekusi opsi (`M`), dan potongan pajak
   (`F`) bukan keputusan membeli — orang dalam tidak "memilih" menerima
   kompensasinya. Transaksi yang ditandai rencana 10b5-1 dibuang: ia
   dijadwalkan berbulan-bulan sebelumnya, jadi tidak memuat pandangan
   hari ini (Cohen, Malloy & Pomorski 2012 — yang prediktif adalah
   pembelian *oportunistik*).
2. **Kepemilikan institusi** dari yfinance (turunan 13F), lag ≤ 45 hari
   setelah akhir kuartal. Terlalu lambat untuk timing; dipakai sebagai
   konfirmasi. Perubahannya diukur terhadap snapshot minggu lalu yang
   di-commit di data/smartmoney.csv, bukan dari 13F mentah.
3. **Short interest** dari yfinance (turunan FINRA), dua kali sebulan.
   Dipakai sebagai flag, bukan skor: short tinggi berarti dua hal sekaligus
   (pesimisme yang mungkin benar, dan bahan bakar short squeeze).

Modul ini tidak mengunduh apa pun sendiri kecuali lewat `KlienSEC` yang
dioper ke dalamnya; pengunduhan dan penulisan berkas ada di
`scripts/perbarui_smartmoney.py`.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .faktor import BATAS_Z, z_sektor

# Kode transaksi Form 4 (Tabel I, "Transaction Code"). Hanya dua yang berarti
# keputusan membeli/menjual di pasar terbuka.
KODE_BELI = "P"
KODE_JUAL = "S"

JENDELA_HARI = 90
JENDELA_CLUSTER_HARI = 30
MIN_INSIDER_CLUSTER = 2

# Berapa lama transaksi disimpan di data/insider.csv. Lebih panjang dari
# jendela 90 hari supaya run yang terlewat satu-dua minggu tidak berlubang,
# dan supaya analisa 180 hari bisa dihitung ulang tanpa mengunduh lagi.
RETENSI_HARI = 180

# Short interest yang dianggap tinggi (docs/03-rancang-bangun.md §5). Di atas
# 30% statusnya HINDARI, tapi status baru ada di Fase 4.
SHORT_TINGGI_PCT = 20.0
# Jual bersih orang dalam yang dianggap material, dalam juta USD.
INSIDER_JUAL_MATERIAL_JUTA = 10.0

BOBOT_SMARTMONEY = {"Insider": 0.6, "Institusi": 0.4}
# Cluster buy = dua orang dalam berbeda membeli di pasar terbuka dalam 30
# hari. Sinyal terkuat di Pilar 3, jadi ia menambah langsung, bukan lewat
# z-score yang bisa tenggelam oleh satu pembelian besar satu orang.
BONUS_CLUSTER = 1.0

KOLOM_INSIDER = ["Ticker", "CIK", "Akses", "Tanggal", "Tanggal_Lapor", "Kode", "Lembar", "Harga",
                 "Nilai", "Arah", "Pemilik", "Pemilik_CIK", "Jabatan", "Peran", "Rencana10b5"]

RE_10B5 = re.compile(r"10b5-?1", re.IGNORECASE)


# --- Form 4 ---------------------------------------------------------------

def _tanpa_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _nilai(el: ET.Element | None) -> str | None:
    """Isi sebuah elemen Form 4. Hampir semua nilai dibungkus <value>;
    sebagian (transactionCode) langsung teks. Nilai yang hanya berisi
    <footnoteId> — mis. harga hibah — dikembalikan sebagai None."""
    if el is None:
        return None
    anak = el.find("value")
    teks = (anak.text if anak is not None else el.text) or ""
    return teks.strip() or None


def _angka(teks: str | None) -> float | None:
    if teks is None:
        return None
    try:
        return float(teks.replace(",", "").replace("$", ""))
    except ValueError:
        return None


def _peran(rel: ET.Element | None) -> str:
    if rel is None:
        return ""
    peta = {"isDirector": "direktur", "isOfficer": "pejabat",
            "isTenPercentOwner": "pemilik10%", "isOther": "lain"}
    return ";".join(nama for tag, nama in peta.items() if (_nilai(rel.find(tag)) or "0") in ("1", "true"))


def baca_form4(xml: bytes | str) -> list[dict]:
    """Transaksi non-derivatif dari satu dokumen Form 4 (atau 4/A).

    Satu dokumen bisa memuat beberapa transaksi dan beberapa pelapor (suami-
    istri, atau satu keluarga dana). Pelapor pertama dipakai sebagai identitas
    barisnya; untuk cluster buy yang dihitung adalah pelapor berbeda, jadi
    pelaporan bersama tidak boleh dihitung sebagai dua orang.

    Transaksi derivatif (opsi, RSU) sengaja tidak dibaca: yang menarik dari
    situ hanya eksekusi opsi, dan itu justru yang harus diabaikan.
    """
    try:
        akar = ET.fromstring(xml)
    except ET.ParseError:
        return []
    for el in akar.iter():
        el.tag = _tanpa_ns(el.tag)

    emiten = akar.find("issuer")
    cik = _nilai(emiten.find("issuerCik")) if emiten is not None else None
    simbol = (_nilai(emiten.find("issuerTradingSymbol")) if emiten is not None else None) or ""

    pemilik = akar.find("reportingOwner")
    nama = jabatan = peran = ""
    pemilik_cik = None
    if pemilik is not None:
        ident = pemilik.find("reportingOwnerId")
        if ident is not None:
            nama = _nilai(ident.find("rptOwnerName")) or ""
            pemilik_cik = _nilai(ident.find("rptOwnerCik"))
        rel = pemilik.find("reportingOwnerRelationship")
        jabatan = (_nilai(rel.find("officerTitle")) if rel is not None else None) or ""
        peran = _peran(rel)

    catatan = {f.get("id"): (f.text or "") for f in akar.iter("footnote")}
    # Kotak centang 10b5-1 baru wajib sejak Desember 2022 dan nama tagnya
    # berbeda antarversi skema; dicari dengan pola, bukan nama pasti. Sebelum
    # itu (dan untuk filer yang mengosongkannya) satu-satunya jejak rencana
    # ada di catatan kaki, yang dibaca per transaksi di bawah.
    rencana_dokumen = any("10b5" in el.tag.lower() and (_nilai(el) or "") in ("1", "true")
                          for el in akar.iter())

    hasil = []
    for trx in akar.iter("nonDerivativeTransaction"):
        kode_el = trx.find("transactionCoding")
        kode = _nilai(kode_el.find("transactionCode")) if kode_el is not None else None
        jumlah = trx.find("transactionAmounts")
        if jumlah is None:
            continue
        lembar = _angka(_nilai(jumlah.find("transactionShares")))
        harga = _angka(_nilai(jumlah.find("transactionPricePerShare")))
        arah = _nilai(jumlah.find("transactionAcquiredDisposedCode")) or ""
        ids = {f.get("id") for f in trx.iter("footnoteId")}
        rencana = rencana_dokumen or any(RE_10B5.search(catatan.get(i, "")) for i in ids)
        hasil.append({
            "Ticker": simbol.upper(),
            "CIK": int(cik) if cik and cik.isdigit() else None,
            "Tanggal": _nilai(trx.find("transactionDate")),
            "Kode": kode,
            "Lembar": lembar,
            "Harga": harga,
            "Nilai": lembar * harga if lembar is not None and harga is not None else None,
            "Arah": arah,
            "Pemilik": nama,
            "Pemilik_CIK": int(pemilik_cik) if pemilik_cik and pemilik_cik.isdigit() else None,
            "Jabatan": jabatan,
            "Peran": peran,
            "Rencana10b5": rencana,
        })
    return hasil


# --- agregasi per emiten --------------------------------------------------

def _cluster(beli: pd.DataFrame) -> tuple[bool, str | None]:
    """Dua pelapor berbeda membeli dalam jendela 30 hari? Kembalikan juga
    tanggal transaksi yang melengkapi cluster pertama kali."""
    if len(beli) < MIN_INSIDER_CLUSTER:
        return False, None
    urut = beli.sort_values("Tanggal")
    tanggal = list(urut["Tanggal"])
    # Pelapor tanpa CIK (jarang, filer lama) dibedakan dengan namanya.
    orang = [c if pd.notna(c) else n for c, n in zip(urut["Pemilik_CIK"], urut["Pemilik"])]
    awal = 0
    for i in range(len(urut)):
        while (tanggal[i] - tanggal[awal]).days > JENDELA_CLUSTER_HARI:
            awal += 1
        if len(set(orang[awal:i + 1])) >= MIN_INSIDER_CLUSTER:
            return True, tanggal[i].date().isoformat()
    return False, None


def ringkas_insider(transaksi: pd.DataFrame, cik_ticker: Mapping[int, list[str]],
                    hari_ini: date | None = None,
                    jendela: int = JENDELA_HARI) -> pd.DataFrame:
    """Satu baris per ticker dari tabel transaksi Form 4 mentah.

    Yang dihitung hanya beli/jual pasar terbuka di luar rencana 10b5-1;
    sisanya tetap dihitung jumlahnya supaya "tidak ada transaksi" bisa
    dibedakan dari "semuanya terjadwal".

    Pengelompokannya per **CIK**, lalu `cik_ticker` memetakannya ke ticker
    universe. Kolom `Ticker` di transaksi tidak dipakai sama sekali: isinya
    medan simbol Form 4 yang diketik filer semaunya — "NONE", "(CALX)",
    "NYSE: KRC", "GEF, GEF-B" semuanya nyata ada. Dulu baris seperti itu
    lenyap tanpa error saat hasilnya di-join ke universe; pada data 15 Sep
    2026 ada 428 baris begitu, 45 di antaranya beli/jual pasar terbuka
    senilai $50,9 juta. CIK selalu terisi karena berasal dari permintaan
    EDGAR-nya sendiri, bukan dari isi dokumen.

    Satu CIK bisa memegang lebih dari satu ticker universe (GOOG/GOOGL,
    FOX/FOXA, NWS/NWSA, UA/UAA, CENT/CENTA). Form 4 dilaporkan di tingkat
    emiten, bukan kelas saham, jadi angkanya disalin ke setiap kelas —
    orang dalam yang membeli di Alphabet adalah sinyal yang sama untuk GOOG
    dan GOOGL.
    """
    kosong = pd.DataFrame(columns=["Insider_Beli90H_JutaUSD", "Insider_Jual90H_JutaUSD",
                                   "Insider_Net90H_JutaUSD", "Insider_Pembeli90H",
                                   "Insider_Penjual90H", "Insider_Transaksi90H",
                                   "Insider_Rencana90H", "Insider_ClusterBuy",
                                   "Insider_ClusterTgl", "Insider_Terakhir"])
    kosong.index.name = "Ticker"
    if transaksi is None or len(transaksi) == 0:
        return kosong

    t = transaksi.copy()
    t["Tanggal"] = pd.to_datetime(t["Tanggal"], errors="coerce")
    t["Nilai"] = pd.to_numeric(t["Nilai"], errors="coerce")
    t["Rencana10b5"] = t["Rencana10b5"].map(lambda v: str(v).strip().lower() in ("true", "1", "yes"))
    batas = pd.Timestamp(hari_ini or date.today()) - pd.Timedelta(days=jendela)
    t["CIK"] = pd.to_numeric(t["CIK"], errors="coerce")
    t = t[t["Tanggal"].notna() & (t["Tanggal"] >= batas) & t["CIK"].notna()
          & t["Kode"].isin([KODE_BELI, KODE_JUAL])]
    if t.empty:
        return kosong

    baris = {}
    for cik, g in t.groupby(t["CIK"].astype("int64")):
        tickers = cik_ticker.get(int(cik))
        if not tickers:
            continue  # emiten di luar universe: Form 4-nya memang tidak dipakai
        bebas = g[~g["Rencana10b5"] & g["Nilai"].notna()]
        beli = bebas[bebas["Kode"] == KODE_BELI]
        jual = bebas[bebas["Kode"] == KODE_JUAL]
        ada_cluster, tgl_cluster = _cluster(beli)
        isi = {
            "Insider_Beli90H_JutaUSD": beli["Nilai"].sum() / 1e6,
            "Insider_Jual90H_JutaUSD": jual["Nilai"].sum() / 1e6,
            "Insider_Net90H_JutaUSD": (beli["Nilai"].sum() - jual["Nilai"].sum()) / 1e6,
            "Insider_Pembeli90H": int(beli["Pemilik_CIK"].nunique()),
            "Insider_Penjual90H": int(jual["Pemilik_CIK"].nunique()),
            "Insider_Transaksi90H": int(len(bebas)),
            "Insider_Rencana90H": int(g["Rencana10b5"].sum()),
            "Insider_ClusterBuy": ada_cluster,
            "Insider_ClusterTgl": tgl_cluster,
            "Insider_Terakhir": g["Tanggal"].max().date().isoformat(),
        }
        for ticker in tickers:
            baris[ticker] = isi
    if not baris:
        return kosong
    hasil = pd.DataFrame.from_dict(baris, orient="index")
    hasil.index.name = "Ticker"
    return hasil[kosong.columns]


def buang_kedaluwarsa(transaksi: pd.DataFrame, hari_ini: date | None = None,
                      retensi: int = RETENSI_HARI) -> pd.DataFrame:
    """Buang transaksi yang lebih tua dari masa simpan, supaya data/insider.csv
    tidak tumbuh selamanya di repo."""
    if transaksi is None or len(transaksi) == 0:
        return transaksi
    tgl = pd.to_datetime(transaksi["Tanggal"], errors="coerce")
    batas = pd.Timestamp(hari_ini or date.today()) - pd.Timedelta(days=retensi)
    return transaksi[tgl.notna() & (tgl >= batas)]


# --- kolom malam & faktor -------------------------------------------------

def _num(t: pd.DataFrame, kolom: str) -> pd.Series:
    if kolom not in t:
        return pd.Series(np.nan, index=t.index)
    return pd.to_numeric(t[kolom], errors="coerce")


def hitung(tabel: pd.DataFrame) -> pd.DataFrame:
    """Tambahkan kolom turunan smart money dan Z_SmartMoney.

    Dipanggil setelah valuasi.hitung: pembelian orang dalam dinilai relatif
    terhadap market cap, karena $5 juta di emiten $2 miliar adalah keyakinan,
    sementara di emiten $2 triliun itu pembulatan.
    """
    t = tabel.copy()
    mcap_juta = _num(t, "MCap_MiliarUSD") * 1000
    t["Insider_Net_PctMCap"] = (_num(t, "Insider_Net90H_JutaUSD") / mcap_juta.where(mcap_juta > 0)) * 100

    sektor = t["Sektor"].fillna("Tidak diketahui")
    ada = t["_SM_Ada"] == True if "_SM_Ada" in t else pd.Series(False, index=t.index)  # noqa: E712
    z_insider, _ = z_sektor(t["Insider_Net_PctMCap"], sektor)
    z_institusi, _ = z_sektor(_num(t, "Institusi_Delta"), sektor)
    cluster = t["Insider_ClusterBuy"].map(lambda v: str(v).strip().lower() == "true") if "Insider_ClusterBuy" in t \
        else pd.Series(False, index=t.index)

    # Komponen yang kosong dianggap netral (0), bukan NaN: emiten tanpa satu
    # pun transaksi orang dalam memang tidak memberi sinyal apa-apa, dan
    # membuang barisnya dari skor akan menghukumnya seperti data rusak
    # (docs/03-rancang-bangun.md §2). Baris yang sama sekali tidak ada di
    # data/smartmoney.csv tetap NaN — itu data hilang, bukan sinyal nol.
    skor = (BOBOT_SMARTMONEY["Insider"] * z_insider.fillna(0)
            + BOBOT_SMARTMONEY["Institusi"] * z_institusi.fillna(0)
            + BONUS_CLUSTER * cluster.astype(float))
    t["Z_SmartMoney"] = skor.clip(-BATAS_Z, BATAS_Z).where(ada)
    t["Insider_ClusterBuy"] = cluster.where(ada)
    return t


def flag_smartmoney(r: pd.Series) -> list[str]:
    """Red flag dari Pilar 3 (docs/03-rancang-bangun.md §5)."""
    f = []
    short = pd.to_numeric(r.get("Short_PctFloat"), errors="coerce")
    if pd.notna(short) and short > SHORT_TINGGI_PCT:
        f.append("SHORT-TINGGI")
    net = pd.to_numeric(r.get("Insider_Net90H_JutaUSD"), errors="coerce")
    if pd.notna(net) and net < -INSIDER_JUAL_MATERIAL_JUTA:
        f.append("INSIDER-JUAL")
    return f


# --- pembanding antar-snapshot --------------------------------------------

def delta_snapshot(baru: pd.Series, lama: pd.Series | None) -> pd.Series:
    """Selisih poin persen terhadap snapshot minggu lalu. Ticker yang belum
    pernah tercatat menghasilkan NaN, bukan nol: "belum diketahui" tidak sama
    dengan "tidak berubah"."""
    baru = pd.to_numeric(baru, errors="coerce")
    if lama is None:
        return pd.Series(np.nan, index=baru.index)
    lama = pd.to_numeric(lama, errors="coerce").reindex(baru.index)
    return baru - lama


def revisi_target(riwayat: pd.DataFrame, sekarang: pd.Series, hari_ini: date | None = None,
                  hari: int = 90, toleransi: int = 45) -> tuple[pd.Series, pd.Series]:
    """Perubahan target harga konsensus (%) terhadap snapshot ± 3 bulan lalu.

    `riwayat` = data/target_riwayat.csv (Tanggal, Ticker, Target_Rata), satu
    baris per ticker per pekan. Pembandingnya snapshot terdekat ke
    `hari - toleransi … hari + toleransi`; kalau belum ada (riwayat baru
    mulai dikumpulkan), hasilnya kosong — bukan diisi dengan revisi seminggu
    yang artinya lain.

    Mengembalikan (revisi persen, umur pembanding dalam hari).
    """
    kosong = pd.Series(np.nan, index=sekarang.index)
    if riwayat is None or len(riwayat) == 0:
        return kosong, kosong
    r = riwayat.copy()
    r["Tanggal"] = pd.to_datetime(r["Tanggal"], errors="coerce")
    r["Target_Rata"] = pd.to_numeric(r["Target_Rata"], errors="coerce")
    r = r[r["Tanggal"].notna() & r["Target_Rata"].gt(0)]
    acuan = pd.Timestamp(hari_ini or date.today())
    r["_umur"] = (acuan - r["Tanggal"]).dt.days
    r = r[(r["_umur"] >= hari - toleransi) & (r["_umur"] <= hari + toleransi)]
    if r.empty:
        return kosong, kosong
    # Snapshot yang umurnya paling dekat ke 90 hari.
    r = r.assign(_jarak=(r["_umur"] - hari).abs()).sort_values("_jarak").drop_duplicates("Ticker")
    lama = r.set_index("Ticker")["Target_Rata"].reindex(sekarang.index)
    umur = r.set_index("Ticker")["_umur"].reindex(sekarang.index)
    kini = pd.to_numeric(sekarang, errors="coerce")
    return (kini / lama - 1) * 100, umur


def hari_bursa_ke(tanggal: pd.Series, dari: date) -> pd.Series:
    """Jarak dalam hari bursa (Senin–Jumat, tanpa memperhitungkan libur) dari
    `dari` ke tanggal earnings. Libur NYSE sengaja diabaikan: selisih satu
    hari tidak mengubah keputusan "jangan masuk sebelum lapkeu", dan tanggal
    earnings dari Yahoo sendiri sering belum pasti."""
    tgl = pd.to_datetime(tanggal, errors="coerce")
    awal = np.datetime64(dari, "D")
    def hitung_satu(v):
        if pd.isna(v):
            return np.nan
        akhir = np.datetime64(v.date(), "D")
        tanda = 1 if akhir >= awal else -1
        return float(tanda * np.busday_count(min(awal, akhir), max(awal, akhir)))
    return tgl.map(hitung_satu)
