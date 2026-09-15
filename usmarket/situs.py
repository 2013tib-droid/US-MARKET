"""Ubah docs/*.md menjadi halaman HTML untuk GitHub Pages.

Dokumen rancangan hanya bisa dibaca di GitHub sampai sekarang: situs Pages
isinya dashboard dan hasil/ saja. Menyalin berkas .md apa adanya tidak
menolong — Pages menyajikannya sebagai text/markdown, yang oleh peramban
diunduh atau ditampilkan mentah lengkap dengan pipa tabelnya.

Tiga hal yang membuat modul ini tidak sekadar "markdown.markdown()":

1.  Tautan silang antar dokumen ditulis sebagai `[03 §4](03-rancang-bangun.md
    #4-kolom-hasilsemuacsv)` supaya hidup di GitHub. Di situs, sasarannya
    bernama .html, jadi setiap tautan relatif ke .md ditulis ulang. Hanya
    atribut href yang disentuh; `docs/04-roadmap.md` di dalam backtick tetap
    apa adanya karena yang diubah elemen <a>, bukan teksnya.

2.  Dokumen ditulis untuk GitHub, yang membolehkan daftar menempel langsung
    di bawah paragraf. Python-Markdown menuntut baris kosong dan tanpa itu
    menelan daftarnya jadi satu paragraf berisi tanda hubung — lihat
    _DaftarMenempel.

3.  Tabel di dokumen ini lebar (kontrak kolom, tag XBRL). Tiap <table>
    dibungkus div yang bisa digeser mendatar, supaya di ponsel tabelnya yang
    bergeser, bukan seluruh halaman.

Slug judul dari ekstensi toc kebetulan sama persis dengan slug GitHub
(huruf kecil, tanda baca dibuang, spasi jadi tanda hubung), jadi anchor yang
sudah ditulis di dokumen tetap sampai. tests/test_situs.py menjaganya.
"""

from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import markdown
from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor

# Dokumen di luar daftar ini tidak ikut terbit. Urutannya urutan baca, bukan
# abjad — kebetulan sama karena namanya berawalan nomor.
URUTAN = ["01-metodologi", "02-infrastruktur", "03-rancang-bangun",
          "04-roadmap", "05-praktik-us-vs-idx"]


# Token warna disalin dari dashboard/index.html supaya dokumen dan dashboard
# terasa satu situs, termasuk mode gelapnya.
GAYA = """
  :root {
    color-scheme: light;
    --surface: #f6f6f4; --surface-raised: #ffffff; --surface-sunken: #efeeeb;
    --head-bg: #f8f8f6; --zebra: #fafaf9;
    --border: #e4e3df; --border-soft: #eceae6;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #8a8984;
    --accent: #2a78d6; --accent-strong: #1c5fae; --accent-soft: #e8f0fb;
    --chip-bg: #efeeea;
    --shadow-sm: 0 1px 2px rgba(16,15,14,.05);
    --shadow-md: 0 2px 4px rgba(16,15,14,.06), 0 8px 24px -12px rgba(16,15,14,.14);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      color-scheme: dark;
      --surface: #131312; --surface-raised: #1e1e1d; --surface-sunken: #191918;
      --head-bg: #262625; --zebra: #212120;
      --border: #3a3936; --border-soft: #2e2d2b;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8a8984;
      --accent: #3987e5; --accent-strong: #83b3f2; --accent-soft: #1e3350;
      --chip-bg: #32312f;
      --shadow-sm: 0 1px 2px rgba(0,0,0,.35);
      --shadow-md: 0 2px 4px rgba(0,0,0,.3), 0 8px 24px -12px rgba(0,0,0,.7);
    }
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin: 0; background: var(--surface); color: var(--text-primary);
    font: 16px/1.65 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 860px; margin: 0 auto; padding: 18px clamp(14px, 3vw, 24px) 64px; }

  /* Nav nomor dokumen: satu baris, bisa digeser di layar sempit. */
  .jejak {
    display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
    padding-bottom: 14px; margin-bottom: 22px;
    border-bottom: 1px solid var(--border);
  }
  .jejak a {
    padding: 4px 10px; border-radius: 999px; text-decoration: none;
    color: var(--text-secondary); background: var(--chip-bg);
    font-size: 13px; white-space: nowrap;
  }
  .jejak a:hover { color: var(--text-primary); }
  .jejak a.aktif { background: var(--accent-soft); color: var(--accent-strong); font-weight: 600; }

  article { overflow-wrap: break-word; }
  h1, h2, h3, h4 { line-height: 1.25; margin: 1.9em 0 .6em; scroll-margin-top: 16px; }
  h1 { font-size: 1.7rem; margin-top: 0; letter-spacing: -.01em; }
  h2 {
    font-size: 1.3rem; padding-bottom: .3em;
    border-bottom: 1px solid var(--border-soft);
  }
  h3 { font-size: 1.08rem; }
  h4 { font-size: .98rem; color: var(--text-secondary); }
  p, ul, ol { margin: 0 0 1em; }
  li { margin-bottom: .35em; }
  a { color: var(--accent); }
  a:hover { color: var(--accent-strong); }
  hr { border: 0; border-top: 1px solid var(--border); margin: 2.2em 0; }
  strong { font-weight: 650; }

  code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: .88em; background: var(--surface-sunken);
    border: 1px solid var(--border-soft); border-radius: 5px; padding: .1em .35em;
  }
  pre {
    background: var(--surface-sunken); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 16px; overflow-x: auto; line-height: 1.5;
  }
  pre code { background: none; border: 0; padding: 0; font-size: .85rem; }

  /* Tabel dokumen lebar; yang bergeser pembungkusnya, bukan halaman. */
  .geser { overflow-x: auto; margin: 0 0 1.3em; }
  table {
    border-collapse: collapse; width: 100%; font-size: .9rem;
    background: var(--surface-raised); border: 1px solid var(--border);
    border-radius: 10px; box-shadow: var(--shadow-sm);
  }
  th, td { padding: 8px 12px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--border-soft); }
  th { background: var(--head-bg); font-weight: 600; white-space: nowrap; }
  tbody tr:nth-child(even) { background: var(--zebra); }
  tbody tr:last-child td { border-bottom: 0; }

  /* Kartu di halaman indeks. */
  .kartu-kartu { display: grid; gap: 10px; }
  .kartu {
    display: block; padding: 14px 16px; text-decoration: none;
    background: var(--surface-raised); border: 1px solid var(--border);
    border-radius: 12px; box-shadow: var(--shadow-sm);
  }
  .kartu:hover { border-color: var(--accent); box-shadow: var(--shadow-md); }
  .kartu .judul { color: var(--accent); font-weight: 600; margin-bottom: 3px; }
  .kartu .ringkas { color: var(--text-secondary); font-size: .88rem; line-height: 1.5; }

  footer {
    margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--border);
    color: var(--text-muted); font-size: .85rem;
  }
"""


@dataclass(frozen=True)
class Dokumen:
    """Satu halaman: nama berkas tanpa ekstensi, judul H1, dan isi <body>."""

    slug: str
    judul: str
    ringkas: str
    isi: str


class _TautanDanTabel(Treeprocessor):
    def run(self, akar: ET.Element) -> None:
        for a in akar.iter("a"):
            tujuan = a.get("href", "")
            if _relatif_ke_md(tujuan):
                a.set("href", re.sub(r"\.md(?=$|#)", ".html", tujuan))
        _bungkus_tabel(akar)


# Penanda daftar. Daftar bernomor hanya boleh menyela paragraf bila mulai
# dari "1." — aturan GFM, dan pengaman supaya baris prosa yang diawali tahun
# ("2026. ...") tidak berubah jadi daftar.
_DAFTAR = re.compile(r"^\s*(?:[-*+]|1[.)])\s+")
_BUKAN_PARAGRAF = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+|^\s*(?:#|>|\||=|-{3,})")
_PAGAR = re.compile(r"^\s*(?:```|~~~)")


class _DaftarMenempel(Preprocessor):
    """Sisipkan baris kosong sebelum daftar yang menempel di bawah paragraf.

    Dokumen ditulis untuk GitHub, yang membolehkan daftar menyela paragraf:

        **Selesai bila**:
        - syarat pertama

    Python-Markdown menuntut baris kosong dan tanpa ini menelan daftarnya jadi
    satu paragraf berisi tanda hubung. Ada 34 tempat seperti itu di docs/, dan
    kegagalannya diam — halaman tetap terbit, hanya daftarnya hilang. Lebih
    baik perendernya yang mengikuti GitHub daripada 34 dokumen yang diubah
    demi perender.
    """

    def run(self, baris: list[str]) -> list[str]:
        hasil: list[str] = []
        dalam_pagar = False
        for teks in baris:
            if _PAGAR.match(teks):
                dalam_pagar = not dalam_pagar
            elif (not dalam_pagar and hasil and _DAFTAR.match(teks)
                    and hasil[-1].strip() and not _BUKAN_PARAGRAF.match(hasil[-1])):
                hasil.append("")
            hasil.append(teks)
        return hasil


class _Situs(Extension):
    def extendMarkdown(self, md: markdown.Markdown) -> None:
        # Prioritas 26: sesudah normalize_whitespace (30), sebelum
        # fenced_code (25). Artinya blok kode belum diangkat saat ini, jadi
        # _DaftarMenempel melacak pagarnya sendiri.
        md.preprocessors.register(_DaftarMenempel(md), "situs_daftar", 26)
        # Prioritas 5: setelah toc (yang memasang id judul) dan setelah
        # inline, jadi elemen <a> sudah ada saat href ditulis ulang.
        md.treeprocessors.register(_TautanDanTabel(md), "situs", 5)


def _relatif_ke_md(tujuan: str) -> bool:
    """Tautan ke dokumen tetangga — bukan URL luar, jangkar, atau mailto."""
    if not tujuan or tujuan.startswith(("#", "/", "mailto:")):
        return False
    if re.match(r"^[a-z][a-z0-9+.-]*:", tujuan, re.I):
        return False
    return re.search(r"\.md(?=$|#)", tujuan) is not None


def _bungkus_tabel(akar: ET.Element) -> None:
    """Sisipkan <div class="geser"> di antara induk dan tiap <table>.

    ElementTree tidak punya "ganti diriku sendiri", jadi pembungkusan harus
    dilakukan dari induknya; karena itu pohonnya ditelusuri per induk.
    """
    for induk in list(akar.iter()):
        for posisi, anak in enumerate(list(induk)):
            if anak.tag == "table":
                pembungkus = ET.Element("div", {"class": "geser"})
                pembungkus.append(anak)
                induk[posisi] = pembungkus


def _mesin() -> markdown.Markdown:
    return markdown.Markdown(extensions=["tables", "fenced_code", "toc", _Situs()])


def baca_teks(teks: str) -> str:
    """Markdown → HTML dengan aturan situs (tautan .md dan pembungkus tabel)."""
    return _mesin().convert(teks)


def baca(sumber: Path) -> Dokumen:
    """Render satu berkas .md. Judul diambil dari H1, ringkasan dari paragraf
    pertama sesudahnya — keduanya dipakai halaman indeks."""
    teks = sumber.read_text(encoding="utf-8")
    isi = baca_teks(teks)

    judul_md = re.search(r"^#\s+(.+)$", teks, re.M)
    judul = _tanpa_markup(judul_md.group(1)) if judul_md else sumber.stem

    sesudah_h1 = teks[judul_md.end():] if judul_md else teks
    paragraf = re.search(r"^(?![#|\s*$])(.+(?:\n(?![#|]|\s*$).*)*)", sesudah_h1, re.M)
    ringkas = _tanpa_markup(" ".join(paragraf.group(1).split())) if paragraf else ""

    return Dokumen(slug=sumber.stem, judul=judul, ringkas=ringkas, isi=isi)


def _tanpa_markup(teks: str) -> str:
    """Buang penanda markdown yang tidak enak dibaca di judul dan ringkasan."""
    teks = re.sub(r"\[([^]]*)\]\([^)]*\)", r"\1", teks)   # tautan → labelnya
    teks = re.sub(r"[`*_]", "", teks)
    return teks.strip()


def _lolos(teks: str) -> str:
    return (teks.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _nav(dokumen: list[Dokumen], aktif: str | None) -> str:
    tautan = ['<a href="../index.html">← Dashboard</a>',
              f'<a href="index.html"{_kelas(aktif is None)}>Dokumen</a>']
    for d in dokumen:
        tautan.append(f'<a href="{d.slug}.html"{_kelas(d.slug == aktif)}>'
                      f'{_lolos(_nomor(d.slug))}</a>')
    return '<nav class="jejak">' + "".join(tautan) + "</nav>"


def _kelas(aktif: bool) -> str:
    return ' class="aktif"' if aktif else ""


def _nomor(slug: str) -> str:
    """"03-rancang-bangun" → "03". Nav harus muat di satu baris di ponsel."""
    return slug.split("-", 1)[0]


def halaman(judul: str, isi: str, nav: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_lolos(judul)} — US Market Screener</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🗽</text></svg>">
<style>{GAYA}</style>
</head>
<body>
<div class="wrap">
{nav}
<article>
{isi}
</article>
<footer>Dokumen ini dibangkitkan dari <code>docs/</code> di
<a href="https://github.com/2013tib-droid/US-MARKET">github.com/2013tib-droid/US-MARKET</a>.</footer>
</div>
</body>
</html>
"""


def _indeks(dokumen: list[Dokumen]) -> str:
    kartu = []
    for d in dokumen:
        kartu.append(
            f'<a class="kartu" href="{d.slug}.html">'
            f'<div class="judul">{_lolos(d.judul)}</div>'
            f'<div class="ringkas">{_lolos(d.ringkas)}</div></a>')
    isi = ("<h1>Dokumen rancangan</h1>\n"
           "<p>Metodologi, infrastruktur, rancang bangun, roadmap, dan catatan "
           "praktik pasar AS untuk investor dari Indonesia. Sumbernya "
           "<code>docs/*.md</code> di repo; halaman ini dibangkitkan ulang "
           "tiap kali situs diterbitkan.</p>\n"
           '<div class="kartu-kartu">' + "".join(kartu) + "</div>")
    return isi


def susun(sumber_dir: Path, tujuan_dir: Path) -> list[Dokumen]:
    """Tulis satu halaman per dokumen plus indeksnya. Mengembalikan dokumen
    yang terbit, supaya pemanggil bisa melaporkan jumlahnya."""
    dokumen = []
    for slug in URUTAN:
        berkas = sumber_dir / f"{slug}.md"
        if not berkas.exists():
            raise FileNotFoundError(
                f"{berkas} tidak ada. Perbarui usmarket.situs.URUTAN bila "
                f"dokumen sengaja dihapus atau diganti nama.")
        dokumen.append(baca(berkas))

    tujuan_dir.mkdir(parents=True, exist_ok=True)
    for d in dokumen:
        (tujuan_dir / f"{d.slug}.html").write_text(
            halaman(d.judul, d.isi, _nav(dokumen, d.slug)), encoding="utf-8")
    (tujuan_dir / "index.html").write_text(
        halaman("Dokumen", _indeks(dokumen), _nav(dokumen, None)), encoding="utf-8")
    return dokumen


def bersihkan(tujuan_dir: Path) -> None:
    """Buang keluaran lama supaya dokumen yang dihapus tidak tertinggal."""
    if tujuan_dir.exists():
        shutil.rmtree(tujuan_dir)
