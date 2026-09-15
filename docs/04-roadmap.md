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

**Keputusan pemilik (14 Sep 2026)**:

| Hal | Keputusan |
|---|---|
| Visibilitas repo | Publik |
| Universe | S&P 1500 + Nasdaq-100 + watchlist, ≈ 1.550 emiten |
| Broker | Tidak dibahas; di luar cakupan sistem |

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

**Hasil (14 Sep 2026, data penutupan 11 Sep 2026)**:

| Syarat | Hasil | Status |
|---|---|---|
| ≥ 1.400 emiten dalam ≤ 10 menit di Actions | 1.521 emiten; unduh + hitung 192 detik, seluruh job < 4 menit | ✅ |
| Momentum & Low-Vol terisi ≥ 95% | 1.509 / 1.521 = 99,2%. Sebelas emiten baru IPO/spin-off < 1 tahun berlabel `DATA-KURANG`; satu (CWEN-A) tidak dimuat Yahoo, berlabel `GAGAL-UNDUH` | ✅ |
| Run saat pasar buka = run pagi | Logikanya diuji unit test dengan jam buatan, termasuk tutup setengah hari 28 Nov 2025. Diuji dengan data sungguhan 14 Sep 2026 pukul 20:55 UTC — setelah bel, sebelum jeda final 60 menit: Yahoo sudah mengirim bar 14 Sep, sistem membuangnya dan tabel tetap bertanggal 11 Sep. Run 21:05 UTC memakainya. Run di tengah sesi sungguhan belum pernah dilakukan, tapi jalur kodenya sama | ✅ |
| 3 malam berturut-turut otomatis | Malam 1 (data 14 Sep): jalan dan sukses, tapi terlambat 2 jam 20 menit dari jadwal karena antrean cron GitHub. Malam 2 dan 3 menyusul | ⏳ 1/3 |

Universe nyatanya ± 1.520, bukan 1.550: 87 dari 102 emiten Nasdaq-100
juga anggota S&P 500.

**Temuan yang mengubah rancangan**: beta harian satu tahun ditolak. Pada
data Sep 2025–Sep 2026 ia memberi AAPL 0,69 (korelasi dengan SPY 0,35),
KO −0,26, dan XOM −0,56 — median universe 0,71. Beta dari return mingguan
dua tahun, jendela baku penyedia data, memberi AAPL 1,07, KO 0,12, XOM
−0,01, median 0,84. Hitungan diperiksa silang dengan unduhan terpisah; angka
harian yang aneh itu memang ada di datanya, bukan salah kode.

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

**Hasil (15 Sep 2026)**:

| Syarat | Hasil | Status |
|---|---|---|
| Metrik inti terisi ≥ 90% non-keuangan | Dari 1.263 emiten non-keuangan: pendapatan 1.240, laba 1.250, OCF 1.244, aset 1.249, ekuitas 1.249, saham 1.238 (98–99%). Bank/asuransi punya jalur sendiri | ✅ |
| 10 emiten acak, selisih ≤ 2% | Dicocokkan dengan laporan kuartalan Yahoo (sumber independen), **bukan dibaca manual dari 10-K**. 48 dari 50 angka cocok ≤ 2%, median selisih 0,00%. Dua pengecualian: laba MTN (3,0%) dan pendapatan HON (5,3%, karena spin-off Solstice 2025 — kuartal lama di jendela TTM masih memuat bisnis yang sudah dipisah) | ✅ dengan catatan |
| F-score 20 emiten identik dengan hitungan manual | **Diganti**: hitungan tangan satu kasus lengkap (9 komponen) di `tests/test_fundamental.py`, hasil identik. Mencocokkan 20 emiten dengan tangan tidak dikerjakan | ⚠️ diganti |
| `analisa.py AAPL` menyebut basis, periode, tag | Ya, lengkap dengan tautan EDGAR | ✅ |

Durasi: pembaruan fundamental ± 200 detik untuk 1.514 CIK; run malam tetap
± 2 menit karena hanya membaca `data/fundamental.csv`.

**Temuan yang mengubah rancangan**:

1. *companyfacts hanya memuat fakta non-dimensional.* Emiten yang
   melaporkan angka per segmen atau per kelas saham kehilangan angka
   totalnya: CAT, Ford, dan GM (utang), APA dan MTH (pendapatan), BRK (jumlah saham sejak
   2015). Ditangani dengan tag cadangan, total utang dari 10-K terakhir (≤ 200
   hari), jadwal jatuh tempo utang, jumlah
   saham setara dari Yahoo, dan flag `UTANG-TAK-TERBACA` — yang kini juga
   menyala bila ada penerbitan atau pelunasan utang material tanpa saldo
   yang terbaca (Ford), supaya emiten berutang tidak tampil bebas utang.
2. *Pencarian teks penuh EDGAR tidak menggabungkan beberapa form.* "8-K"
   memberi 106 emiten dengan Item 4.02; "8-K,8-K/A" hanya 5. Setiap form kini
   dicari sendiri.
3. *Altman Z < 1,8 bukan flag berat.* Lihat Pilar 2 di metodologi:
   174 emiten, sebagian besar padat modal berperingkat investasi. Flag berat
   pindah ke `DISTRES` (Z rendah dan bunga tidak tertutup), 69 emiten.
4. *Frasa going concern longgar salah tangkap.* Hanya kalimat baku auditor
   yang dipakai, dan flag-nya diturunkan menjadi peringatan.
5. *ROIC dengan kas dikurangi meledak* untuk emiten kaya kas; modal investasi
   kini utang + ekuitas.
6. *Emiten pindah CIK.* XOM terdaftar ulang dengan CIK baru 2115436 pada
   2026; histori digabung dari CIK lama lewat `CIK_PENDAHULU`. Tujuh emiten
   lain berhistori pendek (ADIG, HONA, MBGL, MFP, SKT, SPCX, VGNT) — umumnya
   spin-off atau IPO baru, bukan pindah CIK — dicetak tiap run sebagai
   kandidat untuk diperiksa.

**Keterbatasan yang diterima**: spin-off dan operasi yang dihentikan di
dalam jendela TTM (HON); utang dari tag komponen bisa tumpang tindih
(Keyakinan −10); metrik khusus bank tidak tersedia.

## Fase 3 — Smart money & Growth/Revisi (± 2 minggu)

**Dibangun**: `smartmoney.py` (Form 4 langsung dari EDGAR — lihat temuan 1 di
bawah), faktor **Growth/Revisi** di `faktor.py`, `scripts/perbarui_smartmoney.py`,
`scripts/verifikasi_smartmoney.py`, kolom `Z_SmartMoney`, `Z_Growth`,
`Hari_Ke_Earnings`, flag `SHORT-TINGGI`, `INSIDER-JUAL`, `EARNINGS-DEKAT`,
tab **Smart money** di dashboard, dan `hasil/smartmoney.csv` tiap malam.

**Selesai bila**:
- Insider net 90 hari cocok dengan tabel di OpenInsider untuk 10 emiten
  (pembanding gratis, dicek manual).
- Cluster buy terdeteksi pada minimal satu kasus yang diketahui (cari
  contoh terkini saat fase ini dimulai).
- Short % float cocok dengan angka FINRA terakhir ± 1 poin.

**Status (15 Sep 2026)**: kode, uji, dokumen, dan workflow selesai; **ketiga
syarat di atas belum bisa diperiksa** karena semuanya menuntut data sungguhan,
dan pembaruannya baru jalan pada run mingguan berikutnya (Minggu 06:17 WIB)
atau saat `Fundamental & Smart Money Mingguan` dijalankan manual. Yang sudah
diperiksa tanpa jaringan:

| Pemeriksaan | Hasil |
|---|---|
| Parser Form 4: kode P/S, pelapor, nilai, penanda 10b5-1 (kotak centang & catatan kaki), dokumen rusak | Unit test di `tests/test_smartmoney.py` |
| Cluster buy: dua pelapor berbeda dalam 30 hari — dan **bukan** satu pelapor dua kali atau dua pelapor berjarak 60 hari | Unit test |
| Jalur unduh inkremental: nomor akses yang sudah tersimpan tidak diunduh lagi | `tests/test_sec_form4.py` dengan klien EDGAR tiruan |
| Perakitan `hasil/semua.csv` dari tiga sumber, flag baru, dan dashboard | `tests/test_tabel.py` + `node scripts/uji_dashboard.js` terhadap pipeline penuh dengan harga & smart money buatan (1.521 baris) |

Setelah run sungguhan yang pertama, jalankan
`python scripts/verifikasi_smartmoney.py --jumlah 10` — ia mencetak angka kita
bersebelahan dengan versi Yahoo, ditambah tautan OpenInsider, Form 4 asli di
EDGAR, dan short interest FINRA untuk tiga syarat di atas — lalu isi tabel
hasilnya di sini.

**Temuan yang mengubah rancangan**:

1. *Form 4 diambil langsung dari EDGAR, bukan dari yfinance.* Rencana awal
   "yfinance dulu" ditinggalkan sebelum dicoba, karena ringkasan Yahoo tidak
   memuat tiga hal yang justru menentukan artinya: kode transaksi (`P` beli
   pasar terbuka vs `M` eksekusi opsi vs `A` hibah), CIK tiap pelapor (tanpa
   itu cluster buy tidak bisa dibedakan dari satu orang yang membeli dua
   kali), dan penanda rencana 10b5-1. Tanpa ketiganya, "insider buying" akan
   didominasi pemberian kompensasi — yang justru tidak prediktif.
2. *Biayanya dibayar sekali.* Jendela 90 hari untuk 1.500 emiten adalah
   puluhan ribu dokumen (± 40 menit pada 8 permintaan/detik). Karena itu
   transaksi pasar terbuka disimpan 180 hari di `data/insider.csv` dan
   di-commit; run mingguan berikutnya hanya mengunduh nomor akses baru
   (± 5 menit). Berkas itu sekaligus jejak audit: setiap angka bisa dilacak
   ke nomor akses EDGAR-nya.
3. *Revisi target 3 bulan harus dikumpulkan sendiri.* yfinance hanya memberi
   target konsensus hari ini, bukan histori revisinya. `data/target_riwayat.csv`
   menyimpan satu snapshot per pekan, jadi kolom `Target_Revisi` **kosong
   sampai riwayatnya mencapai tiga bulan** — dan sengaja tidak diisi dengan
   revisi seminggu, yang artinya lain.
4. *`Target_Upside` tidak masuk skor.* Jarak harga ke target konsensus naik
   ketika harganya jatuh; target analis bergerak lambat mengikuti harga.
   Yang masuk `Z_Growth` adalah arah revisinya. Upside tetap ditampilkan.
5. *Sebaran `Z_SmartMoney` lebih sempit dari faktor lain* (simpangan ± 0,7
   pada uji pipeline, bukan 1,0), karena sebagian besar emiten memang tidak
   punya transaksi orang dalam dan komponennya bernilai netral 0. Ini
   dibiarkan — memaksa simpangannya jadi 1 akan membesarkan perbedaan antar
   emiten yang sama-sama tidak memberi sinyal. Konsekuensinya: pada bobot
   yang sama, faktor ini menyumbang lebih sedikit ke skor komposit daripada
   angka bobotnya. Fase 4 harus memutuskan itu secara sadar.
6. *`PE_Fwd` ditambahkan sebagai kolom, tidak masuk `Z_Value`.* Alasannya di
   [03 §4](03-rancang-bangun.md#4-kolom-hasilsemuacsv).

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
- Laporan menyebut return setelah biaya (komisi, spread ± 0,05%,
  kurs) dan membandingkannya dengan ETF faktor.

## Fase 6 — Dashboard & operasi (± 1 minggu)

**Dibangun**: `dashboard/index.html` (dari IDX + banner rezim + tab),
`winrate.html`, GitHub Pages, catatan operasional ("Yang perlu sesekali
dilirik" seperti di README IDX).

**Dimajukan sebagian (15 Sep 2026)**: dashboard, panel detail, GitHub Pages,
dan uji dashboard sudah jalan bersama Fase 2 atas permintaan pemilik; tab
Smart money, kelompok kolomnya, dan pewarnaan `Hari ke lapkeu` menyusul
bersama Fase 3. Yang tersisa untuk fase ini: banner rezim, tab
Akumulasi/Pantau, `winrate.html`, dan catatan operasional.

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
