# 05 — Praktik: Beda Pasar AS dan IDX bagi Investor dari Indonesia

Bukan bagian dari kode, tapi menentukan bagaimana hasil screening
dieksekusi. Angka di sini benar saat ditulis (September 2026) — aturan pajak
dan broker berubah, verifikasi ulang sebelum membuka akun.

## 1. Jam & kalender

| | IDX | NYSE / Nasdaq |
|---|---|---|
| Sesi reguler | 09:00–11:30, 13:30–15:50 WIB | 09:30–16:00 ET = **21:30–04:00 WIB** (Mar–Nov, DST) / **22:30–05:00 WIB** (Nov–Mar) |
| Pre/after-market | Tidak ada untuk ritel | 04:00–09:30 & 16:00–20:00 ET; likuiditas tipis, spread lebar — **jangan** pasang market order di sini |
| Jeda siang | Ada | Tidak ada → bar H4 bermakna |
| Libur | Kalender BEI | ± 10 hari/tahun (New Year, MLK, Presidents, Good Friday, Memorial, Juneteenth, July 4, Labor, Thanksgiving, Christmas) + tutup setengah hari sebelum Thanksgiving & Natal |
| Earnings season | Kuartalan, batas waktu longgar | 2–6 minggu setelah akhir kuartal (pertengahan Jan/Apr/Jul/Okt), **padat**: 100–300 emiten per hari |

Implikasi untuk sistem: screening jalan 05:17 WIB, dibaca pagi, order
dipasang malam sebelum 21:30. Cukup waktu untuk berpikir — itu keuntungan,
bukan kerugian.

## 2. Mekanisme perdagangan

| | IDX | AS |
|---|---|---|
| Satuan | Lot 100 lembar | Per lembar; **fraksional** di banyak broker (bisa beli 0,1 lembar) |
| Fraksi harga | Rp1–25 berjenjang | $0,01 seragam (sub-penny untuk order tertentu) |
| Batas harian | ARA/ARB ±20–35% | **Tidak ada**; ada *circuit breaker* per saham (LULD) yang cuma menjeda 5 menit. Gap 30% saat earnings biasa terjadi |
| Penyelesaian | T+2 | **T+1** (sejak Mei 2024) |
| Short selling ritel | Terbatas | Umum; jadi short interest adalah data yang bermakna |
| Auto-rejection | Ada | Tidak ada |
| Pattern Day Trader (PDT) | — | Akun margin < $25.000 dibatasi 3 *day trade* per 5 hari kerja. **Akun cash tidak kena**, tapi dana hasil jual baru bisa dipakai setelah settle (T+1) |

## 3. Pajak (untuk WNI, bukan penduduk AS)

| Hal | Aturan |
|---|---|
| Dividen | AS memotong *withholding tax* **30%**; turun menjadi tarif P3B Indonesia–AS (umumnya **15%**) bila **W-8BEN** diisi di broker. Isi W-8BEN **sebelum** dividen pertama; berlaku 3 tahun |
| Capital gain | **Tidak dipotong** oleh AS untuk non-resident alien. Wajib dilaporkan sendiri di SPT Tahunan Indonesia sebagai penghasilan luar negeri; kredit pajak luar negeri (PPh 24) untuk withholding dividen yang sudah dipotong |
| Estate tax AS | Aset AS > $60.000 milik non-resident bisa kena *estate tax* saat pemilik meninggal. Relevan kalau portofolionya besar; konsultasikan |
| Harta di SPT | Saham AS dilaporkan di daftar harta dengan kurs akhir tahun |

Sistem tidak menghitung pajak, tapi `uji_winrate.py` memasukkan 15%
withholding pada dividen supaya return yang dilaporkan tidak terlalu manis.

## 4. Broker yang bisa dipakai dari Indonesia

| Broker | Jenis | Cakupan | Catatan |
|---|---|---|---|
| **Interactive Brokers (IBKR)** | Broker AS penuh, akun internasional | Semua saham & ETF AS, opsi, banyak bursa lain | Standar profesional. Komisi rendah, ada API. Setoran via transfer bank/wire (biaya & kurs bank). Antarmuka berat untuk pemula |
| **Gotrade** | Aplikasi Indonesia, mitra broker AS | Ribuan saham & ETF AS, fraksional | Mudah, rupiah langsung, cocok untuk mulai. Cek biaya konversi kurs |
| **Pluang / Nanovest** | Aplikasi Indonesia multi-aset | Saham AS pilihan (ratusan), fraksional | Universe lebih sempit; tidak semua kandidat screener tersedia |
| Sekuritas lokal dengan akses global (beberapa) | — | Bervariasi | Biasanya lewat produk struktur; periksa apakah benar-benar kepemilikan saham langsung |

Rekomendasi bertahap: mulai dengan aplikasi Indonesia untuk membiasakan diri
dan uji winrate dengan uang kecil, pindah ke IBKR saat portofolio > $10.000
dan universe screener tidak lagi tercakup.

**Screener menandai** emiten yang tidak tersedia di broker yang dipakai
lewat `tickers/tersedia_<broker>.txt` — kolom `Tersedia` di dashboard — supaya
tidak jatuh cinta pada saham yang tidak bisa dibeli.

## 5. Risiko yang tidak ada di IDX

- **Kurs**. Return 10% dalam USD bisa jadi 3% atau 17% dalam rupiah. Laporan
  selalu menyajikan keduanya, terpisah.
- **Transfer dana**. Setor/tarik ke broker AS makan 1–5 hari kerja + biaya
  kurs. Bukan uang darurat.
- **Jam tidur**. Order bisa disiapkan sebelum tidur (limit / stop-limit), tapi
  earnings dirilis 16:05 ET = 04:05 WIB dan reaksi gap-nya terjadi saat kita
  tidur. Karena itu `TUNGGU-LAPKEU` adalah status, bukan saran.
- **Delisting & merger** lebih sering; arsip pick harus menangani ticker yang
  hilang (dicatat sebagai tutup posisi di harga terakhir, bukan dibuang).

## 6. Istilah yang sering tertukar

| Istilah AS | Bukan | Artinya |
|---|---|---|
| Float | Saham beredar | Lembar yang benar-benar bisa diperdagangkan publik (tanpa insider & pemegang terkunci). Short interest dihitung terhadap ini |
| Guidance | Target harga | Proyeksi manajemen sendiri untuk kuartal/tahun depan; pengubah harga terbesar saat earnings |
| 10-K / 10-Q / 8-K | Lapkeu tahunan/kuartalan/kejadian penting | Semuanya di EDGAR, gratis, wajib |
| Form 4 | — | Laporan transaksi insider, ≤ 2 hari kerja |
| 13F | — | Posisi institusi > $100 juta, per kuartal, terlambat ≤ 45 hari |
| Beat / miss | — | Laba di atas/bawah konsensus analis. Harga bereaksi terhadap **beat + guidance**, bukan laba absolut |
| Ex-dividend | Cum date | Beli sebelum ex-date untuk dapat dividen; harga turun sebesar dividen di ex-date |
