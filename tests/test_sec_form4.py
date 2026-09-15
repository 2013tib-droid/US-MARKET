"""Uji jalur pengunduhan Form 4 tanpa menyentuh jaringan: klien EDGAR diberi
jawaban tiruan, dan skrip pembaru dijalankan terhadap klien itu."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from usmarket import sec

AKAR = Path(__file__).resolve().parent.parent


def modul_skrip(nama: str):
    spec = importlib.util.spec_from_file_location(nama, AKAR / "scripts" / f"{nama}.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules[nama] = modul
    spec.loader.exec_module(modul)
    return modul


perbarui = modul_skrip("perbarui_smartmoney")


class Jawaban:
    def __init__(self, isi=b"", status=200, json_=None):
        self.content, self.status_code, self._json = isi, status, json_

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def klien_tiruan(jawab) -> sec.KlienSEC:
    klien = sec.KlienSEC(user_agent="uji nama@contoh.com")
    klien.get = jawab
    return klien


SUBMISSIONS = {"filings": {"recent": {
    "accessionNumber": ["0001-24-000001", "0001-24-000002", "0001-24-000003"],
    "filingDate": ["2026-09-10", "2026-05-01", "2026-09-12"],
    "reportDate": ["2026-09-08", "2026-04-29", "2026-09-10"],
    "form": ["4", "4", "10-Q"],
    "primaryDocument": ["xslF345X05/wk-form4_1.xml", "xslF345X05/wk-form4_2.xml", "aapl-20260910.htm"],
}}}


def test_filing_terbaru_menyaring_form_dan_tanggal():
    klien = klien_tiruan(lambda url, **k: Jawaban(json_=SUBMISSIONS))
    hasil = klien.filing_terbaru(320193, {"4", "4/A"}, date(2026, 8, 1))
    assert [f["akses"] for f in hasil] == ["0001-24-000001"]
    assert hasil[0]["tanggal_periode"] == "2026-09-08"


def test_submissions_tanpa_blok_recent_tidak_melempar():
    klien = klien_tiruan(lambda url, **k: Jawaban(json_={"filings": {}}))
    assert klien.filing_terbaru(1, {"4"}, date(2026, 1, 1)) == []


def test_dokumen_mengambil_xml_asli_bukan_versi_terjemahan():
    dipanggil = []

    def jawab(url, **k):
        dipanggil.append(url)
        return Jawaban(isi=b"<ownershipDocument/>")

    klien = klien_tiruan(jawab)
    klien.dokumen(320193, "0001-24-000001", "xslF345X05/wk-form4_1.xml")
    assert dipanggil == ["https://www.sec.gov/Archives/edgar/data/320193/000124000001/wk-form4_1.xml"]


FORM4_XML = b"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerCik>0000320193</issuerCik><issuerTradingSymbol>AAPL</issuerTradingSymbol></issuer>
  <reportingOwner><reportingOwnerId><rptOwnerCik>0001214156</rptOwnerCik>
    <rptOwnerName>COOK TIMOTHY D</rptOwnerName></reportingOwnerId></reportingOwner>
  <nonDerivativeTable><nonDerivativeTransaction>
    <transactionDate><value>2026-09-08</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>500</value></transactionShares>
      <transactionPricePerShare><value>200</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>"""


class KlienPalsu:
    """Klien EDGAR tiruan yang mencatat dokumen apa saja yang diminta."""

    def __init__(self):
        self.diminta = []

    def filing_terbaru(self, cik, form, sejak):
        return [{"akses": "0001-24-000001", "tanggal_lapor": "2026-09-10",
                 "tanggal_periode": "2026-09-08", "form": "4", "dokumen": "wk-form4_1.xml"},
                {"akses": "0001-24-000009", "tanggal_lapor": "2026-09-11",
                 "tanggal_periode": "2026-09-09", "form": "4", "dokumen": "wk-form4_9.xml"}]

    def dokumen(self, cik, akses, berkas):
        self.diminta.append(akses)
        return FORM4_XML


def test_unduh_form4_melewati_nomor_akses_yang_sudah_tersimpan():
    klien = KlienPalsu()
    baris, meta = perbarui.unduh_form4(klien, {320193: ["AAPL"]}, {"0001-24-000001"},
                                       date(2026, 6, 17), pekerja=2, maks_per_emiten=400)
    assert klien.diminta == ["0001-24-000009"]
    assert meta["filing_baru"] == 1 and meta["transaksi_baru"] == 1
    (t,) = baris
    assert t["Ticker"] == "AAPL" and t["Kode"] == "P" and t["Nilai"] == 100_000
    assert t["Akses"] == "0001-24-000009" and t["Tanggal_Lapor"] == "2026-09-11"


def test_jadwal_earnings_surprise_dan_tanggal_berikutnya():
    jadwal = pd.DataFrame(
        {"EPS Estimate": [1.0, 1.2, 1.5], "Reported EPS": [1.1, 1.1, None],
         "Surprise(%)": [10.0, -8.33, None]},
        index=pd.to_datetime(["2026-03-01", "2026-06-01", "2026-11-01"], utc=True))
    r = perbarui.dari_jadwal_earnings(jadwal, pd.Timestamp("2026-09-15", tz="UTC"))
    assert r["Surprise_Terakhir"] == -8.33
    assert r["Surprise_Rata4Q"] == pytest.approx(0.835)
    assert r["Surprise_Tanggal"] == "2026-06-01"
    assert r["Earnings_Berikut"] == "2026-11-01"
