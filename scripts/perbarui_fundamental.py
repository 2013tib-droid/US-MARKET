#!/usr/bin/env python3
"""Perbarui data/fundamental.csv dari SEC EDGAR (XBRL companyfacts).

Satu permintaan per emiten (± 1.500, dibatasi 8 per detik), ditambah
pencarian teks penuh untuk going concern dan restatement. Butuh variabel
lingkungan SEC_USER_AGENT berisi nama dan email.

    SEC_USER_AGENT="US-MARKET screener nama@email.com" python scripts/perbarui_fundamental.py
    python scripts/perbarui_fundamental.py --ticker AAPL XOM BRK-B --output -    # uji, cetak saja

Run malam (screener.py) membaca berkas ini; valuasi dan Altman Z dihitung di
sana dengan harga terbaru.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from usmarket import VERSI_SKEMA, fundamental, sec, universe  # noqa: E402

AKAR = Path(__file__).resolve().parent.parent
KELUARAN = AKAR / "data" / "fundamental.csv"
META = AKAR / "data" / "fundamental_meta.json"

# Hanya kalimat baku paragraf going concern di laporan auditor ("…that raise
# substantial doubt about its ability to continue as a going concern").
# Frasa lain diuji 15 Sep 2026 dan hanya menghasilkan salah tangkap di
# universe: "…the Company's ability…" dan "conditions raise substantial doubt"
# adalah kalimat kebijakan akuntansi ASC 205-40 yang ada di laporan emiten
# sehat (menangkap AOSL, WOR, WTFC, TKO); "raises … its ability" menangkap
# IIPR karena membahas penyewanya. Bahkan frasa ini tidak bisa membedakan
# "keraguan … sudah teratasi", jadi flag-nya peringatan untuk dibaca, bukan
# alasan otomatis untuk menghindari.
FRASA_GOING_CONCERN = [
    '"raise substantial doubt about its ability to continue as a going concern"',
]
# Judul item 4.02 ("Non-Reliance on Previously Issued Financial Statements…")
# ditulis dengan banyak variasi dan hanya menemukan 5 dokumen setahun di
# seluruh EDGAR; "Item 4.02" menemukan 106. Hasilnya tetap disaring dengan
# daftar item resmi 8-K-nya, jadi 8-K yang sekadar menyebut item itu tidak ikut.
FRASA_RESTATEMENT = '"Item 4.02"'

INTI = ["Pendapatan", "Laba", "OCF", "Aset", "Ekuitas", "Saham"]


def saham_dari_yahoo(tickers: list[str]) -> dict[str, float]:
    """Cadangan jumlah saham untuk emiten yang tidak melaporkannya secara
    non-dimensional di XBRL (multi-kelas seperti BRK-B). Yang diambil adalah
    saham setara kelas ticker itu: market cap Yahoo ÷ harga terakhirnya,
    sehingga harga ticker × angka ini = market cap seluruh perusahaan."""
    import yfinance as yf
    hasil = {}
    for t in tickers:
        try:
            fi = yf.Ticker(t).fast_info
            mcap, harga = fi["marketCap"], fi["lastPrice"]
            if mcap and harga:
                hasil[t] = float(mcap) / float(harga)
        except Exception as e:  # jaringan, ticker tidak dikenal, dsb.
            print(f"  {t}: cadangan Yahoo gagal ({type(e).__name__})", file=sys.stderr)
    return hasil


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ticker", nargs="+", help="Hanya ticker ini (untuk uji)")
    p.add_argument("--output", default=str(KELUARAN), help="Berkas CSV, atau - untuk cetak ke layar")
    p.add_argument("--pekerja", type=int, default=8, help="Unduhan paralel (batas laju tetap 8/detik)")
    p.add_argument("--tanpa-yahoo", action="store_true", help="Jangan pakai cadangan jumlah saham dari Yahoo")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    mulai = time.monotonic()

    uni = universe.muat()
    if a.ticker:
        uni = uni.loc[[universe.normalisasi_ticker(t) for t in a.ticker if universe.normalisasi_ticker(t) in uni.index]]
    klien = sec.KlienSEC()
    peta = klien.peta_cik()

    cik_ticker: dict[int, list[str]] = {}
    baris: dict[str, dict] = {}
    for t in uni.index:
        cik = peta.get(t)
        if cik is None:
            baris[t] = {"Catatan": "ticker tidak ada di peta CIK SEC"}
        else:
            cik_ticker.setdefault(cik, []).append(t)
    pendahulu = {peta[t]: c for t, c in fundamental.CIK_PENDAHULU.items() if t in peta}

    def kerja(cik: int) -> tuple[int, dict]:
        keuangan = any(uni.loc[t, "Sektor"] == "Financials" for t in cik_ticker[cik])
        facts = klien.companyfacts(cik)
        if facts is None:
            return cik, {"Catatan": "tidak ada data XBRL di SEC"}
        if cik in pendahulu:
            lama = klien.companyfacts(pendahulu[cik])
            if lama:
                facts = fundamental.gabung_facts(facts, lama)
        r = fundamental.ekstrak(facts, keuangan=keuangan)
        r["Nama_SEC"] = facts.get("entityName", "")
        if cik in pendahulu:
            r["CIK_Pendahulu"] = pendahulu[cik]
        return cik, r

    print(f"Mengunduh companyfacts {len(cik_ticker)} CIK untuk {len(uni)} ticker…", file=sys.stderr)
    selesai = 0
    with ThreadPoolExecutor(max_workers=a.pekerja) as ex:
        tugas = {ex.submit(kerja, cik): cik for cik in cik_ticker}
        for f in as_completed(tugas):
            cik = tugas[f]
            try:
                _, r = f.result()
            except Exception as e:
                # Satu emiten yang rusak tidak boleh menghentikan 1.500 lainnya.
                r = {"Catatan": f"gagal: {type(e).__name__}: {str(e)[:80]}"}
            for t in cik_ticker[cik]:
                baris[t] = {"CIK": cik, **r}
            selesai += 1
            if selesai % 250 == 0:
                print(f"  {selesai}/{len(cik_ticker)} ({time.monotonic() - mulai:.0f} detik)", file=sys.stderr)

    tabel = pd.DataFrame.from_dict(baris, orient="index")
    # Kolom yang dipakai di bawah harus ada meski tidak satu emiten pun mengisinya.
    for kolom in ("CIK", "Catatan", "Saham", "Laba", "Tag_Saham", "Tanggal_Saham"):
        if kolom not in tabel:
            tabel[kolom] = None
    tabel.index.name = "Ticker"

    # Going concern & restatement: satu pencarian untuk seluruh EDGAR, lalu
    # dicocokkan dengan CIK universe.
    sejak = date.today() - timedelta(days=400)
    gc: dict[int, str] = {}
    for frasa in FRASA_GOING_CONCERN:
        for cik, tgl in klien.cari_cik(frasa, "10-K,10-K/A,10-Q,10-Q/A", sejak).items():
            gc[cik] = max(tgl, gc.get(cik, ""))
    rs = klien.cari_cik(FRASA_RESTATEMENT, "8-K,8-K/A", sejak, item="4.02")
    cik_kolom = pd.to_numeric(tabel["CIK"], errors="coerce")
    tabel["GoingConcern"] = cik_kolom.map(lambda c: gc.get(int(c), "") if pd.notna(c) else "")
    tabel["Restatement"] = cik_kolom.map(lambda c: rs.get(int(c), "") if pd.notna(c) else "")

    if not a.tanpa_yahoo:
        kosong = tabel.index[tabel["Saham"].isna() & tabel["Laba"].notna()]
        if len(kosong):
            print(f"Jumlah saham kosong di XBRL untuk {len(kosong)} ticker; mengambil dari Yahoo…", file=sys.stderr)
            cadangan = saham_dari_yahoo(list(kosong))
            for t, v in cadangan.items():
                tabel.loc[t, "Saham"] = v
                tabel.loc[t, "Tag_Saham"] = "yahoo:marketCap/lastPrice"
                tabel.loc[t, "Tanggal_Saham"] = date.today().isoformat()

    detik = time.monotonic() - mulai
    nonkeu = uni.loc[tabel.index, "Sektor"] != "Financials"
    terisi = {m: int(tabel.loc[nonkeu, m].notna().sum()) if m in tabel else 0 for m in INTI}
    pendek = sorted(tabel.index[tabel["Catatan"].fillna("").astype(str).str.contains("disetahunkan")])
    meta = {
        "diperbarui": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "versi_skema": VERSI_SKEMA,
        "jumlah_ticker": int(len(tabel)),
        "jumlah_cik": len(cik_ticker),
        "nonkeuangan": int(nonkeu.sum()),
        "inti_terisi_nonkeuangan": terisi,
        "going_concern": sorted(tabel.index[tabel["GoingConcern"] != ""]),
        "restatement": sorted(tabel.index[tabel["Restatement"] != ""]),
        "histori_pendek_kandidat_cik_pendahulu": pendek,
        "durasi_detik": round(detik, 1),
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
        META.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(tabel)} baris → {out} ({detik:.0f} detik)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
