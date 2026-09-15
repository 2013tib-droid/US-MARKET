"""Uji pembangkitan halaman dokumen untuk GitHub Pages.

Yang dijaga terutama tautan silang: dokumen ditulis untuk dibaca di GitHub,
jadi tautannya menyebut .md dan jangkar bergaya GitHub. Kalau penulisan ulang
atau slug judulnya meleset, halamannya tetap terbit dan tetap terlihat benar —
hanya tautannya yang mati. Karena itu docs/ yang sungguhan ikut diuji, bukan
hanya contoh buatan.
"""

from html.parser import HTMLParser
from pathlib import Path

import pytest

from usmarket import situs

DOCS = Path(__file__).resolve().parent.parent / "docs"


class _Halaman(HTMLParser):
    """Kumpulkan id dan href — cukup untuk memeriksa keutuhan tautan."""

    def __init__(self, html: str):
        super().__init__()
        self.id: set[str] = set()
        self.href: list[str] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        atribut = dict(attrs)
        if atribut.get("id"):
            self.id.add(atribut["id"])
        if tag == "a" and atribut.get("href"):
            self.href.append(atribut["href"])


@pytest.fixture(scope="module")
def situs_jadi(tmp_path_factory) -> dict[str, str]:
    tujuan = tmp_path_factory.mktemp("situs")
    situs.susun(DOCS, tujuan)
    return {b.name: b.read_text(encoding="utf-8") for b in tujuan.glob("*.html")}


def test_satu_halaman_per_dokumen_plus_indeks(situs_jadi):
    assert set(situs_jadi) == {f"{s}.html" for s in situs.URUTAN} | {"index.html"}


def test_tautan_internal_dan_jangkarnya_tembus(situs_jadi):
    """Setiap tautan relatif harus menunjuk halaman yang ada, dan setiap
    jangkar harus cocok dengan id judul di halaman tujuan."""
    halaman = {nama: _Halaman(html) for nama, html in situs_jadi.items()}
    rusak = []
    diperiksa = 0

    for nama, isi in halaman.items():
        for tujuan in isi.href:
            if tujuan.startswith(("http://", "https://", "../")):
                continue  # keluar situs, atau dashboard yang disalin terpisah
            berkas, _, jangkar = tujuan.partition("#")
            sasaran = berkas or nama
            diperiksa += 1
            if sasaran not in halaman:
                rusak.append(f"{nama} → {tujuan} (halaman tidak ada)")
            elif jangkar and jangkar not in halaman[sasaran].id:
                rusak.append(f"{nama} → {tujuan} (jangkar tidak ada)")

    assert not rusak, "tautan mati: " + "; ".join(rusak)
    assert diperiksa >= len(situs.URUTAN), "tautan internal tidak terbaca sama sekali"


def test_tautan_md_ditulis_ulang_jangkar_dipertahankan():
    html = situs.baca_teks("[lihat](03-rancang-bangun.md#4-kolom-hasilsemuacsv)")
    assert 'href="03-rancang-bangun.html#4-kolom-hasilsemuacsv"' in html


@pytest.mark.parametrize("sumber, utuh", [
    ("[luar](https://example.com/a.md)", "https://example.com/a.md"),
    ("[mutlak](/docs/a.md)", "/docs/a.md"),
    ("[surel](mailto:a@b.md)", "mailto:a@b.md"),
])
def test_tautan_bukan_dokumen_tetangga_tidak_disentuh(sumber, utuh):
    assert utuh in situs.baca_teks(sumber)


def test_nama_berkas_md_di_dalam_backtick_tetap_md():
    """Yang ditulis ulang elemen <a>, bukan teks — `docs/04-roadmap.md` di
    prosa menyebut berkas sumber, bukan halaman situs."""
    html = situs.baca_teks("Statusnya dicatat di `docs/04-roadmap.md`.")
    assert "<code>docs/04-roadmap.md</code>" in html


def test_tabel_dibungkus_agar_bisa_digeser():
    html = situs.baca_teks("| a | b |\n|---|---|\n| 1 | 2 |")
    assert '<div class="geser"><table>' in html.replace("\n", "")


def test_judul_dan_ringkasan_diambil_untuk_indeks(tmp_path):
    berkas = tmp_path / "09-contoh.md"
    berkas.write_text("# 09 — Judul `berkode`\n\nParagraf **pertama** jadi\n"
                      "ringkasan.\n\n## Bagian\n\nBukan ini.\n", encoding="utf-8")
    d = situs.baca(berkas)
    assert d.slug == "09-contoh"
    assert d.judul == "09 — Judul berkode"
    assert d.ringkas == "Paragraf pertama jadi ringkasan."


def test_dokumen_hilang_menghentikan_pembangunan(tmp_path):
    """Lebih baik build gagal daripada situs terbit diam-diam tanpa satu
    dokumen karena berkasnya diganti nama."""
    (tmp_path / f"{situs.URUTAN[0]}.md").write_text("# a\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match=situs.URUTAN[1]):
        situs.susun(tmp_path, tmp_path / "keluar")


def test_bersihkan_membuang_halaman_dokumen_yang_sudah_dihapus(tmp_path):
    tujuan = tmp_path / "docs"
    tujuan.mkdir()
    (tujuan / "99-lama.html").write_text("basi", encoding="utf-8")
    situs.bersihkan(tujuan)
    situs.susun(DOCS, tujuan)
    assert not (tujuan / "99-lama.html").exists()


def test_teks_dokumen_dilewatkan_apa_adanya(situs_jadi):
    """Penanda halaman utuh: judul H1 tiap dokumen muncul di halamannya."""
    for slug in situs.URUTAN:
        d = situs.baca(DOCS / f"{slug}.md")
        assert d.judul.split("—")[-1].strip()[:12] in situs_jadi[f"{slug}.html"]


def test_daftar_menempel_paragraf_tetap_jadi_daftar():
    """Dokumen ditulis untuk GitHub, yang membolehkan daftar menyela paragraf.
    Tanpa penyesuaian, Python-Markdown menelannya jadi satu paragraf."""
    html = situs.baca_teks("**Selesai bila**:\n- syarat pertama\n- syarat kedua\n")
    assert html.count("<li>") == 2
    assert "<ul>" in html


def test_daftar_di_dalam_pagar_kode_tidak_disentuh():
    html = situs.baca_teks("```\npohon/\n- bukan daftar\n```")
    assert "<li>" not in html
    assert "- bukan daftar" in html


def test_baris_berawalan_tahun_tidak_berubah_jadi_daftar():
    """Aturan GFM: hanya daftar bernomor yang mulai dari 1 boleh menyela
    paragraf. Tanpa batas itu, "2026. ..." di tengah prosa jadi daftar."""
    html = situs.baca_teks("Angka di sini benar saat ditulis.\n2026. Aturan bisa berubah.")
    assert "<li>" not in html


def test_daftar_di_dokumen_sungguhan_terbit_sebagai_daftar(situs_jadi):
    """Penjaga angka: docs/ punya puluhan daftar menempel. Kalau perilakunya
    hilang, jumlah <li> anjlok tapi halamannya tetap terbit."""
    for slug in ("01-metodologi", "04-roadmap"):
        assert situs_jadi[f"{slug}.html"].count("<li>") >= 10
