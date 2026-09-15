#!/usr/bin/env node
/**
 * Uji dashboard tanpa browser — pola yang sama dengan Screening-Saham.
 *
 * Menjalankan JavaScript dashboard/index.html yang SEBENARNYA di Node dengan
 * DOM tiruan seperlunya, memberinya CSV dari folder hasil/, lalu memeriksa
 * HTML yang keluar untuk setiap tab, setiap kelompok kolom, dan panel detail.
 *
 * Yang bisa ditangkap: nilai yang bocor mentah ke halaman ("undefined",
 * "NaN", "[object"), baris yang gagal dirender, dan kolom yang tidak ada di
 * CSV. Yang TIDAK bisa ditangkap: tampilan. Itu tetap perlu mata.
 *
 *     node scripts/uji_dashboard.js            # dari akar repo, memakai hasil/
 *     node scripts/uji_dashboard.js path/hasil # folder CSV lain
 *
 * Keluar dengan kode 1 bila ada pemeriksaan yang gagal.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const AKAR = path.resolve(__dirname, "..");
const HASIL = path.resolve(process.argv[2] || path.join(AKAR, "hasil"));
const html = fs.readFileSync(path.join(AKAR, "dashboard/index.html"), "utf8");
const cocok = html.match(/<script>\r?\n([\s\S]*?)<\/script>/);
if (!cocok) { console.error("Blok <script> tidak ditemukan."); process.exit(1); }

// ---- DOM tiruan ----
const simpan = {};
const elemen = {};
function el(id) {
  if (elemen[id]) return elemen[id];
  const e = {
    id, hidden: false, value: "", dataset: {}, open: false,
    scrollLeft: 0, scrollTop: 0, clientWidth: 1200, scrollWidth: 2400,
    set innerHTML(v) { simpan[id] = v; }, get innerHTML() { return simpan[id] || ""; },
    set textContent(v) { simpan[id + ":teks"] = String(v); }, get textContent() { return simpan[id + ":teks"] || ""; },
    classList: { add() {}, remove() {} },
    addEventListener() {}, appendChild() {}, querySelectorAll() { return []; },
  };
  return (elemen[id] = e);
}
const document = {
  getElementById: el,
  querySelectorAll: () => [],
  createElement: () => ({ set value(v) {}, set textContent(v) {} }),
};
function fetch(url) {
  const nama = url.split("?")[0].replace(/^hasil\//, "");
  const p = path.join(HASIL, nama);
  if (!fs.existsSync(p)) return Promise.resolve({ ok: false });
  const isi = fs.readFileSync(p, "utf8");
  return Promise.resolve({ ok: true, text: async () => isi, json: async () => JSON.parse(isi) });
}

const konteks = {
  document, fetch, console, Intl, Date, Math, Number, String, Set, Map, Promise, Object, Array, JSON,
  encodeURIComponent, decodeURIComponent,
  location: { hash: "", pathname: "/", search: "" },
  history: { replaceState() {} },
  addEventListener() {},
};
vm.createContext(konteks);
// muat() dipanggil di akhir skrip; fungsi lain diekspos untuk diuji.
vm.runInContext(cocok[1] + "\nglobalThis.__uji = { state, pilihTab, bukaDetail, tutupDetail, render, KOLOM, KELOMPOK };",
                konteks, { filename: "dashboard.js" });

let gagal = 0;
function periksa(syarat, pesan) {
  if (!syarat) { gagal++; console.error("GAGAL:", pesan); }
}
function bersih(teks, label) {
  for (const bocor of ["undefined", "NaN", "[object", "null"]) {
    // "null" hanya dicek di dalam sel (>null<), karena kata itu sah di atribut lain.
    const pola = bocor === "null" ? />null</ : new RegExp(bocor.replace("[", "\\["));
    periksa(!pola.test(teks), `${label}: memuat "${bocor}"`);
  }
}

setTimeout(() => {
  const u = konteks.__uji;
  periksa(!u.state.gagal, "dashboard gagal memuat data");
  periksa((u.state.data.semua || []).length > 1000, `semua.csv hanya ${(u.state.data.semua || []).length} baris`);

  const kurang = u.KOLOM.map(k => k.k).filter(k => !u.state.kolomAda.has(k));
  if (kurang.length) console.log(`Info: ${kurang.length} kolom dashboard tidak ada di CSV ini (tampil "–"): ${kurang.join(", ")}`);

  for (const tab of ["tren", "value", "quality", "semua"]) {
    u.pilihTab(tab);
    for (const kel of Object.keys(u.KELOMPOK).concat([""])) {
      u.state.kelompok = kel;
      u.render();
      const t = simpan.tabel || "";
      const adaData = (u.state.data[tab] || []).length > 0;
      periksa(!adaData || t.includes("<table"), `tab ${tab}/${kel || "semua kolom"}: tabel tidak dirender`);
      bersih(t, `tab ${tab}/${kel || "semua kolom"}`);
    }
  }
  const contoh = (u.state.data.semua || []).slice(0, 25).map(r => r.Ticker).concat(["AAPL", "JPM", "BRK-B"]);
  for (const t of contoh) {
    if (!(u.state.data.semua || []).some(r => r.Ticker === t)) continue;
    u.bukaDetail(t);
    const d = simpan.detail || "";
    periksa(d.includes(t), `panel detail ${t} tidak memuat tickernya`);
    bersih(d, `panel detail ${t}`);
    u.tutupDetail();
  }
  periksa((simpan["pembaruan:teks"] || "").length > 0, "teks waktu pembaruan kosong");

  console.log(gagal ? `${gagal} pemeriksaan gagal.` : "Dashboard lolos semua pemeriksaan.");
  process.exit(gagal ? 1 : 0);
}, 50);
