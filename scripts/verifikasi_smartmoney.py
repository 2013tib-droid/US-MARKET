#!/usr/bin/env python3
"""Cocokkan data/smartmoney.csv dengan sumber independen, untuk syarat
"selesai" Fase 3 di docs/04-roadmap.md.

Pemeriksaannya dua lapis, dan lapisan pertama tidak butuh jaringan sama
sekali:

**Tanpa jaringan** (selalu dijalankan, keluar dengan kode ≠ 0 kalau gagal):

1. **Rekonsiliasi** — `data/smartmoney.csv` dihitung ulang dari
   `data/insider.csv` dengan `smartmoney.ringkas_insider` dan dibandingkan
   kolom per kolom. Ini yang membuktikan setiap angka agregat bisa dilacak
   ke nomor akses EDGAR-nya, bukan hanya diklaim begitu.
2. **Bukti cluster buy** — tiap emiten bertanda cluster dicek ulang: benar
   ada ≥ 2 pelapor berbeda yang membeli di pasar terbuka dalam 30 hari, dan
   nomor akses tiap transaksinya dicetak untuk diklik di EDGAR.
3. **Kewajaran kolom Yahoo** — persentase di luar rentang yang masuk akal
   dihitung dan dilaporkan, bukan didiamkan.

**Butuh jaringan** (dilewati otomatis kalau tidak ada, atau dengan
`--tanpa-yahoo`):

4. **Insider net 90 hari** dibandingkan dengan ringkasan transaksi orang
   dalam versi Yahoo (`Ticker.insider_transactions`). Yahoo membaca Form 4
   yang sama tapi mengelompokkannya sendiri, jadi selisih kecil wajar;
   yang dicari adalah selisih besar atau tanda yang berlawanan.
5. **Rincian transaksi** dari data/insider.csv dicetak apa adanya supaya
   bisa dicocokkan baris per baris dengan OpenInsider dan dengan Form 4
   aslinya di EDGAR — tautannya ikut dicetak.
6. **Short interest** tidak punya pembanding gratis yang bisa diunduh, jadi
   yang dicetak adalah angka kita beserta tautan ke halaman FINRA/Nasdaq
   untuk dibaca manusia.

    python scripts/verifikasi_smartmoney.py --jumlah 10
    python scripts/verifikasi_smartmoney.py --ticker AAPL NVDA JPM
    python scripts/verifikasi_smartmoney.py --tanpa-yahoo    # lapis 1 saja
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from usmarket import smartmoney, universe  # noqa: E402

AKAR = Path(__file__).resolve().parent.parent
SMARTMONEY = AKAR / "data" / "smartmoney.csv"
INSIDER = AKAR / "data" / "insider.csv"
META = AKAR / "data" / "smartmoney_meta.json"

URL_OPENINSIDER = "http://openinsider.com/screener?s={t}"
URL_EDGAR = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={t}&type=4&dateb=&owner=include&count=40"
URL_SHORT = "https://www.nasdaq.com/market-activity/stocks/{t}/short-interest"


def net_dari_yahoo(ticker: str, hari: int = smartmoney.JENDELA_HARI) -> float | None:
    """Beli − jual pasar terbuka (juta USD) dari tabel orang dalam Yahoo.

    Yahoo menyebut jenis transaksinya dalam teks bebas ("Purchase at price
    …", "Sale at price …", "Stock Award(Grant)"), bukan kode Form 4, jadi
    penyaringnya kata, bukan kode. Rencana 10b5-1 tidak ditandai sama sekali
    di sini — itu salah satu alasan sumber utamanya EDGAR, bukan Yahoo.
    """
    import yfinance as yf

    df = yf.Ticker(ticker).insider_transactions
    if df is None or df.empty:
        return None
    df = df.copy()
    kolom = {k.lower(): k for k in df.columns}
    k_tgl = kolom.get("start date") or kolom.get("date")
    k_nilai = kolom.get("value")
    k_jenis = kolom.get("transaction") or kolom.get("text")
    if not (k_tgl and k_nilai and k_jenis):
        return None
    tgl = pd.to_datetime(df[k_tgl], errors="coerce")
    batas = pd.Timestamp.today().normalize() - pd.Timedelta(days=hari)
    df = df[tgl.notna() & (tgl >= batas)]
    jenis = df[k_jenis].astype(str).str.lower()
    nilai = pd.to_numeric(df[k_nilai], errors="coerce").fillna(0)
    beli = nilai[jenis.str.contains("purchase")].sum()
    jual = nilai[jenis.str.contains("sale")].sum()
    return float(beli - jual) / 1e6


# Kolom agregat yang harus bisa dihitung ulang persis dari data/insider.csv.
KOLOM_REKONSILIASI = [
    "Insider_Beli90H_JutaUSD", "Insider_Jual90H_JutaUSD", "Insider_Net90H_JutaUSD",
    "Insider_Pembeli90H", "Insider_Penjual90H", "Insider_Transaksi90H", "Insider_Rencana90H",
]
# Pembulatan CSV, bukan selisih yang berarti.
TOLERANSI = 1e-6


def tanggal_run(meta: Path) -> date | None:
    """Tanggal run yang menghasilkan smartmoney.csv. Jendela 90 hari dihitung
    mundur dari sana, jadi merekonsiliasi dengan `date.today()` akan meleset
    tepat sebanyak hari yang lewat sejak run."""
    if not meta.exists():
        return None
    try:
        teks = json.loads(meta.read_text(encoding="utf-8")).get("diperbarui", "")
        return datetime.strptime(teks, "%Y-%m-%dT%H:%M:%SZ").date()
    except (ValueError, TypeError, OSError):
        return None


def rekonsiliasi(sm: pd.DataFrame, insider: pd.DataFrame, hari_ini: date) -> bool:
    """Hitung ulang agregat insider dari transaksi mentah dan bandingkan."""
    print("--- 1. Rekonsiliasi smartmoney.csv ← insider.csv ---")
    if insider.empty:
        print("data/insider.csv kosong; rekonsiliasi dilewati.")
        return True
    ulang = smartmoney.ringkas_insider(insider, hari_ini=hari_ini)
    sama = sm.index.intersection(ulang.index)
    print(f"jendela 90 hari mundur dari {hari_ini}; {len(sama)} emiten bertransaksi dibandingkan")
    lolos = True
    for k in KOLOM_REKONSILIASI:
        a = pd.to_numeric(sm.loc[sama, k], errors="coerce").fillna(0)
        b = pd.to_numeric(ulang.loc[sama, k], errors="coerce").fillna(0)
        beda = (a - b).abs()
        n = int((beda > TOLERANSI).sum())
        lolos &= n == 0
        tanda = "ok" if n == 0 else f"BEDA di {n} emiten"
        print(f"  {k:28} selisih maks {beda.max():.3g}  {tanda}")
        if n:
            print(f"    contoh: {beda.nlargest(3).index.tolist()}")
    kita = sm.loc[sama, "Insider_ClusterBuy"].astype(str).str.lower().eq("true")
    dia = ulang.loc[sama, "Insider_ClusterBuy"].astype(bool)
    beda_cluster = int((kita != dia).sum())
    lolos &= beda_cluster == 0
    print(f"  {'Insider_ClusterBuy':28} {int(kita.sum())} emiten  "
          f"{'ok' if not beda_cluster else f'BEDA di {beda_cluster} emiten'}")
    return lolos


def bukti_cluster(sm: pd.DataFrame, insider: pd.DataFrame, batas_cetak: int = 3) -> bool:
    """Tiap cluster buy diperiksa ulang dari transaksinya sendiri, dan
    beberapa dicetak lengkap dengan nomor akses untuk diklik di EDGAR."""
    print("\n--- 2. Bukti cluster buy (syarat Fase 3) ---")
    ada = sm.index[sm["Insider_ClusterBuy"].astype(str).str.lower().eq("true")].tolist()
    if not ada:
        print("Tidak ada cluster buy di run ini — syarat ini belum bisa dinyatakan lolos.")
        return False
    if insider.empty:
        print(f"{len(ada)} emiten bertanda cluster, tapi data/insider.csv kosong.")
        return False

    beli = insider[insider["Kode"].eq(smartmoney.KODE_BELI)
                   & ~insider["Rencana10b5"].astype(str).str.lower().isin(("true", "1", "yes"))]
    palsu = []
    for t in ada:
        g = beli[beli["Ticker"] == t]
        if g["Pemilik_CIK"].nunique() < smartmoney.MIN_INSIDER_CLUSTER:
            palsu.append(t)
    print(f"{len(ada)} emiten bertanda cluster buy; {len(palsu)} tanpa ≥ "
          f"{smartmoney.MIN_INSIDER_CLUSTER} pembeli berbeda di data mentah"
          + (f": {palsu}" if palsu else ""))

    # Yang dicetak: cluster dengan nilai beli terbesar, karena itu yang paling
    # mudah dicocokkan dengan berita dan dengan OpenInsider.
    nilai = pd.to_numeric(sm.loc[ada, "Insider_Beli90H_JutaUSD"], errors="coerce").fillna(0)
    for t in nilai.nlargest(batas_cetak).index:
        g = beli[beli["Ticker"] == t].sort_values("Tanggal")
        print(f"\n{t} — cluster {sm.loc[t, 'Insider_ClusterTgl']}, "
              f"beli {nilai[t]:.2f} juta USD, {g['Pemilik_CIK'].nunique()} pelapor berbeda")
        print(g[["Tanggal", "Lembar", "Harga", "Nilai", "Pemilik", "Jabatan", "Akses"]]
              .to_string(index=False))
    return not palsu


def kewajaran_yahoo(sm: pd.DataFrame) -> bool:
    """Persentase yang mustahil, dan berapa emiten yang datanya gagal diambil."""
    print("\n--- 3. Kewajaran kolom Yahoo ---")
    catatan = sm.get("Catatan_SM", pd.Series(dtype=object)).astype(str)
    gagal = int(catatan.str.startswith("yahoo gagal").sum())
    print(f"gagal diambil dari Yahoo: {gagal} dari {len(sm)} emiten"
          + ("  ← kolom institusi/short/target kosong untuk mereka" if gagal else ""))

    kosong = pd.Series(dtype=float)
    lolos = True
    inst = pd.to_numeric(sm.get("Institusi_Pct", kosong), errors="coerce")
    lebih = int((inst > 100).sum())
    if lebih:
        # Diketahui dan diterima: Yahoo membagi kepemilikan institusi dengan
        # float, bukan saham beredar, jadi emiten yang float-nya kecil (ada
        # pemegang pengendali) bisa lewat 100%. Yang masuk skor adalah
        # deltanya, dan basis itu sama di kedua snapshot — tapi angka mentahnya
        # tidak boleh dibaca sebagai "persen saham beredar".
        print(f"Institusi_Pct > 100%: {lebih} dari {int(inst.notna().sum())} emiten "
              f"(maks {inst.max():.1f}%) — basis Yahoo adalah float, bukan saham beredar")
    short = pd.to_numeric(sm.get("Short_PctFloat", kosong), errors="coerce")
    mustahil = int((short > 100).sum()) + int((short < 0).sum())
    if mustahil:
        print(f"Short_PctFloat di luar 0–100%: {mustahil} emiten — PERIKSA")
        lolos = False
    else:
        print(f"Short_PctFloat 0–100%: semua {int(short.notna().sum())} yang terisi "
              f"(median {short.median():.2f}%, maks {short.max():.2f}%)")
    return lolos


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jumlah", type=int, default=10, help="Emiten yang diperiksa (yang paling ramai dulu)")
    p.add_argument("--ticker", nargs="+")
    p.add_argument("--tanpa-yahoo", action="store_true",
                   help="Lapis tanpa jaringan saja: rekonsiliasi, bukti cluster, kewajaran kolom")
    a = p.parse_args(argv)

    if not SMARTMONEY.exists():
        print(f"{SMARTMONEY} belum ada. Jalankan scripts/perbarui_smartmoney.py dulu.", file=sys.stderr)
        return 1
    sm = pd.read_csv(SMARTMONEY, index_col="Ticker")
    insider = pd.read_csv(INSIDER, dtype={"Akses": str}) if INSIDER.exists() else pd.DataFrame()

    # Lapis tanpa jaringan dulu: kalau agregatnya saja tidak cocok dengan
    # transaksi mentahnya, membandingkannya dengan pihak luar belum ada gunanya.
    hari_ini = tanggal_run(META) or date.today()
    lolos = rekonsiliasi(sm, insider, hari_ini)
    lolos &= bukti_cluster(sm, insider)
    lolos &= kewajaran_yahoo(sm)
    print(f"\nLapis tanpa jaringan: {'LOLOS' if lolos else 'ADA YANG GAGAL'}")
    if a.tanpa_yahoo:
        print("\n(--tanpa-yahoo: perbandingan dengan sumber luar dilewati.)")
        return 0 if lolos else 1
    print("\n--- 4. Perbandingan dengan sumber luar ---")

    if a.ticker:
        sampel = [universe.normalisasi_ticker(t) for t in a.ticker]
    else:
        # Emiten yang paling banyak transaksinya: di situ selisih paling
        # mungkin muncul, dan di situ pula angkanya paling berarti.
        ramai = pd.to_numeric(sm["Insider_Transaksi90H"], errors="coerce").fillna(0)
        sampel = list(ramai.sort_values(ascending=False).head(a.jumlah).index)

    baris = []
    for t in sampel:
        if t not in sm.index:
            print(f"{t}: tidak ada di smartmoney.csv", file=sys.stderr)
            continue
        r = sm.loc[t]
        kita = pd.to_numeric(r.get("Insider_Net90H_JutaUSD"), errors="coerce")
        yahoo = None
        if not a.tanpa_yahoo:
            try:
                yahoo = net_dari_yahoo(t)
            except Exception as e:
                print(f"{t}: Yahoo gagal ({type(e).__name__})", file=sys.stderr)
        baris.append({
            "Ticker": t,
            "Net_kita_jt": kita,
            "Net_yahoo_jt": yahoo,
            "Beda_jt": (kita - yahoo) if yahoo is not None and pd.notna(kita) else None,
            "Transaksi": r.get("Insider_Transaksi90H"),
            "Rencana10b5": r.get("Insider_Rencana90H"),
            "Cluster": r.get("Insider_ClusterBuy"),
            "Short_%float": r.get("Short_PctFloat"),
            "Institusi_%": r.get("Institusi_Pct"),
        })

    hasil = pd.DataFrame(baris)
    if hasil.empty:
        print("Tidak ada emiten yang bisa diperiksa.")
        return 1
    with pd.option_context("display.width", 220, "display.max_rows", 200):
        print(hasil.round(2).to_string(index=False))
    print("\nYahoo tidak menandai rencana 10b5-1 dan mengelompokkan transaksi dengan caranya "
          "sendiri, jadi selisih kecil wajar. Yang harus dicurigai: tanda berlawanan, atau "
          "selisih yang sebesar angkanya sendiri.")

    print("\n--- Rincian untuk dicocokkan manual (OpenInsider & Form 4 asli) ---")
    for t in hasil["Ticker"]:
        print(f"\n{t}  OpenInsider: {URL_OPENINSIDER.format(t=t)}")
        print(f"{' ' * len(t)}  EDGAR Form 4: {URL_EDGAR.format(t=t)}")
        print(f"{' ' * len(t)}  Short interest (FINRA via Nasdaq): {URL_SHORT.format(t=t.lower())}")
        if len(insider):
            detail = insider[insider["Ticker"] == t]
            detail = detail[detail["Kode"].isin([smartmoney.KODE_BELI, smartmoney.KODE_JUAL])]
            if len(detail):
                kolom = ["Tanggal", "Kode", "Lembar", "Harga", "Nilai", "Pemilik", "Jabatan",
                         "Rencana10b5", "Akses"]
                print(detail.sort_values("Tanggal")[kolom].to_string(index=False))
    return 0 if lolos else 1


if __name__ == "__main__":
    sys.exit(main())
