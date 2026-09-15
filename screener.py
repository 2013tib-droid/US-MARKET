#!/usr/bin/env python3
"""Screener saham AS, Fase 1: universe S&P 1500 + Nasdaq-100, harga harian,
faktor Momentum dan Low-Vol, indikator teknikal, dan trend template.

Pola pakainya sama dengan screener.py di repo Screening-Saham: satu run
penuh menarik data dan menyimpan tabel lengkap, lalu saringan-saringan
dijalankan ulang dari CSV itu dengan --dari-csv tanpa menarik apa pun.

Contoh:
    python screener.py                                  # universe penuh → hasil/semua.csv
    python screener.py --ticker AAPL MSFT NVDA          # ad-hoc, tidak menulis berkas
    python screener.py --dari-csv hasil/semua.csv --likuid --trend-template --tanpa-flag
    python screener.py --dari-csv hasil/semua.csv --min-z-lowvol 1 --sektor Utilities
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from usmarket import VERSI_SKEMA, harga, kalender, tabel, universe, valuasi

AKAR = Path(__file__).resolve().parent
KELUARAN_DEFAULT = AKAR / "hasil" / "semua.csv"
FUNDAMENTAL = AKAR / "data" / "fundamental.csv"

KOLOM_TAMPIL = ["Sektor", "Harga", "MCap_MiliarUSD", "PE_TTM", "EV_EBITDA", "ROIC", "F_Score",
                "Z_Value", "Z_Quality", "Z_Momentum", "Z_LowVol", "RS_Rating", "TrendTemplate",
                "Keyakinan", "Flag"]


def argumen(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sumber = p.add_argument_group("sumber data")
    sumber.add_argument("--dari-csv", type=Path, help="Saring ulang CSV hasil run sebelumnya, tanpa unduh")
    sumber.add_argument("--tickers", type=Path, nargs="+", help="Berkas daftar ticker (.txt atau .csv berkolom Ticker)")
    sumber.add_argument("--ticker", nargs="+", help="Ticker ad-hoc, mis. --ticker AAPL BRK-B")
    sumber.add_argument("--periode", default="2y", help="Panjang histori harga (default 2y)")

    f = p.add_argument_group("saringan")
    f.add_argument("--likuid", action="store_true", help="Hanya yang lolos likuiditas (harga ≥ $5, nilai ≥ $10 juta/hari)")
    f.add_argument("--min-nilai", type=float, help="Nilai transaksi rata-rata 20 hari minimal (juta USD)")
    f.add_argument("--min-harga", type=float, help="Harga minimal (USD)")
    f.add_argument("--trend-template", action="store_true", help="Hanya yang lolos trend template")
    f.add_argument("--di-atas-ma200", action="store_true", help="Harga di atas MA200")
    f.add_argument("--min-z-momentum", type=float, help="Z_Momentum minimal (0 = rata-rata sektornya)")
    f.add_argument("--min-z-lowvol", type=float, help="Z_LowVol minimal")
    f.add_argument("--min-rs-rating", type=float, help="RS rating minimal (1–99)")
    f.add_argument("--min-rsi", type=float)
    f.add_argument("--max-rsi", type=float)
    f.add_argument("--min-volspike", type=float, help="Volume terakhir ÷ rata-rata 20 hari sebelumnya")
    f.add_argument("--max-beta", type=float)
    f.add_argument("--sektor", nargs="+", help="Hanya sektor tertentu (nama GICS, mis. 'Information Technology')")
    f.add_argument("--indeks", nargs="+", choices=["SP500", "SP400", "SP600", "NDX", "WATCH"])
    f.add_argument("--min-z-value", type=float, help="Z_Value minimal")
    f.add_argument("--min-z-quality", type=float, help="Z_Quality minimal")
    f.add_argument("--min-fscore", type=float, help="Piotroski F-score minimal (0–9)")
    f.add_argument("--min-roic", type=float, help="ROIC minimal (%%)")
    f.add_argument("--max-akrual", type=float, help="Akrual maksimal (%% aset)")
    f.add_argument("--max-pe", type=float, help="P/E TTM maksimal (laba negatif otomatis gugur)")
    f.add_argument("--max-ev-ebitda", type=float, help="EV/EBITDA maksimal")
    f.add_argument("--min-fcf-yield", type=float, help="FCF yield minimal (%%)")
    f.add_argument("--min-mcap", type=float, help="Market cap minimal (miliar USD)")
    f.add_argument("--min-keyakinan", type=float, help="Keyakinan data minimal (0–100)")
    f.add_argument("--tanpa-flag", action="store_true", help="Buang semua baris yang punya flag apa pun")
    f.add_argument("--tanpa-flag-berat", action="store_true",
                   help="Buang baris dengan flag berat: " + ", ".join(sorted(valuasi.FLAG_BERAT)))

    k = p.add_argument_group("keluaran")
    k.add_argument("--urut", default="Z_Momentum", help="Kolom pengurut (default Z_Momentum, terbesar dulu)")
    k.add_argument("--naik", action="store_true", help="Urutkan dari yang terkecil")
    k.add_argument("--top", type=int, help="Tampilkan dan simpan N baris teratas saja")
    k.add_argument("--output", type=Path, help="Simpan hasil ke CSV. Run penuh tanpa --output menulis hasil/semua.csv")
    k.add_argument("--meta", type=Path, help="Tulis ringkasan run (waktu, tanggal data, jumlah) ke JSON")
    k.add_argument("--diam", action="store_true", help="Jangan cetak tabel ke layar")
    return p.parse_args(argv)


def saring(df: pd.DataFrame, a) -> pd.DataFrame:
    def benar(kolom):
        # CSV menyimpan boolean sebagai teks; NaN dianggap tidak lolos.
        return df[kolom].map(lambda v: str(v).strip().lower() == "true")

    m = pd.Series(True, index=df.index)
    if a.likuid:
        m &= benar("LolosLikuiditas")
    if a.trend_template:
        m &= benar("TrendTemplate")
    if a.di_atas_ma200:
        m &= df["Harga"] > df["MA200"]
    batas = [("min_nilai", "Nilai20H_JutaUSD", ">="), ("min_harga", "Harga", ">="),
             ("min_z_momentum", "Z_Momentum", ">="), ("min_z_lowvol", "Z_LowVol", ">="),
             ("min_rs_rating", "RS_Rating", ">="), ("min_rsi", "RSI14", ">="),
             ("max_rsi", "RSI14", "<="), ("min_volspike", "VolSpike", ">="),
             ("max_beta", "Beta", "<="), ("min_z_value", "Z_Value", ">="),
             ("min_z_quality", "Z_Quality", ">="), ("min_fscore", "F_Score", ">="),
             ("min_roic", "ROIC", ">="), ("max_akrual", "Akrual", "<="), ("max_pe", "PE_TTM", "<="),
             ("max_ev_ebitda", "EV_EBITDA", "<="), ("min_fcf_yield", "FCF_Yield", ">="),
             ("min_mcap", "MCap_MiliarUSD", ">="), ("min_keyakinan", "Keyakinan", ">=")]
    for nama, kolom, op in batas:
        nilai = getattr(a, nama)
        if nilai is not None:
            m &= (df[kolom] >= nilai) if op == ">=" else (df[kolom] <= nilai)
    if a.sektor:
        m &= df["Sektor"].isin(a.sektor)
    if a.indeks:
        m &= df["Indeks"].fillna("").map(lambda s: any(i in s.split(";") for i in a.indeks))
    if a.tanpa_flag:
        m &= df["Flag"].fillna("").eq("")
    if a.tanpa_flag_berat:
        m &= df["Flag"].fillna("").map(lambda s: not (set(s.split(";")) & valuasi.FLAG_BERAT))
    return df[m]


def universe_dari_argumen(a) -> pd.DataFrame:
    if a.ticker or a.tickers:
        daftar = [universe.normalisasi_ticker(t) for t in (a.ticker or [])]
        for path in a.tickers or []:
            daftar += universe.baca_daftar_ticker(path)
        # Nama & sektor diambil dari universe yang di-commit bila tickernya ada di sana.
        try:
            lengkap = universe.muat()
        except FileNotFoundError:
            lengkap = pd.DataFrame(columns=["Nama", "Sektor", "Industri", "Indeks"])
        ada = [t for t in dict.fromkeys(daftar) if t in lengkap.index]
        lain = [t for t in dict.fromkeys(daftar) if t not in lengkap.index]
        tambahan = pd.DataFrame({"Nama": "", "Sektor": universe.SEKTOR_TAK_DIKETAHUI,
                                 "Industri": "", "Indeks": ""}, index=pd.Index(lain, name="Ticker"))
        return pd.concat([lengkap.loc[ada], tambahan])
    return universe.muat()


def fundamental_diperbarui() -> str | None:
    meta = FUNDAMENTAL.with_name("fundamental_meta.json")
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("diperbarui")
    except (OSError, ValueError):
        return None


def tulis_meta(path: Path, hasil: pd.DataFrame, panel: harga.Panel, detik: float):
    flag = hasil["Flag"].fillna("")
    meta = {
        "diperbarui": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tanggal_data": panel.tutup.index[-1].date().isoformat(),
        "bar_dibuang_belum_final": panel.bar_dibuang,
        "bar_ditambal_dari_data_per_jam": panel.bar_ditambal,
        # Bila Yahoo belum menyediakan penutupan sesi final terakhir (dan
        # penambal pun gagal), tabel tertinggal satu sesi. Dashboard
        # menampilkannya sebagai peringatan, bukan diam-diam.
        "sesi_final_terakhir": kalender.sesi_final_terakhir().isoformat(),
        "tertinggal_sesi": panel.tutup.index[-1].date() < kalender.sesi_final_terakhir(),
        "versi_skema": VERSI_SKEMA,
        "fase": 2,
        "jumlah_emiten": int(len(hasil)),
        "gagal_unduh": int(flag.str.contains("GAGAL-UNDUH").sum()),
        "faktor_terisi": int((hasil["Z_Momentum"].notna() & hasil["Z_LowVol"].notna()).sum()),
        "lolos_likuiditas": int((hasil["LolosLikuiditas"] == True).sum()),  # noqa: E712
        "lolos_trend_template": int((hasil["TrendTemplate"] == True).sum()),  # noqa: E712
        "value_terisi": int(hasil["Z_Value"].notna().sum()),
        "quality_terisi": int(hasil["Z_Quality"].notna().sum()),
        "fundamental_diperbarui": fundamental_diperbarui(),
        "durasi_detik": round(detik, 1),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta


def main(argv=None) -> int:
    a = argumen(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    mulai = time.monotonic()
    panel = None

    if a.dari_csv:
        hasil = pd.read_csv(a.dari_csv, index_col="Ticker")
    else:
        uni = universe_dari_argumen(a)
        print(f"Mengunduh harga {len(uni)} ticker + {tabel.BENCHMARK} ({a.periode})…", file=sys.stderr)
        panel = harga.unduh(list(uni.index) + [tabel.BENCHMARK], periode=a.periode)
        if panel.bar_dibuang:
            print(f"Bar {panel.bar_dibuang} dibuang: sesinya belum tuntas.", file=sys.stderr)
        if panel.bar_ditambal:
            print(f"Bar {panel.bar_ditambal} tidak lengkap dari Yahoo; penutupan diambil dari data per jam.",
                  file=sys.stderr)
        if panel.tutup.index[-1].date() < kalender.sesi_final_terakhir():
            print(f"PERHATIAN: data berhenti di {panel.tutup.index[-1].date()}, padahal sesi final "
                  f"terakhir {kalender.sesi_final_terakhir()}.", file=sys.stderr)
        fund = pd.read_csv(FUNDAMENTAL, index_col="Ticker") if FUNDAMENTAL.exists() else None
        if fund is None:
            print(f"{FUNDAMENTAL.name} belum ada: kolom valuasi & kualitas kosong. "
                  "Jalankan scripts/perbarui_fundamental.py.", file=sys.stderr)
        hasil = tabel.bangun(uni, panel, fund)
        if len(uni) < 300:
            print(f"PERHATIAN: Z-score dan RS rating dihitung terhadap {len(uni)} ticker ini saja, "
                  "bukan terhadap universe. Untuk peringkat yang bermakna, jalankan run penuh lalu "
                  "saring dengan --dari-csv hasil/semua.csv.", file=sys.stderr)
        print(f"Selesai dalam {time.monotonic() - mulai:.0f} detik. "
              f"Data sampai {panel.tutup.index[-1].date()}; {len(panel.gagal)} ticker gagal diunduh.",
              file=sys.stderr)

    penuh = hasil
    hasil = saring(hasil, a)
    if a.urut in hasil:
        hasil = hasil.sort_values(a.urut, ascending=a.naik, na_position="last")
    if a.top:
        hasil = hasil.head(a.top)

    output = a.output
    # Run penuh atas universe default selalu disimpan; run ad-hoc (--ticker)
    # tidak, supaya tidak menimpa tabel lengkap dengan tiga baris.
    if output is None and not a.dari_csv and not (a.ticker or a.tickers):
        output = KELUARAN_DEFAULT
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        hasil.to_csv(output, encoding="utf-8")
        print(f"{len(hasil)} baris disimpan ke {output}", file=sys.stderr)
    if a.meta and panel is not None:
        tulis_meta(a.meta, penuh, panel, time.monotonic() - mulai)

    if not a.diam:
        with pd.option_context("display.max_rows", 60, "display.width", 200,
                               "display.max_columns", 20):
            tampil = hasil[[k for k in KOLOM_TAMPIL if k in hasil]].head(60).copy()
            tampil["Flag"] = tampil["Flag"].fillna("")
            print(tampil.to_string() if len(hasil) else "Tidak ada saham yang lolos saringan.")
            if len(hasil) > 60:
                print(f"… {len(hasil) - 60} baris lagi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
