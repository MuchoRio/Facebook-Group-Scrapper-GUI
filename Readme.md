# 📘 Facebook Group Scraper (GUI) — Tkinter + Selenium

> GUI tool untuk login pakai cookies, scroll halaman **“Groups to join”**, ambil **nama + URL group (unik)**, auto-filter noise (berita/“last active”), dan ekspor CSV/TXT — lengkap dengan **live logs** dan tombol **Stop**.

---

## 🚀 TL;DR (Quick Start)

```bash
pip install -r requirements.txt     # atau: pip install selenium webdriver-manager
python main.py                      # jika file kamu bernama gui.py, jalankan: python gui.py
```

* Pilih **Cookies File** → `www.facebook.com.cookies.json`
* Pilih **Output File (CSV)** → mis. `groups_data.csv`
* (Opsional) **Headless Mode**, **Verbose Logging**
* Atur **Scroll Delay** & **Max Scroll**
* Klik **Start Scraping** ▶️, lihat **Live Logs**, dan **Stop** kapan saja 🛑

---

## 🌟 Fitur Utama

* 🖱️ **GUI Interaktif (Tkinter)**: tanpa argumen CLI, tinggal klik-klik.
* 🔐 **Login pakai Cookies**: tidak perlu input username/password lagi.
* 🤖 **Full Automation**: Selenium scroll & ekstrak data group dari `facebook.com/groups/joins/`.
* 🧠 **Smart Filtering**: buang pola “news/berita”, “last active x minutes ago”, dsb. (keyword + regex).
* 🧾 **Ekspor Rapi**

  * `groups_data.csv` (raw, unik)
  * `*_names_filtered_<Profile>.txt`
  * `*_urls_filtered_<Profile>.txt`
* 📝 **Verbose & Live Logs** di GUI, dengan warna (info/warn/error).
* 🛑 **Graceful Stop**: hentikan proses dengan aman; hasil sementara tetap diproses & disimpan.
* 🧩 **Chromedriver Auto** via `webdriver_manager`.

---

## 🧱 Requirements

* **Python**: 3.9+ direkomendasikan
* **Google Chrome** terpasang
* **Libraries**:

  * `selenium`
  * `webdriver-manager`
  * `tkinter` (umumnya sudah tersedia di instalasi Python desktop)

Install cepat:

```bash
# Jika punya requirements.txt
pip install -r requirements.txt

# Atau manual:
pip install selenium webdriver-manager
```

> `webdriver_manager` otomatis unduh ChromeDriver yang cocok dengan versi Chrome kamu.&#x20;

---

## 🧭 Cara Pakai (Detail)

### 1) Siapkan Cookies Facebook

1. Login Facebook di browser.
2. Pakai ekstensi eksport cookies (contoh: **EditThisCookie**).
3. Ekspor cookies **domain `facebook.com`** dalam format **JSON**.
4. Simpan dengan nama mudah, mis. `www.facebook.com.cookies.json`.

### 2) Jalankan Aplikasi

```bash
python main.py
# (Jika file kamu bernama gui.py, jalankan: python gui.py)
```

### 3) Konfigurasi di GUI

* **Cookies File**: pilih file cookies JSON kamu.
* **Output File (CSV)**: tentukan lokasi simpan, mis. `groups_data.csv`.
* **Headless Mode**: nyalakan jika ingin browser tak terlihat.
* **Scroll Delay** (detik): jeda tiap scroll; naikkan jika loading lambat.
* **Max Scroll Attempts**: berapa kali coba scroll ke bawah.
* **Verbose Logging**: tampilkan log detail di GUI.

Klik **Start Scraping** untuk mulai. Kamu bisa klik **Stop** kapan saja.

---

## 📄 Struktur Output

Setelah selesai/di-stop, kamu akan mendapatkan:

1. **CSV Raw**
   `groups_data.csv` → kolom: `GroupName,GroupURL` (unik).

2. **TXT Filtered (Names)**
   `groups_data_names_filtered_<Profile>.txt` → satu nama per baris (setelah filter).

3. **TXT Filtered (URLs)**
   `groups_data_urls_filtered_<Profile>.txt` → satu URL per baris (setelah filter).

> `<Profile>` diambil otomatis dari `/me/` (H1 nama profil) dan disanitasi agar aman jadi nama file.

---

## 🧠 Tentang Filtering (Keyword + Regex)

Script memblokir item yang mengandung **keyword** noise (mis. “berita hari ini”, “discover”, “view group”, “create new group”, dll.) dan **pola regex** seperti:

* `berita\s+([a-zA-Z\s]+)\s+\d{4}`
* `(terakhir aktif|active)\s+(semenit|sejam|sehari|seminggu|\d+\s+(detik|menit|jam|hari|minggu))\s+(yang )?lalu`
* `(last active|active)\s+(about|a few)?\s*(\d+|a|an)\s+(second|minute|hour|day|week)s?\s+ago`

> Kamu bisa kustom daftar **blacklist\_keywords** & **blacklist\_patterns** di kode utama untuk menyesuaikan bahasa/UX.

---

## 🖼️ Kontrol GUI (Ringkas)

| Kontrol             | Fungsi                                           |
| ------------------- | ------------------------------------------------ |
| Cookies File        | Memuat sesi login melalui cookies JSON.          |
| Output File (CSV)   | Lokasi penyimpanan hasil raw (unik).             |
| Headless Mode       | Menjalankan Chrome tanpa jendela (background).   |
| Verbose Logging     | Memunculkan log proses yang detail.              |
| Scroll Delay        | Jeda antarscroll, atur sesuai kecepatan loading. |
| Max Scroll Attempts | Batas jumlah percobaan scroll.                   |

---

## ▶️ Alur Kerja Internal (Ringkas)

1. Inisialisasi WebDriver (headless opsional)
2. `Load cookies` ke `facebook.com` → refresh
3. Buka `https://www.facebook.com/groups/joins/`
4. Scroll berulang hingga batas/akhir halaman
5. Ekstrak `<a role="link" href*="/groups/">` + teks non-kosong
6. De-duplikasi → dict `{GroupName: GroupURL}`
7. Ambil nama profil via `/me/` untuk suffix output
8. Tulis **CSV raw**
9. **Post-process** CSV → TXT filtered (names & urls)
10. Keluar dengan aman (termasuk saat **Stop**)

---

## 🧪 Contoh Output

```csv
GroupName,GroupURL
Contoh Komunitas AI,https://www.facebook.com/groups/1234567890
Belajar Otomasi QA,https://www.facebook.com/groups/987654321
```

```text
# *_names_filtered_<Profile>.txt
Contoh Komunitas AI
Belajar Otomasi QA
```

```text
# *_urls_filtered_<Profile>.txt
https://www.facebook.com/groups/1234567890
https://www.facebook.com/groups/987654321
```

---

## 🧩 Tips & Troubleshooting

<details>
<summary>📏 Tuning Scroll</summary>

* Tambah **Max Scroll** (mis. 200–400) kalau hasil sedikit.
* Naikkan **Scroll Delay** (2.5–4.0s) bila loading lambat.
* Aktifkan **Verbose** untuk melihat ritme & deteksi “bottom reached”.

</details>

<details>
<summary>🔐 Login & Cookies</summary>

* Pastikan cookies **fresh** dan benar untuk domain `facebook.com`.
* Bila tetap gagal, coba non-headless agar bisa melihat apa yang terjadi.

</details>

<details>
<summary>🧯 Driver/Chrome</summary>

* Update Chrome ke versi terbaru; `webdriver_manager` akan menyesuaikan driver otomatis.
* Jika ada error versi/compatibility, hapus cache driver `~/.wdm/` lalu jalankan ulang.

</details>

---

## 🧪 Checklist Testing

* [ ] Cookies termuat & refresh sukses
* [ ] H1 “Groups/Grup” terdeteksi
* [ ] Scroll mencapai batas atau Max Scroll
* [ ] Ekstraksi menghasilkan item unik (>0)
* [ ] CSV raw tersimpan
* [ ] TXT filtered names/urls terbentuk (dengan suffix profil)
* [ ] Tombol Stop menghentikan proses dengan aman

---

## ⚖️ Disclaimer & Etika

Gunakan untuk **tujuan personal & legal**. Mematuhi **Terms of Service** situs, **robots**, hukum setempat, dan privasi pengguna adalah tanggung jawab kamu. Hindari data personal/sensitif dan batasi laju scraping.&#x20;

---
