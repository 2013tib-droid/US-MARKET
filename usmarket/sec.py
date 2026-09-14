"""Klien SEC EDGAR: peta ticker → CIK, companyfacts (XBRL), dan pencarian
teks penuh untuk going concern dan restatement.

Aturan SEC yang wajib dipatuhi (https://www.sec.gov/os/accessing-edgar-data):
- Header User-Agent berisi nama dan email. Tanpa itu SEC membalas 403.
  Nilainya dibaca dari variabel lingkungan SEC_USER_AGENT (secret di GitHub),
  tidak pernah ditulis di kode karena repo ini publik.
- Maksimal 10 permintaan per detik dari satu mesin. Klien ini membatasi
  dirinya di 8 supaya ada ruang untuk coba ulang.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import date, timedelta

import requests

BATAS_PER_DETIK = 8
URL_TICKER = "https://www.sec.gov/files/company_tickers.json"
URL_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
URL_CARI = "https://efts.sec.gov/LATEST/search-index"


class TanpaUserAgent(RuntimeError):
    pass


class KlienSEC:
    def __init__(self, user_agent: str | None = None, batas_per_detik: float = BATAS_PER_DETIK):
        ua = user_agent or os.environ.get("SEC_USER_AGENT", "").strip()
        if "@" not in ua:
            raise TanpaUserAgent(
                "SEC mewajibkan User-Agent berisi nama dan email. Setel variabel lingkungan "
                "SEC_USER_AGENT, mis. 'US-MARKET screener nama@email.com'. Di GitHub Actions "
                "nilainya diambil dari secret dengan nama yang sama.")
        self.sesi = requests.Session()
        self.sesi.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
        self._jeda = 1.0 / batas_per_detik
        self._kunci = threading.Lock()
        self._berikut = 0.0

    def _tunggu_giliran(self):
        # Satu kunci untuk semua thread: jaminan batas laju berlaku untuk
        # seluruh proses, bukan per thread.
        with self._kunci:
            sekarang = time.monotonic()
            mulai = max(sekarang, self._berikut)
            self._berikut = mulai + self._jeda
        if mulai > sekarang:
            time.sleep(mulai - sekarang)

    def get(self, url: str, params: dict | None = None, percobaan: int = 4) -> requests.Response:
        for ke in range(percobaan):
            self._tunggu_giliran()
            try:
                r = self.sesi.get(url, params=params, timeout=60)
            except requests.RequestException:
                if ke == percobaan - 1:
                    raise
                time.sleep(2 ** ke)
                continue
            # 404 berarti emiten tidak punya data XBRL; tidak perlu diulang.
            if r.status_code in (429, 500, 502, 503, 504) and ke < percobaan - 1:
                time.sleep(2 ** (ke + 1))
                continue
            return r
        return r

    def peta_cik(self) -> dict[str, int]:
        """Ticker (format Yahoo, mis. BRK-B) → CIK."""
        r = self.get(URL_TICKER)
        r.raise_for_status()
        return {v["ticker"].upper(): int(v["cik_str"]) for v in r.json().values()}

    def companyfacts(self, cik: int) -> dict | None:
        r = self.get(URL_FACTS.format(cik=cik))
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def cari_cik(self, frasa: str, forms: str, sejak: date, item: str | None = None) -> dict[int, str]:
        """CIK yang punya dokumen `forms` berisi `frasa` sejak tanggal itu.
        Mengembalikan {cik: tanggal lapor terbaru}. Bila `item` diisi (mis.
        "4.02"), hanya 8-K yang mencantumkan item itu yang dihitung.

        `forms` boleh berisi beberapa form dipisah koma, tapi setiap form
        dicari sendiri-sendiri: API EDGAR tidak menggabungkannya. Diuji 15 Sep
        2026: "8-K" memberi 106 emiten dengan item 4.02, "8-K,8-K/A" hanya 5.
        """
        hasil: dict[int, str] = {}
        for form in [f.strip() for f in forms.split(",") if f.strip()]:
            for cik, tgl in self._cari_satu_form(frasa, form, sejak, item).items():
                if tgl > hasil.get(cik, ""):
                    hasil[cik] = tgl
        return hasil

    def _cari_satu_form(self, frasa: str, forms: str, sejak: date, item: str | None) -> dict[int, str]:
        hasil: dict[int, str] = {}
        dari = 0
        while True:
            params = {"q": frasa, "forms": forms, "dateRange": "custom",
                      "startdt": sejak.isoformat(), "enddt": (date.today() + timedelta(days=1)).isoformat(),
                      "from": dari}
            r = self.get(URL_CARI, params=params)
            r.raise_for_status()
            hits = r.json()["hits"]
            for h in hits["hits"]:
                src = h["_source"]
                if item and item not in (src.get("items") or []):
                    continue
                for c in src.get("ciks") or []:
                    cik = int(c)
                    tgl = src.get("file_date", "")
                    if tgl > hasil.get(cik, ""):
                        hasil[cik] = tgl
            dari += len(hits["hits"])
            if not hits["hits"] or dari >= min(hits["total"]["value"], 10_000):
                return hasil
