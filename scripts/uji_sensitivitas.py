#!/usr/bin/env python3
"""Seberapa rapuh peringkat skor komposit terhadap bobotnya?

Syarat "selesai" ketiga Fase 4 di docs/04-roadmap.md: skor komposit dengan
bobot ± 10 poin per faktor — peringkat 20 besar tidak boleh berubah lebih
dari 30%. Kalau berubah lebih, skornya terlalu bergantung pada angka bobot
yang memang cuma titik awal, dan peringkatnya bukan temuan melainkan
pilihan.

Yang diukur: berapa nama dari 20 besar dasar yang **hilang** dari 20 besar
setelah bobotnya digeser. Enam dari 20 = 30%, itu batasnya.

Bobot digeser satu faktor pada satu waktu, ± 10 poin, lalu sisanya
dinormalisasi ulang ke total yang sama supaya yang diuji benar-benar
*komposisi* bobot dan bukan skalanya (mengalikan semua bobot dengan angka
yang sama tidak mengubah peringkat sama sekali).

Tidak menyentuh jaringan: seluruhnya dihitung dari hasil/semua.csv.

    python scripts/uji_sensitivitas.py
    python scripts/uji_sensitivitas.py --rezim Risk-off --n 20 --geser 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from usmarket import makro  # noqa: E402

AKAR = Path(__file__).resolve().parent.parent
SEMUA = AKAR / "hasil" / "semua.csv"

BATAS_BERUBAH_PCT = 30.0


def geser_bobot(bobot: dict[str, float], faktor: str, delta: float) -> dict[str, float] | None:
    """Geser satu faktor `delta` poin, sisanya dinormalisasi ke total semula.

    None bila hasilnya tidak masuk akal: bobot negatif, atau seluruh sisa
    bobot nol sehingga tidak ada yang bisa menyerap gesernya.
    """
    total = sum(bobot.values())
    baru = dict(bobot)
    baru[faktor] = bobot[faktor] + delta
    if baru[faktor] < 0:
        return None
    sisa_lama = total - bobot[faktor]
    sisa_baru = total - baru[faktor]
    if sisa_lama <= 0:
        return None
    for f in baru:
        if f != faktor:
            baru[f] = bobot[f] * sisa_baru / sisa_lama
    return baru


def peringkat(tabel: pd.DataFrame, bobot: dict[str, float], n: int) -> list[str]:
    skor = makro.skor_faktor(tabel, bobot)
    return list(skor.sort_values(ascending=False).head(n).index)


# Potongan pembanding tambahan. Kalau churn 20 besar cuma efek batas —
# peringkat 20 dan 21 praktis seri — maka potongan yang lebih panjang harus
# jauh lebih stabil. Kalau tidak, kerapuhannya nyata.
POTONGAN = (10, 20, 50, 100)


def diagnosa(dasar: pd.Series, baru: pd.Series) -> dict:
    """Korelasi peringkat seluruh universe, dan irisan di beberapa potongan.

    Korelasi peringkat menjawab "apakah urutannya secara keseluruhan
    berubah"; irisan menjawab "apakah nama yang akan dibeli berubah".
    Keduanya bisa berbeda jauh, dan yang kedua yang menentukan portofolio.
    """
    # Spearman = Pearson atas peringkat; ditulis begini supaya tidak
    # menambah scipy hanya untuk satu angka.
    rho = dasar.rank().corr(baru.rank())
    irisan = {n: 100.0 * len(set(dasar.nlargest(n).index) & set(baru.nlargest(n).index)) / n
              for n in POTONGAN}
    return {"rho": rho, "irisan": irisan}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", type=Path, default=SEMUA)
    p.add_argument("--rezim", default=None, help="Satu rezim saja (default: semua)")
    p.add_argument("--n", type=int, default=20, help="Panjang daftar teratas yang dibandingkan")
    p.add_argument("--geser", type=float, default=10.0, help="Geser bobot ± berapa poin")
    p.add_argument("--hanya-lolos", action="store_true",
                   help="Hanya emiten yang lolos likuiditas dan tanpa flag berat")
    a = p.parse_args(argv)

    if not a.csv.exists():
        print(f"{a.csv} belum ada. Jalankan python screener.py dulu.", file=sys.stderr)
        return 1
    t = pd.read_csv(a.csv, index_col="Ticker")
    if a.hanya_lolos:
        from usmarket import keputusan
        lolos = t["LolosLikuiditas"].map(lambda v: str(v).strip().lower() == "true")
        t = t[lolos & ~keputusan.flag_berat(t)]
    print(f"{len(t)} emiten dari {a.csv}; membandingkan {a.n} besar, geser ± {a.geser:.0f} poin\n")

    rezim_diuji = [a.rezim] if a.rezim else list(makro.BOBOT_REZIM)
    lolos_semua = True
    for nama in rezim_diuji:
        if nama not in makro.BOBOT_REZIM:
            print(f"Rezim '{nama}' tidak dikenal. Pilihan: {', '.join(makro.BOBOT_REZIM)}",
                  file=sys.stderr)
            return 1
        bobot = makro.BOBOT_REZIM[nama]
        skor_dasar = makro.skor_faktor(t, bobot)
        dasar = peringkat(t, bobot, a.n)
        print(f"--- {nama} ---")
        print(f"bobot: {', '.join(f'{f} {b:g}' for f, b in bobot.items() if b)}")
        print(f"{a.n} besar: {', '.join(dasar)}")

        baris = []
        for f in bobot:
            for delta in (-a.geser, a.geser):
                ubah = geser_bobot(bobot, f, delta)
                if ubah is None:
                    # Bobot 0 digeser −10 jadi negatif: tidak ada yang diuji,
                    # dan itu bukan kegagalan.
                    baris.append({"Faktor": f, "Geser": f"{delta:+.0f}", "Berubah_%": None,
                                  "rho": None, "Catatan": "bobot jadi negatif"})
                    continue
                skor_baru = makro.skor_faktor(t, ubah)
                baru = peringkat(t, ubah, a.n)
                hilang = [x for x in dasar if x not in baru]
                pct = 100.0 * len(hilang) / a.n
                lolos_semua &= pct <= BATAS_BERUBAH_PCT
                d = diagnosa(skor_dasar, skor_baru)
                catatan = {f"irisan_top{n}": round(v) for n, v in d["irisan"].items()}
                baris.append({"Faktor": f, "Geser": f"{delta:+.0f}", "Berubah_%": round(pct, 1),
                              "rho": round(d["rho"], 4), **catatan,
                              "Catatan": ("ok" if pct <= BATAS_BERUBAH_PCT else "MELEBIHI 30%")
                              + (f" — keluar: {', '.join(hilang)}" if hilang else "")})
        hasil = pd.DataFrame(baris)
        with pd.option_context("display.width", 220, "display.max_colwidth", 70):
            print(hasil.to_string(index=False))
        diuji = hasil["Berubah_%"].dropna()
        if len(diuji):
            rho_min = hasil["rho"].dropna().min()
            print(f"terburuk: {diuji.max():.1f}% berubah (batas {BATAS_BERUBAH_PCT:.0f}%); "
                  f"korelasi peringkat terendah rho={rho_min:.3f}")
        print()

    if lolos_semua:
        print(f"LOLOS: peringkat {a.n} besar tahan terhadap geseran bobot ± {a.geser:.0f} poin.")
        return 0
    print(f"GAGAL: ada geseran bobot yang mengubah {a.n} besar lebih dari "
          f"{BATAS_BERUBAH_PCT:.0f}%. Lihat baris bertanda MELEBIHI.\n"
          "Baca bersama kolom rho dan irisan_top*: rho tinggi dengan irisan rendah berarti\n"
          "urutan keseluruhan stabil tapi nama yang benar-benar dibeli tidak — dan yang\n"
          "kedua itulah yang menentukan portofolio. Jangan menggeser bobot supaya lolos:\n"
          "syarat ini ada justru untuk menangkap skor yang bobotnya menentukan hasilnya.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
