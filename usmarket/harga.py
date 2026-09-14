"""Harga harian dari Yahoo Finance, diunduh per batch.

Keluarannya "panel": satu DataFrame lebar per kolom harga (baris = tanggal,
kolom = ticker). Bentuk lebar dipilih karena semua ticker berbagi kalender
yang sama, dan faktor dihitung lintas-saham pada tanggal yang sama.

Dua kolom penutupan disimpan terpisah:
- `tutup`: harga penutupan yang sudah disesuaikan split, tapi TIDAK dividen.
  Ini harga yang tampil di grafik mana pun, jadi dipakai untuk MA, 52 minggu,
  ATR, dan nilai transaksi.
- `tutup_adj`: disesuaikan split DAN dividen. Dipakai untuk return
  (momentum, volatilitas, beta, drawdown). Tanpa ini, saham dividen tinggi
  terlihat jatuh setiap ex-date.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from . import kalender

log = logging.getLogger(__name__)

# Log yfinance mencetak satu baris untuk setiap ticker yang gagal. Dengan
# 1.500 ticker itu menenggelamkan ringkasan kita sendiri; kegagalan tetap
# dilaporkan lewat Panel.gagal.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

KOLOM_YAHOO = {"Open": "buka", "High": "tinggi", "Low": "rendah",
               "Close": "tutup", "Adj Close": "tutup_adj", "Volume": "volume"}


@dataclass
class Panel:
    buka: pd.DataFrame
    tinggi: pd.DataFrame
    rendah: pd.DataFrame
    tutup: pd.DataFrame
    tutup_adj: pd.DataFrame
    volume: pd.DataFrame
    gagal: list[str]
    bar_dibuang: str | None = None  # tanggal bar yang dibuang karena belum final

    @property
    def tickers(self) -> list[str]:
        return list(self.tutup.columns)

    def satu(self, ticker: str) -> pd.DataFrame:
        """Histori satu ticker sebagai DataFrame biasa, tanpa baris kosong."""
        df = pd.DataFrame({nama: getattr(self, nama)[ticker] for nama in KOLOM_YAHOO.values()})
        return df.dropna(subset=["tutup"])


def pisah_kolom(mentah: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Ubah keluaran yf.download(group_by="column") jadi dict per kolom.

    Kolom mentahnya MultiIndex (kolom harga, ticker). Ticker yang seluruh
    isinya kosong (tidak dikenal Yahoo) dibuang di sini.
    """
    hasil = {}
    for asli, nama in KOLOM_YAHOO.items():
        lebar = mentah[asli].copy()
        lebar.index = pd.DatetimeIndex(lebar.index).normalize()
        lebar.columns.name = None
        hasil[nama] = lebar
    ada_data = hasil["tutup"].notna().any()
    return {nama: df.loc[:, ada_data] for nama, df in hasil.items()}


def _unduh_batch(tickers: list[str], periode: str) -> dict[str, pd.DataFrame] | None:
    mentah = yf.download(tickers, period=periode, interval="1d", auto_adjust=False,
                         group_by="column", threads=True, progress=False,
                         actions=False, multi_level_index=True, timeout=30)
    if mentah is None or mentah.empty:
        return None
    return pisah_kolom(mentah)


def buang_bar_belum_final(bagian: dict[str, pd.DataFrame], sekarang=None) -> str | None:
    """Buang baris terakhir bila sesinya belum tuntas. Mengembalikan tanggal
    yang dibuang, atau None."""
    indeks = bagian["tutup"].index
    if len(indeks) == 0:
        return None
    terakhir = indeks[-1].date()
    if not kalender.bar_belum_final(terakhir, sekarang):
        return None
    for nama in bagian:
        bagian[nama] = bagian[nama].iloc[:-1]
    return terakhir.isoformat()


def unduh(tickers: list[str], periode: str = "2y", ukuran_batch: int = 200,
          percobaan: int = 3, jeda_detik: float = 20.0, sekarang=None) -> Panel:
    """Unduh harga harian untuk semua ticker.

    Ticker yang gagal di putaran pertama dikumpulkan dan dicoba ulang dalam
    batch yang lebih kecil setelah jeda: kegagalan Yahoo biasanya pembatasan
    laju sesaat, bukan ticker yang salah. Yang tetap gagal setelah
    `percobaan` putaran dilaporkan di Panel.gagal, dan run tetap lanjut.
    """
    tickers = list(dict.fromkeys(tickers))
    potongan: list[dict[str, pd.DataFrame]] = []
    sisa = tickers
    batch = ukuran_batch
    for putaran in range(1, percobaan + 1):
        belum = []
        for i in range(0, len(sisa), batch):
            kelompok = sisa[i:i + batch]
            try:
                hasil = _unduh_batch(kelompok, periode)
            except Exception as e:  # pembatasan laju, putus koneksi, dsb.
                log.warning("Batch %d–%d gagal (%s): %s", i, i + len(kelompok), type(e).__name__, e)
                hasil = None
            if hasil is None:
                belum.extend(kelompok)
                continue
            potongan.append(hasil)
            belum.extend(t for t in kelompok if t not in hasil["tutup"].columns)
        log.info("Putaran %d: %d dari %d ticker belum terunduh", putaran, len(belum), len(sisa))
        sisa = belum
        if not sisa or putaran == percobaan:
            break
        batch = max(20, batch // 4)
        time.sleep(jeda_detik)

    if not potongan:
        raise RuntimeError("Tidak ada satu pun ticker yang berhasil diunduh dari Yahoo.")

    gabungan = {nama: pd.concat([p[nama] for p in potongan], axis=1).sort_index()
                for nama in KOLOM_YAHOO.values()}
    # Ticker yang muncul di dua potongan (mis. berhasil sebagian di putaran
    # pertama) cukup diambil sekali.
    gabungan = {nama: df.loc[:, ~df.columns.duplicated()] for nama, df in gabungan.items()}
    # Baris yang kosong untuk semua ticker (mis. tanggal yang hanya muncul
    # di satu batch karena perbedaan jam unduh) tidak berarti apa pun.
    ada = gabungan["tutup"].notna().any(axis=1)
    gabungan = {nama: df.loc[ada] for nama, df in gabungan.items()}

    dibuang = buang_bar_belum_final(gabungan, sekarang)
    return Panel(**gabungan, gagal=sisa, bar_dibuang=dibuang)
