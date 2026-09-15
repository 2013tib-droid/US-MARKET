# 03 — Rancang Bangun

Turunan teknis dari [01-metodologi.md](01-metodologi.md) dan
[02-infrastruktur.md](02-infrastruktur.md): berkas apa, modul apa, kolom apa.
Ditulis sebelum kode supaya kodenya nanti mengikuti dokumen, bukan sebaliknya.

## 1. Struktur repo (target akhir)

```
US-MARKET/
├── README.md
├── requirements.txt
├── docs/                      ← dokumen ini
├── .github/workflows/
│   ├── screening-malam.yml    ← Sel–Sab 05:17 WIB: harga, faktor, screening, SMC, winrate, Pages
│   └── fundamental-mingguan.yml ← Minggu 06:17 WIB: SEC XBRL, going concern, restatement (smart money di Fase 3)
├── tickers/
│   ├── sp500.csv  sp400.csv  sp600.csv  nasdaq100.csv   ← otomatis, dengan nama & sektor
│   └── watchlist.txt                                    ← manual
├── data/                      ← cache, di-commit
│   ├── fundamental.csv  smartmoney.csv  insider.csv  target_riwayat.csv  makro.csv
├── hasil/                     ← keluaran tiap malam, di-commit
├── dashboard/
│   ├── index.html             ← tabel hasil + filter, baca CSV dari hasil/
│   └── winrate.html
├── usmarket/                  ← paket Python; setiap modul bisa diimpor & diuji
│   ├── universe.py    ← konstituen indeks, watchlist
│   ├── kalender.py    ← libur & jam tutup NYSE, kapan bar harian final
│   ├── harga.py       ← yf.download batch, coba ulang, "selalu data penutupan"
│   ├── tabel.py       ← menyusun hasil/semua.csv: kolom, likuiditas, red flag
│   ├── valuasi.py     ← metrik yang butuh harga: market cap, EV, yield, Altman Z, Z_Value, Z_Quality, Keyakinan
│   ├── sec.py         ← klien EDGAR: CIK, companyfacts, submissions, Form 4
│   ├── fundamental.py ← rasio dari XBRL: ROIC, akrual, F-score, Z-score, shareholder yield
│   ├── smartmoney.py  ← insider net, cluster buy, institusi, short interest
│   ├── makro.py       ← FRED + indeks → rezim
│   ├── faktor.py      ← z-score sektor, bobot rezim, skor komposit
│   ├── teknikal.py    ← MA, ATR, RS line, trend template, volume dollar
│   ├── status.py      ← AKUMULASI / PANTAU / … + red flag
│   └── smc.py         ← disalin dari repo IDX, disesuaikan H4
├── screener.py                ← CLI utama (pola sama dengan IDX)
├── analisa.py                 ← laporan Markdown satu emiten
├── analisa_smc.py             ← zona entri/stop/target untuk kandidat
├── uji_winrate.py             ← arsip pick + hasil forward
├── scripts/
│   ├── perbarui_universe.py  perbarui_fundamental.py  verifikasi_fundamental.py
│   ├── cek_hari_bursa.py  perbarui_smartmoney.py  verifikasi_smartmoney.py
│   └── uji_*.py               ← uji kecil per modul, jalan di CI sebelum screening
└── tests/                     ← pytest untuk fungsi murni (z-score, F-score, rezim)
```

Beda dengan repo IDX: logika dipecah ke paket `usmarket/` alih-alih satu
`screener.py` 50 KB. Alasannya bukan estetika: metrik AS lebih banyak
(XBRL, Form 4, FRED), dan tiap sumber data punya cara gagalnya sendiri.
Modul terpisah = bisa diuji terpisah = bisa `continue-on-error` terpisah.

## 2. Kontrak antar modul

Setiap modul menerima dan mengembalikan `pandas.DataFrame` dengan indeks
`Ticker`. Tidak ada modul yang menulis berkas kecuali `scripts/` dan CLI.
Kolom yang dihasilkan tiap modul tetap (didaftar di §4), sehingga
`screener.py --dari-csv` bisa memfilter ulang tanpa fetch, persis pola IDX.

| Modul | Masukan | Keluaran | Bisa gagal karena | Kalau gagal |
|---|---|---|---|---|
| `universe` | tickers/*.csv + watchlist.txt | daftar Ticker + `Indeks` | Wikipedia berubah | pakai file terakhir yang di-commit |
| `harga` | daftar Ticker | OHLCV 2 tahun (panel) | Yahoo rate-limit | retry 3× dengan jeda; ticker yang kosong ditandai `DATA KURANG`, run lanjut |
| `sec` + `fundamental` | peta CIK SEC (diunduh tiap run) | data/fundamental.csv | EDGAR 403 (User-Agent), tag XBRL beda per emiten | emiten tanpa tag inti → kolom NaN + `Keyakinan` turun; **tidak** dibuang |
| `smartmoney` | peta CIK SEC + daftar Form 4 per emiten + yfinance | data/insider.csv, data/smartmoney.csv, data/target_riwayat.csv | EDGAR 403, dokumen Form 4 rusak, yfinance kena batas laju | Dokumen yang gagal dilewati (run berikutnya mengambilnya lagi karena nomor aksesnya belum tersimpan); komponen yang kosong dianggap **netral (0)**, tapi emiten yang sama sekali tidak ada di smartmoney.csv tetap NaN — itu data hilang, bukan sinyal nol |
| `makro` | — | rezim + tabel | FRED key hilang | rezim = NETRAL + peringatan di meta.json |
| `faktor` | gabungan di atas | z-score per faktor + `Skor` | sektor < 5 emiten | z-score dihitung terhadap universe, ditandai `SektorKecil` |
| `teknikal` | panel harga | MA, ATR, RS, TrendTemplate | data < 250 bar | TrendTemplate = False, `Keyakinan` turun |
| `status` | semua kolom | `Status`, `Flag` | — | — |

## 3. Tag XBRL yang dipakai (dan fallback-nya)

Emiten AS tidak seragam memakai tag. `fundamental.py` mencoba urutan ini dan
mencatat tag mana yang terpakai di kolom `Sumber_<metrik>`:

| Metrik | Tag utama | Fallback |
|---|---|---|
| Revenue | `Revenues` | `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet` |
| Laba bersih | `NetIncomeLoss` | `ProfitLoss` |
| OCF | `NetCashProvidedByUsedInOperatingActivities` | — |
| Capex | `PaymentsToAcquirePropertyPlantAndEquipment` | `PaymentsToAcquireProductiveAssets` |
| Total aset | `Assets` | — |
| Utang | `LongTermDebt` + `DebtCurrent` | `LongTermDebtNoncurrent`, `ShortTermBorrowings` |
| Kas | `CashAndCashEquivalentsAtCarryingValue` | `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents` |
| Ekuitas | `StockholdersEquity` | `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` |
| Saham beredar | `dei:EntityCommonStockSharesOutstanding` | `WeightedAverageNumberOfDilutedSharesOutstanding` |
| Buyback | `PaymentsForRepurchaseOfCommonStock` | — |
| Dividen tunai | `PaymentsOfDividendsCommonStock` | `PaymentsOfDividends` |
| Goodwill | `Goodwill` | — |
| EBIT | `OperatingIncomeLoss` | Laba sebelum pajak + beban bunga |

Nilai TTM = jumlah 4 kuartal terakhir (10-Q) atau langsung dari 10-K bila
kuartalnya tidak lengkap; kolom `Basis` mencatat `TTM-4Q` atau `FY`.

## 4. Kolom `hasil/semua.csv`

Dikelompokkan supaya dashboard bisa menyembunyikan grup yang tidak dibutuhkan.

**Identitas**: `Ticker`, `Nama`, `Sektor`, `Industri`, `Indeks` (SP500/SP400/SP600/NDX/WATCH), `MCap_MiliarUSD`, `Harga`, `Basis`, `Periode_Lapkeu`, `Earnings_Berikut`, `Hari_Ke_Earnings`

**Likuiditas**: `Nilai20H_JutaUSD`, `VolSpike`, `LolosLikuiditas`

**Value** (Fase 2): `EV_EBITDA`, `PE_TTM`, `PB` (kelipatan, untuk dibaca), `EBITDA_EV`, `E_P`, `FCF_Yield` (%; yang dipakai skor), `Z_Value`. `PE_Fwd` ada sejak Fase 3 tapi **tidak** masuk `Z_Value`: EPS forward berasal dari konsensus yfinance yang liputannya tidak merata, dan mencampur proksi ke dalam faktor yang sudah diverifikasi dengan angka audit akan menyembunyikan mana yang salah bila peringkatnya bergeser

**Quality** (Fase 2): `ROIC`, `ROE`, `GrossMargin`, `Akrual` (%), `GM_Stabilitas5T`, `ROA_Variabilitas5T` (poin persen), `NetDebt_EBITDA`, `OCF_Laba`, `Cakupan_Bunga` (x, dibatasi ±999 = tanpa beban bunga), `F_Score`, `Z_Altman`, `Z_Quality`

**Identitas tambahan** (Fase 2): `MCap_MiliarUSD`, `Basis` (TTM-4Q/FY), `Periode_Lapkeu`. Angka mentah (pendapatan, utang, tag XBRL yang terpakai) ada di `data/fundamental.csv`, bukan di tabel malam

**Momentum**: `Ret12_1`, `Ret6_1` (%), `Mom_RiskAdj` (return ÷ `Vol1T`), `Z_Momentum`, `RS_Rating` (1–99)

**Low-Vol**: `Vol1T`, `Beta`, `MaxDD1T`, `Z_LowVol`

**Growth/Revisi** (Fase 3): `Rev_YoY`, `Laba_YoY` (dari SEC, sudah ada sejak Fase 2), `Rev_CAGR3`, `EPS_CAGR3`, `Target_Rata`, `Target_Upside`, `Target_Revisi`, `Rekom_Rata`, `Jumlah_Analis`, `Surprise_Terakhir`, `Z_Growth`. Yang masuk `Z_Growth`: Laba_YoY 25%, Rev_YoY 20%, EPS_CAGR3 15%, Rev_CAGR3 10%, Target_Revisi 20%, Surprise_Terakhir 10% — minimal dua komponen terisi. `Target_Upside` **tidak** masuk skor (upside besar hampir selalu berarti harga yang jatuh, bukan target yang naik); `EPS_YoY` diganti `Laba_YoY` + `EPS_CAGR3`, karena EPS per kuartal tidak tersedia serapi laba bersih di XBRL non-dimensional

**Smart money** (Fase 3): `Insider_Net90H_JutaUSD`, `Insider_Beli90H_JutaUSD`, `Insider_Jual90H_JutaUSD`, `Insider_Pembeli90H`, `Insider_ClusterBuy`, `Insider_Net_PctMCap`, `Insider_Terakhir`, `Institusi_Pct`, `Institusi_Delta`, `Short_PctFloat`, `Short_Ratio`, `Z_SmartMoney`. Angka mentah per transaksi ada di `data/insider.csv`, bukan di tabel malam

**Yield & pertumbuhan** (Fase 2): `DivYield`, `Buyback_Yield` (buyback − penerbitan saham), `Shareholder_Yield`, `Rev_YoY`, `Laba_YoY`, `Dilusi_YoY` (%)

**Teknikal**: `MA50`, `MA150`, `MA200`, `MA200_Naik`, `High52`, `Low52`, `RS_vs_SPX`, `RS_HighBaru`, `ATR14`, `RSI14`, `TrendTemplate`

**Skor & keputusan**: `Rezim`, `Skor`, `Status`, `Flag`, `Keyakinan`, `Alasan`

`Alasan` adalah kalimat pendek yang menjelaskan status ("Skor 82, tren
lolos, insider cluster buy 3 orang") — supaya dashboard tidak perlu
menerjemahkan angka.

## 5. Red flag (kolom `Flag`, dipisah `;`)

| Kode | Arti | Berat? |
|---|---|---|
| `DISTRES` | Altman Z < 1,8 **dan** EBIT/bunga < 1,5 | ✅ → HINDARI |
| `ZONA-BAHAYA` | Altman Z < 1,8 saja (non-keuangan, bukan REIT/utilitas) | ⚠️ — sering salah alarm untuk emiten padat modal |
| `RESTATEMENT` | 8-K Item 4.02 dalam 400 hari | ✅ → HINDARI |
| `GOING-CONCERN` | Kalimat going concern baku auditor di 10-K/10-Q setahun terakhir | ⚠️ — wajib dibaca, bisa kalimat "sudah teratasi" |
| `SAHAM-JANGGAL` | Laba > market cap atau nilai buku > 20× market cap: jumlah saham salah | ✅ → valuasi dikosongkan |
| `UTANG-TAK-TERBACA` | Beban bunga material tapi saldo utang tidak ada di XBRL non-dimensional (non-keuangan) | ⚠️ — EV & leverage kosong |
| `FILER-ASING` | Laporan IFRS atau bukan USD | Fundamental tidak dihitung |
| `LAPKEU-LAMA` | Periode laporan terakhir > 270 hari lalu | Keyakinan −15 |
| `F-RENDAH` | Piotroski ≤ 3 | ✅ → HINDARI |
| `LABA-KERTAS` | OCF/Laba < 0,6 dua tahun | ⚠️ |
| `DILUSI` | Saham beredar naik > 5% YoY | ⚠️ |
| `GOODWILL` | Goodwill/Ekuitas > 100% | ⚠️ |
| `SHORT-TINGGI` | Short > 20% float | ⚠️; > 30% → HINDARI mulai Fase 4 |
| `INSIDER-JUAL` | Insider net jual > $10 juta dalam 90 hari, di luar rencana 10b5-1 | ⚠️ |
| `TIPIS` | Harga < $5, nilai transaksi < $10 juta/hari, atau market cap < $1 miliar | ✅ → HINDARI |
| `EARNINGS-DEKAT` | ≤ 5 hari bursa, dari tanggal earnings yfinance | ⚠️ sekarang; → TUNGGU-LAPKEU mulai Fase 4 |
| `DATA-KURANG` | Fase 1: histori < 1 tahun sehingga Momentum/Low-Vol kosong. Mulai Fase 2: juga > 3 metrik inti kosong | Keyakinan −20 |
| `SEKTOR-KECIL` | Pembanding sektor < 5, z-score diukur terhadap universe | Keyakinan −10 |
| `BASI` | Bar terakhir lebih tua dari tanggal data universe (dihentikan perdagangannya, akan delisting) | ⚠️ |
| `GAGAL-UNDUH` | Yahoo tidak punya data ticker ini (mis. CWEN-A, kelas saham yang tidak dimuat Yahoo) | Baris tetap ada, semua kolom kosong |

Flag ⚠️ tidak mengubah status, hanya tampil — sama dengan IDX: pembaca yang
memutuskan.

## 6. CLI (meniru IDX supaya kebiasaannya sama)

```bash
python screener.py                                   # seluruh universe → hasil/semua.csv
python screener.py --dari-csv hasil/semua.csv --min-skor 70 --trend-template --output hasil/akumulasi.csv
python screener.py --dari-csv hasil/semua.csv --min-skor 70 --output hasil/pantau.csv
python screener.py --dari-csv hasil/semua.csv --max-ev-ebitda 10 --min-fcf-yield 5 --min-fscore 6 --output hasil/value.csv
python screener.py --dari-csv hasil/semua.csv --min-roic 15 --max-akrual 5 --min-fscore 7 --output hasil/quality.csv
python screener.py --dari-csv hasil/semua.csv --likuid --tanpa-flag-berat --min-insider-net 0.5 --urut Z_SmartMoney --output hasil/smartmoney.csv
python screener.py --dari-csv hasil/semua.csv --cluster-buy --min-z-growth 1 --max-short-float 10
python screener.py --tickers tickers/watchlist.txt --rezim netral   # paksa rezim untuk membandingkan (Fase 4)
python analisa.py NVDA --output analisa/NVDA.md
python analisa_smc.py --dari-csv hasil/akumulasi.csv --output hasil/akumulasi_smc.csv
python uji_winrate.py                                # + pembanding SPY, QUAL, MTUM
```

## 7. Dashboard

Satu `index.html` statis yang membaca CSV lewat `fetch` — sistem desainnya
disalin dari dashboard IDX (token warna, kartu, tab, tabel lengket, pager)
supaya dua dashboard terasa satu keluarga. Dibangun lebih awal, 15 Sep 2026,
bersama Fase 2; yang sudah ada:

- Kartu + tab **Tren · Value · Quality · Smart money · Semua**, kelompok kolom
  (Ringkas, Faktor, Valuasi, Kualitas, Pertumbuhan, Smart money, Teknikal),
  saringan sektor, indeks, dan flag. Tab Smart money membuka kelompok
  kolomnya sendiri, supaya tabelnya nyambung dengan judul tabnya.
- **Panel detail** saat baris diklik: batang enam faktor, valuasi, kualitas,
  pertumbuhan, dan smart money terhadap median sektor, arti setiap red flag,
  tautan ke SEC dan Yahoo. Alamat `#TICKER` membukanya langsung.
- Kolom `Hari ke lapkeu` diwarnai merah bila ≤ 5 hari bursa.
- `scripts/uji_dashboard.js` menjalankan JavaScript dashboard di Node dengan
  DOM tiruan terhadap `hasil/*.csv` (dijalankan workflow Uji).

Yang menyusul di fase berikutnya:

- **Banner rezim** di atas: `RISK-ON · SPX +4,2% vs MA200 · VIX 14 · Guard: nonaktif`
  beserta bobot faktor yang sedang dipakai malam ini.
- Tab Akumulasi · Pantau (Fase 4) dan halaman Winrate (Fase 5).
- Harga dalam USD; **tidak** dikonversi ke rupiah di dashboard (kurs berubah,
  angkanya jadi menyesatkan). Kurs hari itu dicatat di meta.json saja.

## 8. Pengujian

| Jenis | Isi | Kapan jalan |
|---|---|---|
| `tests/` (pytest, tanpa internet) | z-score sektor dengan data buatan, F-score dari 9 komponen, Z-score Altman, trend template, parser Form 4 (termasuk penanda 10b5-1 dan dokumen rusak), cluster buy, perakitan `hasil/semua.csv` dari tiga sumber, klien EDGAR dengan jawaban tiruan. Menyusul: deteksi rezim dari seri buatan, momentum-crash guard pada data 2009 & 2020 sintetis | Tiap push |
| `scripts/uji_sec.py` | 5 ticker: tag XBRL inti terisi, TTM masuk akal (revenue AAPL > $300 miliar) | Mingguan sebelum `perbarui_fundamental` |
| `scripts/uji_harga.py` | SPY: 500 bar terakhir, tidak ada tanggal ganda, bar hari ini dibuang jika sesi belum tutup | Malam sebelum screening |
| `uji_winrate.py` | Forward test pick + pembanding ETF | Malam |

"Selalu data penutupan" diuji eksplisit: run pada 23:00 WIB (pasar buka)
harus menghasilkan tabel yang sama dengan run 05:00 WIB hari sebelumnya.

## 9. Keputusan desain yang sudah diambil

| Keputusan | Pilihan | Alasan |
|---|---|---|
| Universe | S&P 1500 + NDX + watchlist ≈ 1.550 emiten, bukan "semua saham AS" (disetujui 14 Sep 2026) | ≈ 1.550 vs ± 6.000: kualitas data & likuiditas. Yang di luar itu jarang layak untuk investor ritel dari Indonesia |
| Visibilitas repo | Publik (disetujui 14 Sep 2026) | Actions & Pages gratis tanpa batas menit; konsekuensinya tidak ada data pribadi di repo |
| Broker | Di luar cakupan | Sistem berhenti di daftar kandidat + zona harga; eksekusi manual |
| Fundamental | SEC XBRL primer, yfinance sekunder | Resmi, gratis, lengkap 20 tahun; yfinance dipakai hanya untuk yang XBRL tidak punya (estimasi, holders, short) |
| Normalisasi | z-score sektor, bukan persentil global | Supaya Value tidak = "beli bank" dan Quality tidak = "beli software" |
| Rezim | Ubah bobot, bukan on/off | Faktor yang dimatikan total = hilang saat titik balik, persis yang mau dihindari |
| Backtest | Forward (arsip pick) + backtest terbatas berlabel bias | Universe historis berbayar; jujur lebih penting dari panjang |
| Bahasa | Indonesia untuk dokumen, komentar, nama kolom; istilah pasar tetap Inggris | Konsisten dengan IDX, dan istilah faktor harus bisa dicari di makalah |
