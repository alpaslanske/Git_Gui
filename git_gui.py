#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont, QColor, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QFileDialog,
    QInputDialog, QMessageBox, QTextEdit, QFrame, QSizePolicy, QComboBox
)

from git_motoru import GitMotoru
from lang import METINLER

PROJE_ANA_DIZINI = Path(os.path.realpath(__file__)).parent
os.chdir(PROJE_ANA_DIZINI)

class ModernButton(QPushButton):
    """Hover efektli modern buton sınıfı"""
    def __init__(self, text, bg_color):
        super().__init__(text)
        self.bg_color = bg_color
        color_obj = QColor(bg_color)
        h, s, l, a = color_obj.getHsl()
        l = min(255, int(l * 1.15))
        self.hover_color = QColor.fromHsl(h, s, l, a).name()
        self.setStyleSheet(self._get_style(self.bg_color))
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        font = self.font()
        font.setBold(True)
        font.setPointSize(10)
        self.setFont(font)

    def _get_style(self, color):
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px;
            }}
            QPushButton:hover {{
                background-color: {self.hover_color};
            }}
            QPushButton:disabled {{
                background-color: #3f3f46;
                color: #71717a;
            }}
        """

    def update_color(self, new_color):
        self.bg_color = new_color
        self.setStyleSheet(self._get_style(new_color))

class GitKonsolu(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.lbl_baslik = QLabel("💻 Git Konsolu (Log)")

        baslik_font = self.lbl_baslik.font()
        baslik_font.setBold(True)
        baslik_font.setPointSize(11)
        self.lbl_baslik.setFont(baslik_font)

        self.lbl_baslik.setStyleSheet("color: #f5f5f7;")
        layout.addWidget(self.lbl_baslik)

        self.txt_konsol = QTextEdit()
        self.txt_konsol.setReadOnly(True)
        self.txt_konsol.setStyleSheet("""
            QTextEdit {
                background-color: #0c0c0d;
                color: #4ade80;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                font-family: Consolas;
                font-size: 13px;
                padding: 5px;
            }
        """)
        self.txt_konsol.setMinimumHeight(100)
        self.txt_konsol.setMaximumHeight(120)
        layout.addWidget(self.txt_konsol)

    def yaz(self, metin):
        self.txt_konsol.append(metin)
        self.txt_konsol.ensureCursorVisible()

class BasitGitGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_file = PROJE_ANA_DIZINI / "data" / "settings.json"
        self.aktif_lang = "tr"
        self.varsayilan_arama_dizini = ""
        self.github_kullanici_adi = ""
        self.resize(650, 800)
        self.setStyleSheet("QMainWindow { background-color: #1e1e24; }")

        sistem_ikonu = QIcon.fromTheme("git", QIcon.fromTheme("vcs-git", QIcon.fromTheme("git-gui")))
        if sistem_ikonu.isNull():
            icon_path = PROJE_ANA_DIZINI / "icon.png"
            if icon_path.exists():
                sistem_ikonu = QIcon(str(icon_path))
        self.setWindowIcon(sistem_ikonu)

        self.motor = GitMotoru()
        self.setup_ui()
        self.motor.log_callback = self.konsol.yaz

        self.ayarlari_yukle()
        self.metinleri_guncelle()
        self.konsol.yaz(self.t("konsol_hazir"))

    def t(self, anahtar):
        return METINLER[self.aktif_lang].get(anahtar, anahtar)

    def ayarlari_yukle(self):
        if not self.settings_file.exists():
            self.set_buttons_state(False)
            return

        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                ayarlar = json.load(f)

            kayitli_dil = ayarlar.get("language", "tr")
            self.aktif_lang = kayitli_dil
            self.combo_lang.blockSignals(True)
            self.combo_lang.setCurrentIndex(1 if kayitli_dil == "en" else 0)
            self.combo_lang.blockSignals(False)

            self.varsayilan_arama_dizini = ayarlar.get("default_search_path", "")
            self.github_kullanici_adi = ayarlar.get("github_username", "")

            if not self.github_kullanici_adi:
                self.github_kullanici_adi = self.otomatik_kullanici_adi_bul()

            son_klasor = ayarlar.get("last_repo_path", "")
            if son_klasor and Path(son_klasor).exists():
                self.motor.repo_path = son_klasor
                self.butonlari_guncelle()
            else:
                self.set_buttons_state(False)
        except Exception as e:
            print(f"Ayar yükleme hatası: {e}")
            self.set_buttons_state(False)

    def otomatik_kullanici_adi_bul(self):
        try:
            res = subprocess.run(["gh", "api", "user", "-q", ".login"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

        try:
            res = subprocess.run(["git", "config", "--get", "github.user"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

        return ""

    def ayarlari_kaydet(self):
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            ayarlar = {}
            if self.settings_file.exists():
                try:
                    with open(self.settings_file, "r", encoding="utf-8") as f:
                        ayarlar = json.load(f)
                except Exception:
                    ayarlar = {}

            ayarlar["language"] = self.aktif_lang
            ayarlar["last_repo_path"] = self.motor.repo_path
            ayarlar["default_search_path"] = ayarlar.get("default_search_path", self.varsayilan_arama_dizini)
            ayarlar["github_username"] = self.github_kullanici_adi

            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(ayarlar, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Ayar kaydetme hatası: {e}")

    def kullanici_adindan_url_olustur(self, repo_adi=""):
        if not self.github_kullanici_adi:
            otomatik = self.otomatik_kullanici_adi_bul()
            kullanici, ok = QInputDialog.getText(
                self,
                self.t("dlg_username_title"),
                self.t("dlg_username_msg"),
                text=otomatik
            )
            if ok and kullanici.strip():
                self.github_kullanici_adi = kullanici.strip()
                self.ayarlari_kaydet()
            else:
                return ""

        if not repo_adi and self.motor.repo_path:
            repo_adi = os.path.basename(os.path.abspath(self.motor.repo_path))

        return f"https://github.com/{self.github_kullanici_adi}/{repo_adi}.git"

    def lang_degistir(self, index):
        self.aktif_lang = "tr" if index == 0 else "en"
        self.metinleri_guncelle()
        self.ayarlari_kaydet()

    def metinleri_guncelle(self):
        self.setWindowTitle(self.t("pencere_baslik"))
        self.btn_sec.setText(self.t("btn_sec"))
        self.btn_login.setText(self.t("btn_login"))
        self.btn_init.setText(self.t("btn_init"))
        self.btn_commit.setText(self.t("btn_commit"))
        self.btn_rollback.setText(self.t("btn_rollback"))
        self.btn_delete_commit.setText(self.t("btn_delete_commit"))
        self.btn_create_repo.setText(self.t("btn_create_repo"))
        self.btn_delete_repo.setText(self.t("btn_delete_repo"))
        self.btn_fetch.setText(self.t("btn_fetch"))
        self.btn_push.setText(self.t("btn_push"))
        self.lbl_gecmis_baslik.setText(self.t("lbl_gecmis"))
        self.konsol.lbl_baslik.setText(self.t("lbl_konsol"))

        if not self.motor.repo_path:
            self.lbl_durum.setText(self.t("lbl_durum_bekleniyor"))
        else:
            self.butonlari_guncelle()

    def setup_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # Üst Çubuk (Banner + Dil Seçici)
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.lbl_banner = QLabel("")

        banner_font = self.lbl_banner.font()
        banner_font.setBold(True)
        banner_font.setPointSize(10)
        self.lbl_banner.setFont(banner_font)

        self.lbl_banner.setAlignment(Qt.AlignCenter)
        self.lbl_banner.hide()
        top_bar.addWidget(self.lbl_banner, 1)

        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["🇹🇷 TR", "🇬🇧 EN"])
        self.combo_lang.setFixedWidth(100)
        self.combo_lang.setStyleSheet("""
            QComboBox { background-color: #3f3f46; color: white; padding: 6px; border-radius: 4px; }
            QComboBox QAbstractItemView { background-color: #2a2a32; color: white; selection-background-color: #007acc; selection-color: white; }
        """)
        self.combo_lang.currentIndexChanged.connect(self.lang_degistir)
        top_bar.addWidget(self.combo_lang, 0)
        main_layout.addLayout(top_bar)

        # Klasör Seçim Çerçevesi
        frame_top = QFrame()
        frame_top.setStyleSheet("QFrame { background-color: #2a2a32; border: 1px solid #3f3f46; border-radius: 6px; }")
        top_layout = QVBoxLayout(frame_top)

        self.btn_sec = ModernButton("", "#007acc")
        self.btn_sec.clicked.connect(self.klasor_sec)
        top_layout.addWidget(self.btn_sec)

        self.lbl_durum = QLabel("")

        durum_font = self.lbl_durum.font()
        durum_font.setPointSize(10)
        self.lbl_durum.setFont(durum_font)

        self.lbl_durum.setStyleSheet("color: #a0a0ab; border: none;")
        self.lbl_durum.setAlignment(Qt.AlignCenter)
        top_layout.addWidget(self.lbl_durum)
        main_layout.addWidget(frame_top)

        # 1. SATIR: Yerel İşlemler (Init & Commit)
        yerel_layout_1 = QHBoxLayout()
        yerel_layout_1.setSpacing(10)

        self.btn_init = ModernButton("", "#28a745")
        self.btn_init.clicked.connect(self.git_init)
        yerel_layout_1.addWidget(self.btn_init)

        self.btn_commit = ModernButton("", "#d97706")
        self.btn_commit.clicked.connect(self.git_commit)
        yerel_layout_1.addWidget(self.btn_commit)

        main_layout.addLayout(yerel_layout_1)

        # 2. SATIR: Geçmiş Yönetimi (Önceki Sürüme Geri Dön & Commit Sil)
        yerel_layout_2 = QHBoxLayout()
        yerel_layout_2.setSpacing(10)

        self.btn_rollback = ModernButton("", "#dc3545")
        self.btn_rollback.clicked.connect(self.git_rollback)
        yerel_layout_2.addWidget(self.btn_rollback)

        self.btn_delete_commit = ModernButton("", "#b91c1c")
        self.btn_delete_commit.clicked.connect(self.git_commit_sil)
        yerel_layout_2.addWidget(self.btn_delete_commit)

        main_layout.addLayout(yerel_layout_2)

        # 3. SATIR: GitHub Giriş ve Depo Yönetimi (Login, Yeni Depo, Depo Sil)
        github_layout = QHBoxLayout()
        github_layout.setSpacing(10)

        self.btn_login = ModernButton("", "#0284c7")
        self.btn_login.clicked.connect(self.github_login)
        github_layout.addWidget(self.btn_login)

        self.btn_create_repo = ModernButton("", "#0f766e")
        self.btn_create_repo.clicked.connect(self.github_repo_olustur)
        github_layout.addWidget(self.btn_create_repo)

        self.btn_delete_repo = ModernButton("", "#991b1b")
        self.btn_delete_repo.clicked.connect(self.repo_sil)
        github_layout.addWidget(self.btn_delete_repo)

        main_layout.addLayout(github_layout)

        # 4. SATIR: Senkronizasyon (Güncellik Kontrolü & Push)
        sync_layout = QHBoxLayout()
        sync_layout.setSpacing(10)

        self.btn_fetch = ModernButton("", "#28a745")
        self.btn_fetch.clicked.connect(self.git_fetch_kontrol)
        sync_layout.addWidget(self.btn_fetch)

        self.btn_push = ModernButton("", "#8b5cf6")
        self.btn_push.clicked.connect(self.git_push)
        sync_layout.addWidget(self.btn_push)

        main_layout.addLayout(sync_layout)

        # Geçmiş Listesi Başlığı
        self.lbl_gecmis_baslik = QLabel("")

        gecmis_font = self.lbl_gecmis_baslik.font()
        gecmis_font.setBold(True)
        gecmis_font.setPointSize(11)
        self.lbl_gecmis_baslik.setFont(gecmis_font)

        self.lbl_gecmis_baslik.setStyleSheet("color: #f5f5f7;")
        main_layout.addWidget(self.lbl_gecmis_baslik)

        # Geçmiş Listesi (QListWidget)
        self.listbox_gecmis = QListWidget()
        self.listbox_gecmis.setStyleSheet("""
            QListWidget { background-color: #2a2a32; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 4px; font-size: 13px; padding: 5px; }
            QListWidget::item:selected { background-color: #007acc; color: white; }
        """)
        main_layout.addWidget(self.listbox_gecmis, 1)

        # Konsol
        self.konsol = GitKonsolu()
        main_layout.addWidget(self.konsol)

        self.setCentralWidget(central_widget)

    def set_buttons_state(self, is_git):
        self.btn_init.setEnabled(not is_git)
        self.btn_commit.setEnabled(is_git)
        self.btn_rollback.setEnabled(is_git)
        self.btn_delete_commit.setEnabled(is_git)
        self.btn_create_repo.setEnabled(is_git)
        self.btn_delete_repo.setEnabled(is_git)
        self.btn_fetch.setEnabled(is_git)
        self.btn_push.setEnabled(is_git)

    def butonlari_guncelle(self):
        if not self.motor.repo_path:
            self.lbl_banner.hide()
            return

        if self.motor.set_path(self.motor.repo_path):
            self.set_buttons_state(True)
            self.gecmisi_yukle()

            is_clean, status_text = self.motor.get_status()
            self.konsol.yaz("> git status")
            self.konsol.yaz(status_text)

            self.lbl_banner.show()
            if is_clean:
                self.lbl_banner.setStyleSheet("QLabel { background-color: #22c55e; color: white; border-radius: 4px; padding: 6px; }")
                self.lbl_banner.setText(self.t("banner_clean"))
                self.lbl_durum.setStyleSheet("color: #4ade80; border: none;")
                self.lbl_durum.setText(self.t("git_aktif") + self.motor.repo_path)
            else:
                self.lbl_banner.setStyleSheet("QLabel { background-color: #ef4444; color: white; border-radius: 4px; padding: 6px; }")
                self.lbl_banner.setText(self.t("banner_dirty"))
                self.lbl_durum.setStyleSheet("color: #fbbf24; border: none;")
                self.lbl_durum.setText(self.t("git_aktif") + self.motor.repo_path)
        else:
            self.lbl_banner.hide()
            self.lbl_durum.setStyleSheet("color: #f87171; border: none;")
            self.lbl_durum.setText(self.t("git_degil") + self.motor.repo_path)
            self.set_buttons_state(False)
            self.listbox_gecmis.clear()

    def git_fetch_kontrol(self):
        self.lbl_durum.setText(self.t("msg_fetch_bekle"))
        QApplication.processEvents()

        basarili, sonuc = self.motor.git_fetch_kontrol()
        if not basarili:
            if sonuc == "no_remote":
                QMessageBox.information(self, self.t("hata"), self.t("fetch_no_remote"))
            else:
                QMessageBox.critical(self, self.t("hata"), str(sonuc))
            self.butonlari_guncelle()
            return

        ileri = sonuc["ileri"]
        geri = sonuc["geri"]

        if ileri == 0 and geri == 0:
            QMessageBox.information(self, self.t("basarili"), self.t("fetch_guncel"))
        elif ileri == 0 and geri > 0:
            QMessageBox.warning(self, self.t("basarili"), self.t("fetch_geride").format(geri))
        elif ileri > 0 and geri == 0:
            QMessageBox.information(self, self.t("basarili"), self.t("fetch_ileride").format(ileri))
        else:
            QMessageBox.warning(self, self.t("basarili"), self.t("fetch_farkli").format(ileri, geri))

        self.butonlari_guncelle()

    def gecmisi_yukle(self):
        self.listbox_gecmis.clear()
        commitler = self.motor.gecmis_getir()
        if commitler is None:
            self.listbox_gecmis.addItem(self.t("gecmis_hata"))
            return
        if not commitler:
            self.listbox_gecmis.addItem(self.t("gecmis_bos"))
            return

        for c in commitler:
            kisa_hash = c["hash"]
            tarih = c["tarih"]
            mesaj = c["mesaj"]
            self.listbox_gecmis.addItem(f" └─ [{kisa_hash}] {tarih} │ {mesaj}")

    def klasor_sec(self):
        if self.motor.repo_path and Path(self.motor.repo_path).exists():
            baslangic = self.motor.repo_path
        elif self.varsayilan_arama_dizini and Path(self.varsayilan_arama_dizini).exists():
            baslangic = self.varsayilan_arama_dizini
        else:
            baslangic = str(Path.home())

        secilen = QFileDialog.getExistingDirectory(self, self.t("secim_penceresi"), baslangic)
        if secilen:
            self.motor.repo_path = secilen
            self.konsol.yaz(self.t("klasor_secildi") + secilen)
            self.butonlari_guncelle()
            self.ayarlari_kaydet()

    def github_repo_olustur(self):
        if not self.motor.repo_path:
            return

        varsayilan_isim = os.path.basename(os.path.abspath(self.motor.repo_path))
        repo_adi, ok = QInputDialog.getText(self, self.t("dlg_repo_name_title"), self.t("dlg_repo_name_msg"), text=varsayilan_isim)
        if not (ok and repo_adi.strip()):
            return

        repo_adi = repo_adi.strip()
        turler = ["public", "private"]
        tur, ok = QInputDialog.getItem(self, self.t("dlg_visibility_title"), self.t("dlg_visibility_msg"), turler, 0, False)
        if not ok:
            return

        self.lbl_durum.setText(self.t("msg_creating_repo"))
        QApplication.processEvents()

        basarili, cikti = self.motor.github_repo_olustur(repo_adi, tur)
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_repo_created").format(repo_adi))
            self.butonlari_guncelle()
        else:
            QMessageBox.critical(self, self.t("hata"), self.t("err_repo_create").format(cikti))
            self.konsol.yaz(f"HATA: {cikti}")

    def github_login(self):
        try:
            self.konsol.yaz(self.t("msg_baglaniliyor"))
            QApplication.processEvents()

            github_env = os.environ.copy()
            github_env["GH_PROMPT_DISABLED"] = "1"

            process = subprocess.Popen(
                ["gh", "auth", "login", "--web", "--git-protocol", "https"],
                env=github_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )

            kod = None
            for _ in range(10):
                line = process.stdout.readline()
                if not line:
                    break
                if "one-time code" in line:
                    kod = line.split(":")[-1].strip()
                    break

            if kod:
                QApplication.clipboard().setText(kod)
                QMessageBox.information(self, self.t("github_girisi"), self.t("kod_kopyalandi").format(kod))
                webbrowser.open("https://github.com")
                self.lbl_durum.setText(self.t("onay_bekleniyor"))
                self.konsol.yaz(self.t("log_onay_bekleniyor").format(kod))

                process.wait()

                if process.returncode == 0:
                    subprocess.run(["gh", "auth", "setup-git"], check=True)
                    yeni_user = self.otomatik_kullanici_adi_bul()
                    if yeni_user:
                        self.github_kullanici_adi = yeni_user
                        self.ayarlari_kaydet()

                    QMessageBox.information(self, self.t("basarili"), self.t("msg_login_basarili"))
                    self.lbl_durum.setStyleSheet("color: #4ade80; border: none;")
                    self.lbl_durum.setText(self.t("lbl_github_baglandi"))
                    self.konsol.yaz(self.t("log_baglanti_tamam"))
                else:
                    QMessageBox.critical(self, self.t("hata"), self.t("msg_onay_hata"))
                    self.konsol.yaz(self.t("log_onay_hata"))
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_kod_alinamadi"))
                process.kill()

        except FileNotFoundError:
            QMessageBox.warning(self, self.t("eksik_paket"), self.t("msg_eksik_paket"))
        except Exception as e:
            QMessageBox.critical(self, self.t("hata"), self.t("beklenmeyen_hata").format(e))

    def git_init(self):
        if self.motor.git_init():
            QMessageBox.information(self, self.t("basarili"), self.t("msg_init_basarili"))
            self.butonlari_guncelle()
            self.ayarlari_kaydet()

    def git_commit(self):
        commit_mesaji, ok = QInputDialog.getText(self, self.t("commit_baslik"), self.t("commit_soru"))
        if ok and commit_mesaji.strip():
            if self.motor.git_commit(commit_mesaji):
                QMessageBox.information(self, self.t("basarili"), self.t("msg_commit_basarili"))
                self.butonlari_guncelle()
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_commit_hata"))

    def git_push(self):
        try:
            if not self.motor.has_remotes():
                otomatik_url = self.kullanici_adindan_url_olustur()
                remote_url, ok = QInputDialog.getText(
                    self,
                    self.t("github_link_baslik"),
                    self.t("github_link_soru"),
                    text=otomatik_url
                )
                if ok and remote_url.strip():
                    self.motor.add_remote(remote_url.strip())
                else:
                    return

            self.lbl_durum.setStyleSheet("color: #60a5fa; border: none;")
            self.lbl_durum.setText(self.t("msg_push_bekle"))
            QApplication.processEvents()

            aktif_branch = self.motor.git_push()
            if aktif_branch:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_push_basarili").format(aktif_branch))
        except Exception as e:
            hata_mesaji = str(e)
            # Hem normal ret durumları hem de 'stale info' (baştan kurulan repo durumu) için force-push yeteneği
            tetikleyiciler = ["non-fast-forward", "Updates were rejected", "Güncellemeler reddedildi", "uzak konum karşıtından geride", "stale info"]
            if any(kelime in hata_mesaji for kelime in tetikleyiciler):
                cevap = QMessageBox.warning(
                    self,
                    self.t("dlg_force_push_title"),
                    self.t("dlg_force_push_msg"),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if cevap == QMessageBox.Yes:
                    try:
                        self.motor.git_push(force=True)
                        QMessageBox.information(self, self.t("basarili"), self.t("msg_force_push_basarili"))
                    except Exception as force_err:
                        QMessageBox.critical(self, self.t("hata"), f"Force push başarısız oldu:\n{force_err}")
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_push_hata").format(hata_mesaji))
        finally:
            self.butonlari_guncelle()

    def git_rollback(self):
        commitler = self.motor.gecmis_getir(adet=30)
        if not commitler:
            QMessageBox.warning(self, self.t("hata"), self.t("gecmis_bos"))
            return

        secenekler = [f"[{c['hash']}] {c['tarih']} - {c['mesaj']}" for c in commitler]
        secilen_metin, ok = QInputDialog.getItem(self, self.t("dlg_rollback_title"), self.t("dlg_rollback_msg"), secenekler, 0, False)
        if not ok or not secilen_metin:
            return

        hedef_hash = secilen_metin.split("]")[0].replace("[", "").strip()

        cevap = QMessageBox.warning(self, self.t("emin_misiniz"), f"{secilen_metin}\n\n{self.t('rollback_soru')}", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if cevap == QMessageBox.Yes:
            if self.motor.git_rollback(hedef_hash):
                QMessageBox.information(self, self.t("basarili"), self.t("msg_rollback_basarili"))
                self.butonlari_guncelle()
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_rollback_hata"))

    def git_commit_sil(self):
        commitler = self.motor.gecmis_getir(adet=30)
        if not commitler:
            QMessageBox.warning(self, self.t("hata"), self.t("gecmis_bos"))
            return

        secenekler = [f"[{c['hash']}] {c['tarih']} - {c['mesaj']}" for c in commitler]
        secilen_metin, ok = QInputDialog.getItem(
            self,
            self.t("dlg_delete_commit_title"),
            self.t("dlg_delete_commit_msg"),
            secenekler,
            0,
            False
        )
        if not ok or not secilen_metin:
            return

        hedef_hash = secilen_metin.split("]")[0].replace("[", "").strip()

        cevap = QMessageBox.warning(
            self,
            self.t("emin_misiniz"),
            f"{secilen_metin}\n\n{self.t('delete_commit_soru')}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if cevap == QMessageBox.Yes:
            basarili, sebep = self.motor.git_commit_sil(hedef_hash)
            if basarili:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_delete_commit_basarili"))
            else:
                if sebep == "root_commit":
                    QMessageBox.warning(self, self.t("hata"), self.t("err_root_commit_silinemez"))
                elif sebep == "conflict":
                    QMessageBox.warning(self, self.t("hata"), self.t("msg_delete_commit_conflict"))
                else:
                    QMessageBox.critical(self, self.t("hata"), self.t("msg_delete_commit_hata"))
            self.butonlari_guncelle()

    def repo_sil(self):
        if not self.motor.repo_path:
            return

        repo_adi = os.path.basename(os.path.abspath(self.motor.repo_path))
        secenekler = [
            self.t("opt_delete_local_git"),
            self.t("opt_delete_github_only"),
            self.t("opt_delete_both")
        ]

        secim, ok = QInputDialog.getItem(
            self,
            self.t("dlg_delete_repo_title"),
            self.t("dlg_delete_repo_options_msg"),
            secenekler,
            0,
            False
        )
        if not ok or not secim:
            return

        onay = QMessageBox.warning(
            self,
            self.t("emin_misiniz"),
            self.t("delete_repo_confirm_msg").format(repo_adi),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if onay != QMessageBox.Yes:
            return

        hatalar = []

        if secim == self.t("opt_delete_local_git"):
            basarili, err = self.motor.yerel_git_sil()
            if not basarili:
                hatalar.append(f"Yerel silme: {err}")

        elif secim == self.t("opt_delete_github_only"):
            basarili, err = self.motor.github_repo_sil(repo_adi, self.github_kullanici_adi)
            if not basarili:
                hatalar.append(f"GitHub silme: {err}")

        elif secim == self.t("opt_delete_both"):
            basarili_gh, err_gh = self.motor.github_repo_sil(repo_adi, self.github_kullanici_adi)
            if not basarili_gh:
                hatalar.append(f"GitHub silme: {err_gh}")

            basarili_loc, err_loc = self.motor.yerel_git_sil()
            if not basarili_loc:
                hatalar.append(f"Yerel silme: {err_loc}")

        if hatalar:
            hata_metni = "\n".join(hatalar)
            if "delete_repo" in hata_metni:
                cevap = QMessageBox.question(
                    self,
                    self.t("dlg_auth_required_title"),
                    self.t("dlg_auth_required_msg"),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if cevap == QMessageBox.Yes:
                    subprocess.Popen(["gh", "auth", "refresh", "-h", "github.com", "-s", "delete_repo"])
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_delete_repo_err").format(hata_metni))
        else:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_delete_repo_success"))

        self.butonlari_guncelle()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Git_Gui")
    app.setDesktopFileName("Git_Gui")

    font_yolu = str(PROJE_ANA_DIZINI / "font.ttf")
    if os.path.exists(font_yolu):
        font_id = QFontDatabase.addApplicationFont(font_yolu)
        if font_id >= 0:
            font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            custom_font = QFont(font_family)
            app.setFont(custom_font)

    window = BasitGitGUI()
    window.show()
    sys.exit(app.exec())
