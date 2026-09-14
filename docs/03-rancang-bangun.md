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
│   └── fundamental-mingguan.yml ← Selasa 06:17 WIB: universe, CIK, SEC XBRL, smart money
├── tickers/
│   ├── sp500.txt  sp400.txt  sp600.txt  nasdaq100.txt   ← otomatis
│   └── watchlist.txt                                    ← manual
├── data/                      ← cache, di-commit
│   ├── cik.csv  fundamental.csv  smartmoney.csv  makro.csv
├── hasil/                     ← keluaran tiap malam, di-commit
├── dashboard/
│   ├── index.html             ← tabel hasil + filter, baca CSV dari hasil/
│   └── winrate.html
├── usmarket/                  ← paket Python; setiap modul bisa diimpor & diuji
│   ├── universe.py    ← konstituen indeks, watchlist, filter likuiditas
│   ├── harga.py       ← yf.download batch, pembersihan, "selalu data penutupan"
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
│   ├── perbarui_universe.py  perbarui_cik.py
│   ├── perbarui_fundamental.py  perbarui_smartmoney.py
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
| `universe` | tickers/*.txt | daftar Ticker + `Indeks` | Wikipedia berubah | pakai file terakhir yang di-commit |
| `harga` | daftar Ticker | OHLCV 2 tahun (panel) | Yahoo rate-limit | retry 3× dengan jeda; ticker yang kosong ditandai `DATA KURANG`, run lanjut |
| `sec` + `fundamental` | data/cik.csv | data/fundamental.csv | EDGAR 403 (User-Agent), tag XBRL beda per emiten | emiten tanpa tag inti → kolom NaN + `Keyakinan` turun; **tidak** dibuang |
| `smartmoney` | Ticker | data/smartmoney.csv | yfinance holders kosong | skor smart money = 0 (netral), bukan NaN |
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

**Value**: `EV_EBITDA`, `PE_Fwd`, `PE_TTM`, `FCF_Yield`, `PB`, `Z_Value`

**Quality**: `ROIC`, `ROE`, `GrossMargin`, `GM_Stabilitas5T`, `NetDebt_EBITDA`, `Akrual`, `EPS_Variabilitas`, `F_Score`, `Z_Altman`, `OCF_Laba`, `Z_Quality`

**Momentum**: `Ret12_1`, `Ret6`, `Vol12`, `Mom_RiskAdj`, `Z_Momentum`

**Low-Vol**: `Vol1T`, `Beta`, `MaxDD1T`, `Z_LowVol`

**Growth/Revisi**: `EPS_YoY`, `Rev_YoY`, `EPS_CAGR3`, `Target_Rata`, `Target_Upside`, `Rekom_Rata`, `Surprise_Terakhir`, `Z_Growth`

**Smart money**: `Insider_Net90H_JutaUSD`, `Insider_ClusterBuy`, `Institusi_Pct`, `Institusi_Delta`, `Short_PctFloat`, `Short_Ratio`, `Z_SmartMoney`

**Yield**: `DivYield`, `Buyback_Yield`, `Shareholder_Yield`

**Teknikal**: `MA50`, `MA150`, `MA200`, `MA200_Naik`, `High52`, `Low52`, `RS_vs_SPX`, `RS_HighBaru`, `ATR14`, `RSI14`, `TrendTemplate`

**Skor & keputusan**: `Rezim`, `Skor`, `Status`, `Flag`, `Keyakinan`, `Alasan`

`Alasan` adalah kalimat pendek yang menjelaskan status ("Skor 82, tren
lolos, insider cluster buy 3 orang") — supaya dashboard tidak perlu
menerjemahkan angka.

## 5. Red flag (kolom `Flag`, dipisah `;`)

| Kode | Arti | Berat? |
|---|---|---|
| `ZONA-BAHAYA` | Altman Z < 1,8 (non-keuangan) | ✅ → HINDARI |
| `GOING-CONCERN` | Frasa going concern di 10-K terakhir | ✅ → HINDARI |
| `F-RENDAH` | Piotroski ≤ 3 | ✅ → HINDARI |
| `LABA-KERTAS` | OCF/Laba < 0,6 dua tahun | ⚠️ |
| `DILUSI` | Saham beredar naik > 5% YoY | ⚠️ |
| `GOODWILL` | Goodwill/Ekuitas > 100% | ⚠️ |
| `SHORT-TINGGI` | Short > 20% float | ⚠️; > 30% → HINDARI |
| `INSIDER-JUAL` | Insider net jual > $10 juta dalam 90 hari, bukan 10b5-1 | ⚠️ |
| `TIPIS` | Nilai transaksi < $10 juta/hari | ✅ → HINDARI |
| `EARNINGS-DEKAT` | ≤ 5 hari bursa | → TUNGGU-LAPKEU |
| `DATA-KURANG` | > 3 metrik inti kosong | Keyakinan −20 |
| `SEKTOR-KECIL` | Pembanding sektor < 5 | Keyakinan −10 |

Flag ⚠️ tidak mengubah status, hanya tampil — sama dengan IDX: pembaca yang
memutuskan.

## 6. CLI (meniru IDX supaya kebiasaannya sama)

```bash
python screener.py                                   # seluruh universe → hasil/semua.csv
python screener.py --dari-csv hasil/semua.csv --min-skor 70 --trend-template --output hasil/akumulasi.csv
python screener.py --dari-csv hasil/semua.csv --min-skor 70 --output hasil/pantau.csv
python screener.py --dari-csv hasil/semua.csv --max-ev-ebitda 10 --min-fcf-yield 5 --min-fscore 6 --output hasil/value.csv
python screener.py --dari-csv hasil/semua.csv --min-roic 15 --max-akrual 0.05 --min-fscore 7 --output hasil/quality.csv
python screener.py --sektor Technology Healthcare --min-insider-net 1 --urut Skor
python screener.py --tickers tickers/watchlist.txt --rezim netral   # paksa rezim untuk membandingkan
python analisa.py NVDA --output analisa/NVDA.md
python analisa_smc.py --dari-csv hasil/akumulasi.csv --output hasil/akumulasi_smc.csv
python uji_winrate.py                                # + pembanding SPY, QUAL, MTUM
```

## 7. Dashboard

Satu `index.html` statis yang membaca CSV lewat `fetch` — sama persis dengan
IDX, jadi `dashboard/index.html` IDX menjadi titik awal. Tambahan khusus AS:

- **Banner rezim** di atas: `RISK-ON · SPX +4,2% vs MA200 · VIX 14 · Guard: nonaktif`
  beserta bobot faktor yang sedang dipakai malam ini.
- Kolom `Hari_Ke_Earnings` diwarnai merah bila ≤ 5.
- Tab: Akumulasi · Pantau · Value · Quality · Semua · Winrate.
- Harga dalam USD; **tidak** dikonversi ke rupiah di dashboard (kurs berubah,
  angkanya jadi menyesatkan). Kurs hari itu dicatat di meta.json saja.

## 8. Pengujian

| Jenis | Isi | Kapan jalan |
|---|---|---|
| `tests/` (pytest, tanpa internet) | z-score sektor dengan data buatan, F-score dari 9 komponen, Z-score Altman, deteksi rezim dari seri buatan, momentum-crash guard pada data 2009 & 2020 sintetis, trend template | Tiap push |
| `scripts/uji_sec.py` | 5 ticker: tag XBRL inti terisi, TTM masuk akal (revenue AAPL > $300 miliar) | Mingguan sebelum `perbarui_fundamental` |
| `scripts/uji_harga.py` | SPY: 500 bar terakhir, tidak ada tanggal ganda, bar hari ini dibuang jika sesi belum tutup | Malam sebelum screening |
| `uji_winrate.py` | Forward test pick + pembanding ETF | Malam |

"Selalu data penutupan" diuji eksplisit: run pada 23:00 WIB (pasar buka)
harus menghasilkan tabel yang sama dengan run 05:00 WIB hari sebelumnya.

## 9. Keputusan desain yang sudah diambil

| Keputusan | Pilihan | Alasan |
|---|---|---|
| Universe | S&P 1500 + NDX + watchlist, bukan "semua saham AS" | 1.500 vs 6.000: kualitas data & likuiditas. Yang di luar itu jarang layak untuk investor ritel dari Indonesia |
| Fundamental | SEC XBRL primer, yfinance sekunder | Resmi, gratis, lengkap 20 tahun; yfinance dipakai hanya untuk yang XBRL tidak punya (estimasi, holders, short) |
| Normalisasi | z-score sektor, bukan persentil global | Supaya Value tidak = "beli bank" dan Quality tidak = "beli software" |
| Rezim | Ubah bobot, bukan on/off | Faktor yang dimatikan total = hilang saat titik balik, persis yang mau dihindari |
| Backtest | Forward (arsip pick) + backtest terbatas berlabel bias | Universe historis berbayar; jujur lebih penting dari panjang |
| Bahasa | Indonesia untuk dokumen, komentar, nama kolom; istilah pasar tetap Inggris | Konsisten dengan IDX, dan istilah faktor harus bisa dicari di makalah |
