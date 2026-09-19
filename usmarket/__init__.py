"""Paket analisa saham AS. Rancangannya ada di docs/, urutan pembangunannya
di docs/04-roadmap.md.

Versi skema dinaikkan setiap kali kolom hasil/semua.csv berubah arti atau
bertambah, supaya dashboard dan uji winrate bisa menolak CSV yang tidak
mereka pahami alih-alih salah membacanya diam-diam.
"""

VERSI_SKEMA = 4  # 2: fundamental (Fase 2); 3: smart money & Growth (Fase 3);
#                  4: Rezim, Skor, Status, Alasan (Fase 4)

import sys as _sys

# Konsol Windows masih memakai cp1252, yang tidak punya karakter seperti
# "→" atau "≥". Tanpa ini, satu print berisi tanda panah menghentikan skrip
# dengan UnicodeEncodeError setelah semua data selesai diunduh.
for _aliran in (_sys.stdout, _sys.stderr):
    if hasattr(_aliran, "reconfigure") and (_aliran.encoding or "").lower() != "utf-8":
        _aliran.reconfigure(encoding="utf-8", errors="replace")

# Jaringan kantor sering memasang sertifikat TLS sendiri di tengah jalan.
# requests memakai daftar sertifikat certifi yang tidak mengenalnya, jadi
# setiap unduhan gagal dengan CERTIFICATE_VERIFY_FAILED. truststore membuat
# Python memakai daftar sertifikat sistem operasi. Paket ini hanya ada di
# requirements-dev.txt: di runner GitHub tidak terpasang dan baris ini diam.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass
