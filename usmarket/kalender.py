"""Kalender NYSE: hari bursa, jam tutup per tanggal, dan kapan bar harian
boleh dianggap final.

Jam tutup diambil dari kalender, bukan dipatok 16:00 ET, karena dua alasan.
Pertama, ET bergeser antara UTC−4 dan UTC−5 mengikuti DST. Kedua, NYSE
tutup lebih awal (13:00 ET) beberapa kali setahun: sehari setelah
Thanksgiving, malam Natal, dan kadang 3 Juli. Aturan "16:00 ET" akan
menganggap bar hari itu belum final selama tiga jam setelah bursa tutup.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal

ET = ZoneInfo("America/New_York")

# Yahoo butuh waktu memperbarui bar harian setelah bursa tutup, terutama
# volumenya: angka konsolidasi dari semua venue baru lengkap beberapa saat
# setelah bel. Enam puluh menit sengaja longgar. Run malam dijadwalkan
# 22:17 UTC, jadi jeda ini tidak pernah menghalanginya.
JEDA_FINAL = timedelta(minutes=60)


@lru_cache(maxsize=8)
def _jadwal_tahun(tahun: int) -> pd.DataFrame:
    """Jadwal sesi NYSE setahun penuh. Disimpan per tahun supaya satu run
    yang memeriksa 1.500 ticker tidak membangun jadwal 1.500 kali."""
    nyse = mcal.get_calendar("NYSE")
    jadwal = nyse.schedule(start_date=f"{tahun}-01-01", end_date=f"{tahun}-12-31")
    jadwal.index = pd.DatetimeIndex(jadwal.index).date
    return jadwal


def jam_tutup(tanggal: date) -> datetime | None:
    """Jam tutup sesi pada tanggal itu dalam UTC, atau None bila libur."""
    jadwal = _jadwal_tahun(tanggal.year)
    if tanggal not in jadwal.index:
        return None
    return jadwal.loc[tanggal, "market_close"].to_pydatetime()


def adalah_hari_bursa(tanggal: date) -> bool:
    return jam_tutup(tanggal) is not None


def bar_belum_final(tanggal_bar: date, sekarang: datetime | None = None) -> bool:
    """True bila bar bertanggal `tanggal_bar` masih bisa berubah.

    Selama sesi berjalan, Yahoo tetap mengirim bar untuk hari itu, tapi
    isinya baru sebagian hari. Volume setengah hari yang dibagi rata-rata 20
    hari penuh membuat VolSpike seluruh pasar anjlok, dan harga "penutupan"
    yang dipakai MA dan momentum sebenarnya harga siang. Pelajaran yang sama
    dari repo IDX (lihat bar_terakhir_belum_final di Screening-Saham).

    Bar dari tanggal yang bukan hari bursa dianggap final: tidak ada sesi
    yang bisa mengubahnya.
    """
    sekarang = sekarang or datetime.now(timezone.utc)
    tutup = jam_tutup(tanggal_bar)
    if tutup is None:
        return False
    return sekarang < tutup + JEDA_FINAL


def tanggal_et(sekarang: datetime | None = None) -> date:
    """Tanggal kalender di New York saat ini."""
    sekarang = sekarang or datetime.now(timezone.utc)
    return sekarang.astimezone(ET).date()


def sesi_final_terakhir(sekarang: datetime | None = None) -> date:
    """Tanggal sesi NYSE terakhir yang barnya sudah boleh dianggap final."""
    sekarang = sekarang or datetime.now(timezone.utc)
    hari = tanggal_et(sekarang)
    for _ in range(15):
        if adalah_hari_bursa(hari) and not bar_belum_final(hari, sekarang):
            return hari
        hari -= timedelta(days=1)
    return hari
