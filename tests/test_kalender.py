from datetime import date, datetime, timezone

from usmarket import kalender


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_libur_dan_hari_bursa():
    assert not kalender.adalah_hari_bursa(date(2026, 9, 7))   # Labor Day
    assert not kalender.adalah_hari_bursa(date(2026, 9, 12))  # Sabtu
    assert kalender.adalah_hari_bursa(date(2026, 9, 8))


def test_bar_hari_ini_saat_sesi_berjalan_belum_final():
    # Jumat 11 Sep 2026, 14:00 ET (DST, UTC−4) = 18:00 UTC: bursa masih buka.
    assert kalender.bar_belum_final(date(2026, 9, 11), utc(2026, 9, 11, 18, 0))


def test_bar_final_setelah_tutup_ditambah_jeda():
    # Tutup 16:00 ET = 20:00 UTC; jeda 60 menit → final mulai 21:00 UTC.
    assert kalender.bar_belum_final(date(2026, 9, 11), utc(2026, 9, 11, 20, 30))
    assert not kalender.bar_belum_final(date(2026, 9, 11), utc(2026, 9, 11, 21, 30))


def test_jadwal_run_malam_selalu_final():
    # Cron 22:17 UTC, baik saat DST maupun tidak.
    assert not kalender.bar_belum_final(date(2026, 9, 11), utc(2026, 9, 11, 22, 17))
    assert not kalender.bar_belum_final(date(2026, 1, 15), utc(2026, 1, 15, 22, 17))


def test_tutup_setengah_hari_setelah_thanksgiving():
    # 28 Nov 2025 tutup 13:00 ET = 18:00 UTC. Aturan "16:00 ET" akan salah
    # menganggap bar ini belum final sampai 22:00 UTC.
    assert not kalender.bar_belum_final(date(2025, 11, 28), utc(2025, 11, 28, 19, 30))


def test_bar_hari_lalu_final():
    assert not kalender.bar_belum_final(date(2026, 9, 10), utc(2026, 9, 11, 15, 0))


def test_tanggal_et_berbeda_dari_tanggal_utc():
    # 02:00 UTC Selasa masih Senin malam di New York.
    assert kalender.tanggal_et(utc(2026, 9, 15, 2, 0)) == date(2026, 9, 14)


def test_sesi_final_terakhir():
    # Selasa 15 Sep 2026 01:04 UTC = Senin malam di New York: sesi Senin sudah final.
    assert kalender.sesi_final_terakhir(utc(2026, 9, 15, 1, 4)) == date(2026, 9, 14)
    # Senin 14 Sep 18:00 UTC, sesi berjalan: yang final masih Jumat 11 Sep.
    assert kalender.sesi_final_terakhir(utc(2026, 9, 14, 18, 0)) == date(2026, 9, 11)
    # Selasa 8 Sep 12:00 UTC, sehari setelah Labor Day: final terakhir Jumat 4 Sep.
    assert kalender.sesi_final_terakhir(utc(2026, 9, 8, 12, 0)) == date(2026, 9, 4)
