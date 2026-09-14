"""Ekstraksi fundamental dari companyfacts SEC (XBRL, US GAAP).

Keluarannya satu baris per emiten: angka mentah dalam USD (TTM atau tahun
fiskal terakhir) dan rasio yang TIDAK bergantung harga. Rasio yang butuh
harga (valuasi, Altman Z, market cap) dihitung tiap malam di tabel.py dari
angka mentah ini, supaya harga dan laporan keuangan tidak perlu diunduh
bersamaan.

Tiga masalah XBRL yang ditangani di sini, dan cara menanganinya:

1. Tag tidak seragam. Pendapatan bisa di `Revenues`, `RevenueFromContract…`,
   atau `SalesRevenueNet` (tag lama sebelum ASC 606). Setiap metrik punya
   daftar kandidat; tag dengan periode terbaru dipakai sebagai utama, dan
   periode lama yang hanya ada di tag lain dipakai untuk mengisi histori.
   Tag yang terpakai dicatat di kolom Tag_*.
2. Kuartal keempat tidak pernah dilaporkan sendiri: 10-K hanya berisi angka
   setahun. Q4 diturunkan dari angka tahunan dikurangi sembilan bulan. Cara
   yang sama menurunkan kuartal dari selisih dua angka year-to-date.
3. Satu periode muncul di banyak laporan (sebagai pembanding tahun lalu),
   kadang dengan angka yang direvisi. Yang dipakai adalah angka dari laporan
   yang paling akhir dilaporkan.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import pstdev

import numpy as np

FORM_DITERIMA = {"10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT", "10-KT/A",
                 "20-F", "20-F/A", "40-F", "40-F/A", "6-K"}

# Rentang durasi (hari). Tahun fiskal 52/53 minggu membuat kuartal 91 atau 98
# hari dan tahun 364 atau 371 hari, jadi rentangnya sengaja longgar.
KUARTAL = (75, 105)
TAHUN = (350, 380)

# Laporan dengan periode lebih tua dari ini dianggap basi untuk screening.
MAKS_UMUR_HARI = 270

TAG = {
    "Pendapatan": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                   "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                   "SalesRevenueGoodsNet", "RevenuesNetOfInterestExpense",
                   # Industri khusus, di akhir daftar supaya tidak mengalahkan
                   # total pendapatan bila emiten melaporkan keduanya.
                   "RegulatedAndUnregulatedOperatingRevenue",   # utilitas
                   "OperatingLeaseLeaseIncome"],                # REIT sewa
    "LabaKotor": ["GrossProfit"],
    "HPP": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices"],
    "EBIT": ["OperatingIncomeLoss"],
    "LabaSebelumPajak": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                         "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
                         "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"],
    "BebanBunga": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    "Pajak": ["IncomeTaxExpenseBenefit"],
    "BungaDibayar": ["InterestPaidNet", "InterestPaid"],
    "Penyusutan": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                   "DepreciationAndAmortization", "DepreciationAmortizationAndOther"],
    "Laba": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "OCF": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "Capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements"],
    "Dividen": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "PaymentsOfOrdinaryDividends"],
    "Buyback": ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"],
    "Penerbitan": ["ProceedsFromIssuanceOfCommonStock", "ProceedsFromIssuanceOrSaleOfEquity"],
    "SahamRataDilusi": ["WeightedAverageNumberOfDilutedSharesOutstanding",
                        "WeightedAverageNumberOfSharesOutstandingBasic"],
    # Cadangan bila tidak ada tag gabungan D&A: banyak emiten besar (MSFT,
    # GOOGL, TSLA) melaporkan depresiasi dan amortisasi di baris terpisah.
    "Depresiasi": ["Depreciation"],
    "AmortisasiIntangible": ["AmortizationOfIntangibleAssets"],
    # Instan (neraca)
    "Aset": ["Assets"],
    "AsetLancar": ["AssetsCurrent"],
    "LiabLancar": ["LiabilitiesCurrent"],
    "Liabilitas": ["Liabilities"],
    "Ekuitas": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "EkuitasTotal": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"],
    "Kas": ["CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash"],
    "InvestasiJangkaPendek": ["ShortTermInvestments", "MarketableSecuritiesCurrent",
                              "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "UtangJPTotal": ["LongTermDebt"],
    "UtangJP": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "UtangJPLancar": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "UtangJPendek": ["ShortTermBorrowings", "CommercialPaper"],
    "UtangLancarTotal": ["DebtCurrent"],
    "Goodwill": ["Goodwill"],
    "Intangible": ["IntangibleAssetsNetExcludingGoodwill"],
    "LabaDitahan": ["RetainedEarningsAccumulatedDeficit"],
    "SahamBeredar": ["CommonStockSharesOutstanding"],
}
INSTAN = {"Aset", "AsetLancar", "LiabLancar", "Liabilitas", "Ekuitas", "EkuitasTotal", "Kas",
          "InvestasiJangkaPendek", "UtangJPTotal", "UtangJP", "UtangJPLancar", "UtangJPendek",
          "UtangLancarTotal", "Goodwill", "Intangible", "LabaDitahan", "SahamBeredar"}
# Pos yang memang tidak dilaporkan bila kejadiannya tidak ada: emiten yang
# tidak membeli kembali saham tidak punya tag Buyback sama sekali. Untuk pos
# ini, tag yang tidak ada berarti nol, bukan data hilang.
NOL_BILA_TIDAK_ADA = {"Dividen", "Buyback", "Penerbitan", "Goodwill", "Intangible",
                      "InvestasiJangkaPendek", "AmortisasiIntangible"}


# Emiten yang pindah CIK karena reorganisasi (mis. membentuk holding baru):
# CIK baru hanya membawa laporan sejak reorganisasi, histori ada di CIK lama.
# Tanpa digabung, TTM dan F-score tidak bisa dihitung sampai CIK baru punya
# lima kuartal laporan. Daftar ini diisi manual; perbarui_fundamental.py
# mencetak emiten yang historinya terlalu pendek sebagai kandidat.
CIK_PENDAHULU = {
    "XOM": 34088,   # Exxon Mobil: CIK baru 2115436 sejak laporan Q2 2026
}


def gabung_facts(utama: dict, pendahulu: dict) -> dict:
    """Satukan companyfacts emiten dengan companyfacts CIK lamanya. Fakta
    ganda untuk periode yang sama diselesaikan di _fakta_tag: laporan yang
    paling akhir menang, dan itu selalu laporan CIK baru."""
    hasil = {"cik": utama.get("cik"), "entityName": utama.get("entityName"), "facts": {}}
    for sumber in (pendahulu, utama):
        for taks, tags in sumber.get("facts", {}).items():
            for tag, node in tags.items():
                tujuan = hasil["facts"].setdefault(taks, {}).setdefault(tag, {"units": {}})
                for unit, daftar in node.get("units", {}).items():
                    tujuan["units"].setdefault(unit, []).extend(daftar)
    return hasil


def _tanggal(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _hari(a: date, b: date) -> int:
    return (b - a).days


class Seri:
    """Fakta satu metrik setelah digabung dari beberapa tag kandidat.

    `fakta` berisi {(start, end): nilai}; start None untuk pos neraca.
    """

    def __init__(self, fakta: dict, tag: str | None):
        self.fakta = fakta
        self.tag = tag

    # --- pos arus (laba rugi, arus kas) ---
    def kuartal(self, turunan: bool = True) -> dict[date, float]:
        """Nilai per kuartal, dikunci tanggal akhir kuartal.

        `turunan=False` untuk jumlah saham: rata-rata tertimbang tidak bisa
        dikurangkan (rata-rata 9 bulan − rata-rata 6 bulan bukan rata-rata
        kuartal ketiga), jadi hanya fakta tiga bulan yang dipakai.
        """
        q: dict[date, float] = {}
        per_awal: dict[date, list] = defaultdict(list)
        for (s, e), v in self.fakta.items():
            if s is None:
                continue
            if KUARTAL[0] <= _hari(s, e) <= KUARTAL[1]:
                q[e] = v
            per_awal[s].append((e, v))
        if not turunan:
            return q
        # Kuartal yang tidak dilaporkan sendiri = selisih dua angka YTD
        # berawal sama (9 bulan − 6 bulan, tahunan − 9 bulan, dst.).
        for s, isi in per_awal.items():
            isi.sort()
            for (e1, v1), (e2, v2) in zip(isi, isi[1:]):
                if KUARTAL[0] <= _hari(e1, e2) <= KUARTAL[1] and e2 not in q:
                    q[e2] = v2 - v1
        return q

    def tahunan(self) -> dict[date, float]:
        return {e: v for (s, e), v in self.fakta.items()
                if s is not None and TAHUN[0] <= _hari(s, e) <= TAHUN[1]}

    def ttm(self, ujung: date) -> float | None:
        """Jumlah empat kuartal berurutan yang berakhir di `ujung` (toleransi
        10 hari), atau angka tahunan yang berakhir di `ujung`."""
        q = self.kuartal()
        akhir = [e for e in sorted(q) if e <= ujung + timedelta(days=10)]
        if akhir and abs(_hari(akhir[-1], ujung)) <= 10 and len(akhir) >= 4:
            empat = akhir[-4:]
            if all(KUARTAL[0] <= _hari(a, b) <= KUARTAL[1] for a, b in zip(empat, empat[1:])):
                return float(sum(q[e] for e in empat))
        for e, v in self.tahunan().items():
            if abs(_hari(e, ujung)) <= 10:
                return float(v)
        return None

    # --- pos neraca ---
    def instan(self, pada: date, toleransi: int = 20) -> float | None:
        calon = [(abs(_hari(e, pada)), e, v) for (s, e), v in self.fakta.items()
                 if s is None and abs(_hari(e, pada)) <= toleransi]
        return float(min(calon)[2]) if calon else None


def _fakta_tag(facts: dict, tag: str, unit: str) -> dict:
    """{(start, end): nilai} satu tag, memakai laporan yang paling akhir."""
    for taks in ("us-gaap", "dei"):
        node = facts.get(taks, {}).get(tag)
        if node and unit in node.get("units", {}):
            terbaik: dict = {}
            for f in node["units"][unit]:
                if f.get("form") not in FORM_DITERIMA or f.get("val") is None:
                    continue
                kunci = (_tanggal(f.get("start")), _tanggal(f["end"]))
                lama = terbaik.get(kunci)
                if lama is None or f.get("filed", "") >= lama[1]:
                    terbaik[kunci] = (float(f["val"]), f.get("filed", ""))
            return {k: v for k, (v, _) in terbaik.items()}
    return {}


def seri(facts: dict, metrik: str) -> Seri:
    unit = "shares" if metrik in ("SahamRataDilusi", "SahamBeredar") else "USD"
    per_tag = []
    for urutan, tag in enumerate(TAG[metrik]):
        f = _fakta_tag(facts, tag, unit)
        if f:
            per_tag.append((max(e for _, e in f), -urutan, tag, f))
    if not per_tag:
        return Seri({}, None)
    # Tag utama = yang periodenya paling baru; bila sama, urutan daftar kandidat.
    per_tag.sort(reverse=True)
    gabung = dict(per_tag[0][3])
    for _, _, _, f in per_tag[1:]:
        for k, v in f.items():
            gabung.setdefault(k, v)
    return Seri(gabung, per_tag[0][2])


def _bagi(a, b):
    if a is None or b is None or b == 0 or (isinstance(b, float) and np.isnan(b)):
        return None
    return a / b


def _rata(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2


def saham_beredar(facts: dict, periode: date) -> tuple[float | None, str | None, date | None]:
    """Jumlah saham beredar terbaru: sampul laporan (dei), lalu neraca, lalu
    rata-rata tertimbang dilusi kuartal terakhir."""
    dei = facts.get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    dei = [f for f in dei if f.get("form") in FORM_DITERIMA and f.get("val")]
    if dei:
        akhir = max(f["end"] for f in dei)
        # Emiten multi-kelas bisa melaporkan beberapa angka non-dimensional
        # pada tanggal yang sama dari laporan berbeda; ambil laporan terakhir.
        terbaru = max((f for f in dei if f["end"] == akhir), key=lambda f: f.get("filed", ""))
        tgl = _tanggal(akhir)
        if _hari(periode, tgl) > -120:
            return float(terbaru["val"]), "dei:EntityCommonStockSharesOutstanding", tgl
    s = seri(facts, "SahamBeredar")
    v = s.instan(periode, 45)
    if v:
        return v, s.tag, periode
    s = seri(facts, "SahamRataDilusi")
    q = s.kuartal(turunan=False) or s.tahunan()
    # Angka yang jauh lebih tua dari periode laporan (BRK berhenti melaporkan
    # saham non-dimensional pada 2015) lebih buruk daripada kosong: kosong
    # memicu cadangan dari Yahoo di perbarui_fundamental.py.
    if q and abs(_hari(max(q), periode)) <= 120:
        e = max(q)
        return q[e], s.tag, e
    return None, None, None


UTANG_GABUNGAN = ["DebtLongtermAndShorttermCombinedAmount",
                  "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                  "DebtAndCapitalLeaseObligations"]
# Dipakai hanya bila tidak ada satu pun tag total. NotesPayable biasanya
# sudah mencakup surat utang bertanggungan dan tidak bertanggungan (MAA:
# 5.657 = 360 + 5.296), jadi bila ada, komponen di TUMPANG tidak dijumlah lagi.
KOMPONEN_UTANG = ["NotesPayable", "SeniorNotes", "ConvertibleNotesPayable", "ConvertibleDebtNoncurrent",
                  "ConvertibleDebtCurrent", "LongTermNotesPayable", "SecuredDebt", "UnsecuredDebt",
                  "LoansPayable", "OtherLoansPayable", "LongTermLineOfCredit", "LineOfCredit",
                  "OtherLongTermDebtNoncurrent", "ShortTermBankLoansAndNotesPayable",
                  "LongTermNotesAndLoans", "NotesPayableCurrent"]
TUMPANG = {"NotesPayable": {"SecuredDebt", "UnsecuredDebt", "LongTermNotesPayable", "SeniorNotes"},
           "LongTermNotesAndLoans": {"LongTermNotesPayable", "SeniorNotes"}}
# Jadwal jatuh tempo pokok utang (catatan atas laporan keuangan tahunan).
# Jumlahnya = pokok utang jangka panjang, dan tersedia non-dimensional bahkan
# untuk emiten yang saldo utangnya dipecah per segmen (CAT). Dipakai paling
# akhir karena hanya ada di 10-K dan tidak mencakup pinjaman jangka pendek.
JATUH_TEMPO = ["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
               "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
               "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
               "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
               "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
               "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive"]


def utang_total(ss: dict[str, Seri], pada: date, cadangan: dict[str, Seri] | None = None,
                bunga: float | None = None, aset: float | None = None) -> tuple[float | None, str]:
    """Utang berbunga (tanpa sewa operasi). Kombinasi tag yang dipakai dicatat
    karena emiten memecah utangnya dengan cara berbeda-beda.

    Bila tidak ada tag utang sama sekali, nol hanya dipercaya kalau beban
    bunganya juga kecil. Emiten seperti CAT melaporkan utang per segmen
    (fakta dimensional) yang tidak ikut di companyfacts; menganggapnya nol
    akan membuat emiten berutang puluhan miliar tampak bebas utang.
    """
    jp_total = ss["UtangJPTotal"].instan(pada)
    jpendek = ss["UtangJPendek"].instan(pada) or 0.0
    if jp_total is not None:
        return jp_total + jpendek, "LongTermDebt+ShortTermBorrowings"
    jp = ss["UtangJP"].instan(pada)
    lancar_total = ss["UtangLancarTotal"].instan(pada)
    if lancar_total is not None:
        lancar, sumber_lancar = lancar_total, "DebtCurrent"
    else:
        lancar = (ss["UtangJPLancar"].instan(pada) or 0.0) + jpendek
        sumber_lancar = "LongTermDebtCurrent+ShortTermBorrowings"
    if jp is not None or lancar_total is not None or lancar:
        return (jp or 0.0) + lancar, f"{ss['UtangJP'].tag or '-'}+{sumber_lancar}"

    cadangan = cadangan or {}
    for tag in UTANG_GABUNGAN:
        s = cadangan.get(tag)
        v = s.instan(pada) if s else None
        if v is not None:
            return v + jpendek, tag
    ada = {t: cadangan[t].instan(pada) for t in KOMPONEN_UTANG if t in cadangan}
    ada = {t: v for t, v in ada.items() if v is not None}
    for induk, anak in TUMPANG.items():
        if induk in ada:
            ada = {t: v for t, v in ada.items() if t not in anak}
    if ada:
        return sum(ada.values()) + jpendek, "komponen:" + "+".join(ada)

    jadwal = [cadangan[t] for t in JATUH_TEMPO if t in cadangan]
    if jadwal:
        akhir = max(e for s in jadwal for (_, e) in s.fakta)
        if abs(_hari(akhir, pada)) <= 400:
            total = sum(s.instan(akhir, 5) or 0.0 for s in jadwal)
            if total > 0:
                return total + jpendek, f"komponen:jadwal jatuh tempo {akhir.isoformat()}"

    if bunga and bunga > 10e6 and aset and bunga / aset > 0.002:
        return None, "utang tidak terbaca (bunga material)"
    return 0.0, "tidak ada tag utang"


def _fscore(k: dict) -> tuple[int | None, str]:
    """Piotroski F-score dari komponen yang sudah dihitung. Butuh minimal
    8 dari 9 komponen; di bawah itu skornya tidak berarti."""
    label = ["ROA", "OCF", "dROA", "AKRUAL", "LEVERAGE", "CR", "SAHAM", "MARGIN", "ATO"]
    nilai = [k.get(x) for x in label]
    ada = [v for v in nilai if v is not None]
    rincian = " ".join(f"{x}{'+' if v else '-' if v is not None else '?'}" for x, v in zip(label, nilai))
    if len(ada) < 8:
        return None, rincian
    return int(sum(ada)), rincian


def _std_tahunan(pembilang: Seri, penyebut: Seri | None, instan: Seri | None = None,
                 tahun: int = 5) -> float | None:
    """Simpangan baku rasio tahunan (poin persen) selama `tahun` fiskal
    terakhir. Penyebut arus (pendapatan) atau neraca rata-rata (aset)."""
    atas = pembilang.tahunan()
    rasio = []
    for e in sorted(atas)[-tahun:]:
        if penyebut is not None:
            b = penyebut.tahunan().get(e)
        else:
            b = _rata(instan.instan(e, 20), instan.instan(e - timedelta(days=365), 45))
        if b:
            rasio.append(atas[e] / b * 100)
    return pstdev(rasio) if len(rasio) >= 3 else None


def ekstrak(facts: dict, keuangan: bool = False, hari_ini: date | None = None) -> dict:
    """Satu baris fundamental dari JSON companyfacts.

    `keuangan` = emiten sektor Financials (bank, asuransi, pialang): pos
    lancar, laba kotor, EBITDA, Altman Z, dan F-score tidak berlaku.
    """
    hari_ini = hari_ini or date.today()
    fk = facts.get("facts", {})
    if "us-gaap" not in fk:
        tax = ",".join(sorted(fk)) or "kosong"
        return {"Catatan": f"tanpa us-gaap ({tax})"}

    ss = {m: seri(fk, m) for m in TAG}
    laba_q = ss["Laba"].kuartal()
    laba_fy = ss["Laba"].tahunan()

    # Periode acuan = akhir periode terbaru yang punya laba bersih.
    kandidat = sorted(set(laba_q) | set(laba_fy))
    if not kandidat:
        return {"Catatan": "tanpa laba bersih dalam USD (filer asing: IFRS atau mata uang lain)"}
    periode = kandidat[-1]
    if periode in laba_q and ss["Laba"].ttm(periode) is not None:
        basis = "TTM-4Q"
    elif laba_fy:
        # Empat kuartal terakhir tidak bisa disusun berurutan (mis. emiten
        # baru IPO, atau ganti tahun fiskal): mundur ke tahun fiskal terakhir.
        basis, periode = "FY", max(laba_fy)
    else:
        return {"Catatan": f"laba {periode} tidak bisa disetahunkan"}
    lalu = periode - timedelta(days=364)
    dua_lalu = periode - timedelta(days=728)

    def alur(m, pada=periode):
        v = ss[m].ttm(pada)
        if v is None and m in NOL_BILA_TIDAK_ADA:
            return 0.0
        return v

    def inst(m, pada=periode, tol=20):
        v = ss[m].instan(pada, tol)
        if v is None and m in NOL_BILA_TIDAK_ADA:
            return 0.0
        return v

    r: dict = {"Basis": basis, "Periode_Lapkeu": periode.isoformat()}

    # Laporan terakhir yang memuat periode itu, untuk jejak audit.
    for f in fk["us-gaap"].get(ss["Laba"].tag, {}).get("units", {}).get("USD", []):
        if f.get("end") == periode.isoformat() and f.get("form") in FORM_DITERIMA:
            if f.get("filed", "") >= r.get("Tanggal_Lapor", ""):
                r["Tanggal_Lapor"], r["Form"] = f.get("filed", ""), f.get("form")

    # --- angka mentah ---
    pendapatan = alur("Pendapatan")
    laba_kotor = alur("LabaKotor")
    hpp = alur("HPP")
    if laba_kotor is None and pendapatan is not None and hpp is not None:
        laba_kotor = pendapatan - hpp
    ebit = alur("EBIT")
    tag_ebit = ss["EBIT"].tag
    if ebit is None:
        lsp, bunga = alur("LabaSebelumPajak"), alur("BebanBunga")
        if lsp is not None:
            ebit = lsp + (bunga or 0.0)
            tag_ebit = "LabaSebelumPajak+BebanBunga"
    penyusutan = alur("Penyusutan")
    tag_penyusutan = ss["Penyusutan"].tag
    if penyusutan is None and ss["Depresiasi"].tag:
        dep = alur("Depresiasi")
        if dep is not None:
            penyusutan = dep + (alur("AmortisasiIntangible") or 0.0)
            tag_penyusutan = "Depreciation+AmortizationOfIntangibleAssets"
    ebitda = ebit + penyusutan if ebit is not None and penyusutan is not None else None

    r.update({
        "Pendapatan": pendapatan, "Pendapatan_Lalu": alur("Pendapatan", lalu),
        "LabaKotor": laba_kotor, "EBIT": ebit, "EBITDA": ebitda,
        "Laba": alur("Laba"), "Laba_Lalu": alur("Laba", lalu), "BebanBunga": alur("BebanBunga"),
        "OCF": alur("OCF"), "OCF_Lalu": alur("OCF", lalu),
        "Capex": alur("Capex"), "Dividen": alur("Dividen"), "Buyback": alur("Buyback"),
        "Penerbitan": alur("Penerbitan"),
        "Aset": inst("Aset"), "Aset_Awal": inst("Aset", lalu, 45),
        "AsetLancar": inst("AsetLancar"), "LiabLancar": inst("LiabLancar"),
        "Ekuitas": inst("Ekuitas"), "Ekuitas_Awal": inst("Ekuitas", lalu, 45),
        "Kas": inst("Kas"), "Goodwill": inst("Goodwill"), "Intangible": inst("Intangible"),
        "LabaDitahan": inst("LabaDitahan"),
    })
    liab = inst("Liabilitas")
    if liab is None and r["Aset"] is not None:
        ekuitas_total = inst("EkuitasTotal")
        if ekuitas_total is not None:
            liab = r["Aset"] - ekuitas_total
    r["Liabilitas"] = liab
    r["KasPlus"] = (r["Kas"] or 0.0) + (inst("InvestasiJangkaPendek") or 0.0) if r["Kas"] is not None else None
    cadangan_utang = {t: Seri(f, t) for t in UTANG_GABUNGAN + KOMPONEN_UTANG + JATUH_TEMPO
                      if (f := _fakta_tag(fk, t, "USD"))}
    # Bukti adanya utang: beban bunga, atau bunga yang dibayar (arus kas).
    bunga = max(alur("BebanBunga") or 0.0, alur("BungaDibayar") or 0.0)
    r["Utang"], r["Tag_Utang"] = utang_total(ss, periode, cadangan_utang, bunga, r["Aset"])
    utang_lalu, _ = utang_total(ss, lalu, cadangan_utang,
                                max(alur("BebanBunga", lalu) or 0.0, alur("BungaDibayar", lalu) or 0.0), r["Aset_Awal"])

    saham, tag_saham, tgl_saham = saham_beredar(fk, periode)
    r["Saham"], r["Tag_Saham"] = saham, tag_saham
    r["Tanggal_Saham"] = tgl_saham.isoformat() if tgl_saham else None
    dil = ss["SahamRataDilusi"]
    # Kuartal langsung + angka tahunan sebagai pengganti Q4 (rata-rata setahun,
    # cukup dekat untuk mengukur dilusi ±5%).
    saham_q = {**dil.tahunan(), **dil.kuartal(turunan=False)}
    s_kini = saham_q.get(periode) if saham_q else None
    s_lalu = None
    if saham_q:
        dekat = [e for e in saham_q if abs(_hari(e, lalu)) <= 20]
        s_lalu = saham_q[dekat[0]] if dekat else None
    r["Dilusi_YoY"] = (_bagi(s_kini, s_lalu) - 1) * 100 if s_kini and s_lalu else None

    for m in ("Pendapatan", "Laba", "OCF", "Utang"):
        r[f"Tag_{m}"] = r.get(f"Tag_{m}") or ss.get(m, Seri({}, None)).tag

    # --- rasio tanpa harga ---
    aset_rata = _rata(r["Aset"], r["Aset_Awal"])
    ekuitas_rata = _rata(r["Ekuitas"], r["Ekuitas_Awal"])
    r["ROA"] = _bagi(r["Laba"], aset_rata)
    r["ROE"] = _bagi(r["Laba"], ekuitas_rata) if ekuitas_rata and ekuitas_rata > 0 else None
    r["Rev_YoY"] = (_bagi(pendapatan, r["Pendapatan_Lalu"]) - 1) if pendapatan and r["Pendapatan_Lalu"] and r["Pendapatan_Lalu"] > 0 else None
    r["Laba_YoY"] = (_bagi(r["Laba"], r["Laba_Lalu"]) - 1) if r["Laba"] is not None and r["Laba_Lalu"] and r["Laba_Lalu"] > 0 else None
    r["Tag_Penyusutan"], r["Tag_EBIT"] = tag_penyusutan, tag_ebit
    r["OCF_Laba"] = _bagi(r["OCF"], r["Laba"]) if r["Laba"] and r["Laba"] > 0 else None
    r["OCF_Laba_Lalu"] = _bagi(r["OCF_Lalu"], r["Laba_Lalu"]) if r["Laba_Lalu"] and r["Laba_Lalu"] > 0 else None
    r["Akrual"] = _bagi(r["Laba"] - r["OCF"], aset_rata) if r["Laba"] is not None and r["OCF"] is not None else None
    r["ROA_Variabilitas5T"] = _std_tahunan(ss["Laba"], None, ss["Aset"])
    r["Goodwill_Ekuitas"] = _bagi(r["Goodwill"], r["Ekuitas"]) if r["Ekuitas"] and r["Ekuitas"] > 0 else None

    if keuangan:
        # Arus kas operasi bank dan pialang didominasi pergerakan aset
        # perdagangan dan pinjaman (OCF JPM TTM Jun 2026: −$162 miliar), jadi
        # rasio yang memakai OCF tidak berarti apa pun untuk mereka.
        r["OCF_Laba"] = r["OCF_Laba_Lalu"] = r["Akrual"] = None
    else:
        r["GrossMargin"] = _bagi(laba_kotor, pendapatan) if pendapatan and pendapatan > 0 else None
        if ss["LabaKotor"].tag:
            laba_kotor_s = ss["LabaKotor"]
        elif ss["HPP"].tag:
            # Tanpa tag laba kotor: bangun seri tahunan pendapatan − HPP.
            pdp, hpp_t = ss["Pendapatan"].tahunan(), ss["HPP"].tahunan()
            laba_kotor_s = Seri({(e - timedelta(days=364), e): pdp[e] - hpp_t[e]
                                 for e in pdp if e in hpp_t}, "Pendapatan−HPP")
        else:
            laba_kotor_s = None
        r["GM_Stabilitas5T"] = _std_tahunan(laba_kotor_s, ss["Pendapatan"]) if laba_kotor_s else None
        r["NetDebt_EBITDA"] = _bagi(r["Utang"] - (r["KasPlus"] or 0.0), ebitda) if ebitda and ebitda > 0 and r["Utang"] is not None else None

        lsp, pajak = alur("LabaSebelumPajak"), alur("Pajak")
        tarif = _bagi(pajak, lsp) if lsp and lsp > 0 and pajak is not None else None
        tarif = min(max(tarif, 0.0), 0.35) if tarif is not None else 0.21
        ekuitas_total = inst("EkuitasTotal") or r["Ekuitas"]
        # Modal investasi = utang berbunga + ekuitas, TANPA dikurangi kas.
        # Versi dikurangi kas diuji dan ditolak: untuk emiten yang kasnya
        # hampir menyamai modalnya, penyebutnya mendekati nol dan ROIC meledak
        # (data 14 Sep 2026: CVLT 3.475%, RSI 1.524%, PLTR 1.038%).
        ic = r["Utang"] + ekuitas_total if ekuitas_total is not None and r["Utang"] is not None else None
        ekuitas_total_lalu = inst("EkuitasTotal", lalu, 45)
        ic_lalu = utang_lalu + ekuitas_total_lalu if ekuitas_total_lalu is not None and utang_lalu is not None else None
        ic_rata = _rata(ic if ic and ic > 0 else None, ic_lalu if ic_lalu and ic_lalu > 0 else None)
        r["ROIC"] = _bagi(ebit * (1 - tarif), ic_rata) if ebit is not None and ic_rata else None

        # Piotroski: periode ini vs setahun sebelumnya.
        aset_awal_lalu = inst("Aset", dua_lalu, 45)
        roa_k = _bagi(r["Laba"], r["Aset_Awal"])
        roa_l = _bagi(r["Laba_Lalu"], aset_awal_lalu)
        ocf_k = r["OCF"]
        # Leverage memakai seluruh utang berbunga, bukan hanya utang jangka
        # panjang seperti di makalah aslinya: pemecahan jangka panjang/lancar
        # di XBRL terlalu tidak seragam untuk dibandingkan antarperiode.
        lev_k = _bagi(r["Utang"], r["Aset"])
        lev_l = _bagi(utang_lalu, r["Aset_Awal"])
        cr_k = _bagi(r["AsetLancar"], r["LiabLancar"])
        cr_l = _bagi(inst("AsetLancar", lalu, 45), inst("LiabLancar", lalu, 45))
        # Margin: laba kotor bila ada; emiten jasa tanpa HPP memakai margin EBIT.
        lk_lalu = alur("LabaKotor", lalu)
        if lk_lalu is None and r["Pendapatan_Lalu"] is not None and alur("HPP", lalu) is not None:
            lk_lalu = r["Pendapatan_Lalu"] - alur("HPP", lalu)
        if laba_kotor is not None and lk_lalu is not None:
            m_k, m_l = _bagi(laba_kotor, pendapatan), _bagi(lk_lalu, r["Pendapatan_Lalu"])
        else:
            m_k, m_l = _bagi(ebit, pendapatan), _bagi(alur("EBIT", lalu), r["Pendapatan_Lalu"])
        ato_k = _bagi(pendapatan, r["Aset_Awal"])
        ato_l = _bagi(r["Pendapatan_Lalu"], aset_awal_lalu)

        def beda(a, b, lebih_besar=True):
            if a is None or b is None:
                return None
            return a > b if lebih_besar else a < b

        k = {
            "ROA": roa_k > 0 if roa_k is not None else None,
            "OCF": ocf_k > 0 if ocf_k is not None else None,
            "dROA": beda(roa_k, roa_l),
            "AKRUAL": (ocf_k > r["Laba"]) if ocf_k is not None and r["Laba"] is not None else None,
            # Emiten tanpa utang jangka panjang di kedua periode dianggap lolos:
            # "<" murni akan menghukum neraca yang paling bersih.
            "LEVERAGE": (lev_k < lev_l or lev_k == 0) if lev_k is not None and lev_l is not None else None,
            "CR": beda(cr_k, cr_l),
            "SAHAM": (s_kini <= s_lalu) if s_kini and s_lalu else None,
            "MARGIN": beda(m_k, m_l),
            "ATO": beda(ato_k, ato_l),
        }
        r["F_Score"], r["F_Rincian"] = _fscore(k)

    umur = _hari(periode, hari_ini)
    if umur > MAKS_UMUR_HARI:
        r["Catatan"] = f"laporan terakhir {umur} hari lalu"
    return r
