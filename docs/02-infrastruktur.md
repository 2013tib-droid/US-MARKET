# 02 — Infrastruktur

Prinsip: **semuanya gratis, semuanya jalan di GitHub Actions, hasilnya
di-commit ke repo dan tampil di GitHub Pages** — persis pola Screening-Saham.
Tidak ada server, tidak ada database, tidak ada langganan.

## 1. Sumber data

| Kebutuhan | Sumber | Gratis? | API key | Kuota / batas | Catatan |
|---|---|---|---|---|---|
| Harga harian & intraday (H1) | **yfinance** | ✅ | ❌ | Tidak resmi; batch `yf.download` 1.500 ticker ± 3–5 menit | Sumber yang sama dengan repo IDX. Ticker AS tanpa suffix (`AAPL`); kelas saham pakai `-` (`BRK-B`) |
| Fundamental resmi (10-K/10-Q, XBRL) | **SEC EDGAR `companyfacts` API** | ✅ | ❌ tapi **wajib header `User-Agent: nama email`** | 10 request/detik | Data primer, bukan turunan pihak ketiga. Satu request per emiten mengembalikan seluruh histori tag XBRL (`Revenues`, `NetIncomeLoss`, `NetCashProvidedByOperatingActivities`, …). 1.500 emiten ≈ 3–5 menit |
| Peta ticker → CIK | SEC `company_tickers.json` | ✅ | ❌ | — | Diperbarui tiap run, di-commit ke `data/cik.csv` |
| Transaksi insider (Form 4) | SEC EDGAR `submissions` API + XML Form 4 | ✅ | ❌ | 10 req/detik | Alternatif cepat: yfinance `insider_transactions` (lebih ringkas, sudah dibersihkan, tapi tidak lengkap) — dipakai dulu di Fase 3, EDGAR langsung kalau butuh cluster buy |
| Kepemilikan institusi (13F) | yfinance `institutional_holders`, `major_holders` | ✅ | ❌ | — | Cukup untuk % kepemilikan & jumlah pemegang. Agregasi 13F penuh dari EDGAR ditunda — datanya besar (ribuan filer × ribuan posisi) |
| Short interest | yfinance `info` (`shortPercentOfFloat`, `shortRatio`, `sharesShort`) | ✅ | ❌ | — | Sumber aslinya FINRA, 2× sebulan |
| Estimasi analis, target harga, tanggal earnings | yfinance `analyst_price_targets`, `recommendations`, `earnings_dates` | ✅ | ❌ | — | Konsensus lengkap (I/B/E/S, Zacks) berbayar; ini proksi |
| Makro | **FRED API** (REST) | ✅ | ✅ gratis, daftar sekali | 120 req/menit | Seri: `T10Y2Y`, `BAMLH0A0HYM2`, `DFF`, `UNRATE`, `VIXCLS` |
| Konstituen S&P 500/400/600, Nasdaq-100 | Wikipedia (tabel) | ✅ | ❌ | — | Rapuh kalau tabelnya diubah editor; `continue-on-error` + fallback ke file ticker terakhir yang di-commit, seperti `perbarui_universe.py` di IDX |
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
4. **GitHub Actions** gratis tanpa batas untuk repo publik; repo privat 2.000
   menit/bulan. Run malam ± 10 menit × 21 hari = 210 menit; run fundamental
   mingguan ± 30 menit × 4 = 120 menit. Total ± 330 menit/bulan — aman meski
   privat.
5. **Zona waktu**. NYSE tutup 16:00 ET. ET = UTC−4 saat DST (Maret–November),
   UTC−5 di luar itu. Cron GitHub dalam UTC, jadi satu jadwal harus menutupi
   keduanya: **22:17 UTC = 05:17 WIB** (WIB tidak bergeser). Tutup pasar
   paling lambat 21:00 UTC, jadi ada jeda ≥ 1 jam untuk data Yahoo final.
   Hari kerja UTC Senin–Jumat sudah tepat karena tanggal UTC belum berganti
   pada 22:17.

## 3. Pipeline

```
[Mingguan / Selasa 06:17 WIB]          [Malam / Sel–Sab 05:17 WIB]
 perbarui_universe.py                    harga.py  (yf.download batch, 2 th)
   Wikipedia → tickers/sp1500.txt   ┐    makro.py  (FRED + ^GSPC + ^VIX)
 perbarui_cik.py                    │    faktor.py (z-score sektor, rezim,
   SEC → data/cik.csv               │              skor komposit)
 perbarui_fundamental.py            ├──▶ screener.py --output hasil/semua.csv
   SEC companyfacts + yfinance info │    screener.py --dari-csv … → hasil/akumulasi.csv
   → data/fundamental.csv           │                            → hasil/pantau.csv
 perbarui_smartmoney.py             │                            → hasil/value.csv
   Form 4 + holders + short         ┘                            → hasil/quality.csv
   → data/smartmoney.csv                 analisa_smc.py --dari-csv hasil/akumulasi.csv
                                         uji_winrate.py  (arsip pick + hitung ulang)
                                         meta.json → commit → GitHub Pages
```

Dua workflow terpisah dengan satu `concurrency: group: tulis-repo` — pola
yang sudah terbukti di IDX menghindari dua run berebut push.

## 4. Struktur data

| Berkas | Isi | Diperbarui |
|---|---|---|
| `tickers/sp500.txt`, `sp400.txt`, `sp600.txt`, `nasdaq100.txt` | Konstituen, satu ticker per baris | Mingguan |
| `tickers/watchlist.txt` | Manual: saham di luar indeks yang mau dipantau | Manual |
| `data/cik.csv` | ticker, CIK, nama resmi | Mingguan |
| `data/fundamental.csv` | Satu baris per emiten: ~60 kolom XBRL 8 kuartal terakhir + rasio turunan + `sumber`, `periode`, `diperbarui` | Mingguan (earnings season) / bulanan |
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

Tidak ada secret lain. Tidak ada kredensial broker di repo — eksekusi order
tetap manual.

## 6. Dependensi (dipin, alasannya ada di `requirements.txt` IDX)

```
yfinance==1.7.0
pandas==3.0.5
requests==2.32.5
pandas_market_calendars==5.1.1
```

`fredapi` tidak perlu — REST FRED cukup dengan `requests`. Versi
`pandas_market_calendars` dan `requests` diverifikasi ulang saat Fase 1
dimulai; angka di atas adalah rilis yang diketahui saat dokumen ini ditulis.

## 7. Biaya

| Komponen | Biaya |
|---|---|
| Data (yfinance, SEC, FRED, Wikipedia) | Rp 0 |
| GitHub Actions + Pages (repo publik) | Rp 0 |
| Broker untuk eksekusi | Di luar sistem; lihat [05-praktik-us-vs-idx.md](05-praktik-us-vs-idx.md) |
| **Opsional, kalau suatu hari mau backtest bebas survivorship bias** | Sharadar (Nasdaq Data Link) ± $50/bulan — **tidak dibangun sebelum diminta** |
