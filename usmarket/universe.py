"""Universe: S&P 500 + S&P 400 + S&P 600 + Nasdaq-100 + watchlist manual.

Konstituen diambil dari tabel Wikipedia. Setiap indeks disimpan di berkasnya
sendiri (tickers/sp500.csv, dst.) supaya kegagalan satu halaman tidak
menyentuh indeks lain: berkas yang gagal diperbarui tetap memakai versi
terakhir yang di-commit.

Sektor memakai GICS dari tabel S&P. Halaman Nasdaq-100 memakai klasifikasi
ICB, jadi emiten Nasdaq-100 yang tidak ada di S&P 1500 (kebanyakan ADR asing
seperti ASML atau ARM) dipetakan ke nama sektor GICS terdekat.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

AKAR = Path(__file__).resolve().parent.parent
FOLDER_TICKERS = AKAR / "tickers"

# Wikipedia menolak permintaan tanpa User-Agent yang jelas.
USER_AGENT = "US-MARKET screener (https://github.com/2013tib-droid/US-MARKET)"


@dataclass(frozen=True)
class SumberIndeks:
    kode: str
    halaman: str
    kolom_ticker: str
    kolom_nama: str
    kolom_sektor: str
    kolom_industri: str
    # Jumlah baris yang wajar. Di luar rentang ini tabelnya dianggap rusak
    # (sedang diedit, dirusak, atau strukturnya berubah) dan berkas lama
    # dipertahankan. S&P 500 berisi 503 baris karena beberapa emiten punya
    # dua kelas saham (GOOGL/GOOG, FOXA/FOX, NWSA/NWS).
    minimal: int
    maksimal: int


SUMBER = {
    "SP500": SumberIndeks("SP500", "List_of_S%26P_500_companies", "Symbol", "Security",
                          "GICS Sector", "GICS Sub-Industry", 495, 510),
    "SP400": SumberIndeks("SP400", "List_of_S%26P_400_companies", "Symbol", "Security",
                          "GICS Sector", "GICS Sub-Industry", 390, 410),
    "SP600": SumberIndeks("SP600", "List_of_S%26P_600_companies", "Symbol", "Security",
                          "GICS Sector", "GICS Sub-Industry", 585, 615),
    "NDX": SumberIndeks("NDX", "List_of_NASDAQ-100_companies", "Ticker", "Company",
                        "ICB Industry", "ICB Subsector", 98, 105),
}

# Urutan ini juga urutan prioritas sektor: klasifikasi GICS dari S&P
# didahulukan daripada ICB dari Nasdaq-100.
URUTAN_INDEKS = ["SP500", "SP400", "SP600", "NDX"]

ICB_KE_GICS = {
    "Technology": "Information Technology",
    "Telecommunications": "Communication Services",
    "Health Care": "Health Care",
    "Financials": "Financials",
    "Real Estate": "Real Estate",
    "Consumer Discretionary": "Consumer Discretionary",
    "Consumer Staples": "Consumer Staples",
    "Industrials": "Industrials",
    "Basic Materials": "Materials",
    "Energy": "Energy",
    "Utilities": "Utilities",
}

SEKTOR_TAK_DIKETAHUI = "Tidak diketahui"


class TabelTidakWajar(Exception):
    """Tabel konstituen terbaca, tapi isinya tidak masuk akal."""


def normalisasi_ticker(teks: str) -> str:
    """Ubah ticker ke format Yahoo: huruf besar, kelas saham pakai minus.

    Wikipedia menulis BRK.B, Yahoo mengenalnya sebagai BRK-B. Catatan kaki
    seperti "[1]" dan spasi ikut dibuang.
    """
    teks = re.sub(r"\[\w+\]", "", str(teks)).strip().upper()
    return teks.replace(".", "-").replace(" ", "")


def _bersihkan_kolom(kolom) -> str:
    return re.sub(r"\[\w+\]", "", str(kolom)).strip()


def urai_tabel(html: str, sumber: SumberIndeks) -> pd.DataFrame:
    """Ambil tabel ber-id "constituents" dari HTML halaman Wikipedia."""
    tabel = pd.read_html(io.StringIO(html), attrs={"id": "constituents"}, flavor="lxml")[0]
    tabel.columns = [_bersihkan_kolom(k) for k in tabel.columns]
    wajib = [sumber.kolom_ticker, sumber.kolom_nama, sumber.kolom_sektor, sumber.kolom_industri]
    hilang = [k for k in wajib if k not in tabel.columns]
    if hilang:
        raise TabelTidakWajar(f"{sumber.kode}: kolom {hilang} tidak ada; kolom tabel: {list(tabel.columns)}")

    hasil = pd.DataFrame({
        "Ticker": tabel[sumber.kolom_ticker].map(normalisasi_ticker),
        "Nama": tabel[sumber.kolom_nama].astype(str).str.strip(),
        "Sektor": tabel[sumber.kolom_sektor].astype(str).str.strip(),
        "Industri": tabel[sumber.kolom_industri].astype(str).str.strip(),
    })
    if sumber.kolom_sektor.startswith("ICB"):
        hasil["Sektor"] = hasil["Sektor"].map(ICB_KE_GICS).fillna(SEKTOR_TAK_DIKETAHUI)

    hasil = hasil[hasil["Ticker"].str.fullmatch(r"[A-Z][A-Z0-9-]{0,9}")]
    hasil = hasil.drop_duplicates("Ticker").reset_index(drop=True)

    if not sumber.minimal <= len(hasil) <= sumber.maksimal:
        raise TabelTidakWajar(
            f"{sumber.kode}: {len(hasil)} baris, wajarnya {sumber.minimal}–{sumber.maksimal}")
    return hasil


def ambil_indeks(kode: str, sesi: requests.Session | None = None) -> pd.DataFrame:
    sumber = SUMBER[kode]
    sesi = sesi or requests.Session()
    r = sesi.get(f"https://en.wikipedia.org/wiki/{sumber.halaman}",
                 headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return urai_tabel(r.text, sumber)


def berkas_indeks(kode: str, folder: Path = FOLDER_TICKERS) -> Path:
    nama = {"SP500": "sp500", "SP400": "sp400", "SP600": "sp600", "NDX": "nasdaq100"}[kode]
    return folder / f"{nama}.csv"


def baca_daftar_ticker(path: Path) -> list[str]:
    """Baca berkas satu-ticker-per-baris; baris kosong dan # diabaikan.

    Berkas .csv dengan kolom Ticker juga diterima, supaya --tickers bisa
    diarahkan ke tickers/sp500.csv maupun ke watchlist.txt.
    """
    if path.suffix.lower() == ".csv":
        return [normalisasi_ticker(t) for t in pd.read_csv(path)["Ticker"].dropna()]
    hasil = []
    for baris in path.read_text(encoding="utf-8").splitlines():
        baris = baris.split("#", 1)[0].strip()
        if baris:
            hasil.append(normalisasi_ticker(baris))
    return hasil


def gabung(per_indeks: dict[str, pd.DataFrame], watchlist: list[str]) -> pd.DataFrame:
    """Satukan indeks jadi satu tabel ber-indeks Ticker.

    Kolom Indeks mencatat keanggotaan, dipisah titik koma (mis. "SP500;NDX").
    Nama, sektor, dan industri diambil dari indeks pertama menurut
    URUTAN_INDEKS yang memuat ticker itu.
    """
    baris: dict[str, dict] = {}
    for kode in URUTAN_INDEKS:
        df = per_indeks.get(kode)
        if df is None:
            continue
        for r in df.itertuples(index=False):
            if r.Ticker in baris:
                baris[r.Ticker]["Indeks"].append(kode)
            else:
                baris[r.Ticker] = {"Nama": r.Nama, "Sektor": r.Sektor,
                                   "Industri": r.Industri, "Indeks": [kode]}
    for t in watchlist:
        if t in baris:
            baris[t]["Indeks"].append("WATCH")
        else:
            baris[t] = {"Nama": "", "Sektor": SEKTOR_TAK_DIKETAHUI,
                        "Industri": "", "Indeks": ["WATCH"]}

    hasil = pd.DataFrame.from_dict(baris, orient="index")
    hasil.index.name = "Ticker"
    hasil["Indeks"] = hasil["Indeks"].map(";".join)
    return hasil.sort_index()


def muat(folder: Path = FOLDER_TICKERS) -> pd.DataFrame:
    """Universe dari berkas yang sudah di-commit, tanpa akses internet."""
    per_indeks = {}
    for kode in URUTAN_INDEKS:
        path = berkas_indeks(kode, folder)
        if path.exists():
            per_indeks[kode] = pd.read_csv(path, dtype=str).fillna("")
    watch_path = folder / "watchlist.txt"
    watchlist = baca_daftar_ticker(watch_path) if watch_path.exists() else []
    if not per_indeks and not watchlist:
        raise FileNotFoundError(
            f"Belum ada daftar konstituen di {folder}. Jalankan dulu: python scripts/perbarui_universe.py")
    return gabung(per_indeks, watchlist)
