# 01 — Metodologi: Kungfu Pasar Saham AS

Dokumen ini menjelaskan **apa** yang diukur, **kenapa** itu yang diukur, dan
**bagaimana** semuanya digabung jadi satu skor. Ditulis supaya orang yang
membaca hasil screening tahu persis dari mana angkanya datang.

## 1. Pemetaan dari kungfu IDX

| Kungfu IDX | Kenapa tidak bisa dipindah mentah-mentah | Padanannya di AS |
|---|---|---|
| **Bandarmologi** (broker summary, akumulasi/distribusi per sekuritas) | Tidak ada broker summary. Order flow dipecah ke belasan venue + dark pool; data konsolidasinya berbayar mahal. Saham besar tidak bisa "digoreng" satu pihak. | **Smart money yang wajib dilaporkan**: Form 4 (insider), 13F (institusi), short interest (FINRA), buyback (10-Q). Sinyalnya lebih lambat (2 hari–45 hari) tapi legal dan terbukti secara akademik. |
| **Fundamental** (PER, PBV, ROE, DER) | Bisa dipindah, tapi datanya jauh lebih baik: XBRL resmi SEC, 10-K/10-Q terstandar, 20+ tahun histori. Rasio yang "biasa" di IDX (PBV, PER) di AS kalah kuat dibanding ROIC, FCF yield, akrual. | **Fundamental kualitas + faktor Value/Quality** dengan metrik yang riset AS buktikan ada preminya. |
| **Teknikal** (MA, RSI, volume) | Bisa dipindah. Bedanya: pasar AS lebih *trending* dan tidak ada auto-reject/ARA-ARB, jadi breakout bisa 20% dalam sehari. Volume spike lebih sering berarti berita (earnings), bukan bandar. | **Momentum (faktor) + trend template + relative strength vs S&P 500** untuk timing. SMC dari repo IDX bisa dipakai ulang. |
| — | Di IDX jarang dipakai sistematis | **Rezim makro**: Fed, yield curve, VIX, credit spread. Data FRED gratis dan harian. |

## 2. Kenapa faktor, bukan "feeling"

Pasar AS cukup efisien sehingga informasi yang gampang (laba naik, PER murah)
sudah termasuk dalam harga dalam hitungan detik. Yang masih tersisa adalah
premi yang **bertahan puluhan tahun karena ada alasan struktural atau
perilaku** di baliknya — dan setiap premi di bawah ini punya makalah yang
menemukannya, direplikasi, dan (yang penting) punya penjelasan kenapa tidak
hilang meski semua orang tahu:

| Faktor | Makalah kunci | Kenapa preminya bertahan |
|---|---|---|
| **Value** | Fama & French (1992, 1993) | Investor membayar terlalu mahal untuk cerita bagus; saham "membosankan" diabaikan |
| **Momentum** | Jegadeesh & Titman (1993); Daniel & Moskowitz (2016) untuk *crash*-nya | Informasi diserap pelan (underreaction), lalu berlebihan (overreaction). Risikonya: berbalik tajam di titik balik pasar |
| **Quality / Profitability** | Novy-Marx (2013); Asness, Frazzini & Pedersen "Quality Minus Junk" (2019) | Pasar kurang menghargai laba yang *stabil dan jadi kas* dibanding laba yang tumbuh cepat tapi rapuh |
| **Low Volatility** | Ang, Hodrick, Xing & Zhang (2006); Blitz & van Vliet (2007) | Investor memburu saham "lotere"; saham tenang jadi kurang diminati padahal return per risikonya lebih baik |
| **Size** | Banz (1981); Fama & French (1993) | Premi kecil dan sudah melemah sejak 1990-an; **dipakai hanya sebagai tilt, bukan pilar** |
| **Yield / Shareholder yield** | Boudoukh, Michaely, Richardson & Roberts (2007) | Dividen + buyback − penerbitan saham baru. Di AS buyback lebih besar dari dividen, jadi *dividend yield* saja menyesatkan |
| **PEAD / Revisi estimasi** | Ball & Brown (1968); Bernard & Thomas (1989) | Setelah earnings surprise, harga masih *drift* searah selama 1–3 bulan. Salah satu anomali paling awet |
| **Insider buying** | Cohen, Malloy & Pomorski (2012) | Pembelian insider *rutin* tidak berarti apa-apa; pembelian *oportunistik* (tidak terjadwal, beberapa insider sekaligus) prediktif |

Yang tidak masuk daftar karena buktinya lemah atau datanya tidak bisa diakses
gratis: pola candlestick, Elliott wave, "unusual options activity" (datanya
berbayar dan sinyalnya berisik), dark pool prints.

## 3. Lima pilar, satu per satu

### Pilar 1 — Faktor kuantitatif (inti sistem)

Setiap saham diberi skor per faktor. Semua metrik dinormalisasi jadi
**z-score di dalam sektornya**, dipangkas di ±3 supaya satu outlier tidak
merusak peringkat. Sektor-netral penting: kalau tidak, faktor Value akan
selalu memilih bank dan energi, faktor Quality selalu memilih software.

| Faktor | Metrik (arah "bagus") | Sumber data | Catatan |
|---|---|---|---|
| **Value** | EBITDA/EV 30%, laba/harga 30%, FCF yield 30%, nilai buku/harga 10% — semuanya sebagai *yield* (tinggi = murah). Bank: laba/harga 50%, nilai buku berwujud/harga 50% | SEC XBRL + harga | Yield, bukan kelipatan: P/E patah di laba nol dan terbalik urutannya saat laba negatif. P/B nyaris tidak berarti untuk perusahaan aset tak berwujud; bobotnya kecil. P/E forward butuh estimasi analis dan menyusul di Fase 3 |
| **Quality** | ROIC 30%, margin kotor 20%, stabilitas margin 5 tahun 15%, utang bersih/EBITDA rendah 15%, akrual = (Laba − OCF)/Aset rendah 20%. Bank: ROE 40%, ROA 30%, stabilitas ROA 5 tahun 30% | SEC XBRL | Akrual adalah pendeteksi "laba kertas" paling sederhana dan paling teruji. ROIC = EBIT × (1 − pajak efektif) ÷ (utang berbunga + ekuitas), **tanpa dikurangi kas**: versi dikurangi kas meledak untuk emiten kaya kas (CVLT 3.475%, PLTR 1.038% pada data 14 Sep 2026). Komponen boleh bolong — perusahaan jasa tidak punya laba kotor — asal minimal 2 (Value) atau 3 (Quality) terisi |
| **Momentum** | Return 12 bulan **dikurangi 1 bulan terakhir** (12-1) dan return 6-1 bulan, keduanya dibagi volatilitas 1 tahun (*risk-adjusted*). Z-score keduanya dirata-rata | Harga harian, disesuaikan dividen | Bulan terakhir di-skip karena ada efek pembalikan jangka pendek (Jegadeesh 1990). Konstruksinya mengikuti MSCI Momentum Index |
| **Low Volatility** | Volatilitas harian 1 tahun (rendah), beta vs SPY dari **return mingguan 2 tahun** (rendah), max drawdown 1 tahun (kecil) | Harga harian | Dipakai sebagai **overlay rezim**, bukan penambah skor di pasar bullish. Beta harian ditolak setelah diuji: terlalu berisik, lihat catatan Fase 1 di roadmap |
| **Shareholder Yield** | (Dividen + buyback − penerbitan saham) / market cap | SEC XBRL (cash flow statement) | Lebih jujur dari dividend yield |
| **Growth & Revisi** | Pertumbuhan EPS & revenue YoY dan 3 tahun; arah revisi target harga analis 3 bulan; earnings surprise kuartal terakhir | yfinance (terbatas) | Revisi estimasi konsensus (I/B/E/S, Zacks) **berbayar**. Yang gratis: target harga rata-rata & jumlah rekomendasi dari yfinance — proksi kasar, ditandai sebagai proksi |
| **Size** | log(market cap) — hanya untuk tilt ke mid cap dalam universe S&P 1500 | yfinance | Tidak masuk skor komposit; hanya kolom |

### Pilar 2 — Fundamental kualitas (saringan, bukan skor)

Sebelum masuk peringkat, tiap emiten lewat **saringan biner** — meniru kolom
Flag di repo IDX:

- **Piotroski F-score** ≥ 5 dari 9 (profitabilitas, leverage, efisiensi). Di
  bawah 4 = red flag. Dibandingkan TTM terakhir dengan TTM setahun sebelumnya.
  Satu penyimpangan dari makalah aslinya: leverage memakai seluruh utang
  berbunga, bukan hanya utang jangka panjang, karena pemecahan jangka
  panjang/lancar di XBRL tidak seragam antarperiode. Emiten tanpa utang di
  kedua periode dianggap lolos komponen itu.
- **Altman Z-score** untuk non-keuangan, di luar Real Estate dan Utilities.
  Z < 1,8 **saja** hanya peringatan (`ZONA-BAHAYA`): pada data 14 Sep 2026
  ia menandai 174 emiten, termasuk VZ, T, TMUS, WMB, KMI, dan ORCL —
  perusahaan padat modal berperingkat investasi yang disalahbaca rumus
  manufaktur 1968 itu. Flag berat `DISTRES` butuh konfirmasi: Z < 1,8
  **dan** EBIT < 1,5× beban bunga (kira-kira wilayah peringkat B/CCC).
  Hasilnya 69 emiten, antara lain WBD, F, KHC, dan AAL.
- **OCF / Laba bersih** < 0,6 selama 2 tahun = laba tidak jadi kas.
- **Dilusi**: jumlah saham beredar naik > 5% YoY tanpa akuisisi = red flag.
- **Goodwill / Ekuitas** > 100% = neraca hasil akuisisi, rawan impairment.
- **Restatement** — 8-K Item 4.02 (laporan lama tidak bisa diandalkan) dalam
  400 hari terakhir, dari pencarian teks penuh EDGAR = flag berat.
- **Going concern** — kalimat baku auditor "…raise substantial doubt about
  its ability to continue as a going concern" di 10-K/10-Q = **peringatan,
  bukan flag berat**. Frasa yang lebih longgar diuji dan hanya menangkap
  kalimat kebijakan akuntansi di laporan emiten sehat, dan bahkan frasa baku
  tidak bisa membedakan "keraguan itu sudah teratasi". Wajib dibaca manusia.
- **Bank & asuransi** dinilai terpisah: ROIC, EV/EBITDA, FCF, akrual,
  Altman Z, dan F-score tidak berlaku (arus kas operasi bank didominasi
  pergerakan pinjaman dan aset perdagangan; OCF JPM TTM Jun 2026 −$162
  miliar). Dipakai ROE, ROA, stabilitas ROA, laba/harga, dan nilai buku
  berwujud/harga. Efficiency ratio, NIM, NPL, dan CET1 tidak tersedia di XBRL
  non-dimensional; kekurangan itu dicerminkan di Keyakinan (−10).

### Pilar 3 — Smart money (pengganti bandarmologi)

| Sinyal | Sumber | Lag | Cara baca |
|---|---|---|---|
| **Insider net buying** (Form 4) | SEC EDGAR | ≤ 2 hari kerja | Hitung nilai beli − jual *open market* 90 hari terakhir (abaikan exercise opsi & 10b5-1 plan yang terjadwal). ≥ 2 insider berbeda membeli dalam 30 hari = **cluster buy**, sinyal terkuat |
| **Perubahan kepemilikan institusi** (13F) | SEC EDGAR | ≤ 45 hari setelah akhir kuartal | Jumlah pemegang institusi naik + % kepemilikan naik = akumulasi. Terlalu lambat untuk timing, cukup untuk konfirmasi |
| **Short interest** | FINRA (via yfinance `shortPercentOfFloat`, `shortRatio`) | 2× sebulan | > 20% float = risiko *short squeeze* dua arah. Naik cepat = smart money pesimis. Dipakai sebagai **flag**, bukan skor |
| **Buyback aktif** | 10-Q cash flow | Kuartalan | Sudah masuk Shareholder Yield |
| **Kepemilikan institusi total** | yfinance `heldPercentInstitutions` | — | < 20% di saham > $2 miliar = tidak dilirik institusi, tanya kenapa |

Skor smart money = z-score insider net buying (bobot 60%) + perubahan
kepemilikan institusi (40%). Cluster buy menambah +1 langsung.

### Pilar 4 — Rezim makro & rotasi (overlay, bukan pemilih saham)

Grafik MSCI di README adalah alasannya: faktor yang bagus tahun ini bisa
juru kunci tahun depan. Rezim ditentukan tiap malam dari data gratis:

| Indikator | Sumber | Ambang |
|---|---|---|
| SPX vs MA200 & MA50 | yfinance `^GSPC` | Di atas keduanya = **risk-on**; di bawah MA200 = **risk-off** |
| VIX | yfinance `^VIX` | > 25 = stres; > 35 = panik |
| Yield curve 10Y − 2Y | FRED `T10Y2Y` | Negatif = resesi mengintai (lag 6–18 bulan) |
| High-yield credit spread | FRED `BAMLH0A0HYM2` | > 5% = kredit mengetat |
| Breadth: % saham S&P 500 di atas MA200 | Dihitung sendiri dari universe | < 30% = oversold pasar; > 80% = euforia |
| **Momentum-crash guard** | Dihitung sendiri | SPX pernah turun ≥ 20% dalam 12 bulan terakhir **dan** sudah naik ≥ 15% dari dasarnya dalam ≤ 3 bulan → bobot momentum dipotong setengah selama 6 bulan (pelajaran 2009 & 2020) |

Rezim mengubah **bobot** faktor, bukan mematikan faktor:

| Rezim | Quality | Momentum | Value | Growth/Revisi | Smart money | Low-Vol |
|---|---|---|---|---|---|---|
| Risk-on (SPX > MA200, VIX < 25) | 25 | 30 | 15 | 20 | 10 | 0 |
| Netral | 30 | 25 | 20 | 15 | 10 | 0 |
| Risk-off (SPX < MA200 atau VIX > 25) | 35 | 10 | 20 | 10 | 10 | 15 |
| Momentum-crash guard aktif | 30 | 10 | 30 | 10 | 15 | 5 |

Bobot ini **titik awal**, bukan hasil optimasi. Fase 4 di roadmap menguji
kombinasi lain dengan data 2010–sekarang; kalau selisihnya kecil, bobot
sederhana dipertahankan (bobot yang "dioptimasi" ke masa lalu biasanya cuma
overfit).

### Pilar 5 — Tren & relative strength (timing)

Faktor menjawab "saham apa". Timing menjawab "sekarang atau nanti":

- **Trend template** (Minervini): harga > MA50 > MA150 > MA200; MA200 naik ≥ 1
  bulan; harga ≥ 25% di atas low 52 minggu; ≤ 25% di bawah high 52 minggu.
- **Relative strength line** vs S&P 500 (harga saham ÷ SPY) membuat high baru
  sebelum harganya sendiri = kekuatan tersembunyi.
- **RS rating** 1–99 ala IBD: peringkat persentil return tertimbang
  (40% tiga bulan terakhir, masing-masing 20% untuk tiga kuartal sebelumnya)
  terhadap seluruh universe. Syarat ke-8 trend template Minervini adalah RS
  rating ≥ 70. Beda dengan Z_Momentum: lintas universe, bukan per sektor,
  dan tidak dibagi volatilitas.
- **Volume**: rata-rata 20 hari (dalam **dollar**, bukan lembar) untuk
  likuiditas; spike ≥ 1,5× di hari naik = konfirmasi.
- **Earnings dalam ≤ 5 hari bursa** = jangan masuk sebelum lapkeu (gap 10–20%
  dua arah biasa terjadi). Kolom `Earnings_Berikut` wajib ada.
- **SMC** (dari `smc.py` repo IDX): D1 + H4 + H1. H4 di AS bermakna karena
  sesi 6,5 jam tanpa jeda siang. Zona entri, stop, target, R/R.

## 4. Skor komposit

```
Skor_Faktor  = Σ (bobot_rezim[f] × z_sektor[f])   untuk f di {Quality, Momentum, Value, Growth, SmartMoney, LowVol}
Skor_Akhir   = peringkat persentil Skor_Faktor di universe (0–100)
```

Lalu saringan bertahap, urutannya penting:

1. **Universe**: S&P 1500 + Nasdaq-100 + watchlist manual (± 1.520 emiten
   unik; 87 anggota Nasdaq-100 juga ada di S&P 500).
2. **Likuiditas**: harga ≥ $5, nilai transaksi rata-rata 20 hari ≥ $10 juta,
   market cap ≥ $1 miliar (syarat market cap aktif mulai Fase 2, saat jumlah
   saham beredar tersedia dari SEC).
3. **Red flag**: buang yang kena flag berat (`DISTRES`, `RESTATEMENT`, `F-RENDAH`, `TIPIS`, `SAHAM-JANGGAL`, `GAGAL-UNDUH`).
4. **Skor** ≥ 70 masuk daftar *kandidat*.
5. **Timing**: trend template lolos → **AKUMULASI**; belum lolos → **PANTAU**.
6. **Earnings ≤ 5 hari** → status ditunda jadi **TUNGGU-LAPKEU** apa pun skornya.

## 5. Label status

Meniru repo IDX supaya dashboardnya bisa dipakai dengan kebiasaan yang sama:

| Status | Syarat |
|---|---|
| **AKUMULASI** | Skor ≥ 70, tanpa red flag berat, trend template lolos, earnings > 5 hari |
| **PANTAU** | Skor ≥ 70, tanpa red flag berat, tapi tren belum konfirmasi |
| **TUNGGU-LAPKEU** | Apa pun skornya, earnings dalam ≤ 5 hari bursa |
| **TAHAN** | Skor 50–69, sudah dipegang: belum alasan jual, belum alasan tambah |
| **KURANGI** | Skor < 50 **atau** harga tutup < MA200 setelah sebelumnya di atas |
| **HINDARI** | Red flag berat, atau short interest > 30% float, atau likuiditas gagal |

## 6. Manajemen risiko (bagian dari sistem, bukan catatan kaki)

- Ukuran posisi: maksimum 5% ekuitas per saham untuk skor 70–84, 8% untuk ≥ 85.
- Maksimum 25% ekuitas per sektor.
- Stop awal: 1,5 × ATR(14) di bawah entri atau −8% (mana yang lebih dekat),
  meniru aturan O'Neil. Tidak ada rata-rata ke bawah.
- Risiko kurs USD/IDR dicatat di laporan portofolio sebagai baris tersendiri,
  bukan disembunyikan dalam return.
- Maksimum 12 posisi. Lebih dari itu, faktor sudah dibeli lebih murah lewat ETF
  (`QUAL`, `MTUM`, `VLUE`, `USMV`) — dan itu perbandingan yang wajib ada di
  uji winrate: apakah sistem ini mengalahkan ETF faktor setelah biaya?

## 7. Yang sengaja tidak dilakukan

- **DCF** — alasannya sama dengan repo IDX: presisi palsu.
- **Prediksi harga dengan machine learning** — dengan ~1.500 emiten × 15 tahun,
  data terlalu sedikit dan terlalu berkorelasi untuk model non-linear; hasilnya
  overfit yang terlihat pintar di backtest. Faktor linear + peringkat sudah
  menangkap sebagian besar premi yang ada.
- **Intraday / scalping** — jam bursa AS = 21:30–04:00 WIB, data real-time
  gratis tidak ada, dan aturan PDT membatasi akun < $25.000.
- **Opsi** — di luar cakupan sampai sistem sahamnya terbukti.
- **Backtest faktor penuh dengan universe historis** — daftar S&P 1500 masa
  lalu (bebas survivorship bias) berbayar. Uji winrate dilakukan *forward*
  (mencatat pick tiap malam lalu menghitung hasilnya), plus backtest terbatas
  dengan konstituen sekarang **yang biasnya dinyatakan eksplisit**.
