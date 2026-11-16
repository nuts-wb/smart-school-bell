# Smart School Bell – Management System

Aplikasi web pengelola bel sekolah. Frontend: HTML, CSS, Bootstrap, JavaScript. Backend: Python Flask. Database: SQLite.

## Menjalankan di Visual Studio Code

1. Buka folder ini di VS Code, lalu buka terminal (`Ctrl+``).
2. Buat lingkungan Python dan pasang kebutuhan:
   ```
   python -m venv venv
   venv\Scripts\activate          (Windows)   |   source venv/bin/activate   (macOS/Linux)
   pip install -r requirements.txt
   ```
3. Buat akun pertama (akan menjadi **petugas utama**):
   ```
   python manage.py create-user
   ```
   Akun berikutnya otomatis berperan *petugas* (menerima notifikasi serah-terima). Lupa password: `python manage.py reset-password`.
4. Jalankan: `python app.py` lalu buka http://127.0.0.1:5000
5. (Opsional) Buat ulang nada bel pengganti: `python tools/generate_sounds.py`

Koneksi internet dibutuhkan saat membuka aplikasi karena Bootstrap, Bootstrap Icons, dan font Google (Poppins, Playfair Display, Crimson Pro) dimuat dari CDN. Tanpa internet, aplikasi tetap berfungsi tetapi ikon dan font tampil seadanya.

## Struktur project

```
app.py              Flask: rute halaman + API, logika bel & pengingat
database.py         Skema SQLite + data awal
i18n.py             Teks Indonesia / English
manage.py           Buat akun, reset password
templates/          HTML (Jinja)
static/css/         style.css
static/js/          app.js (jam, penjadwal, notifikasi), modal-shim.js
static/img/         foto sekolah, logo, maskot, ikon (diekstrak dari PDF desain)
static/sounds/bel/  nada bel (WAV)      static/sounds/lagu/  taruh MP3 lagu di sini
data/               smartbell.db (dibuat otomatis)
```

Tabel: `users`, `app_settings`, `sound_settings`, `special_bells`, `schedule`, `special_schedules`, `bell_log` (riwayat bel), `reminder_log` (status pengingat).

## Cara kerja bel dan pengingat

- Bel berbunyi dari **browser yang sedang membuka aplikasi** (tab harus terbuka). Aplikasi tidak berjalan di latar belakang.
- Browser sering memblokir suara otomatis sebelum pengguna mengetuk halaman. Setelah membuka aplikasi, klik/ketuk layar sekali. Jika bel tertahan, muncul pesan "Ketuk layar untuk membunyikan bel" dan bel dibunyikan saat layar diketuk.
- Notifikasi muncul sebagai kartu di dalam aplikasi, dan sebagai notifikasi sistem bila tab sedang tidak aktif dan izin notifikasi diberikan. Tidak ada Web Push, jadi tidak ada notifikasi saat browser ditutup.
- Pengingat per bel: (1) N menit sebelum bel, (2) saat waktu bel, (3) +2 menit jika bel belum dijalankan (petugas utama), (4) +3 menit diserahkan ke petugas lain (akun lain yang membuka aplikasi). Status dihitung server dan disimpan di `reminder_log`.
- Hanya satu perangkat yang membunyikan bel otomatis per jadwal: perangkat yang pertama mencatatnya.

## Keputusan yang saya ambil karena desain belum menjelaskan (mohon konfirmasi)

1. **Mode Otomatis/Manual**: ditentukan oleh tombol "suara bel aktif" di header. Aktif = Otomatis (bel berbunyi sendiri), nonaktif = Manual (teks "suara bel nonaktif"; hanya pengingat yang jalan). Di kedua mode, tombol jenis bel menampilkan dialog konfirmasi.
2. **Bel Khusus** dari menu Bunyikan Bel membuka daftar kegiatan (sesuai panah di desain). Bel khusus dibunyikan otomatis menurut jadwalnya; tombol ▶ di detail hanya untuk mencoba suara.
3. **Jadwal jam pelajaran** berlaku Senin–Jumat. Daftar awal kosong; isi lewat + Tambah atau Unggah Data (PDF teks dengan baris seperti `07.00 Masuk Sekolah bel masuk`).
4. **Jadwal Khusus**: pada rentang tanggalnya, jadwal biasa diganti dua bel: bel masuk di jam mulai dan bel pulang di jam selesai.
5. **Kegiatan Bel Khusus bawaan** (5 kegiatan dari desain) diset jam 10.00 dan **nonaktif**; aktifkan dan atur sesuai kebutuhan. Lagu belum disertakan: letakkan MP3 di `static/sounds/lagu/` (mis. `indonesia_raya.mp3`). Bila file tidak ada, dibunyikan nada bel pengganti.
6. **Nada bel** adalah suara sintetis pengganti (`static/sounds/bel/`). Ganti dengan rekaman asli memakai nama file yang sama.
7. **Pengaturan Suara**: dropdown memilih jenis bel yang volumenya diatur; "Suara Notifikasi" berlaku untuk semua.
8. **Dark mode** memakai palet buatan saya (desain tidak punya), dan teks **English** terjemahan saya.
9. Font label serif memakai Crimson Pro (perkiraan dari gambar); jam memakai Playfair Display; judul memakai Poppins.

## Perbedaan dengan desain Figma

- Bar status ponsel (9:41, sinyal, baterai) tidak dibuat karena itu bagian perangkat.
- Elemen yang tidak ada di desain tetapi dibutuhkan agar fitur berfungsi, dibuat dengan gaya yang sama: formulir tambah/edit jadwal dan jadwal khusus (dialog), pesan kesalahan login, teks "Belum ada jadwal bel", pesan kilat "Tersimpan", dan penanda bahasa terpilih.
- Di desktop, aplikasi tampil selebar layar ponsel (390 px) di tengah halaman.
- Tombol "Unggah Data" memakai teks dari halaman Beranda (halaman menu memakai "Unggah PDF").
