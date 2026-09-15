#!/usr/bin/env python3
"""Perbarui data/smartmoney.csv: orang dalam (Form 4 dari EDGAR), kepemilikan
institusi, short interest, dan estimasi analis.

    SEC_USER_AGENT="US-MARKET screener nama@email.com" python scripts/perbarui_smartmoney.py
    python scripts/perbarui_smartmoney.py --ticker AAPL NVDA --output -      # uji, cetak saja
    python scripts/perbarui_smartmoney.py --lewati-form4                     # hanya bagian Yahoo

Dua sumber, dua sifat:

**Form 4** diambil langsung dari EDGAR, bukan dari yfinance: yang dibutuhkan
adalah kode transaksi (`P` beli pasar terbuka vs `M` eksekusi opsi), identitas
tiap pelapor, dan penanda rencana 10b5-1 — tiga hal yang tidak ada di ringkasan
Yahoo. Biayanya satu permintaan daftar filing per emiten plus satu per dokumen
Form 4 baru. Supaya itu tidak terulang tiap minggu, transaksi yang sudah
diunduh disimpan di `data/insider.csv` dan run berikutnya hanya mengambil
nomor akses yang belum ada di sana (run pertama ± 40 menit, run rutin ± 5
menit).

**Institusi, short interest, dan estimasi analis** dari yfinance, satu
permintaan per emiten. Semuanya turunan sumber resmi (13F, FINRA, konsensus
broker) yang versi mentahnya tidak gratis atau tidak sepadan usahanya;
karena itu kolomnya ditandai proksi di dokumen dan tidak dipakai sebagai
flag berat.

Berbeda dengan data/fundamental.csv yang menyimpan rasio sebagai pecahan,
berkas ini menyimpan persen sebagai persen: ia dibaca manusia sesering
dibaca mesin.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from usmarket import VERSI_SKEMA, sec, smartmoney, universe  # noqa: E402

AKAR = Path(__file__).resolve().parent.parent
KELUARAN = AKAR / "data" / "smartmoney.csv"
INSIDER = AKAR / "data" / "insider.csv"
RIWAYAT_TARGET = AKAR / "data" / "target_riwayat.csv"
META = AKAR / "data" / "smartmoney_meta.json"

FORM4 = {"4", "4/A"}
# Form 4 harus dilapor dalam 2 hari kerja, tapi pelaporan terlambat ada.
# Jendela unduh dibuat lebih lebar dari jendela hitung 90 hari supaya
# transaksi yang dilapor terlambat tetap tertangkap.
MARGIN_LAPOR_HARI = 10

# Kolom yfinance yang dipakai, dan namanya di sini. Tidak semua emiten punya
# semuanya; yang kosong tetap kosong, tidak diisi nol.
PETA_YAHOO = {
    "heldPercentInstitutions": "Institusi_Pct",
    "shortPercentOfFloat": "Short_PctFloat",
    "shortRatio": "Short_Ratio",
    "sharesShort": "Short_Lembar",
    "sharesShortPriorMonth": "Short_Lembar_Lalu",
    "targetMeanPrice": "Target_Rata",
    "targetHighPrice": "Target_Tinggi",
    "targetLowPrice": "Target_Rendah",
    "recommendationMean": "Rekom_Rata",
    "numberOfAnalystOpinions": "Jumlah_Analis",
    "forwardEps": "EPS_Fwd",
}
# Dua kolom Yahoo di atas adalah pecahan (0,0234 = 2,34%); disimpan sebagai persen.
PECAHAN_YAHOO = ["Institusi_Pct", "Short_PctFloat"]

KOLOM_KELUARAN = [
    "CIK",
    "Insider_Beli90H_JutaUSD", "Insider_Jual90H_JutaUSD", "Insider_Net90H_JutaUSD",
    "Insider_Pembeli90H", "Insider_Penjual90H", "Insider_Transaksi90H", "Insider_Rencana90H",
    "Insider_ClusterBuy", "Insider_ClusterTgl", "Insider_Terakhir",
    "Institusi_Pct", "Institusi_Pct_Lalu", "Institusi_Delta",
    "Short_PctFloat", "Short_Ratio", "Short_Lembar", "Short_Lembar_Lalu",
    "Target_Rata", "Target_Tinggi", "Target_Rendah", "Target_Revisi", "Target_Revisi_Umur",
    "Rekom_Rata", "Jumlah_Analis", "EPS_Fwd",
    "Surprise_Terakhir", "Surprise_Rata4Q", "Surprise_Tanggal", "Earnings_Berikut",
    "Catatan_SM",
]


# --- Form 4 ---------------------------------------------------------------

def muat_insider() -> pd.DataFrame:
    if not INSIDER.exists():
        return pd.DataFrame(columns=smartmoney.KOLOM_INSIDER)
    return pd.read_csv(INSIDER, dtype={"Akses": str})


def unduh_form4(klien: sec.KlienSEC, cik_ticker: dict[int, list[str]], sudah: set[str],
                sejak: date, pekerja: int, maks_per_emiten: int) -> tuple[list[dict], dict]:
    """Daftar filing per emiten, lalu dokumen Form 4 yang belum pernah diunduh."""
    mulai = time.monotonic()
    daftar: list[tuple[int, dict]] = []
    gagal_daftar = []

    def ambil_daftar(cik: int):
        return cik, klien.filing_terbaru(cik, FORM4, sejak - timedelta(days=MARGIN_LAPOR_HARI))

    print(f"Mencari Form 4 di {len(cik_ticker)} emiten sejak {sejak}…", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=pekerja) as ex:
        tugas = {ex.submit(ambil_daftar, cik): cik for cik in cik_ticker}
        for n, f in enumerate(as_completed(tugas), 1):
            cik = tugas[f]
            try:
                _, filing = f.result()
            except Exception as e:
                gagal_daftar.append(cik)
                logging.warning("Daftar filing CIK %s gagal: %s", cik, type(e).__name__)
                continue
            baru = [x for x in filing if x["akses"] not in sudah]
            # Emiten dengan pelaporan luar biasa banyak (mis. dana yang
            # melapor tiap hari) dibatasi supaya satu emiten tidak menghabiskan
            # seluruh anggaran permintaan; yang dibuang yang paling lama.
            baru = sorted(baru, key=lambda x: x["tanggal_lapor"], reverse=True)[:maks_per_emiten]
            daftar += [(cik, x) for x in baru]
            if n % 250 == 0:
                print(f"  daftar {n}/{len(cik_ticker)} ({time.monotonic() - mulai:.0f} detik), "
                      f"{len(daftar)} dokumen baru", file=sys.stderr)

    print(f"{len(daftar)} dokumen Form 4 baru akan diunduh "
          f"(± {len(daftar) / sec.BATAS_PER_DETIK / 60:.0f} menit).", file=sys.stderr)
    baris: list[dict] = []
    gagal_dokumen = 0

    def ambil_dokumen(cik: int, filing: dict):
        isi = klien.dokumen(cik, filing["akses"], filing["dokumen"])
        if isi is None:
            return []
        hasil = smartmoney.baca_form4(isi)
        for t in hasil:
            t["Akses"] = filing["akses"]
            t["Tanggal_Lapor"] = filing["tanggal_lapor"]
            # Emiten yang tidak mencantumkan simbol di Form 4-nya tetap bisa
            # dikenali dari CIK-nya.
            if not t.get("Ticker"):
                t["Ticker"] = cik_ticker[cik][0]
            t["CIK"] = t.get("CIK") or cik
        return hasil

    with ThreadPoolExecutor(max_workers=pekerja) as ex:
        tugas = [ex.submit(ambil_dokumen, cik, filing) for cik, filing in daftar]
        for n, f in enumerate(as_completed(tugas), 1):
            try:
                baris += f.result()
            except Exception as e:
                gagal_dokumen += 1
                logging.warning("Dokumen Form 4 gagal: %s", type(e).__name__)
            if n % 2000 == 0:
                print(f"  dokumen {n}/{len(daftar)} ({time.monotonic() - mulai:.0f} detik)",
                      file=sys.stderr)

    return baris, {"filing_baru": len(daftar), "transaksi_baru": len(baris),
                   "gagal_daftar_cik": len(gagal_daftar), "gagal_dokumen": gagal_dokumen}


# --- yfinance -------------------------------------------------------------

def dari_yahoo(tickers: list[str], pekerja: int = 8) -> pd.DataFrame:
    """Institusi, short interest, target analis, dan earnings surprise.

    Satu `Ticker.info` per emiten, plus riwayat earnings untuk surprise dan
    tanggal lapkeu berikutnya. Kegagalan satu emiten dicatat di kolom
    Catatan_SM dan tidak menghentikan yang lain: Yahoo rutin membatasi laju
    dan kehilangan 20 dari 1.500 baris tidak merusak peringkat.
    """
    import yfinance as yf

    def satu(t: str) -> dict:
        r: dict = {}
        saham = yf.Ticker(t)
        info = saham.info or {}
        for asal, tujuan in PETA_YAHOO.items():
            nilai = info.get(asal)
            if isinstance(nilai, (int, float)):
                r[tujuan] = float(nilai)
        for k in PECAHAN_YAHOO:
            if k in r:
                r[k] *= 100
        try:
            jadwal = saham.earnings_dates
        except Exception:
            jadwal = None
        if jadwal is not None and len(jadwal):
            r.update(dari_jadwal_earnings(jadwal))
        return r

    hasil: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=pekerja) as ex:
        tugas = {ex.submit(satu, t): t for t in tickers}
        for n, f in enumerate(as_completed(tugas), 1):
            t = tugas[f]
            try:
                hasil[t] = f.result()
            except Exception as e:
                hasil[t] = {"Catatan_SM": f"yahoo gagal: {type(e).__name__}"}
            if n % 250 == 0:
                print(f"  yahoo {n}/{len(tickers)}", file=sys.stderr)
    tabel = pd.DataFrame.from_dict(hasil, orient="index")
    tabel.index.name = "Ticker"
    return tabel


def dari_jadwal_earnings(jadwal: pd.DataFrame, sekarang: pd.Timestamp | None = None) -> dict:
    """Surprise kuartal terakhir (%), rata-rata empat kuartal, dan tanggal
    lapkeu berikutnya, dari tabel `Ticker.earnings_dates` yang berisi baris
    masa lalu maupun yang dijadwalkan."""
    df = jadwal.copy()
    df.index = pd.to_datetime(df.index, errors="coerce", utc=True)
    df = df[df.index.notna()].sort_index()
    sekarang = sekarang or pd.Timestamp.now(tz="UTC")

    kolom = {k.lower().replace(" ", ""): k for k in df.columns}
    kol_surprise = kolom.get("surprise(%)") or kolom.get("surprisepercent")
    r: dict = {}
    if kol_surprise:
        lalu = df[df.index <= sekarang][kol_surprise].dropna()
        if len(lalu):
            r["Surprise_Terakhir"] = float(lalu.iloc[-1])
            r["Surprise_Rata4Q"] = float(lalu.tail(4).mean())
            r["Surprise_Tanggal"] = lalu.index[-1].date().isoformat()
    depan = df[df.index > sekarang]
    if len(depan):
        r["Earnings_Berikut"] = depan.index[0].date().isoformat()
    return r


# --- perakitan ------------------------------------------------------------

def peta_cik_ticker(tickers, peta: Mapping[str, int],
                    lama: pd.DataFrame | None) -> dict[int, list[str]]:
    """CIK → daftar ticker universe yang memakainya.

    Dipakai dua kali: memilih emiten yang Form 4-nya diunduh, dan
    mengelompokkan transaksi yang sudah turun. Keduanya harus memakai peta
    yang sama, kalau tidak ada emiten yang diunduh tapi hasilnya tidak
    terpasang ke mana-mana.

    `data/smartmoney.csv` run sebelumnya jadi cadangan: pada `--lewati-form4`
    tidak ada koneksi ke EDGAR untuk mengambil peta yang hidup, dan sesekali
    ada ticker yang tidak terdaftar di berkas peta SEC padahal CIK-nya sudah
    diketahui dari run lalu.
    """
    cik_ticker: dict[int, list[str]] = {}
    lama_cik = (pd.to_numeric(lama["CIK"], errors="coerce")
                if lama is not None and "CIK" in lama.columns else None)
    for t in tickers:
        cik = peta.get(t)
        if cik is None and lama_cik is not None and t in lama_cik.index:
            nilai = lama_cik.loc[t]
            cik = int(nilai) if pd.notna(nilai) else None
        if cik is not None:
            cik_ticker.setdefault(int(cik), []).append(t)
    return cik_ticker


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ticker", nargs="+", help="Hanya ticker ini (untuk uji)")
    p.add_argument("--output", default=str(KELUARAN), help="Berkas CSV, atau - untuk cetak ke layar")
    p.add_argument("--pekerja", type=int, default=8, help="Unduhan paralel (batas laju SEC tetap 8/detik)")
    p.add_argument("--lewati-form4", action="store_true", help="Pakai data/insider.csv apa adanya")
    p.add_argument("--lewati-yahoo", action="store_true", help="Jangan ambil institusi/short/target")
    p.add_argument("--maks-filing-per-emiten", type=int, default=400,
                   help="Batas dokumen Form 4 baru yang diunduh per emiten per run")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    mulai = time.monotonic()
    hari_ini = date.today()

    uni = universe.muat()
    if a.ticker:
        pilih = [universe.normalisasi_ticker(t) for t in a.ticker]
        uni = uni.loc[[t for t in pilih if t in uni.index]]

    transaksi = muat_insider()
    meta_form4: dict = {"dilewati": True}
    peta: dict[str, int] = {}
    lama = pd.read_csv(KELUARAN, index_col="Ticker") if KELUARAN.exists() else None
    if not a.lewati_form4:
        klien = sec.KlienSEC()
        peta = klien.peta_cik()
    cik_ticker = peta_cik_ticker(uni.index, peta, lama)
    if not a.lewati_form4:
        sudah = set(transaksi["Akses"].astype(str)) if len(transaksi) else set()
        baris, meta_form4 = unduh_form4(klien, cik_ticker, sudah,
                                        hari_ini - timedelta(days=smartmoney.JENDELA_HARI),
                                        a.pekerja, a.maks_filing_per_emiten)
        if baris:
            baru = pd.DataFrame(baris).reindex(columns=smartmoney.KOLOM_INSIDER)
            transaksi = pd.concat([transaksi, baru], ignore_index=True)
        transaksi = smartmoney.buang_kedaluwarsa(transaksi, hari_ini)
        transaksi = transaksi.drop_duplicates(
            subset=["Akses", "Tanggal", "Kode", "Lembar", "Harga", "Pemilik_CIK"])
        transaksi = transaksi.sort_values(["Ticker", "Tanggal", "Akses"], kind="stable")

    ringkas = smartmoney.ringkas_insider(transaksi, cik_ticker, hari_ini)
    tabel = pd.DataFrame(index=uni.index).join(ringkas, how="left")
    tabel.index.name = "Ticker"
    if not a.lewati_form4:
        # Emiten tanpa transaksi pasar terbuka 90 hari terakhir memang nol,
        # bukan tidak diketahui — asal Form 4-nya ikut diambil run ini.
        for kolom, nol in (("Insider_Beli90H_JutaUSD", 0.0), ("Insider_Jual90H_JutaUSD", 0.0),
                           ("Insider_Net90H_JutaUSD", 0.0), ("Insider_Pembeli90H", 0),
                           ("Insider_Penjual90H", 0), ("Insider_Transaksi90H", 0),
                           ("Insider_Rencana90H", 0), ("Insider_ClusterBuy", False)):
            tabel[kolom] = tabel[kolom].fillna(nol)

    if not a.lewati_yahoo:
        print(f"Mengambil institusi, short interest, dan target analis {len(uni)} emiten dari Yahoo…",
              file=sys.stderr)
        yahoo = dari_yahoo(list(uni.index), a.pekerja)
        tabel = tabel.join(yahoo, how="left")
    elif lama is not None:
        tabel = tabel.join(lama[[k for k in lama.columns if k in PETA_YAHOO.values()]], how="left")

    if lama is not None and "Institusi_Pct" in lama:
        tabel["Institusi_Pct_Lalu"] = pd.to_numeric(lama["Institusi_Pct"], errors="coerce").reindex(tabel.index)
        tabel["Institusi_Delta"] = smartmoney.delta_snapshot(
            tabel.get("Institusi_Pct", pd.Series(index=tabel.index, dtype=float)),
            tabel["Institusi_Pct_Lalu"])

    riwayat = pd.read_csv(RIWAYAT_TARGET) if RIWAYAT_TARGET.exists() else None
    target = tabel.get("Target_Rata", pd.Series(index=tabel.index, dtype=float))
    tabel["Target_Revisi"], tabel["Target_Revisi_Umur"] = smartmoney.revisi_target(
        riwayat, target, hari_ini)

    tabel["CIK"] = tabel.index.map(lambda t: peta.get(t))
    if lama is not None and "CIK" in lama:
        tabel["CIK"] = tabel["CIK"].fillna(pd.to_numeric(lama["CIK"], errors="coerce").reindex(tabel.index))
    for kolom in KOLOM_KELUARAN:
        if kolom not in tabel:
            tabel[kolom] = None
    tabel = tabel[KOLOM_KELUARAN]

    net = pd.to_numeric(tabel["Insider_Net90H_JutaUSD"], errors="coerce")
    meta = {
        "diperbarui": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "versi_skema": VERSI_SKEMA,
        "jumlah_ticker": int(len(tabel)),
        "jendela_insider_hari": smartmoney.JENDELA_HARI,
        "form4": meta_form4,
        "transaksi_disimpan": int(len(transaksi)),
        "emiten_ada_transaksi_90h": int((pd.to_numeric(tabel["Insider_Transaksi90H"], errors="coerce") > 0).sum()),
        "cluster_buy": sorted(tabel.index[tabel["Insider_ClusterBuy"] == True]),  # noqa: E712
        "insider_beli_terbesar": sorted(
            net.nlargest(10).round(2).to_dict().items(), key=lambda x: -x[1]),
        "insider_jual_terbesar": sorted(
            net.nsmallest(10).round(2).to_dict().items(), key=lambda x: x[1]),
        "institusi_terisi": int(pd.to_numeric(tabel["Institusi_Pct"], errors="coerce").notna().sum()),
        "short_terisi": int(pd.to_numeric(tabel["Short_PctFloat"], errors="coerce").notna().sum()),
        "target_terisi": int(pd.to_numeric(tabel["Target_Rata"], errors="coerce").notna().sum()),
        "target_revisi_terisi": int(pd.to_numeric(tabel["Target_Revisi"], errors="coerce").notna().sum()),
        "earnings_terisi": int(tabel["Earnings_Berikut"].notna().sum()),
        "durasi_detik": round(time.monotonic() - mulai, 1),
    }
    print(json.dumps(meta, indent=2, ensure_ascii=False), file=sys.stderr)

    if a.output == "-":
        with pd.option_context("display.max_columns", 80, "display.width", 250):
            print(tabel.T.to_string())
        return 0

    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tabel.sort_index().to_csv(out, encoding="utf-8")
    if out.resolve() == KELUARAN.resolve():
        if not a.lewati_form4:
            transaksi.to_csv(INSIDER, index=False, encoding="utf-8")
        simpan_riwayat_target(target, hari_ini)
        META.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(tabel)} baris → {out} ({meta['durasi_detik']:.0f} detik)", file=sys.stderr)
    return 0


def simpan_riwayat_target(target: pd.Series, hari_ini: date):
    """Satu baris per emiten per pekan, supaya revisi target 3 bulan bisa
    dihitung tanpa sumber berbayar. Berkasnya hanya menyimpan satu tahun."""
    target = pd.to_numeric(target, errors="coerce").dropna()
    if target.empty:
        return
    baru = pd.DataFrame({"Tanggal": hari_ini.isoformat(), "Ticker": target.index,
                         "Target_Rata": target.round(2).values})
    lama = pd.read_csv(RIWAYAT_TARGET) if RIWAYAT_TARGET.exists() else None
    gabung = pd.concat([lama, baru], ignore_index=True) if lama is not None else baru
    tgl = pd.to_datetime(gabung["Tanggal"], errors="coerce")
    gabung = gabung[tgl.notna() & (tgl >= pd.Timestamp(hari_ini) - pd.Timedelta(days=370))]
    gabung = gabung.drop_duplicates(subset=["Tanggal", "Ticker"], keep="last")
    gabung.sort_values(["Tanggal", "Ticker"]).to_csv(RIWAYAT_TARGET, index=False, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
