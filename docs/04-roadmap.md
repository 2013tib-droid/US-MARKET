# 04 — Roadmap

Enam fase. Setiap fase punya keluaran yang bisa dilihat dan syarat "selesai"
yang bisa diperiksa — bukan "kira-kira sudah". Fase berikutnya tidak dimulai
sebelum yang sekarang lolos syaratnya.

Perkiraan durasi mengasumsikan kerja sambilan beberapa jam per minggu.

## Fase 0 — Rancangan ✅ (dokumen ini)

**Keluaran**: README + docs/01–05.
**Selesai bila**: pemilik repo sudah membaca dan menyetujui lima pilar,
label status, dan keputusan "data gratis saja". Perubahan setelah ini
dicatat sebagai revisi dokumen, bukan diskusi ulang.

## Fase 1 — Universe, harga, dua faktor pertama (± 2 minggu)

Tujuan: pipeline ujung ke ujung jalan dengan data yang paling mudah (harga),
supaya kerangkanya terbukti sebelum bagian yang sulit (SEC) dikerjakan.

**Dibangun**: `universe.py`, `harga.py`, `teknikal.py`, faktor **Momentum**
dan **Low-Vol** (keduanya hanya butuh harga), `screener.py` versi minimum,
`scripts/perbarui_universe.py`, workflow `screening-malam.yml` tanpa SEC.

**Selesai bila**:
- `python screener.py` menghasilkan `hasil/semua.csv` untuk ≥ 1.400 emiten
  dalam ≤ 10 menit di GitHub Actions.
- Kolom Momentum & Low-Vol terisi ≥ 95% emiten; sisanya berlabel `DATA-KURANG`.
- Run pada jam pasar buka menghasilkan tabel yang sama dengan run pagi
  (uji "selalu data penutupan").
- Workflow jalan otomatis 3 malam berturut-turut tanpa intervensi.

## Fase 2 — Fundamental dari SEC: Quality, Value, red flag (± 3 minggu)

Bagian paling berat dan paling bernilai. Tag XBRL tidak seragam antar
emiten; ini fase yang menentukan apakah data gratisnya cukup baik.

**Dibangun**: `sec.py`, `fundamental.py`, faktor **Quality** dan **Value**,
F-score, Z-score, akrual, shareholder yield, kolom `Flag`,
`scripts/perbarui_fundamental.py`, workflow `fundamental-mingguan.yml`,
`analisa.py`.

**Selesai bila**:
- Metrik inti (revenue, laba, OCF, aset, ekuitas, saham beredar) terisi
  untuk ≥ 90% universe non-keuangan; bank/asuransi punya jalur sendiri.
- 10 emiten acak dicocokkan manual dengan 10-K-nya: selisih ≤ 2%.
- F-score untuk 20 emiten dicocokkan dengan hitungan manual: identik.
- `analisa.py AAPL` menghasilkan laporan yang menyebut basis (TTM/FY),
  periode, dan tag yang terpakai.

## Fase 3 — Smart money & Growth/Revisi (± 2 minggu)

**Dibangun**: `smartmoney.py` (yfinance dulu; Form 4 langsung dari EDGAR
bila cluster buy tidak bisa dideteksi dari yfinance), faktor **Growth/Revisi**,
`scripts/perbarui_smartmoney.py`.

**Selesai bila**:
- Insider net 90 hari cocok dengan tabel di OpenInsider untuk 10 emiten
  (pembanding gratis, dicek manual).
- Cluster buy terdeteksi pada minimal satu kasus yang diketahui (cari
  contoh terkini saat fase ini dimulai).
- Short % float cocok dengan angka FINRA terakhir ± 1 poin.

## Fase 4 — Rezim & skor komposit (± 2 minggu)

**Dibangun**: `makro.py`, `faktor.py` versi lengkap (bobot rezim,
momentum-crash guard), kolom `Skor`, `Status`, `Alasan`, banner rezim.

**Selesai bila**:
- Rezim yang dihitung ulang untuk 2008, 2009, 2020, 2022 dengan data
  historis SPX/VIX cocok dengan yang seorang analis akan sebut untuk periode
  itu (risk-off di Q4 2008, guard aktif Apr–Sep 2009 dan Apr–Sep 2020,
  risk-off sebagian besar 2022).
- Backtest terbatas (konstituen sekarang, 2015–sekarang, rebalance bulanan,
  10 saham skor tertinggi) menghasilkan return per risiko ≥ SPY.
  **Kalau tidak**, bobot tidak diutak-atik sampai lolos — fase ini berhenti
  dan alasannya ditulis. Survivorship bias dinyatakan di laporan.
- Tabel sensitivitas: skor komposit dengan bobot ±10 poin per faktor —
  peringkat 20 besar tidak berubah > 30%. Kalau berubah lebih, skornya
  terlalu rapuh.

## Fase 5 — Timing, SMC, uji winrate (± 2 minggu)

**Dibangun**: `analisa_smc.py` (adaptasi dari IDX: H4 alih-alih SESI, fraksi
harga $0,01), `uji_winrate.py` dengan pembanding SPY / QUAL / MTUM / VLUE,
`hasil/riwayat_pick.csv`.

**Selesai bila**:
- Tiap pick malam tercatat dengan harga masuk = open sesi berikutnya (bukan
  close malam itu — itu harga yang tidak bisa didapat).
- Winrate 5/10/20 hari bursa dihitung ulang tiap malam untuk seluruh arsip.
- Laporan menyebut return setelah biaya (komisi broker, spread ± 0,05%,
  kurs) dan membandingkannya dengan ETF faktor.

## Fase 6 — Dashboard & operasi (± 1 minggu)

**Dibangun**: `dashboard/index.html` (dari IDX + banner rezim + tab),
`winrate.html`, GitHub Pages, catatan operasional ("Yang perlu sesekali
dilirik" seperti di README IDX).

**Selesai bila**:
- Dashboard bisa dibuka dari HP, filter jalan, memuat < 3 detik.
- Satu bulan penuh run otomatis tanpa gagal yang tidak tertangkap
  `continue-on-error`.

## Setelah Fase 6 — hanya kalau diminta

- Form 4 dan 13F langsung dari EDGAR (agregasi penuh).
- Universe historis bebas survivorship bias (berbayar, ± $50/bulan).
- Portofolio: catat posisi nyata, hitung eksposur sektor & kurs.
- Notifikasi (Telegram/email) untuk status baru AKUMULASI atau KURANGI.

## Yang tidak akan dibangun tanpa keputusan tertulis

Eksekusi order otomatis, data real-time berbayar, opsi, prediksi harga ML,
scalping. Alasannya ada di [01-metodologi.md §7](01-metodologi.md#7-yang-sengaja-tidak-dilakukan).
