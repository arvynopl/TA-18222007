# Panduan Penguji — Uji Penerimaan Pengguna (UAT)

**Sistem CDT (Cognitive Digital Twin) — Deteksi Bias Investasi**

Terima kasih telah bersedia menjadi penguji. Panduan ini berisi semua yang Anda perlukan untuk menjalankan satu sesi pengujian secara mandiri, kira-kira **15–20 menit** dari awal hingga akhir.

---

## 1. Tujuan & Apa yang Dinilai

Penelitian ini menguji apakah sistem CDT:

1. **Mudah dan nyaman digunakan** oleh investor ritel di Indonesia (kemudahan penggunaan / *usability*).
2. **Memberikan umpan balik bias yang dirasakan bermanfaat** (relevansi konten edukatif).
3. **Stabil** ketika dipakai pada perangkat sehari-hari (laptop, browser desktop, atau ponsel).

Hasil pengujian Anda akan dipakai untuk perbaikan akhir sebelum sidang tugas akhir. **Tidak ada jawaban benar atau salah; yang dinilai adalah sistem, bukan diri Anda.**

---

## 2. Estimasi Waktu

| Aktivitas | Perkiraan Waktu |
|---|---|
| Mendaftar dan mengisi survei awal | 3 menit |
| Menjalankan satu sesi simulasi (14 putaran) | 5–8 menit |
| Membaca umpan balik dan profil kognitif | 2 menit |
| Mengisi kuesioner umpan balik (SUS) | 2–3 menit |
| Menjawab pertanyaan terbuka (opsional) | 2–4 menit |
| **Total per sesi** | **15–20 menit** |

Disarankan menjalankan **minimal 1 sesi penuh** lalu mengisi formulir *Feedback Penguji* di dalam aplikasi. Jika berkenan, sesi ke-2 dan ke-3 sangat membantu — sistem dirancang untuk belajar dari pola Anda lintas sesi.

---

## 3. Tautan Aplikasi

> **URL aplikasi:** `https://cdt-bias-uat.streamlit.app`
> *(Jika tautan berbeda, peneliti akan memberitahukan URL final melalui pesan WhatsApp/email saat undangan.)*

Buka tautan tersebut di browser modern (Chrome, Edge, Firefox, atau Safari). Disarankan koneksi internet stabil minimal 1 Mbps. **Tidak diperlukan instalasi aplikasi tambahan.**

---

## 4. Skenario Pengujian

Mohon jalankan **ketiga skenario** di bawah secara berurutan dalam satu sesi.

### Skenario A — Pendaftaran & Simulasi Lengkap

1. Buka URL aplikasi.
2. Pada halaman **Beranda**, masukkan nama pengguna baru (mis. `nama.anda01`) lalu klik **Lanjutkan**.
3. Lengkapi formulir pendaftaran:
   - Data diri: nama lengkap, usia, jenis kelamin
   - Profil investor: profil risiko, pengalaman investasi
   - Kata sandi (minimal 8 karakter)
4. Isi **Survei Awal Kecenderungan Bias** (9 pernyataan, skala 1–5) dengan jujur. Survei ini dipakai untuk mengkalibrasi profil awal CDT Anda.
5. Centang persetujuan partisipasi penelitian, lalu klik **Daftar & Mulai Simulasi**.
6. Mainkan **14 putaran** simulasi. Pada tiap putaran, untuk masing-masing dari 12 saham IDX, pilih *Beli*, *Jual*, atau *Tahan* sesuai perkiraan Anda. Tidak ada batas waktu.
7. Selesaikan seluruh 14 putaran. **Penting:** jangan tutup tab sebelum putaran ke-14 selesai — hasil sesi hanya tersimpan saat sesi diselesaikan penuh.

### Skenario B — Lihat Umpan Balik & Profil

1. Setelah putaran ke-14, sistem akan menampilkan halaman **Hasil Analisis & Umpan Balik**.
2. Bacalah seluruh konten halaman: skor bias, severity (ringan/sedang/berat), penjelasan, dan rekomendasi tindak lanjut.
3. Di akhir halaman, isi **Evaluasi Diri** singkat (4 pertanyaan, skala 1–5) tentang seberapa Anda menyadari bias-bias yang dideteksi.
4. Buka halaman **Profil Kognitif Saya** dari menu atas untuk melihat profil CDT Anda dan grafik radar.

### Skenario C — Ekspor Data Pribadi (opsional)

1. Pada halaman **Profil Kognitif Saya**, gulir ke bawah hingga bagian **Ekspor Data**.
2. Klik tombol **Unduh Riwayat Sesi (CSV)**.
3. Pastikan file `.csv` berhasil diunduh dan dapat dibuka di Excel atau Google Sheets.

---

## 5. Mengisi Kuesioner Umpan Balik (Wajib)

Setelah ketiga skenario di atas selesai:

1. Klik menu **Feedback Penguji** di bilah navigasi atas.
2. Lengkapi formulir berikut:

### Bagian 1 — Kuesioner Usability (Wajib, ±2 menit)

10 pernyataan singkat tentang pengalaman menggunakan sistem. Skala 1–5:
- 1 = Sangat Tidak Setuju
- 5 = Sangat Setuju

Mohon jawab semua 10 pernyataan dengan jujur — tidak ada jawaban yang dianggap "buruk".

### Bagian 2 — Pertanyaan Terbuka (Opsional, namun sangat dihargai)

3 pertanyaan terbuka untuk menangkap pengalaman Anda yang tidak tertangkap oleh skala numerik:

1. **Apa yang membingungkan?** — bagian sistem mana yang sulit dipahami atau memerlukan tebakan?
2. **Apa yang berguna?** — fitur atau bagian mana yang paling membantu Anda?
3. **Saran perbaikan / ide fitur tambahan** — apa yang ingin Anda lihat ditambahkan, diubah, atau dihilangkan?

> Anda boleh mengosongkan ketiganya, namun jawaban Anda — sekecil apa pun — sangat membantu peneliti memahami konteks di balik skor numerik.

3. Klik **Kirim Tanggapan**. Sistem akan menampilkan konfirmasi bahwa data tersimpan.

### Mengirim Ulang Tanggapan (Re-fill)

Pendapat Anda boleh berubah setelah menggunakan sistem lebih lama. Untuk itu:

- **Anda dapat membuka ulang halaman Feedback Penguji kapan saja** dan mengirim tanggapan baru.
- Sistem **menyimpan seluruh riwayat pengiriman** (tidak ada yang ditimpa). Setiap pengiriman menjadi catatan tersendiri.
- Untuk analisis tesis, peneliti **menggunakan tanggapan terbaru** Anda. Kiriman lama tetap tersimpan sebagai jejak audit penelitian.
- Tidak ada batasan jumlah pengiriman. Jujurlah pada pendapat terkini Anda.

---

## 6. Bagaimana Data Anda Digunakan

Transparansi adalah fondasi penelitian ini. Berikut rincian data yang Anda berikan dan bagaimana kami memperlakukannya.

| Aspek | Detail |
|---|---|
| **Apa yang dikumpulkan** | Tindakan simulasi (beli/jual/tahan), durasi keputusan, skor bias yang dihitung, jawaban survei awal, evaluasi diri pasca-sesi, dan tanggapan kuesioner umpan balik (SUS + pertanyaan terbuka). |
| **Apa yang TIDAK dikumpulkan** | Tidak ada data finansial nyata. Tidak ada akses ke akun broker, rekening, atau portofolio sebenarnya. Sistem ini murni simulasi. |
| **Identitas** | Nama lengkap, usia, jenis kelamin, profil risiko, dan pengalaman investasi dipakai **hanya untuk agregasi statistik** dalam laporan tugas akhir. Identitas individu tidak akan dipublikasikan. |
| **Penyimpanan** | Data disimpan pada **Neon Postgres** dengan koneksi terenkripsi (TLS). Akses ke database hanya melalui kredensial yang dipegang peneliti. |
| **Akses pihak ketiga** | Tidak ada. Data tidak dijual, tidak dibagi ke perusahaan atau pihak komersial. |
| **Halaman peneliti** | Peneliti memiliki dasbor agregat tersembunyi (URL khusus + kata sandi) yang menampilkan ringkasan kohort. Halaman ini tidak menampilkan kata sandi pengguna. |
| **Riwayat & retensi** | Seluruh kiriman survei disimpan sebagai riwayat (tidak ada penimpaan). Data dipertahankan selama proses sidang dan revisi tugas akhir, kira-kira 6–12 bulan, lalu dapat diarsipkan atau dihapus atas permintaan Anda. |
| **Hak Anda** | Anda dapat berhenti kapan saja tanpa konsekuensi. Anda dapat meminta data Anda dihapus melalui peneliti. |

> **Catatan penting:** sistem tidak menampilkan skor numerik kuesioner SUS Anda. Ini disengaja agar tanggapan Anda murni mencerminkan persepsi, bukan disesuaikan dengan target skor tertentu.

---

## 7. Cara Melaporkan Bug atau Kendala

**Hubungi peneliti secara langsung** melalui kontak yang Anda terima saat undangan (WhatsApp atau email). Tidak ada formulir atau sistem ticketing yang perlu Anda akses.

Saat melapor, mohon sertakan:

- Nama pengguna yang Anda pakai saat menemukan bug.
- Halaman tempat masalah muncul (Beranda / Simulasi / Hasil / Profil / Feedback Penguji).
- Apa yang Anda lakukan tepat sebelum masalah muncul.
- Apa yang terjadi vs. apa yang Anda harapkan.
- (Opsional) tangkapan layar atau rekaman singkat.
- Waktu kira-kira saat masalah muncul (WIB).

Peneliti akan merespons dalam 1×24 jam.

---

## 8. Catatan Teknis Singkat

- **Browser disarankan:** Chrome 100+, Edge 100+, Firefox 102+, atau Safari 15+.
- **Mobile:** sistem mendukung tampilan ponsel; rotasikan ke landscape bila grafik terlihat sempit.
- **Sesi tidak tersimpan:** jika Anda menutup tab di tengah simulasi (sebelum putaran ke-14 selesai), data putaran tersebut **tidak** akan tercatat. Mohon selesaikan satu sesi penuh sebelum keluar.
- **Lupa kata sandi:** hubungi peneliti — saat ini belum ada alur reset kata sandi mandiri.

---

## 9. Catatan Validitas Translasi SUS

Kuesioner usability pada halaman *Feedback Penguji* menggunakan terjemahan Bahasa Indonesia yang **belum tervalidasi secara formal**. Pada saat fase UAT diluncurkan, peneliti belum memperoleh referensi terjemahan SUS Indonesia yang telah lulus uji reliabilitas (mis. Cronbach α) dan validitas konstruk pada populasi Indonesia. Tanggapan Anda karenanya akan ditafsirkan secara **eksploratif** — sebagai sinyal kualitatif, bukan benchmark internasional.

Jika di kemudian hari ditemukan terjemahan SUS Indonesia yang tervalidasi (mis. Sharfina & Santoso, 2016, atau versi yang lebih baru), peneliti akan memutakhirkan terjemahan dan mendokumentasikan perubahan di repositori sebelum laporan akhir diserahkan.

---

## 10. Bantuan & Etika Partisipasi

- **Berhenti kapan saja.** Anda dapat berhenti sewaktu-waktu tanpa konsekuensi apa pun.
- **Tidak ada paksaan.** Pertanyaan terbuka bersifat opsional; lewati bila tidak ingin menjawab.
- **Hubungi peneliti** bila ada kendala selama pengujian, melalui WhatsApp atau email yang diberikan saat undangan.

**Selamat menguji, dan terima kasih atas waktu serta kontribusi Anda.**

---

*Dokumen ini bagian dari thesis "Sistem Deteksi dan Mitigasi Bias Perilaku bagi Investor Ritel di Pasar Modal Indonesia" — Arvyno Pranata Limahardja (NIM 18222007), Institut Teknologi Bandung, 2026.*
