# Panduan Penguji — Uji Penerimaan Pengguna (UAT)

**Sistem CDT (Cognitive Digital Twin) — Deteksi Bias Investasi**

Terima kasih telah bersedia menjadi penguji untuk sistem **CDT Bias Detection**.
Panduan ini berisi semua yang Anda perlukan untuk menjalankan satu sesi
pengujian secara mandiri.

---

## 1. Tujuan UAT

Penelitian ini menguji apakah sistem CDT:

1. **Dapat dipakai dengan nyaman** oleh investor ritel di Indonesia
   (kemudahan penggunaan / *usability*).
2. **Memberikan umpan balik bias yang dirasakan bermanfaat**
   (relevansi konten edukatif).
3. **Stabil** ketika dipakai pada perangkat sehari-hari
   (laptop, browser desktop, atau ponsel).

Hasil pengujian Anda akan dipakai untuk perbaikan akhir sebelum sidang
tugas akhir (skripsi). Tidak ada jawaban benar atau salah; yang dinilai
adalah **sistem**, bukan diri Anda.

---

## 2. Ekspektasi Waktu

| Aktivitas                                           | Perkiraan Waktu |
| --------------------------------------------------- | --------------- |
| Mendaftar dan mengisi survei awal                   | 3 menit         |
| Menjalankan satu sesi simulasi (14 putaran)         | 5–8 menit       |
| Membaca umpan balik dan profil kognitif             | 2 menit         |
| Mengisi kuesioner SUS dan komentar terbuka          | 2 menit         |
| **Total per sesi**                                  | **~10–15 menit**|

Disarankan menjalankan minimal **1 sesi penuh** lalu mengisi formulir
*Feedback Penguji* di dalam aplikasi.

---

## 3. Tautan Aplikasi

> **URL aplikasi:** `https://cdt-bias-uat.streamlit.app`
> *(Jika tautan berbeda, pewawancara/peneliti akan memberitahukan URL final
> melalui pesan WhatsApp/email saat undangan.)*

Buka tautan tersebut di browser modern (Chrome, Edge, Firefox, atau Safari).
Disarankan koneksi internet stabil minimal 1 Mbps. Tidak diperlukan instalasi
aplikasi tambahan.

---

## 4. Tiga Skenario Pengujian Wajib

Mohon jalankan **ketiga skenario** di bawah secara berurutan dalam satu sesi.

### Skenario A — Simulasi Lengkap

1. Buka URL aplikasi.
2. Pada halaman **Beranda**, masukkan nama pengguna baru
   (mis. `nama.anda01`) lalu klik **Lanjutkan**.
3. Lengkapi formulir pendaftaran (nama lengkap, usia, jenis kelamin, profil
   risiko, pengalaman investasi) dan kata sandi minimal 8 karakter.
4. Isi **Survei Awal Kecenderungan Bias** (9 pernyataan) dengan jujur.
5. Centang persetujuan partisipasi penelitian, lalu klik
   **Daftar & Mulai Simulasi**.
6. Mainkan **14 putaran** simulasi: pada tiap putaran, untuk masing-masing
   saham, pilih *Beli*, *Jual*, atau *Tahan* sesuai perkiraan Anda. Tidak
   ada batas waktu.
7. Selesaikan seluruh 14 putaran (jangan tutup tab sebelum putaran ke-14
   selesai, karena hasil hanya tersimpan saat sesi diselesaikan).

### Skenario B — Lihat Umpan Balik

1. Setelah putaran ke-14, sistem akan menampilkan halaman
   **Hasil Analisis & Umpan Balik**.
2. Bacalah seluruh konten halaman: skor bias, severity, penjelasan, dan
   rekomendasi tindak lanjut.
3. Buka juga halaman **Profil Kognitif Saya** dari menu atas untuk melihat
   profil CDT Anda dan grafik radar.

### Skenario C — Ekspor Data

1. Pada halaman **Profil Kognitif Saya**, gulir ke bawah hingga bagian
   **Ekspor Data**.
2. Klik tombol **Unduh Riwayat Sesi (CSV)**.
3. Pastikan file `.csv` berhasil diunduh dan dapat dibuka di Excel atau
   Google Sheets.

---

## 5. Mengisi Kuesioner Umpan Balik

Setelah ketiga skenario di atas selesai:

1. Klik menu **Feedback Penguji** di bilah navigasi atas.
2. Isi **10 pernyataan SUS** menggunakan skala 1–5
   (1 = Sangat Tidak Setuju, 5 = Sangat Setuju).
3. Lengkapi dua pertanyaan terbuka:
   - *Apa yang membingungkan?*
   - *Apa yang berguna?*
4. Klik **Kirim Tanggapan**. Anda akan melihat skor SUS Anda secara langsung
   sebagai konfirmasi bahwa data tersimpan.

---

## 6. Cara Melaporkan Bug

> **Direkomendasikan untuk penguji non-teknis:** gunakan **Google Form**.
> Penguji teknis boleh memilih GitHub Issues bila lebih nyaman.

### Opsi 1 — Google Form (direkomendasikan)

> **Tautan formulir laporan bug:** *(akan dikirimkan terpisah oleh peneliti).*

Isikan:
- Nama pengguna yang dipakai saat menemukan bug.
- Halaman tempat bug muncul (Beranda / Simulasi / Hasil / Profil / Feedback).
- Apa yang Anda lakukan tepat sebelum bug muncul.
- Apa yang terjadi vs. apa yang Anda harapkan.
- Tangkapan layar (jika memungkinkan).

### Opsi 2 — GitHub Issues (untuk penguji teknis)

1. Buka https://github.com/arvynopl/ta-18222007/issues
2. Klik **New Issue**.
3. Beri judul singkat (mis. `Bug: tombol Beli tidak responsif di putaran 8`).
4. Sertakan langkah reproduksi dan environment (browser + OS).

---

## 7. Etika & Privasi Data

- Anda dapat berhenti kapan saja tanpa konsekuensi.
- Data yang dikumpulkan: tanggapan simulasi, skor bias, jawaban survei,
  dan tanggapan SUS. **Tidak ada data finansial nyata** yang diminta.
- Data identitas (nama lengkap, usia, jenis kelamin) hanya dipakai untuk
  agregasi statistik dalam laporan tugas akhir dan tidak akan dipublikasikan
  per individu.
- Data disimpan pada Neon Postgres dengan koneksi terenkripsi (TLS).

---

## 8. Catatan Teknis Singkat

- **Browser disarankan:** Chrome 100+, Edge 100+, Firefox 102+, atau
  Safari 15+.
- **Mobile:** sistem mendukung tampilan ponsel; rotasikan ke landscape
  bila grafik terlihat sempit.
- **Sesi tidak tersimpan:** jika Anda menutup tab di tengah simulasi
  (sebelum putaran ke-14 selesai), data putaran-putaran tersebut **tidak**
  akan tercatat. Mohon selesaikan satu sesi penuh sebelum keluar.

---

## 9. Catatan Validitas Translasi SUS

Kuesioner SUS pada halaman *Feedback Penguji* menggunakan terjemahan
Bahasa Indonesia **ad-hoc, pending validation**. Pada saat Phase 4
diluncurkan, peneliti belum memperoleh referensi terjemahan SUS Indonesia
yang telah tervalidasi secara statistik (mis. uji reliabilitas Cronbach α
dan validitas konstruk pada populasi Indonesia). Skor SUS yang dihasilkan
karenanya bersifat **eksploratif** dan akan ditafsirkan secara hati-hati,
bukan dibandingkan langsung dengan benchmark internasional.

Jika di kemudian hari ditemukan terjemahan SUS Indonesia yang tervalidasi
(mis. dari publikasi peer-reviewed seperti Sharfina & Santoso (2016) atau
versi yang lebih baru), peneliti akan memutakhirkan terjemahan dan
men-dokumentasikan perubahan di repositori sebelum laporan akhir
diserahkan.

---

## 10. Bantuan

Jika ada kendala selama pengujian, hubungi peneliti melalui kontak yang
diberikan saat undangan. Sertakan:

- Nama pengguna Anda.
- Waktu kira-kira saat masalah muncul (WIB).
- Deskripsi singkat masalah.

**Selamat menguji, dan terima kasih atas waktu Anda!**
