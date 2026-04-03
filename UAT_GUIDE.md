# Panduan Penggunaan Sistem CDT Deteksi Bias Investasi
## Untuk Peserta User Acceptance Test (UAT)

---

## 1. Persyaratan Sistem

Sebelum memulai, pastikan komputer kamu memiliki:
- **Python 3.11 atau lebih baru**
  - Cek dengan membuka Terminal/Command Prompt dan ketik: `python --version`
- **Koneksi internet** (untuk mengunduh dependensi saat pertama kali setup)

---

## 2. Instalasi (Hanya Dilakukan Sekali)

### Cara Mudah (Satu Perintah)

Buka Terminal / Command Prompt, masuk ke folder proyek, lalu jalankan:

```bash
bash setup.sh
```

### Cara Manual (Jika Cara di Atas Gagal)

```bash
pip install -r requirements.txt
```

---

## 3. Menjalankan Aplikasi

Setelah instalasi selesai, jalankan:

```bash
streamlit run app.py
```

Aplikasi akan terbuka otomatis di browser kamu di alamat `http://localhost:8501`.
Jika tidak terbuka otomatis, buka browser dan ketik alamat tersebut secara manual.

---

## 4. Alur Penggunaan Aplikasi

### Langkah 1 — Baca Informasi Penelitian & Berikan Persetujuan

Halaman pertama yang muncul adalah **Informasi & Persetujuan**.

1. Baca penjelasan tentang tujuan penelitian dan data yang dikumpulkan.
2. Centang kotak **"Saya memahami dan menyetujui partisipasi dalam penelitian ini"**.
3. Klik tombol **"Lanjut ke Beranda →"**.

> **Catatan:** Kamu tidak bisa mengakses fitur lain sebelum memberikan persetujuan.

### Langkah 2 — Login / Daftar Akun

Di halaman **Beranda**:

1. Masukkan **nama atau alias** (boleh nama panggilan, bukan nama asli).
   - Contoh: "Budi123", "InvestorPemula"
   - Minimal 2 karakter, hanya huruf, angka, dan spasi.
2. Pilih **tingkat pengalaman investasi** kamu (Pemula / Menengah / Berpengalaman).
3. Klik **"Masuk →"**.

> Jika alias sudah pernah digunakan, sistem akan langsung login sebagai pengguna yang ada.
> Kamu bisa melanjutkan sesi yang sebelumnya.

### Langkah 3 — Menjalankan Simulasi Investasi

Di halaman **Simulasi Investasi**, kamu akan bermain sebagai investor selama **14 putaran**.

#### Penjelasan Simulasi
- Setiap **putaran** mewakili satu hari perdagangan menggunakan data historis nyata.
- Tersedia **6 saham IDX**: BBCA, TLKM, ANTM, GOTO, UNVR, BBRI.
- Di setiap putaran, kamu memutuskan untuk setiap saham: **Tahan / Beli / Jual**.

#### Cara Bermain
1. Lihat **grafik harga** dan indikator teknikal (MA5, MA20, Tren) untuk setiap saham.
2. Pilih keputusan di bawah setiap kartu saham:
   - **Tahan** — tidak melakukan transaksi untuk saham ini
   - **Beli** — masukkan jumlah lembar yang ingin dibeli
   - **Jual** — masukkan jumlah lembar yang ingin dijual
3. Setelah semua saham ditentukan, klik **"✅ Eksekusi Keputusan"**.
4. Lanjutkan hingga putaran 14 selesai.

#### Tips Membaca Grafik
- **Garis biru** = Harga penutupan harian
- **Garis oranye putus-putus (MA5)** = Rata-rata harga 5 hari terakhir
- **Garis hijau titik-titik (MA20)** = Rata-rata harga 20 hari terakhir
- Jika harga di **atas MA** → tren naik (bullish)
- Jika harga di **bawah MA** → tren turun (bearish)
- **Modal awal**: Rp 10.000.000

### Langkah 4 — Lihat Hasil Analisis

Setelah sesi selesai, klik **"Lihat Hasil Analisis →"** atau pilih **"Hasil Analisis & Umpan Balik"** di menu samping.

Kamu akan melihat **3 kartu bias**:

| Bias | Apa artinya? |
|------|-------------|
| **Efek Disposisi** | Apakah kamu menjual saham untung terlalu cepat? |
| **Overconfidence** | Apakah kamu terlalu sering trading dengan hasil buruk? |
| **Loss Aversion** | Apakah kamu menahan saham rugi terlalu lama? |

Setiap kartu menampilkan:
- **Tingkat keparahan**: Tidak Ada / Ringan / Sedang / Berat
- **Penjelasan** tentang perilakumu di sesi ini
- **Rekomendasi** untuk memperbaiki keputusan investasi

### Langkah 5 — Lihat Profil Kognitif

Di halaman **Profil Kognitif Saya**:
- **Radar Chart** — visualisasi intensitas ketiga bias (skala 0–1)
- **Indeks Stabilitas** — seberapa konsisten perilakumu antar sesi (0 = sangat berubah-ubah, 1 = sangat konsisten)
- **Preferensi Risiko** — kecenderungan memilih saham berisiko tinggi atau rendah
- **Grafik riwayat** — perubahan setiap bias dari sesi ke sesi

### Langkah 6 — Ulangi untuk 2-3 Sesi

Untuk hasil yang lebih akurat, selesaikan **minimal 2-3 sesi simulasi**. Profil CDT kamu akan diperbarui secara otomatis setelah setiap sesi.

Untuk memulai sesi baru: klik **"Simulasi Investasi"** di menu samping, lalu klik tombol reset jika tersedia.

---

## 5. FAQ / Troubleshooting

**Q: Aplikasi tidak terbuka di browser?**
A: Buka browser dan ketik `http://localhost:8501` secara manual.

**Q: Muncul pesan error saat instalasi?**
A: Pastikan Python 3.11+ terinstal. Coba jalankan `pip install -r requirements.txt` secara manual.

**Q: Saya lupa nama alias saya?**
A: Coba beberapa variasi nama yang kamu pakai. Jika tidak berhasil, daftar dengan alias baru — data lama tetap tersimpan.

**Q: Aplikasi tiba-tiba berhenti/error saat simulasi?**
A: Refresh browser (F5). Sesi tidak akan hilang karena sudah tersimpan di database.

**Q: Bagaimana cara keluar dari aplikasi?**
A: Tutup tab browser, lalu tekan Ctrl+C di Terminal untuk menghentikan server.

**Q: Data saya aman?**
A: Semua data disimpan secara lokal di komputer ini. Tidak ada data yang dikirim ke server eksternal.

---

## 6. Kontak

Jika kamu mengalami masalah teknis yang tidak tercantum di atas, hubungi:

**Arvyno Pranata Limahardja**
Mahasiswa Sistem dan Teknologi Informasi ITB
NIM: 18222007
