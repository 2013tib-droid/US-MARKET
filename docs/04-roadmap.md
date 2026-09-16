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
| 3 malam berturut-turut otomatis | Dua malam sukses tanpa tangan, keduanya terlambat ± 2 jam (lihat di bawah). Malam 3 jatuh 16 Sep 22:17 UTC | ⏳ 2/3 |

Rincian malam otomatis, dari daftar run `screening-malam.yml` bertrigger
`schedule` (jadwal 22:17 UTC, Senin–Jumat):

| Malam | Dijadwalkan | Mulai | Telat | Hasil |
|---|---|---|---|---|
| 1 (data 14 Sep) | 14 Sep 22:17 | 15 Sep 00:37 | 2j 20m | sukses |
| 2 (data 15 Sep) | 15 Sep 22:17 | 16 Sep 00:18 | 2j 01m | sukses |

Telat ± 2 jam muncul di **kedua** malam, jadi itu sifat tetap antrean cron
GitHub, bukan insiden sekali. Tidak merusak apa pun — jadwal 22:17 UTC sudah
≥ 1 jam setelah bel tutup, dan tabelnya tetap memakai penutupan sesi yang
benar — tapi jangan diperlakukan sebagai anomali kalau terulang lagi.

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

**Status (15 Sep 2026)**: kode, uji, dokumen, dan workflow selesai dan sudah
digabung ke `main` lewat PR #4. Run malam pertama dengan skema 3 jalan sukses
tanpa tangan: 1.521 emiten, 152 detik, `growth_terisi` 1.250, `Z_SmartMoney`
nol emiten — memang nol, karena `data/smartmoney.csv` belum ada saat itu dan
`hasil/smartmoney.csv` hanya berisi kepala kolom. Workflow **Fundamental &
Smart Money Mingguan** dijalankan manual 15 Sep 2026 pukul 07:40 UTC untuk
mengisinya; run pertama ± 40 menit karena mengunduh tiap Form 4 dalam jendela
90 hari sekali.

Satu jebakan yang ditemukan saat itu: workflow mingguan juga terpicu oleh
push ke branch `fase-*` yang menyentuh berkas smart money, jadi menggabungkan
`main` ke branch fitur menjadwalkan unduhan Form 4 kedua yang akan meng-commit
`data/` ke branch itu. Grup concurrency `tulis-data` menahannya di antrean
(bukan jalan berbarengan dan melewati batas 8 permintaan/detik SEC), tapi
antrean itu tetap harus dibatalkan manual. Kalau nanti terulang: batalkan run
`fase-*`-nya, biarkan yang di `main`.

**Ketiga syarat "selesai" di atas belum diperiksa** — semuanya menuntut data
sungguhan. Yang sudah diperiksa tanpa jaringan:

| Pemeriksaan | Hasil |
|---|---|
| Parser Form 4: kode P/S, pelapor, nilai, penanda 10b5-1 (kotak centang & catatan kaki), dokumen rusak | Unit test di `tests/test_smartmoney.py` |
| Cluster buy: dua pelapor berbeda dalam 30 hari — dan **bukan** satu pelapor dua kali atau dua pelapor berjarak 60 hari | Unit test |
| Jalur unduh inkremental: nomor akses yang sudah tersimpan tidak diunduh lagi | `tests/test_sec_form4.py` dengan klien EDGAR tiruan |
| Perakitan `hasil/semua.csv` dari tiga sumber, flag baru, dan dashboard | `tests/test_tabel.py` + `node scripts/uji_dashboard.js` terhadap pipeline penuh dengan harga & smart money buatan (1.521 baris) |

**Tiga dugaan bentuk API sudah terjawab (16 Sep 2026).** Tiga hal di
`perbarui_smartmoney.py` adalah tebakan tentang bentuk API yang tidak bisa
diuji tanpa jaringan, dan ketiganya gagal dengan diam. Run mingguan 15 Sep
sudah menjawabnya; buktinya di `data/smartmoney_meta.json` dan
`data/insider.csv` yang ikut ter-commit, jadi tidak perlu jaringan untuk
memeriksanya ulang:

| Dugaan | Gejala kalau salah | Kenyataannya |
|---|---|---|
| `primaryDocument` Form 4 menunjuk versi terjemahan XSL, dan nama berkas di belakangnya adalah XML aslinya | `filing_baru` ribuan tapi `transaksi_baru` nol | **Benar.** `filing_baru` 16.752 → `transaksi_baru` 33.102, `gagal_dokumen` 0. Tidak perlu `…-index.json` per filing |
| Kotak centang 10b5-1 memakai nama tag yang memuat "10b5" | `Insider_Rencana90H` nol di seluruh universe, padahal penjualan terjadwal lazim | **Benar.** 12.745 dari 32.541 transaksi bertanda rencana (39%), 446 emiten punya ≥ 1. CRWV 785, ALAB 128 — persis pola penjualan terjadwal yang diharapkan |
| Nama medan yfinance (`heldPercentInstitutions`, `targetMeanPrice`, …) dan kolom `Ticker.earnings_dates` | `institusi_terisi`, `target_terisi`, atau `earnings_terisi` nol | **Benar, tapi cakupannya bocor** — lihat di bawah. Institusi 1.143, short 1.136, target 1.132, earnings 509 |

Yang tidak terduga justru muncul di dugaan ketiga: `Catatan_SM` berisi
`yahoo gagal: YFRateLimitError` untuk **375 dari 1.521 emiten** — seperempat
universe hilang bukan karena nama medannya salah, melainkan karena Yahoo
membatasi laju dan kode lama menyerah pada percobaan pertama. Itu bukan
kerugian kosmetik: `Institusi_Delta` yang ikut kosong justru punya bobot 0,4
di `Z_SmartMoney`. Sejak 16 Sep, galat sementara (batas laju, timeout,
koneksi putus) diulang sampai tiga kali dengan jeda menaik dan pekerja yang
dikurangi separuh tiap putaran, sedangkan galat permanen (simbol delisting)
tetap langsung menyerah. Jumlah yang akhirnya gagal kini dicatat sebagai
`yahoo_gagal` di meta — angka itu yang membedakan "Yahoo memang tidak punya
datanya" dari "kita ditolak".

`Earnings_Berikut` 509 (33% universe, 44% dari yang tidak kena batas laju)
adalah sifat sumbernya, bukan kerusakan: `Ticker.earnings_dates` hanya memuat
jadwal yang sudah dikonfirmasi emitennya. Konsekuensinya flag `EARNINGS-DEKAT`
hanya menyala untuk sepertiga universe; ketiadaannya tidak boleh dibaca
sebagai "tidak ada lapkeu dekat".

### Syarat "selesai" Fase 3

`python scripts/verifikasi_smartmoney.py` kini dua lapis. Lapis pertama tidak
butuh jaringan sama sekali dan keluar dengan kode ≠ 0 kalau gagal; lapis kedua
(`--jumlah 10`) membandingkan dengan Yahoo dan mencetak tautan OpenInsider,
EDGAR, dan FINRA untuk dibaca manusia.

| Syarat | Hasil | Status |
|---|---|---|
| Insider net 90 hari cocok dengan OpenInsider, 10 emiten | Belum. Yang sudah: seluruh agregat di `smartmoney.csv` dihitung ulang dari `insider.csv` dan cocok untuk 1.022 emiten bertransaksi, selisih maks 5,7e-14 (pembulatan float). Itu membuktikan jejak auditnya utuh — setiap angka bisa dilacak ke nomor akses EDGAR — tapi **bukan** pembanding independen | ⏳ |
| Cluster buy terdeteksi pada minimal satu kasus nyata | **Ya.** 44 emiten, semuanya lolos pemeriksaan ulang ≥ 2 pelapor berbeda. Kasus paling jelas: GME 8–10 Sep (Cohen $20,4 jt + tiga direktur), PFE 5–12 Agu (Bourla + dua direktur), BSX 31 Jul–3 Agu (Mahoney + dua direktur). AMR membuktikan aturan "bukan satu pelapor dua kali" jalan: Courtis membeli sendirian sejak 12 Jun tanpa memicu apa pun, dan tanda baru menyala 21 Agu ketika Gorzynski ikut. Sumbernya Form 4 asli, nomor aksesnya dicetak — tapi belum diklik silang ke EDGAR oleh manusia | ✅ dengan catatan |
| Short % float ± 1 poin dari FINRA | Belum. Yang sudah: 1.136 nilai semuanya di dalam 0–100% (median 6,38%, maks 49,48%), jadi tidak ada yang mustahil. Pembanding FINRA butuh jaringan | ⏳ |

Kedua syarat yang masih ⏳ menuntut sumber luar (OpenInsider, FINRA) dan
tidak bisa dikerjakan dari sesi tanpa akses keluar; jalankan
`python scripts/verifikasi_smartmoney.py --jumlah 10` dari mesin biasa, lalu
isi kolomnya di sini.

**Satu temuan sampingan dari lapis pertama**: `Institusi_Pct` > 100% untuk 468
dari 1.143 emiten yang terisi (maks NTST 160%). Bukan salah baca — Yahoo
membagi kepemilikan institusi dengan *float*, bukan saham beredar, jadi emiten
yang punya pemegang pengendali bisa lewat 100%. Yang masuk skor adalah
deltanya, dan basis itu sama di kedua snapshot, jadi angkanya dibiarkan; tapi
kolom mentahnya tidak boleh dibaca sebagai "persen saham beredar".

Dua kolom baru sengaja masih kosong sampai datanya terkumpul, dan itu bukan
kerusakan: `Rev_CAGR3`/`EPS_CAGR3` terisi setelah `perbarui_fundamental.py`
jalan sekali lagi (per 16 Sep masih 0 dari 1.521 di `data/fundamental.csv` —
kolomnya sudah ada di kode dan di kepala berkas, isinya belum), dan
`Target_Revisi` setelah `data/target_riwayat.csv` mencapai tiga bulan. Riwayat
itu kini berisi satu snapshot (15 Sep, 1.132 emiten), jadi ± 12 run mingguan
lagi.

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
5. *Sebaran `Z_SmartMoney` jauh lebih sempit dari faktor lain* — dan lebih
   sempit dari yang diperkirakan uji pipeline. Angka ± 0,7 yang tercatat di
   sini semula berasal dari data buatan; pada run malam sungguhan
   (`hasil/semua.csv`, data 15 Sep 2026) simpangannya **0,365**, sekitar
   sepertiga faktor lain:

   | Faktor | Terisi | Simpangan | p10 … p90 |
   |---|---|---|---|
   | `Z_Momentum` | 1.509 | 0,994 | −1,27 … 1,26 |
   | `Z_LowVol` | 1.509 | 0,985 | −1,43 … 1,07 |
   | `Z_Quality` | 1.448 | 0,964 | −1,06 … 1,23 |
   | `Z_Value` | 1.502 | 0,946 | −0,98 … 1,09 |
   | `Z_Growth` | 1.324 | 0,910 | −0,86 … 1,04 |
   | `Z_SmartMoney` | 1.521 | **0,365** | **−0,01 … 0,15** |

   Simpangan pun masih terlalu ramah sebagai ringkasan: rentang p10–p90
   `Z_SmartMoney` cuma selebar 0,16, artinya **80% universe praktis bernilai
   sama**, dan simpangan 0,365 itu datang dari segelintir pencilan. Sebabnya
   sama seperti dugaan semula — sebagian besar emiten memang tidak punya
   transaksi orang dalam, komponennya netral 0 — tapi akibatnya lebih tajam:
   pada bobot nominal yang sama, faktor ini hampir tidak membedakan emiten
   satu dari yang lain.

   Tetap dibiarkan apa adanya sampai Fase 4: memaksa simpangannya jadi 1 akan
   membesar-besarkan perbedaan antar emiten yang sama-sama tidak memberi
   sinyal, dan itu keputusan desain, bukan tambalan. Yang harus Fase 4
   putuskan secara sadar: memberi faktor ini bobot nominal yang jauh lebih
   besar, atau menormalkannya hanya di antara emiten yang punya transaksi,
   atau menerima bahwa ia berfungsi sebagai penyaring pencilan dan bukan
   faktor peringkat.
6. *`PE_Fwd` ditambahkan sebagai kolom, tidak masuk `Z_Value`.* Alasannya di
   [03 §4](03-rancang-bangun.md#4-kolom-hasilsemuacsv).
7. *Batas laju Yahoo harus diulang, bukan dicatat lalu dilupakan.* Kode awal
   menganggap kegagalan satu emiten sebagai kerugian yang bisa diterima
   ("kehilangan 20 dari 1.500 baris tidak merusak peringkat"). Run sungguhan
   15 Sep kehilangan 375 — asumsinya meleset 19 kali lipat, karena batas laju
   mengenai satu gelombang emiten sekaligus, bukan satu-satu secara acak.
   Kegagalan sementara kini diulang; yang permanen tetap tidak, supaya emiten
   delisting tidak membuang waktu tiga kali. Pelajarannya lebih umum:
   "kegagalan sebagian yang dicatat di kolom catatan" hanya aman kalau
   jumlahnya ikut dipantau di meta — kalau tidak, ia gagal dengan diam persis
   seperti dugaan API yang salah.

## Fase 4 — Rezim & skor komposit (± 2 minggu)

**Dibangun**: `makro.py` (rezim, momentum-crash guard, skor komposit),
`keputusan.py` (label status & `Alasan`), kolom `Rezim`, `Skor_Faktor`,
`Skor`, `Status`, `Alasan`, banner rezim di dashboard, saringan `--min-skor`
dan `--status` di `screener.py`, serta tiga skrip uji:
`scripts/uji_sensitivitas.py`, `scripts/uji_rezim_historis.py`,
`scripts/backtest.py`. Versi skema naik ke 4.

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

**Hasil (16 Sep 2026)**: kodenya selesai dan teruji, tapi **fase ini tidak
lolos**. Satu dari tiga syarat sudah bisa diperiksa dan syarat itu gagal.

| Syarat | Hasil | Status |
|---|---|---|
| Rezim 2008/2009/2020/2022 cocok dengan sebutan analis | Belum diperiksa. `scripts/uji_rezim_historis.py` siap pakai; butuh ^GSPC dan ^VIX sejak 2007 dari Yahoo | ⏳ |
| Backtest 2015–sekarang: return per risiko ≥ SPY | Belum diperiksa. `scripts/backtest.py` siap pakai; butuh harga harian seluruh universe sejak 2014 | ⏳ |
| Bobot ±10 poin: peringkat 20 besar berubah ≤ 30% | **Terburuk 50%** (Risk-on, Momentum −10). Delapan dari 44 geseran melebihi 30% | ❌ |

### Syarat 3 gagal, dan bobotnya tidak diutak-atik

`python scripts/uji_sensitivitas.py --hanya-lolos` terhadap 1.335 emiten yang
lolos likuiditas dan bebas flag berat di `hasil/semua.csv` (data 15 Sep):

| Rezim | Geseran terburuk | Berubah | Korelasi peringkat terendah |
|---|---|---|---|
| Risk-on | Momentum −10 | **50%** | ρ = 0,963 |
| Netral | Momentum +10 | **40%** | ρ = 0,954 |
| Risk-off | Value +10 | **35%** | ρ = 0,952 |
| Momentum-crash guard | (semua ≤ 30%) | 30% | ρ = 0,945 |

Aturan fase ini melarang menggeser bobot sampai lolos, dan larangan itu
justru paling berlaku di sini: syarat sensitivitas ada **untuk menangkap
skor yang hasilnya ditentukan oleh angka bobot**, jadi menyetel bobot agar
lolos berarti membuang alat ukurnya, bukan memperbaiki yang diukur.

Satu pembelaan yang wajar diuji lebih dulu — dan gugur. Dugaannya: churn 20
besar cuma efek batas, karena peringkat 20 dan 21 di antara 1.335 emiten
praktis seri, jadi potongan yang lebih panjang mestinya jauh lebih stabil.
Ternyata tidak: irisannya ~80% di top-100 juga, hampir sama dengan di top-20.
Turnover ~20% merata di tiap potongan, bukan riak di perbatasan.

Yang justru terbaca dari angkanya: **korelasi peringkat seluruh universe
sangat tinggi (ρ = 0,945–0,996) sementara irisan nama teratas rendah.**
Urutan besar-besaran stabil; yang tidak stabil adalah 10–20 nama yang
benar-benar akan dibeli. Untuk sistem yang memegang maksimum 12 posisi,
justru yang kedua yang menentukan hasil.

`Z_SmartMoney` sekali lagi jadi kasus tersendiri: menggesernya ± 10 poin
hampir tidak mengubah apa pun (ρ = 0,993–0,996, irisan 90–100%). Itu bukan
kestabilan yang menenangkan — itu temuan 5 Fase 3 muncul lagi dari arah
lain: faktor yang sebarannya 0,365 memang tidak bisa memindahkan peringkat
berapa pun bobotnya.

**Tiga pilihan untuk pemilik repo**, dan ini keputusan desain, bukan
tambalan kode:

1. **Terima dan ubah cara pakainya.** Skor dipakai sebagai penyaring
   (misalnya "Skor ≥ 70" sebagai daftar kandidat 300-an nama), bukan sebagai
   peringkat yang 20 besarnya dibeli. Timing Fase 5 yang memilih dari
   kandidat itu. Ini mengakui apa yang datanya katakan tanpa menyembunyikan.
2. **Perlebar potongan yang dianggap "hasil".** Kalau yang dipakai 50–100
   nama teratas, irisannya ~80% dan syaratnya lewat. Tapi syarat aslinya
   menyebut 20 besar karena itu yang mendekati portofolio nyata, jadi
   melebarkannya harus ditulis sebagai perubahan syarat, bukan kelulusan.
3. **Kurangi jumlah faktor.** Enam faktor dengan bobot yang berdekatan
   membuat peringkat teratas ditentukan oleh selisih kecil. Empat faktor
   dengan bobot yang berjauhan akan lebih tahan — tapi itu merombak Pilar 1–4,
   dan tidak boleh diputuskan dari satu tabel sensitivitas.

Sampai salah satunya dipilih, Fase 4 tetap **belum lolos** dan Fase 5 belum
dimulai. Kolom `Skor` dan `Status` tetap dihitung dan ditampilkan — menahannya
tidak membuat sistemnya lebih jujur, sedangkan mencatat kerapuhannya di sini
membuatnya bisa dibaca dengan benar.

**Catatan yang harus ikut ketika syarat 2 dijalankan nanti**: `backtest.py`
sengaja hanya menguji faktor dari harga (Momentum dan Low-Vol). Quality,
Value, dan Growth tidak punya deret waktu di repo ini — hanya snapshot
terakhir — jadi memakainya untuk tanggal 2015 adalah look-ahead. Yang diuji
karena itu bagian skor yang bisa diuji jujur, bukan seluruh skor, dan
laporannya harus menyebut itu bersama survivorship bias.

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
