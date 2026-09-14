# US-MARKET 🇺🇸

Sistem analisa dan screening saham Amerika Serikat — saudara kandung dari
[Screening-Saham](https://github.com/2013tib-droid/Screening-Saham) (IDX), tapi
dengan **kungfu yang berbeda**, karena pasarnya berbeda.

> **Status: Fase 0 — rancangan.** Repo ini baru berisi dokumen desain. Belum ada
> kode yang jalan. Urutan pembangunannya ada di [docs/04-roadmap.md](docs/04-roadmap.md).

## Kenapa kungfunya harus beda

Di IDX ada tiga kungfu: **teknikal, fundamental, bandarmologi**. Yang ketiga
hidup karena BEI mempublikasikan *broker summary* — siapa beli, siapa jual,
lewat sekuritas mana — dan karena satu-dua pihak besar memang bisa menggerakkan
saham berkapitalisasi kecil-menengah.

Di AS tidak ada broker summary, dan tidak ada "bandar" dalam arti IDX. Volume
harian NYSE + Nasdaq sekitar 10–15 miliar lembar, 70–80% di antaranya
institusi dan algoritma. Satu pihak tidak bisa "menggoreng" Apple. Yang ada
justru **data publik yang jauh lebih kaya dan wajib hukum**: laporan keuangan
XBRL di SEC, transaksi orang dalam (Form 4) yang harus dilapor dalam 2 hari
kerja, kepemilikan institusi (13F) tiap kuartal, short interest tiap dua
minggu. Dan ada tiga puluh tahun riset akademik yang sudah membuktikan
premi apa yang benar-benar ada di pasar ini — dan premi apa yang hanya mitos.

Jadi kungfu AS bukan "teknikal + fundamental + bandarmologi", melainkan:

| # | Pilar | Menjawab pertanyaan | Padanan IDX |
|---|---|---|---|
| 1 | **Faktor kuantitatif** (Quality, Value, Momentum, Low-Vol, Yield, Size) | Saham *jenis apa* yang secara statistik memberi premi, dan kapan | Sebagian fundamental + sebagian teknikal, tapi diukur, bukan diraba |
| 2 | **Fundamental kualitas** (Piotroski F-score, ROIC, akrual, laba jadi kas) | Apakah bisnisnya *benar-benar* bagus, bukan cuma terlihat bagus | Fundamental |
| 3 | **Smart money** (insider Form 4, 13F institusi, short interest, buyback) | Apa yang dilakukan orang yang tahu lebih banyak dari kita | Bandarmologi — tapi legal, terdokumentasi, dan tertinggal 2 hari–45 hari |
| 4 | **Rezim makro & rotasi** (SPX vs MA200, VIX, yield curve, credit spread) | Faktor mana yang sedang "musimnya" — lihat gambar MSCI di bawah | Tidak ada padanan yang rapi; di IDX orang bilang "market lagi bagus/jelek" |
| 5 | **Tren & relative strength** (trend template, RS line, breakout, SMC) | *Kapan* masuk dan di harga berapa batal | Teknikal |

Uraian lengkapnya, beserta bukti akademiknya, ada di
[docs/01-metodologi.md](docs/01-metodologi.md).

## Pelajaran dari grafik MSCI (enam faktor, 1999–2016)

Grafik yang dijadikan rujukan menyusun enam faktor MSCI (Volatility, Yield,
Quality, Momentum, Value, Size) plus MSCI World tiap tahun dari yang paling
tinggi ke paling rendah. Dibaca sebagai analis, isinya tiga kalimat:

1. **Momentum adalah faktor paling sering juara** (1999, 2005, 2007, dan
   nomor dua di 2010, 2013, 2015) — **dan paling sering juru kunci persis di
   titik balik pasar** (2000, 2001, 2009, 2016). Di 2009 momentum hanya 14,8%
   sementara faktor lain 31–42%. Ini "momentum crash" (Daniel & Moskowitz,
   2016): begitu pasar berbalik dari dasar, saham yang tadinya paling jelek
   justru melesat, dan portofolio momentum tertinggal jauh.
2. **Tidak ada faktor yang menang setiap tahun.** Peringkatnya berputar.
   Min-Volatility paling tahan di 2008 (−29,2% vs −40% lebih untuk yang lain)
   tapi biasa-biasa saja di tahun bullish.
3. Karena itu **jawabannya bukan memilih satu faktor, melainkan (a) gabungan
   beberapa faktor yang korelasinya rendah, dan (b) kesadaran rezim** — tahu
   kapan momentum harus dikurangi bobotnya. Itu persis desain skor komposit
   di dokumen metodologi.

## Peta dokumen

| Dokumen | Isi |
|---|---|
| [docs/01-metodologi.md](docs/01-metodologi.md) | Lima pilar kungfu AS, bukti akademik, definisi tiap metrik, skor komposit, overlay rezim, dan apa yang sengaja tidak dilakukan |
| [docs/02-infrastruktur.md](docs/02-infrastruktur.md) | Sumber data (semuanya gratis), batas kuota, pipeline, jadwal CI dalam WIB, cache, biaya |
| [docs/03-rancang-bangun.md](docs/03-rancang-bangun.md) | Struktur repo, modul, kolom output, label status, red flag, dashboard, pengujian |
| [docs/04-roadmap.md](docs/04-roadmap.md) | Enam fase pembangunan, keluaran tiap fase, dan syarat "selesai" |
| [docs/05-praktik-us-vs-idx.md](docs/05-praktik-us-vs-idx.md) | Jam bursa dalam WIB, T+1, fraksional, aturan PDT, pajak W-8BEN, risiko khusus AS |

## Prinsip yang dibawa dari Screening-Saham

- **Data gratis, tanpa langganan.** Kalau suatu fitur butuh layanan berbayar,
  biayanya disebut di depan dan fiturnya ditandai opsional — bukan dibangun
  dulu lalu ternyata bayar.
- **Selalu data penutupan.** Screening jalan setelah Wall Street tutup
  (sekitar pukul 05:00 WIB), keputusan dieksekusi sesi berikutnya.
- **Skor menyatakan biasnya.** Setiap angka yang diturunkan dari asumsi harus
  menyebut asumsinya. Tidak ada DCF sepuluh tahun dari data tiga tahun.
- **Diuji, bukan dipercaya.** Setiap daftar pick dicatat dan dihitung
  winrate-nya seperti `uji_winrate.py` di IDX — sebelum uang sungguhan masuk.
- **Bahasa Indonesia di dokumen dan komentar**, istilah pasar tetap dalam
  bahasa aslinya (momentum, quality, short interest) supaya bisa dicari.

## Disclaimer

Alat bantu riset, bukan rekomendasi investasi. Saham AS punya risiko kurs
(USD/IDR), risiko pajak lintas negara, dan jam perdagangan malam hari WIB.
Keputusan dan risikonya sepenuhnya di tangan pengguna.
