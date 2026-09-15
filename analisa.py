#!/usr/bin/env python3
"""Laporan fundamental satu emiten dalam Markdown, dari data yang sudah ada
(hasil/semua.csv dan data/fundamental.csv) — tanpa menarik apa pun dari
internet.

    python analisa.py AAPL
    python analisa.py XOM --output analisa/XOM.md

Screener menjawab "dari 1.500 emiten, mana yang layak dilihat". Laporan ini
menjawab "emiten ini bagaimana persisnya": setiap angka dibandingkan dengan
median sektornya, setiap angka menyebut dari tag XBRL mana ia diambil, dan
setiap red flag dijelaskan. Rekomendasi sengaja tidak dibuat di sini; label
status (AKUMULASI, PANTAU, …) baru ada di Fase 4 bersama skor komposit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from usmarket import universe, valuasi

AKAR = Path(__file__).resolve().parent

ARTI_FLAG = {
    "TIPIS": "Tidak lolos likuiditas: harga < $5, nilai transaksi < $10 juta/hari, atau market cap < $1 miliar.",
    "DATA-KURANG": "Histori harga < 1 tahun, atau lebih dari 3 metrik inti laporan keuangan kosong.",
    "BASI": "Tidak ada transaksi pada sesi terakhir (dihentikan perdagangannya atau menjelang delisting).",
    "SEKTOR-KECIL": "Pembanding sektor < 5 emiten; z-score diukur terhadap seluruh universe.",
    "GAGAL-UNDUH": "Yahoo tidak punya data harga ticker ini.",
    "FILER-ASING": "Laporan tidak dalam US GAAP/USD (IFRS atau mata uang lain); fundamental tidak dihitung.",
    "LAPKEU-LAMA": "Laporan terakhir lebih dari 270 hari lalu.",
    "ZONA-BAHAYA": "Altman Z < 1,8. Untuk emiten padat modal (telekomunikasi, pipa migas) ini sering salah alarm; lihat cakupan bunga.",
    "DISTRES": "Altman Z < 1,8 DAN EBIT tidak sampai 1,5× beban bunga: tekanan keuangan terkonfirmasi.",
    "GOING-CONCERN": "Kalimat going concern baku auditor ditemukan di 10-K/10-Q setahun terakhir. Baca laporannya: bisa juga kalimat 'keraguan sudah teratasi'.",
    "RESTATEMENT": "8-K Item 4.02 dalam 400 hari terakhir: laporan keuangan lama dinyatakan tidak bisa diandalkan.",
    "F-RENDAH": "Piotroski F-score ≤ 3: fundamental memburuk di banyak sisi sekaligus.",
    "LABA-KERTAS": "Arus kas operasi < 60% laba bersih dua periode berturut-turut: laba tidak menjadi kas.",
    "DILUSI": "Jumlah saham (rata-rata tertimbang dilusi) naik > 5% setahun.",
    "GOODWILL": "Goodwill > ekuitas (atau ekuitas negatif): neraca hasil akuisisi, rawan impairment.",
    "SAHAM-JANGGAL": "Jumlah saham tidak konsisten dengan harga (laba > market cap atau nilai buku > 20× market cap); valuasi dikosongkan.",
    "UTANG-TAK-TERBACA": "Beban bunga material tapi saldo utang tidak ada di XBRL non-dimensional; EV dan leverage tidak dihitung.",
    "SHORT-TINGGI": "Short interest > 20% float: dua arah — pesimisme yang bisa saja benar, sekaligus bahan bakar short squeeze.",
    "INSIDER-JUAL": "Orang dalam menjual bersih > $10 juta di pasar terbuka dalam 90 hari, di luar rencana 10b5-1.",
    "EARNINGS-DEKAT": "Laporan keuangan dalam ≤ 5 hari bursa. Gap 10–20% dua arah biasa terjadi di AS.",
}

ARTI_F = {
    "ROA": "Laba bersih positif", "OCF": "Arus kas operasi positif", "dROA": "ROA naik dari tahun lalu",
    "AKRUAL": "Arus kas operasi > laba bersih", "LEVERAGE": "Utang/aset turun (atau tanpa utang)",
    "CR": "Rasio lancar naik", "SAHAM": "Tidak menambah jumlah saham", "MARGIN": "Margin kotor (atau EBIT) naik",
    "ATO": "Perputaran aset naik",
}


def _fmt(v, desimal=1, akhiran=""):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    if isinstance(v, (int, float)):
        return f"{v:,.{desimal}f}{akhiran}".replace(",", "_").replace(".", ",").replace("_", ".")
    return str(v)


def _bulat(v) -> int:
    """Nilai kosong (NaN) dibaca sebagai nol. Dipakai hanya untuk jumlah
    kejadian — bukan untuk angka yang "tidak diketahui" berbeda dari nol."""
    v = pd.to_numeric(v, errors="coerce")
    return 0 if pd.isna(v) else int(v)


def _usd(v):
    if v is None or pd.isna(v):
        return "–"
    for batas, satuan in ((1e12, "triliun"), (1e9, "miliar"), (1e6, "juta")):
        if abs(v) >= batas:
            return f"${_fmt(v / batas, 2)} {satuan}"
    return f"${_fmt(v, 0)}"


def _tabel(baris: list[list], kepala: list[str]) -> str:
    out = ["| " + " | ".join(kepala) + " |", "|" + "|".join("---" for _ in kepala) + "|"]
    out += ["| " + " | ".join(str(x) for x in b) + " |" for b in baris]
    return "\n".join(out)


def laporan(ticker: str, semua: pd.DataFrame, fund: pd.DataFrame) -> str:
    if ticker not in semua.index:
        raise SystemExit(f"{ticker} tidak ada di hasil/semua.csv")
    r = semua.loc[ticker]
    fr = fund.loc[ticker] if ticker in fund.index else pd.Series(dtype=object)
    sektor = r["Sektor"]
    rekan = semua[semua["Sektor"] == sektor]
    flag = [x for x in str(r.get("Flag") or "").split(";") if x and x != "nan"]
    keu = sektor == valuasi.KEUANGAN

    # Kolom yang belum ada di CSV (mis. hasil run fase sebelumnya) tampil
    # sebagai "–", bukan menghentikan laporan.
    def median(k):
        return rekan[k].median() if k in rekan else float("nan")

    def persentil(k):
        v = r.get(k)
        if k not in rekan or pd.isna(v):
            return "–"
        return f"{(rekan[k].dropna() <= v).mean() * 100:.0f}"

    L = [f"# {r.get('Nama') or ticker} ({ticker})", ""]
    L.append(f"{sektor} · {r.get('Industri') or '–'} · indeks {r.get('Indeks') or '–'}  ")
    L.append(f"Harga ${_fmt(r['Harga'], 2)} (penutupan {r.get('Tanggal_Data')}) · market cap "
             f"{_usd(r['MCap_MiliarUSD'] * 1e9) if pd.notna(r.get('MCap_MiliarUSD')) else '–'}  ")
    if len(fr):
        L.append(f"Laporan keuangan: basis **{fr.get('Basis')}**, periode berakhir {fr.get('Periode_Lapkeu')}, "
                 f"dari {fr.get('Form')} yang dilaporkan {fr.get('Tanggal_Lapor')} "
                 f"([EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={int(fr['CIK']) if pd.notna(fr.get('CIK')) else ''}&type=10-&dateb=&owner=include&count=40))")
    L += ["", "> Alat bantu riset, bukan rekomendasi. Status beli/jual baru ada di Fase 4.", ""]

    # --- keyakinan ---
    baris_gabung = pd.concat([fr, r])
    baris_gabung = baris_gabung[~baris_gabung.index.duplicated(keep="last")]
    alasan = valuasi.alasan_keyakinan(baris_gabung, flag)
    L += ["## Tingkat keyakinan data", "",
          f"**{_fmt(r.get('Keyakinan'), 0)} / 100.** Mengukur seberapa jauh angka di laporan ini boleh "
          "dipercaya, bukan seberapa yakin sahamnya naik.", ""]
    L += [f"- −{p}: {a}" for p, a in alasan] or ["- Tidak ada potongan."]
    L.append("")

    # --- faktor ---
    L += ["## Posisi faktor di dalam sektor", "",
          "Z-score 0 = rata-rata sektor; +1 = satu simpangan di atasnya. Persentil = persen emiten "
          f"sektor {sektor} yang nilainya sama atau lebih rendah.", ""]
    faktor = [("Value", "Z_Value", "murah terhadap laba, EBITDA, arus kas, dan nilai buku"),
              ("Quality", "Z_Quality", "ROIC, margin, stabilitas, leverage, kualitas laba"),
              ("Momentum", "Z_Momentum", "return 12-1 dan 6-1 bulan dibagi volatilitas"),
              ("Low-Vol", "Z_LowVol", "volatilitas, beta, drawdown rendah"),
              ("Growth", "Z_Growth", "pertumbuhan EPS & pendapatan, revisi target analis, earnings surprise"),
              ("Smart money", "Z_SmartMoney", "beli bersih orang dalam dan arah kepemilikan institusi")]
    L.append(_tabel([[n, _fmt(r.get(k), 2), persentil(k), ket] for n, k, ket in faktor],
                    ["Faktor", "Z", "Persentil sektor", "Isi"]))
    L.append("")

    # --- valuasi ---
    kol_v = [("P/E TTM", "PE_TTM", "x"), ("P/B", "PB", "x"), ("Laba/harga", "E_P", "%"),
             ("Dividend yield", "DivYield", "%"), ("Shareholder yield", "Shareholder_Yield", "%")]
    if not keu:
        kol_v = [("EV/EBITDA", "EV_EBITDA", "x"), ("FCF yield", "FCF_Yield", "%"),
                 ("EBITDA/EV", "EBITDA_EV", "%")] + kol_v
    L += ["## Valuasi", ""]
    L.append(_tabel([[n, _fmt(r.get(k), 2 if s == "x" else 1, s), _fmt(median(k), 2 if s == "x" else 1, s)]
                     for n, k, s in kol_v], ["Metrik", ticker, f"Median {sektor}"]))
    L += ["", "Kelipatan (P/E, EV/EBITDA) kosong bila penyebutnya negatif; versi yield-nya tetap terisi "
          "dan itulah yang dipakai Z_Value.", ""]

    # --- kualitas ---
    if keu:
        kol_q = [("ROE", "ROE", "%"), ("Variabilitas ROA 5 th (pp)", "ROA_Variabilitas5T", "")]
    else:
        kol_q = [("ROIC", "ROIC", "%"), ("ROE", "ROE", "%"), ("Margin kotor", "GrossMargin", "%"),
                 ("Stabilitas margin 5 th (pp)", "GM_Stabilitas5T", ""),
                 ("Utang bersih/EBITDA", "NetDebt_EBITDA", "x"), ("Akrual (% aset)", "Akrual", "%"),
                 ("Arus kas operasi/laba", "OCF_Laba", "x"), ("Variabilitas ROA 5 th (pp)", "ROA_Variabilitas5T", ""),
                 ("Cakupan bunga (EBIT/bunga)", "Cakupan_Bunga", "x"), ("Altman Z", "Z_Altman", "")]
    L += ["## Kualitas", ""]
    def sel(k, v, s):
        # Cakupan bunga dibatasi ±999 di tabel; itu artinya tidak ada beban
        # bunga yang dilaporkan, bukan angka 999 sungguhan.
        if k == "Cakupan_Bunga" and pd.notna(v) and abs(v) >= 999:
            return "tanpa beban bunga" if v > 0 else "EBIT negatif, tanpa beban bunga"
        return _fmt(v, 2 if s == "x" else 1, s)

    L.append(_tabel([[n, sel(k, r.get(k), s), sel(k, median(k), s)] for n, k, s in kol_q],
                    ["Metrik", ticker, f"Median {sektor}"]))
    L.append("")

    # --- Piotroski ---
    if not keu and isinstance(fr.get("F_Rincian"), str):
        L += [f"## Piotroski F-score: {_fmt(r.get('F_Score'), 0)} / 9", "",
              "Periode terakhir dibandingkan dengan setahun sebelumnya.", ""]
        baris = []
        for bagian in fr["F_Rincian"].split():
            nama, tanda = bagian[:-1], bagian[-1]
            baris.append([nama, {"+": "✅ lolos", "-": "❌ tidak", "?": "– data kosong"}[tanda], ARTI_F.get(nama, "")])
        L.append(_tabel(baris, ["Komponen", "Hasil", "Arti"]))
        L.append("")

    # --- pertumbuhan ---
    L += ["## Pertumbuhan, dilusi, dan pandangan analis", ""]
    kol_g = [("Pendapatan YoY", "Rev_YoY", "%"), ("Laba bersih YoY", "Laba_YoY", "%"),
             ("Pendapatan 3 th (CAGR)", "Rev_CAGR3", "%"), ("EPS 3 th (CAGR)", "EPS_CAGR3", "%"),
             ("Jumlah saham YoY", "Dilusi_YoY", "%"),
             ("Revisi target analis 3 bln", "Target_Revisi", "%"),
             ("Jarak ke target konsensus", "Target_Upside", "%"),
             ("Earnings surprise terakhir", "Surprise_Terakhir", "%"),
             ("P/E forward", "PE_Fwd", "x")]
    L.append(_tabel([[n, _fmt(r.get(k), 2 if s == "x" else 1, s), _fmt(median(k), 2 if s == "x" else 1, s)]
                     for n, k, s in kol_g], ["Metrik", ticker, f"Median {sektor}"]))
    L += ["", "Pertumbuhan tiga tahun dihitung dari tahun fiskal dan kosong bila basisnya rugi. "
          "Target dan surprise berasal dari yfinance — **proksi** untuk revisi konsensus yang "
          "aslinya berbayar. Yang masuk Z_Growth adalah arah revisinya, bukan jarak ke target: "
          "upside besar biasanya berarti harganya yang jatuh, bukan targetnya yang naik.", ""]

    # --- smart money ---
    L += ["## Smart money", "",
          f"Orang dalam (Form 4, {_bulat(r.get('Insider_Pembeli90H'))} pembeli dan "
          f"{_bulat(r.get('Insider_Penjual90H'))} penjual dalam 90 hari), kepemilikan institusi, "
          "dan short interest. Hanya transaksi pasar terbuka di luar rencana 10b5-1 yang dihitung.", ""]
    cluster = "ya" if str(r.get("Insider_ClusterBuy")) == "True" else "tidak"
    kol_sm = [["Beli bersih orang dalam 90 hari", f"${_fmt(r.get('Insider_Net90H_JutaUSD'), 2)} juta",
               f"{_fmt(r.get('Insider_Net_PctMCap'), 3, '%')} market cap"],
              ["Beli / jual kotor", f"${_fmt(r.get('Insider_Beli90H_JutaUSD'), 2)} juta",
               f"${_fmt(r.get('Insider_Jual90H_JutaUSD'), 2)} juta"],
              ["Cluster buy (≥ 2 orang dalam, 30 hari)", cluster,
               f"transaksi terakhir {_fmt(r.get('Insider_Terakhir'))}"],
              ["Kepemilikan institusi", _fmt(r.get("Institusi_Pct"), 1, "%"),
               f"{_fmt(r.get('Institusi_Delta'), 2)} pp sejak snapshot lalu"],
              ["Short interest", _fmt(r.get("Short_PctFloat"), 2, "% float"),
               f"{_fmt(r.get('Short_Ratio'), 1)} hari volume"],
              ["Rekomendasi analis (1 beli – 5 jual)", _fmt(r.get("Rekom_Rata"), 2),
               f"{_fmt(r.get('Jumlah_Analis'), 0)} analis"],
              ["Lapkeu berikutnya", _fmt(r.get("Earnings_Berikut")),
               f"{_fmt(r.get('Hari_Ke_Earnings'), 0)} hari bursa lagi"]]
    L.append(_tabel(kol_sm, ["Sinyal", "Nilai", "Konteks"]))
    L += ["", "Kepemilikan institusi dan short interest dari yfinance (turunan 13F dan FINRA, "
          "tertinggal dua minggu sampai 45 hari). Perubahan institusi diukur terhadap snapshot "
          "mingguan repo ini, bukan antar-kuartal 13F.", ""]

    # --- angka mentah ---
    if len(fr):
        mentah = [("Pendapatan", "Pendapatan", "Tag_Pendapatan"), ("Laba bersih", "Laba", "Tag_Laba"),
                  ("Arus kas operasi", "OCF", "Tag_OCF"), ("EBIT", "EBIT", "Tag_EBIT"),
                  ("EBITDA", "EBITDA", "Tag_Penyusutan"), ("Capex", "Capex", None), ("Aset", "Aset", None),
                  ("Ekuitas", "Ekuitas", None), ("Utang berbunga", "Utang", "Tag_Utang"),
                  ("Kas + investasi jangka pendek", "KasPlus", None), ("Saham beredar", "Saham", "Tag_Saham")]
        baris = []
        for nama, k, tag in mentah:
            v = pd.to_numeric(fr.get(k), errors="coerce")
            nilai = _fmt(v / 1e6, 1) + " juta lembar" if k == "Saham" and pd.notna(v) else _usd(v)
            baris.append([nama, nilai, f"`{fr.get(tag)}`" if tag and isinstance(fr.get(tag), str) else ""])
        L += ["## Angka dasar dan asal-usulnya", "",
              f"Semua dari XBRL SEC, {fr.get('Basis')} berakhir {fr.get('Periode_Lapkeu')}. Kolom sumber "
              "menyebut tag yang terpakai supaya angkanya bisa dicek ulang di laporan aslinya.", ""]
        L.append(_tabel(baris, ["Pos", "Nilai", "Sumber"]))
        L.append("")

    # --- teknikal ---
    tt = "lolos" if str(r.get("TrendTemplate")) == "True" else "tidak lolos"
    L += ["## Tren", "",
          f"Trend template **{tt}** · RS rating {_fmt(r.get('RS_Rating'), 0)} · harga vs MA200 "
          f"{_fmt((r['Harga'] / r['MA200'] - 1) * 100 if pd.notna(r.get('MA200')) else None, 1, '%')} · "
          f"{_fmt((r['Harga'] / r['High52'] - 1) * 100 if pd.notna(r.get('High52')) else None, 1, '%')} dari high 52 minggu · "
          f"RSI {_fmt(r.get('RSI14'), 0)}", ""]

    # --- red flag ---
    L += ["## Red flag", ""]
    if flag:
        for x in flag:
            berat = " **(berat)**" if x in valuasi.FLAG_BERAT else ""
            tambahan = ""
            if x == "GOING-CONCERN":
                tambahan = f" Dokumen: {fr.get('GoingConcern')}."
            if x == "RESTATEMENT":
                tambahan = f" 8-K: {fr.get('Restatement')}."
            L.append(f"- `{x}`{berat}: {ARTI_FLAG.get(x, '')}{tambahan}")
    else:
        L.append("- Tidak ada.")
    L.append("")

    # --- yang tidak dijawab ---
    L += ["## Yang tidak dijawab laporan ini", "",
          "Bagian ini menuntut penilaian atas hal yang tidak ada di angka laporan keuangan. Pertanyaannya "
          "sudah disiapkan; jawabannya ada di 10-K (Item 1 Business, Item 1A Risk Factors, Item 7 MD&A) "
          "dan transkrip earnings call.", "",
          "- **Moat.** Apakah ROIC di atas bertahan 5 tahun karena keunggulan struktural (skala, jaringan, "
          "biaya beralih, merek), atau karena siklus yang sedang di puncak?",
          "- **Katalis.** Apa yang bisa mengubah persepsi pasar dalam 6–12 bulan: produk baru, divestasi, "
          "buyback besar, perubahan regulasi?",
          "- **Manajemen.** Seberapa sering guidance tercapai? Apakah kompensasi eksekutif terikat ROIC atau "
          "sekadar pertumbuhan pendapatan?",
          "- **Risiko terbesar.** Bila Z_Value tinggi: apakah murah karena pasar tahu sesuatu (value trap)? "
          "Bila Z_Momentum tinggi: seberapa jauh kenaikan sudah mendahului laba?", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ticker")
    p.add_argument("--output", type=Path, help="Simpan ke berkas Markdown")
    p.add_argument("--semua", type=Path, default=AKAR / "hasil" / "semua.csv")
    p.add_argument("--fundamental", type=Path, default=AKAR / "data" / "fundamental.csv")
    a = p.parse_args(argv)
    semua = pd.read_csv(a.semua, index_col="Ticker")
    fund = pd.read_csv(a.fundamental, index_col="Ticker") if a.fundamental.exists() else pd.DataFrame()
    teks = laporan(universe.normalisasi_ticker(a.ticker), semua, fund)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(teks + "\n", encoding="utf-8")
        print(f"Laporan disimpan ke {a.output}", file=sys.stderr)
    else:
        print(teks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
