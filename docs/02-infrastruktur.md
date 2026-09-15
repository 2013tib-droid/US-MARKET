# 02 — Infrastruktur

Prinsip: **semuanya gratis, semuanya jalan di GitHub Actions, hasilnya
di-commit ke repo dan tampil di GitHub Pages** — persis pola Screening-Saham.
Tidak ada server, tidak ada database, tidak ada langganan.

## 1. Sumber data

| Kebutuhan | Sumber | Gratis? | API key | Kuota / batas | Catatan |
|---|---|---|---|---|---|
| Harga harian & intraday (H1) | **yfinance** | ✅ | ❌ | Tidak resmi; batch `yf.download` 1.500 ticker ± 3–5 menit | Sumber yang sama dengan repo IDX. Ticker AS tanpa suffix (`AAPL`); kelas saham pakai `-` (`BRK-B`) |
| Fundamental resmi (10-K/10-Q, XBRL) | **SEC EDGAR `companyfacts` API** | ✅ | ❌ tapi **wajib header `User-Agent: nama email`** | 10 request/detik | Data primer, bukan turunan pihak ketiga. Satu request per emiten mengembalikan seluruh histori tag XBRL (`Revenues`, `NetIncomeLoss`, `NetCashProvidedByOperatingActivities`, …). 1.500 emiten ≈ 3–5 menit |
| Peta ticker → CIK | SEC `company_tickers.json` | ✅ | ❌ | — | Diunduh di awal setiap pembaruan fundamental (satu berkas ± 800 KB); tidak disimpan karena selalu segar. Format ticker kelas saham sama dengan Yahoo (`BRK-B`) |
| Transaksi insider (Form 4) | SEC EDGAR `submissions` API + XML Form 4 | ✅ | ❌ | 10 req/detik | Alternatif cepat: yfinance `insider_transactions` (lebih ringkas, sudah dibersihkan, tapi tidak lengkap) — dipakai dulu di Fase 3, EDGAR langsung kalau butuh cluster buy |
| Kepemilikan institusi (13F) | yfinance `institutional_holders`, `major_holders` | ✅ | ❌ | — | Cukup untuk % kepemilikan & jumlah pemegang. Agregasi 13F penuh dari EDGAR ditunda — datanya besar (ribuan filer × ribuan posisi) |
| Short interest | yfinance `info` (`shortPercentOfFloat`, `shortRatio`, `sharesShort`) | ✅ | ❌ | — | Sumber aslinya FINRA, 2× sebulan |
| Estimasi analis, target harga, tanggal earnings | yfinance `analyst_price_targets`, `recommendations`, `earnings_dates` | ✅ | ❌ | — | Konsensus lengkap (I/B/E/S, Zacks) berbayar; ini proksi |
| Makro | **FRED API** (REST) | ✅ | ✅ gratis, daftar sekali | 120 req/menit | Seri: `T10Y2Y`, `BAMLH0A0HYM2`, `DFF`, `UNRATE`, `VIXCLS` |
| Konstituen S&P 500/400/600, Nasdaq-100 | Wikipedia (tabel ber-id `constituents`) | ✅ | ❌ tapi wajib User-Agent | — | Rapuh kalau tabelnya diubah editor. Tiap indeks divalidasi jumlah barisnya; yang tidak wajar dilewati dan berkas lamanya dipakai. Daftar Nasdaq-100 ada di halaman `List_of_NASDAQ-100_companies`, bukan halaman indeksnya, dan memakai sektor ICB yang dipetakan ke GICS |
| Sektor & industri | yfinance `info` (`sector`, `industry`) | ✅ | ❌ | — | Bukan GICS resmi, tapi cukup untuk sektor-netral |
| Kalender libur NYSE | Library `pandas_market_calendars` | ✅ | ❌ | — | Supaya cron tidak jalan sia-sia di hari libur |

**Yang berbayar dan sengaja tidak dipakai** (dicatat supaya tidak dibahas
ulang): Polygon.io ($29+/bln, real-time), Financial Modeling Prep (free tier
250 req/hari — terlalu kecil untuk 1.500 emiten), Tiingo (free tier cukup
untuk harga tapi tidak fundamental), Nasdaq Data Link / Sharadar ($50+/bln —
ini yang dipakai kuant profesional untuk universe bebas survivorship bias;
kalau suatu hari mau backtest serius, ini yang dibeli).

## 2. Batasan yang menentukan desain

1. **yfinance `.info` lambat** (~1–2 detik per ticker, dan sering kena
   rate-limit kalau paralel). 1.500 ticker = 30–50 menit. Solusi sama dengan
   IDX: **cache fundamental mingguan** di `data/fundamental.csv`, run malam
   hanya tarik harga.
2. **SEC EDGAR butuh User-Agent** berisi nama + email, dan menolak > 10
   req/detik. Simpan sebagai secret `SEC_USER_AGENT` di GitHub, jangan
   hardcode.
3. **Earnings season** (minggu ke-2 sampai ke-6 setelah akhir kuartal) —
   ratusan emiten lapor per minggu. Cache fundamental harus diperbarui
   **mingguan selama earnings season**, cukup bulanan di luar itu.
4. **Repo publik** (keputusan 14 Sep 2026). GitHub Actions dan Pages gratis
   tanpa batas menit untuk repo publik. Perkiraan pemakaian: run malam
   ± 10 menit × 21 hari + run fundamental ± 30 menit × 4 ≈ 330 menit/bulan.
   Konsekuensinya, isi repo terbaca siapa saja: jangan pernah commit API key
   atau data posisi pribadi — semuanya lewat GitHub Secrets.
5. **Zona waktu**. NYSE tutup 16:00 ET. ET = UTC−4 saat DST (Maret–November),
   UTC−5 di luar itu. Cron GitHub dalam UTC, jadi satu jadwal harus menutupi
   keduanya: **22:17 UTC = 05:17 WIB** (WIB tidak bergeser). Tutup pasar
   paling lambat 21:00 UTC, jadi ada jeda ≥ 1 jam untuk data Yahoo final.
   Hari kerja UTC Senin–Jumat sudah tepat karena tanggal UTC belum berganti
   pada 22:17.

## 3. Pipeline

```
[Mingguan / Minggu 06:17 WIB]          [Malam / Sel–Sab 05:17 WIB]
                                         cek_hari_bursa.py (libur NYSE → lewati)
                                         perbarui_universe.py (4 halaman
                                           Wikipedia → tickers/*.csv)
                                    ┐    harga.py  (yf.download batch, 2 th)
                                    │    makro.py  (FRED + ^GSPC + ^VIX)
 peta CIK (SEC, di dalam skrip)    │    faktor.py (z-score sektor, rezim,
                                    │              skor komposit)
 perbarui_fundamental.py            ├──▶ screener.py --output hasil/semua.csv
   SEC companyfacts + EDGAR FTS     │    screener.py --dari-csv … → hasil/akumulasi.csv
   → data/fundamental.csv           │                            → hasil/pantau.csv
 perbarui_smartmoney.py             │                            → hasil/value.csv
   Form 4 + holders + short         ┘                            → hasil/quality.csv
   → data/smartmoney.csv                 analisa_smc.py --dari-csv hasil/akumulasi.csv
                                         uji_winrate.py  (arsip pick + hitung ulang)
                                         meta.json → commit → GitHub Pages
```

Dua workflow terpisah, masing-masing dengan grup concurrency sendiri
(`tulis-hasil` untuk screening, `tulis-data` untuk fundamental). Rancangan
awalnya satu grup bersama seperti di IDX, tapi GitHub hanya menyimpan satu run
yang menunggu per grup: pada 15 Sep 2026 run fundamental dibatalkan tanpa
pernah jalan karena run screening terjadwal (terlambat 2 jam) memegang grup
itu. Tabrakan push antar-workflow ditangani langkah commit masing-masing.

Cron GitHub tidak tepat waktu. Run terjadwal pertama (22:17 UTC) baru jalan
00:37 UTC — dan keterlambatan itu ternyata mengubah data. Setelah tengah
malam UTC, Yahoo mengirim bar harian sesi terakhir dengan Open dan Volume
tapi tanpa Close/High/Low; bar itu terbuang dan tabel diam-diam tertinggal
satu sesi (diamati 15 Sep 2026 untuk bar 14 Sep). Sejak itu `harga.py`
menambal penutupan yang kosong dari bar 1 jam hari yang sama (median selisih
0,02% dari penutupan resmi), mencatatnya di `meta.json`
(`bar_ditambal_dari_data_per_jam`), dan menandai `tertinggal_sesi` bila
tabel tetap lebih tua dari sesi final terakhir menurut kalender NYSE.
Dashboard menampilkan keduanya.

## 4. Struktur data

| Berkas | Isi | Diperbarui |
|---|---|---|
| `tickers/sp500.csv`, `sp400.csv`, `sp600.csv`, `nasdaq100.csv` | Ticker, Nama, Sektor (GICS), Industri per indeks | Malam (cuma 4 request; murah) |
| `tickers/watchlist.txt` | Manual: saham di luar indeks yang mau dipantau | Manual |
| `data/fundamental.csv` | Satu baris per ticker: angka mentah TTM (atau tahun fiskal) dari XBRL, rasio yang tidak butuh harga, F-score, tag XBRL yang terpakai (`Tag_*`), tanggal going concern dan restatement, `Catatan` bila tidak bisa dihitung | Mingguan (Minggu 06:17 WIB) |
| `data/fundamental_meta.json` | Waktu pembaruan, jumlah metrik inti terisi, daftar going concern, restatement, dan emiten berhistori pendek | Mingguan |
| `data/smartmoney.csv` | Insider net 90 hari, cluster buy, % institusi, short % float, short ratio | Mingguan |
| `data/makro.csv` | Seri harian FRED + rezim yang diturunkan | Malam |
| `hasil/semua.csv` | Tabel lengkap universe | Malam |
| `hasil/akumulasi.csv`, `pantau.csv`, `value.csv`, `quality.csv` | Hasil saringan | Malam |
| `hasil/akumulasi_smc.csv` | Zona entri/stop/target | Malam |
| `hasil/riwayat_pick.csv`, `hasil/winrate.csv` | Arsip pick dan hasilnya | Malam |
| `hasil/meta.json` | Waktu run, rezim malam ini, jumlah emiten, versi skema | Malam |

Semua CSV, semua di-commit. Riwayat = riwayat git, seperti IDX. Kalau
`hasil/semua.csv` (1.500 baris × 80 kolom ≈ 1 MB/hari) membuat repo gemuk
setelah setahun, pindahkan arsip harian ke branch `arsip` — bukan masalah
tahun ini.

## 5. Secret & konfigurasi

| Nama | Isi | Wajib? |
|---|---|---|
| `SEC_USER_AGENT` | `"US-MARKET screener nama@email"` | ✅ untuk EDGAR |
| `FRED_API_KEY` | Dari fred.stlouisfed.org, gratis | ✅ untuk makro; tanpa ini, rezim jatuh ke mode "netral" dengan peringatan |

Tidak ada secret lain. Eksekusi order tetap manual dan di luar sistem.

## 6. Dependensi (dipin, alasannya ada di `requirements.txt` IDX)

Diperiksa di PyPI pada 14 Sep 2026, saat Fase 1 dibangun:

```
yfinance==1.7.0
pandas==3.0.5
numpy==2.5.3
requests==2.34.2
lxml==6.1.3                    # parser untuk pandas.read_html
pandas_market_calendars==5.4.0
```

`requirements-dev.txt` menambahkan `pytest` dan `truststore`. Yang kedua
hanya untuk mesin di jaringan kantor yang memasang sertifikat TLS sendiri:
tanpa itu, Python lokal gagal membuka Wikipedia dengan
`CERTIFICATE_VERIFY_FAILED`. Runner GitHub tidak memasangnya.

Python 3.14, sama di lokal dan di CI. `fredapi` tidak perlu — REST FRED
cukup dengan `requests`.

## 7. Biaya

| Komponen | Biaya |
|---|---|
| Data (yfinance, SEC, FRED, Wikipedia) | Rp 0 |
| GitHub Actions + Pages (repo publik) | Rp 0 |
| **Opsional, kalau suatu hari mau backtest bebas survivorship bias** | Sharadar (Nasdaq Data Link) ± $50/bulan — **tidak dibangun sebelum diminta** |
