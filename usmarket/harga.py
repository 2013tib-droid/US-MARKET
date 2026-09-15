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
    bar_ditambal: str | None = None  # "YYYY-MM-DD: N ticker" bila penutupan diambil dari data per jam

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
    # Urutannya penting: buang bar yang sesinya belum tuntas DULU, baru tambal
    # bar final yang penutupannya kosong, baru buang baris yang tetap kosong.
    dibuang = buang_bar_belum_final(gabungan, sekarang)
    ditambal = tambal_bar_terakhir(gabungan, ambil_per_jam)
    ada = gabungan["tutup"].notna().any(axis=1)
    gabungan = {nama: df.loc[ada] for nama, df in gabungan.items()}
    return Panel(**gabungan, gagal=sisa, bar_dibuang=dibuang, bar_ditambal=ditambal)


def ambil_per_jam(tickers: list[str], ukuran_batch: int = 200) -> dict[str, pd.DataFrame]:
    """Bar 1 jam lima hari terakhir (sesi reguler), dipecah per kolom seperti
    pisah_kolom. Indeks dikonversi ke jam New York."""
    potongan = []
    for i in range(0, len(tickers), ukuran_batch):
        try:
            mentah = yf.download(tickers[i:i + ukuran_batch], period="5d", interval="1h",
                                 auto_adjust=False, group_by="column", threads=True,
                                 progress=False, prepost=False, multi_level_index=True, timeout=30)
        except Exception as e:
            log.warning("Unduh data per jam gagal (%s): %s", type(e).__name__, e)
            continue
        if mentah is not None and not mentah.empty:
            potongan.append({k: mentah[k] for k in ("Open", "High", "Low", "Close")})
    if not potongan:
        return {}
    return {k: pd.concat([p[k] for p in potongan], axis=1) for k in ("Open", "High", "Low", "Close")}


# Bar terakhir dianggap "tidak lengkap" bila lebih dari separuh ticker yang
# punya volume untuk tanggal itu tidak punya harga penutupan.
AMBANG_TIDAK_LENGKAP = 0.5


def tambal_bar_terakhir(bagian: dict[str, pd.DataFrame], ambil=ambil_per_jam) -> str | None:
    """Isi penutupan bar terakhir yang kosong dari bar 1 jam hari yang sama.

    Diamati 15 Sep 2026: setelah tengah malam UTC, Yahoo mengirim bar harian
    14 Sep dengan Open dan Volume, tapi Close, High, Low, dan Adj Close
    kosong — padahal pukul 21:05 UTC semuanya ada. Tanpa penambal, baris itu
    terbuang dan tabel diam-diam tertinggal satu sesi setiap kali cron
    GitHub terlambat melewati tengah malam UTC (pagi itu 2 jam 20 menit).

    Penutupan bar 1 jam terakhir adalah transaksi terakhir sebelum 16:00 ET,
    bukan harga lelang penutupan resmi. Diukur terhadap penutupan resmi 14 Sep
    untuk 1.520 ticker: median selisih 0,02%, 95% ticker ≤ 0,11%, terbesar
    0,96% (STX). Adj Close bar terakhir = Close, karena penyesuaian dividen
    hanya mengubah histori sebelum ex-date.
    """
    tutup, volume = bagian["tutup"], bagian["volume"]
    if tutup.empty:
        return None
    akhir = tutup.index[-1]
    ber_volume = volume.loc[akhir].notna() & (volume.loc[akhir] > 0)
    kosong = ber_volume & tutup.loc[akhir].isna()
    if ber_volume.sum() == 0 or kosong.sum() / ber_volume.sum() <= AMBANG_TIDAK_LENGKAP:
        return None
    per_jam = ambil(list(kosong.index[kosong]))
    if not per_jam:
        return None
    idx = pd.DatetimeIndex(per_jam["Close"].index)
    if idx.tz is not None:
        idx = idx.tz_convert("America/New_York")
    hari = idx.normalize().tz_localize(None) == akhir
    if not hari.any():
        return None
    jam = {k: v.loc[hari] for k, v in per_jam.items()}
    diisi = 0
    for t in kosong.index[kosong]:
        if t not in jam["Close"].columns:
            continue
        c = jam["Close"][t].dropna()
        if c.empty:
            continue
        bagian["tutup"].loc[akhir, t] = float(c.iloc[-1])
        bagian["tutup_adj"].loc[akhir, t] = float(c.iloc[-1])
        if pd.isna(bagian["tinggi"].loc[akhir, t]):
            bagian["tinggi"].loc[akhir, t] = float(jam["High"][t].max())
        if pd.isna(bagian["rendah"].loc[akhir, t]):
            bagian["rendah"].loc[akhir, t] = float(jam["Low"][t].min())
        if pd.isna(bagian["buka"].loc[akhir, t]):
            bagian["buka"].loc[akhir, t] = float(jam["Open"][t].dropna().iloc[0])
        diisi += 1
    if not diisi:
        return None
    log.warning("Bar %s tidak lengkap dari Yahoo: penutupan %d ticker diambil dari data per jam",
                akhir.date(), diisi)
    return f"{akhir.date().isoformat()}: {diisi} ticker"
