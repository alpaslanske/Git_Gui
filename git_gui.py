#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QIcon, QFont, QColor, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QFileDialog, QDialog,
    QInputDialog, QMessageBox, QTextEdit, QFrame, QSizePolicy, QComboBox, QScrollArea, QLineEdit
)

from git_motoru import GitMotoru
from lang import METINLER

def get_system_documents_dir():
    if "APPIMAGE" in os.environ:
        return Path(os.environ["APPIMAGE"]).parent
    else:
        return Path(os.path.realpath(__file__)).parent

LocationForDocs = get_system_documents_dir()
PROJE_ANA_DIZINI = LocationForDocs


# ==========================================
# İŞ PARÇACIKLARI (THREADS)
# Her bir işçi UI kilidini engeller ve 
# bağımsız bir GitMotoru kopyasıyla çalışarak Thread Safety sağlar.
# ==========================================

class UsernameIscisi(QThread):
    sonuc_sinyali = Signal(str)
    
    def run(self):
        try:
            res = subprocess.run(["gh", "api", "user", "-q", ".login"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                self.sonuc_sinyali.emit(res.stdout.strip())
                return
        except: pass
        try:
            res = subprocess.run(["git", "config", "--get", "github.user"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                self.sonuc_sinyali.emit(res.stdout.strip())
                return
        except: pass
        self.sonuc_sinyali.emit("")

class SurumIscisi(QThread):
    sonuc_sinyali = Signal(bool, str)
    log_sinyali = Signal(str)

    def __init__(self, repo_path, tag_adi, aciklama, dosya_yolu):
        super().__init__()
        self.repo_path = repo_path
        self.tag_adi = tag_adi
        self.aciklama = aciklama
        self.dosya_yolu = dosya_yolu

    def run(self):
        motor = GitMotoru()
        motor.set_path(self.repo_path)
        motor.log_callback = self.log_sinyali.emit
        basarili, hata = motor.git_tag_olustur(self.tag_adi, self.aciklama, self.dosya_yolu)
        self.sonuc_sinyali.emit(basarili, hata)

class KlonlamaIsçisi(QThread):
    sonuc_sinyali = Signal(bool, str, str)
    log_sinyali = Signal(str)
    def __init__(self, url, hedef_yol):
        super().__init__()
        self.url = url
        self.hedef_yol = hedef_yol
    def run(self):
        motor = GitMotoru()
        motor.log_callback = self.log_sinyali.emit
        try:
            basarili, cikti = motor.git_clone(self.url, self.hedef_yol)
            self.sonuc_sinyali.emit(basarili, cikti, self.hedef_yol)
        except Exception as e:
            self.sonuc_sinyali.emit(False, str(e), self.hedef_yol)

class PushIscisi(QThread):
    sonuc_sinyali = Signal(bool, str)
    log_sinyali = Signal(str)

    def __init__(self, repo_path, force=False):
        super().__init__()
        self.repo_path = repo_path
        self.force = force

    def run(self):
        motor = GitMotoru()
        motor.set_path(self.repo_path)
        motor.log_callback = self.log_sinyali.emit
        try:
            aktif_branch = motor.git_push(force=self.force)
            self.sonuc_sinyali.emit(True, aktif_branch)
        except Exception as e:
            self.sonuc_sinyali.emit(False, str(e))

class FetchIscisi(QThread):
    sonuc_sinyali = Signal(bool, object)
    log_sinyali = Signal(str)
    
    def __init__(self, repo_path):
        super().__init__()
        self.repo_path = repo_path
        
    def run(self):
        motor = GitMotoru()
        motor.set_path(self.repo_path)
        motor.log_callback = self.log_sinyali.emit
        basarili, sonuc = motor.git_fetch_kontrol()
        self.sonuc_sinyali.emit(basarili, sonuc)
class PullIscisi(QThread):
    sonuc_sinyali = Signal(bool, str)
    log_sinyali = Signal(str)

    def __init__(self, repo_path):
        super().__init__()
        self.repo_path = repo_path

    def run(self):
        try:
            # Arayüzü dondurmamak için alt işlem olarak git pull çalıştırıyoruz
            res = subprocess.run(["git", "pull"], cwd=self.repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if res.returncode == 0:
                self.sonuc_sinyali.emit(True, res.stdout.strip())
            else:
                self.sonuc_sinyali.emit(False, res.stderr.strip())
        except Exception as e:
            self.sonuc_sinyali.emit(False, str(e))
class LoginIscisi(QThread):
    kod_sinyali = Signal(str)
    sonuc_sinyali = Signal(bool, str)

    def run(self):
        try:
            github_env = os.environ.copy()
            github_env["GH_PROMPT_DISABLED"] = "1"
            process = subprocess.Popen(
                ["gh", "auth", "login", "--web", "--git-protocol", "https"],
                env=github_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace'
            )
            kod = None
            for _ in range(20):
                line = process.stdout.readline()
                if not line:
                    break
                if "one-time code" in line and ":" in line:
                    olasi_kod = line.split(":")[-1].strip()
                    if "-" in olasi_kod and len(olasi_kod) >= 8:
                        kod = olasi_kod
                        break

            if kod:
                self.kod_sinyali.emit(kod)
                process.wait()
                if process.returncode == 0:
                    subprocess.run(["gh", "auth", "setup-git"], check=True)
                    self.sonuc_sinyali.emit(True, "")
                else:
                    self.sonuc_sinyali.emit(False, "auth_failed")
            else:
                process.kill()
                self.sonuc_sinyali.emit(False, "no_code")
        except Exception as e:
            self.sonuc_sinyali.emit(False, str(e))


# ==========================================
# ARAYÜZ (UI) BİLEŞENLERİ
# ==========================================

class ModernButton(QPushButton):
    def __init__(self, text, bg_color):
        super().__init__(text)
        self.bg_color = bg_color
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.update_style()

    def update_style(self):
        color_obj = QColor(self.bg_color)
        h, s, l, a = color_obj.getHsl()
        l = min(255, int(l * 1.15))
        hover_color = QColor.fromHsl(h, s, l, a).name()
        
        # Sabit font ve point-size kaldırıldı, dinamik CSS eklendi
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.bg_color};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:disabled {{
                background-color: #3f3f46;
                color: #71717a;
            }}
        """)

    def update_color(self, new_color):
        self.bg_color = new_color
        self.update_style()

class GitKonsolu(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.lbl_baslik = QLabel("💻 Git Konsolu (Log)")
        baslik_font = self.lbl_baslik.font()
        baslik_font.setBold(True)
        baslik_font.setPointSize(12)
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

class GitGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_file = PROJE_ANA_DIZINI / "data" / "settings.json"
        self.aktif_lang = "tr"
        self.varsayilan_arama_dizini = ""
        self.github_kullanici_adi = ""
        self.repo_history = []
        self.resize(900, 810)
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
            self.butonlari_guncelle()
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
            
            # Github adını arkadan senkronize et (Arayüz kilitlenmez)
            self.github_kullanici_adi = ayarlar.get("github_username", "")
            if not self.github_kullanici_adi:
                self.otomatik_kullanici_adi_baslat()

            # Yalnızca var olan ve Git deposu olan klasörleri filtreleyerek yükle
            ham_gecmis = ayarlar.get("repo_history", [])
            self.repo_history = [p for p in ham_gecmis if os.path.exists(p) and self.motor.git_klasoru_mu(p)]
            self.combo_repos.blockSignals(True)
            self.combo_repos.clear()
            self.combo_repos.addItem(self.t("combo_repo_history"))
            self.combo_repos.addItems(self.repo_history)
            self.combo_repos.blockSignals(False)

            self.yan_panel_guncelle()

            son_klasor = ayarlar.get("last_repo_path", "")
            if son_klasor and Path(son_klasor).exists():
                self.motor.repo_path = son_klasor
                self.gecmise_repo_ekle(son_klasor) 
            
            self.butonlari_guncelle()
        except Exception as e:
            print(f"Ayar yükleme hatası: {e}")
            self.repo_history = []
            self.butonlari_guncelle()

    def ayarlari_kaydet(self):
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            ayarlar = {}
            if self.settings_file.exists():
                try:
                    with open(self.settings_file, "r", encoding="utf-8") as f:
                        ayarlar = json.load(f)
                except Exception:
                    pass
            ayarlar["language"] = self.aktif_lang
            ayarlar["last_repo_path"] = self.motor.repo_path
            ayarlar["default_search_path"] = ayarlar.get("default_search_path", self.varsayilan_arama_dizini)
            ayarlar["github_username"] = self.github_kullanici_adi
            ayarlar["repo_history"] = getattr(self, 'repo_history', [])

            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(ayarlar, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Ayar kaydetme hatası: {e}")

    # Ana Thread'i bloklamamak için QThread üzerinden Github bilgisini alır
    def otomatik_kullanici_adi_baslat(self):
        self.user_isci = UsernameIscisi()
        self.user_isci.sonuc_sinyali.connect(self.otomatik_kullanici_adi_tamamlandi)
        self.user_isci.start()
        
    def otomatik_kullanici_adi_tamamlandi(self, username):
        if username:
            self.github_kullanici_adi = username
            self.ayarlari_kaydet()

    def otomatik_kullanici_adi_bul(self):
        # Fallback senkron fonksiyon (Eğer işlem bitmeden acil lazımsa)
        try:
            res = subprocess.run(["gh", "api", "user", "-q", ".login"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception: pass
        try:
            res = subprocess.run(["git", "config", "--get", "github.user"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception: pass
        return ""

    def kullanici_adindan_url_olustur(self, repo_adi=""):
        if not self.github_kullanici_adi:
            otomatik = self.otomatik_kullanici_adi_bul()
            kullanici, ok = QInputDialog.getText(self, self.t("dlg_username_title"), self.t("dlg_username_msg"), text=otomatik)
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
        self.btn_squash.setText(self.t("btn_squash"))
        self.btn_rebase.setText(self.t("btn_rebase"))
        self.btn_create_repo.setText(self.t("btn_create_repo"))
        self.btn_clone.setText(self.t("btn_clone"))
        self.btn_delete_repo.setText(self.t("btn_delete_repo"))
        self.btn_fetch.setText(self.t("btn_fetch"))
        self.btn_push.setText(self.t("btn_push"))
        self.btn_tag.setText(self.t("btn_tag"))
        self.lbl_gecmis_baslik.setText(self.t("lbl_gecmis"))
        self.konsol.lbl_baslik.setText(self.t("lbl_konsol"))
        self.combo_repos.setItemText(0, self.t("combo_repo_history"))
        self.btn_remotes.setText(self.t("btn_remotes"))
        self.lbl_yan_baslik.setText(self.t("lbl_yan_baslik"))
        self.btn_toggle_sidebar.setText(self.t("btn_repolar"))
        self.btn_yeni_dal.setText(self.t("btn_yeni_dal"))
        self.btn_dal_sil.setText(self.t("btn_dal_sil"))
        self.btn_dal_birlestir.setText(self.t("btn_dal_birlestir"))
        
        if self.combo_branches.count() == 1:
            self.combo_branches.setItemText(0, self.t("combo_dal_sec"))
        
        if not self.motor.repo_path:
            self.lbl_durum.setText(self.t("lbl_durum_bekleniyor"))
        else:
            self.butonlari_guncelle()

    def setup_ui(self):
        central_widget = QWidget()
        ana_yatay_layout = QHBoxLayout(central_widget)
        ana_yatay_layout.setContentsMargins(0, 0, 0, 0)
        ana_yatay_layout.setSpacing(0)

        # --- YAN PANEL (SIDEBAR) ---
        self.yan_panel = QFrame()
        self.yan_panel.setFixedWidth(250)
        self.yan_panel.setStyleSheet("""
            QFrame { background-color: #2a2a32; border-right: 1px solid #3f3f46; }
        """)
        yan_panel_layout = QVBoxLayout(self.yan_panel)
        yan_panel_layout.setContentsMargins(10, 10, 10, 10)
        yan_panel_layout.setSpacing(10)

        self.lbl_yan_baslik = QLabel("")
        baslik_font = self.lbl_yan_baslik.font()
        baslik_font.setBold(True)
        baslik_font.setPointSize(12)
        self.lbl_yan_baslik.setFont(baslik_font)
        self.lbl_yan_baslik.setStyleSheet("color: #f5f5f7; border: none;")
        self.lbl_yan_baslik.setAlignment(Qt.AlignCenter)
        yan_panel_layout.addWidget(self.lbl_yan_baslik)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        self.scroll_icerik = QWidget()
        self.scroll_icerik.setStyleSheet("background-color: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_icerik)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(5)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        
        scroll_area.setWidget(self.scroll_icerik)
        yan_panel_layout.addWidget(scroll_area)
        
        ana_yatay_layout.addWidget(self.yan_panel)

        # --- SAĞ TARAF (ANA UYGULAMA) ---
        sag_widget = QWidget()
        main_layout = QVBoxLayout(sag_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        
        self.btn_toggle_sidebar = QPushButton("")
        self.btn_toggle_sidebar.setStyleSheet("""
            QPushButton {
                background-color: #3f3f46; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #52525b; }
        """)
        self.btn_toggle_sidebar.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        top_bar.addWidget(self.btn_toggle_sidebar, 0)

        self.lbl_banner = QLabel("")
        banner_font = self.lbl_banner.font()
        banner_font.setBold(True)
        banner_font.setPointSize(12)
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

        frame_top = QFrame()
        frame_top.setStyleSheet("QFrame { background-color: #2a2a32; border: 1px solid #3f3f46; border-radius: 6px; }")
        top_layout = QVBoxLayout(frame_top)
        
        secim_layout = QHBoxLayout()
        secim_layout.setSpacing(10)

        self.btn_sec = ModernButton("", "#007acc")
        self.btn_sec.clicked.connect(self.klasor_sec)
        secim_layout.addWidget(self.btn_sec, 1) 

        self.combo_repos = QComboBox()
        self.combo_repos.setMinimumHeight(40)
        self.combo_repos.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_repos.setStyleSheet("""
            QComboBox { background-color: #60a5fa; color: white; border: none; border-radius: 4px; padding: 8px; font-weight: bold;}
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #2a2a32; color: white; selection-background-color: #007acc; }
        """)
        self.combo_repos.addItem("📂 Mevcut Repolar...")
        self.combo_repos.currentIndexChanged.connect(self.repo_combobox_degisti)
        secim_layout.addWidget(self.combo_repos, 2) 
        self.combo_branches = QComboBox()
        self.combo_branches.setMinimumHeight(40)
        self.combo_branches.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_branches.setStyleSheet("""
            QComboBox { background-color: #10b981; color: white; border: none; border-radius: 4px; padding: 8px; font-weight: bold;}
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #2a2a32; color: white; selection-background-color: #10b981; }
        """)
        self.combo_branches.addItem("🌿 Dal Seçimi...")
        self.combo_branches.currentIndexChanged.connect(self.dal_degistir)
        secim_layout.addWidget(self.combo_branches, 1)
        top_layout.addLayout(secim_layout)

        self.lbl_durum = QLabel("")
        durum_font = self.lbl_durum.font()
        durum_font.setPointSize(12)
        self.lbl_durum.setFont(durum_font)
        self.lbl_durum.setStyleSheet("color: #a0a0ab; border: none;")
        self.lbl_durum.setAlignment(Qt.AlignCenter)
        top_layout.addWidget(self.lbl_durum)
        main_layout.addWidget(frame_top)

        orta_layout = QHBoxLayout()
        orta_layout.setSpacing(20)

        sol_layout = QVBoxLayout()
        sol_layout.setSpacing(10)
        self.btn_init = ModernButton("", "#28a745")
        self.btn_init.clicked.connect(self.git_init)
        sol_layout.addWidget(self.btn_init)
        
        self.btn_commit = ModernButton("", "#d97706")
        self.btn_commit.clicked.connect(self.git_commit)
        sol_layout.addWidget(self.btn_commit)
        
        self.btn_delete_commit = ModernButton("", "#b91c1c")
        self.btn_delete_commit.clicked.connect(self.git_commit_sil)
        sol_layout.addWidget(self.btn_delete_commit)
        
        self.btn_rollback = ModernButton("", "#dc3545")
        self.btn_rollback.clicked.connect(self.git_rollback)
        sol_layout.addWidget(self.btn_rollback)
        
        self.btn_rebase = ModernButton("", "#475569")
        self.btn_rebase.clicked.connect(self.git_rebase)
        
        self.btn_yeni_dal = ModernButton("", "#10b981") # Zümrüt Yeşili
        self.btn_yeni_dal.clicked.connect(self.yeni_dal_olustur)
        sol_layout.addWidget(self.btn_yeni_dal)

        self.btn_dal_sil = ModernButton("", "#f43f5e") # Gül Kurusu
        self.btn_dal_sil.clicked.connect(self.dal_sil)
        sol_layout.addWidget(self.btn_dal_sil)

        self.btn_dal_birlestir = ModernButton("", "#8b5cf6") # Mor renk
        self.btn_dal_birlestir.clicked.connect(self.dal_birlestir)
        sol_layout.addWidget(self.btn_dal_birlestir)
        
        sol_layout.addWidget(self.btn_rebase)
        orta_layout.addLayout(sol_layout)

        sag_layout = QVBoxLayout()
        sag_layout.setSpacing(10)
        self.btn_login = ModernButton("", "#0284c7")
        self.btn_login.clicked.connect(self.github_login)
        sag_layout.addWidget(self.btn_login)

        create_clone_layout = QHBoxLayout()
        create_clone_layout.setSpacing(10)
        self.btn_create_repo = ModernButton("", "#0f766e")
        self.btn_create_repo.clicked.connect(self.github_repo_olustur)
        create_clone_layout.addWidget(self.btn_create_repo)
        self.btn_clone = ModernButton("", "#0369a1")
        self.btn_clone.clicked.connect(self.github_repo_indir)
        create_clone_layout.addWidget(self.btn_clone)
        sag_layout.addLayout(create_clone_layout)

        push_remotes_layout = QHBoxLayout()
        push_remotes_layout.setSpacing(10)
        self.btn_remotes = ModernButton("", "#3b82f6")
        self.btn_remotes.clicked.connect(self.yonet_remotes)
        push_remotes_layout.addWidget(self.btn_remotes)
        self.btn_push = ModernButton("", "#8b5cf6")
        self.btn_push.clicked.connect(self.git_push)
        push_remotes_layout.addWidget(self.btn_push)
        sag_layout.addLayout(push_remotes_layout)

        fetch_delete_layout = QHBoxLayout()
        fetch_delete_layout.setSpacing(10)
        self.btn_fetch = ModernButton("", "#28a745")
        self.btn_fetch.clicked.connect(self.git_fetch_kontrol)
        fetch_delete_layout.addWidget(self.btn_fetch)
        self.btn_delete_repo = ModernButton("", "#991b1b")
        self.btn_delete_repo.clicked.connect(self.repo_sil)
        fetch_delete_layout.addWidget(self.btn_delete_repo)
        sag_layout.addLayout(fetch_delete_layout)

        tag_squash_layout = QHBoxLayout()
        tag_squash_layout.setSpacing(10)
        self.btn_tag = ModernButton("", "#4b5563")
        self.btn_tag.clicked.connect(self.git_sürüm_olustur)
        tag_squash_layout.addWidget(self.btn_tag)
        self.btn_squash = ModernButton("", "#0891b2")
        self.btn_squash.clicked.connect(self.git_squash)
        tag_squash_layout.addWidget(self.btn_squash)
        sag_layout.addLayout(tag_squash_layout)

        orta_layout.addLayout(sag_layout)
        main_layout.addLayout(orta_layout)

        self.lbl_gecmis_baslik = QLabel("")
        gecmis_font = self.lbl_gecmis_baslik.font()
        gecmis_font.setBold(True)
        gecmis_font.setPointSize(14)
        self.lbl_gecmis_baslik.setFont(gecmis_font)
        self.lbl_gecmis_baslik.setStyleSheet("color: #f5f5f7;")
        main_layout.addWidget(self.lbl_gecmis_baslik)

        self.listbox_gecmis = QListWidget()
        self.listbox_gecmis.setStyleSheet("""
            QListWidget { background-color: #2a2a32; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 4px; padding: 5px; }
            QListWidget::item:selected { background-color: #007acc; color: white; }
        """)
        main_layout.addWidget(self.listbox_gecmis, 1)

        self.konsol = GitKonsolu()
        main_layout.addWidget(self.konsol)
        
        ana_yatay_layout.addWidget(sag_widget, 1)
        self.setCentralWidget(central_widget)

    def toggle_sidebar(self):
        hedef_genislik = 250 if self.yan_panel.width() == 0 else 0
        
        self.anim = QPropertyAnimation(self.yan_panel, b"minimumWidth")
        self.anim.setDuration(250) 
        self.anim.setStartValue(self.yan_panel.width())
        self.anim.setEndValue(hedef_genislik)
        self.anim.setEasingCurve(QEasingCurve.InOutQuart)
        
        self.anim_max = QPropertyAnimation(self.yan_panel, b"maximumWidth")
        self.anim_max.setDuration(250) 
        self.anim_max.setStartValue(self.yan_panel.width())
        self.anim_max.setEndValue(hedef_genislik)
        self.anim_max.setEasingCurve(QEasingCurve.InOutQuart)
        
        self.anim.start()
        self.anim_max.start()

    # Bellek ve CPU optimizasyonlu Yan Panel Güncelleme
    def yan_panel_guncelle(self):
        mevcut_buton_sayisi = self.scroll_layout.count()
        gecmis_sayisi = len(self.repo_history)

        for i in range(max(mevcut_buton_sayisi, gecmis_sayisi)):
            if i < gecmis_sayisi:
                repo_path = self.repo_history[i]
                if not repo_path or not os.path.exists(repo_path):
                    continue
                klasor_adi = os.path.basename(os.path.abspath(repo_path))
                
                # --- MODERN TASARIM VE RENKLENDİRME ---
                if hasattr(self.motor, 'repo_path') and self.motor.repo_path == repo_path:
                    # Aktif Repo Stili (Mavi arka plan, sol vurgu çizgisi ve beyaz metin)
                    buton_stili = """
                        QPushButton {
                            background-color: #0369a1; 
                            color: #ffffff; 
                            border: none; 
                            border-left: 4px solid #38bdf8; 
                            border-radius: 4px; 
                            padding: 10px 15px; 
                            text-align: left; 
                            font-weight: bold;
                            font-size: 13px;
                        }
                    """
                    gosterim_adi = f"📂 {klasor_adi}" # Aktif klasör ikonu
                else:
                    # Pasif Repo Stili (Şeffaf arka plan, gri metin, hover efekti)
                    buton_stili = """
                        QPushButton {
                            background-color: transparent; 
                            color: #a1a1aa; 
                            border: none; 
                            border-left: 4px solid transparent; 
                            border-radius: 4px; 
                            padding: 10px 15px; 
                            text-align: left; 
                            font-weight: normal;
                            font-size: 13px;
                        }
                        QPushButton:hover { 
                            background-color: #3f3f46; 
                            color: #f4f4f5; 
                            border-left: 4px solid #71717a; 
                        }
                    """
                    gosterim_adi = f"📁 {klasor_adi}" # Pasif klasör ikonu
                # -------------------------------------------
                
                if i < mevcut_buton_sayisi:
                    # Var olan butonu yeniden kullan
                    btn = self.scroll_layout.itemAt(i).widget()
                    btn.setText(gosterim_adi)
                    btn.setToolTip(repo_path)
                    btn.setStyleSheet(buton_stili)
                    btn.show()
                    try: btn.clicked.disconnect() 
                    except: pass
                    btn.clicked.connect(lambda checked=False, p=repo_path: self.yan_panelden_repo_sec(p))
                else:
                    # Yeni buton ekle
                    btn = QPushButton(gosterim_adi)
                    btn.setToolTip(repo_path)
                    btn.setStyleSheet(buton_stili)
                    btn.setCursor(Qt.PointingHandCursor)
                    btn.clicked.connect(lambda checked=False, p=repo_path: self.yan_panelden_repo_sec(p))
                    self.scroll_layout.addWidget(btn)
            else:
                # Fazlalık butonları gizle
                widget = self.scroll_layout.itemAt(i).widget()
                if widget:
                    widget.hide()

    def yan_panelden_repo_sec(self, repo_path):
        if os.path.exists(repo_path):
            self.motor.repo_path = repo_path
            self.konsol.yaz(self.t("klasor_secildi") + repo_path)
            self.gecmise_repo_ekle(repo_path)
            self.butonlari_guncelle()
        else:
            QMessageBox.warning(self, self.t("hata"), "Klasör artık mevcut değil.")
            if repo_path in self.repo_history:
                self.repo_history.remove(repo_path)
                self.gecmise_repo_ekle(self.motor.repo_path if self.motor.repo_path else "")

    # set_buttons_state ve butonlari_guncelle metotları birleştirildi.
    def butonlari_guncelle(self):
        if not self.motor.repo_path:
            self.lbl_banner.hide()
            self.lbl_durum.setText("") # Klasör bekleniyor yazısını kaldırdık
            self.listbox_gecmis.clear()
            self._set_ui_lock(False)
            return

        is_git = self.motor.set_path(self.motor.repo_path)
        self._set_ui_lock(is_git)

        if is_git:
            self.gecmisi_yukle()
            is_clean, status_text = self.motor.get_status()
            self.dallari_guncelle()
            self.konsol.yaz("> git status")
            self.konsol.yaz(status_text)
            self.lbl_banner.show()
            
            self.lbl_durum.setText("") # Git aktif yazısını kaldırdık
            
            if is_clean:
                self.lbl_banner.setStyleSheet("QLabel { background-color: #22c55e; color: white; border-radius: 4px; padding: 6px; }")
                self.lbl_banner.setText(self.t("banner_clean"))
            else:
                self.lbl_banner.setStyleSheet("QLabel { background-color: #ef4444; color: white; border-radius: 4px; padding: 6px; }")
                self.lbl_banner.setText(self.t("banner_dirty"))
        else:
            self.lbl_banner.show()
            self.lbl_banner.setStyleSheet("QLabel { background-color: #64748b; color: white; border-radius: 4px; padding: 6px; }")
            self.lbl_banner.setText("Git Klasörü Değil") 
            
            self.lbl_durum.setText("") # Git değil yazısını kaldırdık
            self.listbox_gecmis.clear()

    def _set_ui_lock(self, is_git):
        self.btn_init.setEnabled(not is_git)
        self.btn_commit.setEnabled(is_git)
        self.btn_rollback.setEnabled(is_git)
        self.btn_delete_commit.setEnabled(is_git)
        self.btn_squash.setEnabled(is_git)
        self.btn_rebase.setEnabled(is_git)
        self.btn_create_repo.setEnabled(is_git)
        self.btn_delete_repo.setEnabled(is_git)
        self.btn_clone.setEnabled(True)
        self.btn_fetch.setEnabled(is_git)
        self.btn_push.setEnabled(is_git)
        self.btn_tag.setEnabled(is_git)
        self.btn_remotes.setEnabled(is_git)
        self.combo_branches.setEnabled(is_git)
        self.btn_yeni_dal.setEnabled(is_git)
        self.btn_dal_sil.setEnabled(is_git)
        self.btn_dal_birlestir.setEnabled(is_git)
        
    def git_fetch_kontrol(self):
        # lbl_durum kaldırıldığı için mesajı konsola yazdırıyoruz
        self.konsol.yaz("> Fetch işlemi bekleniyor...")
        self._set_ui_lock(False)
        QApplication.processEvents()
        
        self.fetch_isci = FetchIscisi(self.motor.repo_path)
        self.fetch_isci.log_sinyali.connect(self.konsol.yaz)
        self.fetch_isci.sonuc_sinyali.connect(self.fetch_tamamlandi)
        self.fetch_isci.start()        
        
    def fetch_tamamlandi(self, basarili, sonuc):
        if not basarili:
            if sonuc == "no_remote":
                QMessageBox.information(self, self.t("hata"), self.t("fetch_no_remote"))
            else:
                QMessageBox.critical(self, self.t("hata"), str(sonuc))
            self.butonlari_guncelle()
        else:
            ileri = sonuc["ileri"]
            geri = sonuc["geri"]
            if ileri == 0 and geri == 0:
                QMessageBox.information(self, self.t("basarili"), self.t("fetch_guncel"))
                self.butonlari_guncelle()
            elif ileri == 0 and geri > 0:
                # Gerideyse soru sor
                cevap = QMessageBox.question(
                    self, self.t("basarili"), 
                    f"{self.t('fetch_geride').format(geri)}\n\nUzak sunucudaki değişiklikleri şimdi çekmek (Pull) ister misiniz?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                )
                if cevap == QMessageBox.Yes:
                    self.git_pull_baslat()
                else:
                    self.butonlari_guncelle()
            elif ileri > 0 and geri == 0:
                QMessageBox.information(self, self.t("basarili"), self.t("fetch_ileride").format(ileri))
                self.butonlari_guncelle()
            else:
                # Hem ileri hem geriyse (Farklı branch'ler)
                cevap = QMessageBox.question(
                    self, self.t("basarili"), 
                    f"{self.t('fetch_farkli').format(ileri, geri)}\n\nDeğişiklikleri birleştirmek (Pull / Merge) ister misiniz?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                )
                if cevap == QMessageBox.Yes:
                    self.git_pull_baslat()
                else:
                    self.butonlari_guncelle()
                    
    def git_pull_baslat(self):
        self.konsol.yaz("> git pull işlemi başlatılıyor...")
        self._set_ui_lock(False)
        QApplication.processEvents()
        
        self.pull_isci = PullIscisi(self.motor.repo_path)
        self.pull_isci.log_sinyali.connect(self.konsol.yaz)
        self.pull_isci.sonuc_sinyali.connect(self.pull_tamamlandi)
        self.pull_isci.start()

    def pull_tamamlandi(self, basarili, mesaj):
        self.butonlari_guncelle()
        if basarili:
            self.konsol.yaz(mesaj)
            QMessageBox.information(self, self.t("basarili"), "Değişiklikler başarıyla çekildi (Pull tamamlandı).")
        else:
            self.konsol.yaz(f"PULL HATASI:\n{mesaj}")
            QMessageBox.critical(self, self.t("hata"), f"Pull işlemi sırasında hata oluştu. Muhtemelen yerel değişikliklerinizle çakışma (conflict) var:\n\n{mesaj}")

    def gecmise_repo_ekle(self, path):
        if not hasattr(self, 'repo_history'):
            self.repo_history = []

        path = str(path)
        
        # --- YENİ KONTROL: Git klasörü değilse geçmişe eklemeyi durdur ---
        if not self.motor.git_klasoru_mu(path):
            return
        # -----------------------------------------------------------------
        
        if path not in self.repo_history:
            self.repo_history.append(path)

        self.repo_history.sort(key=lambda p: os.path.basename(os.path.abspath(p)).lower())
        self.repo_history = self.repo_history[:15] 

        self.combo_repos.blockSignals(True)
        self.combo_repos.clear()
        self.combo_repos.addItem(self.t("combo_repo_history"))
        self.combo_repos.addItems(self.repo_history)
        
        if path in self.repo_history:
            idx = self.repo_history.index(path)
            self.combo_repos.setCurrentIndex(idx + 1)
            
        self.combo_repos.blockSignals(False)
        self.yan_panel_guncelle()
        self.ayarlari_kaydet()
        
    def repo_combobox_degisti(self, index):
        if index > 0:
            secilen = self.combo_repos.currentText()
            if os.path.exists(secilen):
                self.motor.repo_path = secilen
                self.konsol.yaz(self.t("klasor_secildi") + secilen)
                self.gecmise_repo_ekle(secilen)
                self.butonlari_guncelle()
            else:
                QMessageBox.warning(self, self.t("hata"), "Klasör artık mevcut değil.")
                self.repo_history.remove(secilen)
                self.gecmise_repo_ekle(self.motor.repo_path if self.motor.repo_path else "")

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

        dialog = QFileDialog(self)
        dialog.setWindowTitle(self.t("secim_penceresi"))
        dialog.setDirectory(baslangic)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.DontUseNativeDialog, False)

        if dialog.exec():
            secilen_yollar = dialog.selectedFiles()
            if secilen_yollar:
                secilen = secilen_yollar[0]
                if not self.motor.git_klasoru_mu(secilen):
                    cevap = QMessageBox.question(
                        self,
                        self.t("emin_misiniz"),
                        self.t("msg_not_git_repo"),
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if cevap == QMessageBox.Yes:
                        self.motor.repo_path = secilen
                        self.git_init()
                    else:
                        self.motor.repo_path = secilen
                else:
                    self.motor.repo_path = secilen
                self.konsol.yaz(self.t("klasor_secildi") + secilen)
                self.gecmise_repo_ekle(secilen)
                self.butonlari_guncelle()
                self.ayarlari_kaydet()

    def github_repo_olustur(self):
        if not self.motor.repo_path: return
        varsayilan_isim = os.path.basename(os.path.abspath(self.motor.repo_path))
        repo_adi, ok = QInputDialog.getText(self, self.t("dlg_repo_name_title"), self.t("dlg_repo_name_msg"), text=varsayilan_isim)
        if not (ok and repo_adi.strip()): return
        repo_adi = repo_adi.strip()
        turler = ["public", "private"]
        tur, ok = QInputDialog.getItem(self, self.t("dlg_visibility_title"), self.t("dlg_visibility_msg"), turler, 0, False)
        if not ok: return
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
            self._set_ui_lock(False)
            self.btn_login.setEnabled(False)
            QApplication.processEvents()
            self.login_isci = LoginIscisi()
            self.login_isci.kod_sinyali.connect(self.login_kod_goster)
            self.login_isci.sonuc_sinyali.connect(self.login_tamamlandi)
            self.login_isci.start()
        except FileNotFoundError:
            QMessageBox.warning(self, self.t("eksik_paket"), self.t("msg_eksik_paket"))
            self.butonlari_guncelle()
        except Exception as e:
            QMessageBox.critical(self, self.t("hata"), self.t("beklenmeyen_hata").format(e))
            self.butonlari_guncelle()

    def login_kod_goster(self, kod):
        pano = QApplication.clipboard()
        pano.clear()
        pano.setText(kod)
        QApplication.processEvents() 

        QMessageBox.information(self, self.t("github_girisi"), self.t("kod_kopyalandi").format(kod))
        webbrowser.open("https://github.com/login/device")
        self.lbl_durum.setText(self.t("onay_bekleniyor"))
        self.konsol.yaz(self.t("log_onay_bekleniyor").format(kod))

    def login_tamamlandi(self, basarili, hata_kodu):
        self.btn_login.setEnabled(True)
        if basarili:
            self.otomatik_kullanici_adi_baslat()
            QMessageBox.information(self, self.t("basarili"), self.t("msg_login_basarili"))
            self.lbl_durum.setStyleSheet("color: #4ade80; border: none;")
            self.lbl_durum.setText(self.t("lbl_github_baglandi"))
            self.konsol.yaz(self.t("log_baglanti_tamam"))
        else:
            if hata_kodu == "no_code":
                QMessageBox.critical(self, self.t("hata"), self.t("msg_kod_alinamadi"))
            elif hata_kodu == "auth_failed":
                QMessageBox.critical(self, self.t("hata"), self.t("msg_onay_hata"))
                self.konsol.yaz(self.t("log_onay_hata"))
            else:
                QMessageBox.critical(self, self.t("hata"), f"Hata: {hata_kodu}")
        self.butonlari_guncelle()

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
            mevcut_url = self.motor.get_remote_url() if hasattr(self.motor, 'get_remote_url') else ""
            otomatik_url = mevcut_url if mevcut_url else self.kullanici_adindan_url_olustur()

            remote_url, ok = QInputDialog.getText(self, self.t("github_link_baslik"), self.t("github_link_soru"), text=otomatik_url)

            if not ok or not remote_url.strip():
                return

            remote_url = remote_url.strip()

            if remote_url != mevcut_url:
                self.motor.add_remote(remote_url)

            self.lbl_durum.setStyleSheet("color: #60a5fa; border: none;")
            self.lbl_durum.setText(self.t("msg_push_bekle"))
            self._set_ui_lock(False)
            self.btn_push.setEnabled(False)
            QApplication.processEvents()

            self.push_isci = PushIscisi(self.motor.repo_path, force=False)
            self.push_isci.log_sinyali.connect(self.konsol.yaz)
            self.push_isci.sonuc_sinyali.connect(self.push_tamamlandi)
            self.push_isci.start()

        except Exception as e:
            QMessageBox.critical(self, self.t("hata"), self.t("beklenmeyen_hata").format(str(e)))
            self.butonlari_guncelle()

    def push_tamamlandi(self, basarili, mesaj):
        self.butonlari_guncelle()
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_push_basarili").format(mesaj))
        else:
            hata_mesaji = str(mesaj)
            tetikleyiciler = ["non-fast-forward", "Updates were rejected", "Güncellemeler reddedildi", "uzak konum karşıtından geride", "stale info"]
            if any(kelime in hata_mesaji for kelime in tetikleyiciler):
                cevap = QMessageBox.warning(
                    self, self.t("dlg_force_push_title"), self.t("dlg_force_push_msg"),
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if cevap == QMessageBox.Yes:
                    self.lbl_durum.setStyleSheet("color: #60a5fa; border: none;")
                    self.lbl_durum.setText(self.t("msg_push_bekle"))
                    self._set_ui_lock(False)
                    QApplication.processEvents()
                    self.push_isci = PushIscisi(self.motor.repo_path, force=True)
                    self.push_isci.log_sinyali.connect(self.konsol.yaz)
                    self.push_isci.sonuc_sinyali.connect(self.force_push_tamamlandi)
                    self.push_isci.start()
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_push_hata").format(hata_mesaji))

    def force_push_tamamlandi(self, basarili, mesaj):
        self.butonlari_guncelle()
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_force_push_basarili"))
        else:
            QMessageBox.critical(self, self.t("hata"), f"Force push başarısız oldu:\n{mesaj}")

    def git_rollback(self):
        commitler = self.motor.gecmis_getir(adet=30)
        if not commitler:
            QMessageBox.warning(self, self.t("hata"), self.t("gecmis_bos"))
            return
        secenekler = [f"[{c['hash']}] {c['tarih']} - {c['mesaj']}" for c in commitler]
        secilen_metin, ok = QInputDialog.getItem(self, self.t("dlg_rollback_title"), self.t("dlg_rollback_msg"), secenekler, 0, False)
        if not ok or not secilen_metin: return
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
        secilen_metin, ok = QInputDialog.getItem(self, self.t("dlg_delete_commit_title"), self.t("dlg_delete_commit_msg"), secenekler, 0, False)
        if not ok or not secilen_metin: return
        hedef_hash = secilen_metin.split("]")[0].replace("[", "").strip()
        cevap = QMessageBox.warning(self, self.t("emin_misiniz"), f"{secilen_metin}\n\n{self.t('delete_commit_soru')}", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
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
        if not self.motor.repo_path: return
        repo_adi = os.path.basename(os.path.abspath(self.motor.repo_path))
        secenekler = [self.t("opt_delete_local_git"), self.t("opt_delete_github_only"), self.t("opt_delete_both")]
        secim, ok = QInputDialog.getItem(self, self.t("dlg_delete_repo_title"), self.t("dlg_delete_repo_options_msg"), secenekler, 0, False)
        if not ok or not secim: return
        onay = QMessageBox.warning(self, self.t("emin_misiniz"), self.t("delete_repo_confirm_msg").format(repo_adi), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if onay != QMessageBox.Yes: return
        hatalar = []
        if secim == self.t("opt_delete_local_git"):
            basarili, err = self.motor.yerel_git_sil()
            if not basarili: hatalar.append(f"Yerel silme: {err}")
        elif secim == self.t("opt_delete_github_only"):
            basarili, err = self.motor.github_repo_sil(repo_adi, self.github_kullanici_adi)
            if not basarili: hatalar.append(f"GitHub silme: {err}")
        elif secim == self.t("opt_delete_both"):
            basarili_gh, err_gh = self.motor.github_repo_sil(repo_adi, self.github_kullanici_adi)
            if not basarili_gh: hatalar.append(f"GitHub silme: {err_gh}")
            basarili_loc, err_loc = self.motor.yerel_git_sil()
            if not basarili_loc: hatalar.append(f"Yerel silme: {err_loc}")
        if hatalar:
            hata_metni = "\n".join(hatalar)
            if "delete_repo" in hata_metni:
                cevap = QMessageBox.question(self, self.t("dlg_auth_required_title"), self.t("dlg_auth_required_msg"), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if cevap == QMessageBox.Yes: subprocess.Popen(["gh", "auth", "refresh", "-h", "github.com", "-s", "delete_repo"])
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_delete_repo_err").format(hata_metni))
        else:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_delete_repo_success"))
        self.butonlari_guncelle()

    def github_repo_indir(self):
        url, ok = QInputDialog.getText(self, self.t("dlg_clone_title"), self.t("dlg_clone_msg"))
        if not (ok and url.strip()): return
        url = url.strip()
        varsayilan_isim = url.split("/")[-1].replace(".git", "") if "/" in url else "yeni_proje"
        baslangic = self.varsayilan_arama_dizini if self.varsayilan_arama_dizini else str(Path.home())
        QMessageBox.information(self, self.t("dlg_clone_title"), "Lütfen projenin indirileceği ana klasörü seçin.")
        ana_dizin = QFileDialog.getExistingDirectory(self, self.t("secim_penceresi"), baslangic)
        if not ana_dizin: return
        hedef_tam_yol = os.path.join(ana_dizin, varsayilan_isim)
        sayac = 1
        orjinal_yol = hedef_tam_yol
        while os.path.exists(hedef_tam_yol):
            hedef_tam_yol = f"{orjinal_yol}_{sayac}"
            sayac += 1
        self.lbl_durum.setText(self.t("msg_cloning"))
        self.konsol.yaz(f"> Depo klonlanıyor (Arka Plan İşlemi): {url}")
        self._set_ui_lock(False)
        self.btn_clone.setEnabled(False)
        QApplication.processEvents()
        self.isci = KlonlamaIsçisi(url, hedef_tam_yol)
        self.isci.log_sinyali.connect(self.konsol.yaz)
        self.isci.sonuc_sinyali.connect(self.klonlama_tamamlandi)
        self.isci.start()

    def klonlama_tamamlandi(self, basarili, cikti, hedef_yol):
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_clone_success"))
            self.motor.repo_path = hedef_yol
            self.gecmise_repo_ekle(hedef_yol)
            self.butonlari_guncelle()
            self.ayarlari_kaydet()
        else:
            QMessageBox.critical(self, self.t("hata"), self.t("err_clone_fail").format(cikti))
            self.butonlari_guncelle()

    def dallari_guncelle(self):
        if not self.motor.repo_exists:
            self.combo_branches.blockSignals(True)
            self.combo_branches.clear()
            self.combo_branches.addItem(self.t("combo_dal_sec"))
            self.combo_branches.blockSignals(False)
            return

        dallar, aktif = self.motor.get_branches()
        self.combo_branches.blockSignals(True)
        self.combo_branches.clear()
        if dallar:
            for dal in dallar:
                self.combo_branches.addItem(dal)
            if aktif in dallar:
                self.combo_branches.setCurrentText(aktif)
        else:
            self.combo_branches.addItem(self.t("combo_dal_sec"))
        self.combo_branches.blockSignals(False)
        
    def dal_degistir(self, index):
        if index < 0: return
        hedef_dal = self.combo_branches.currentText()
        if hedef_dal and "..." not in hedef_dal:
            basarili, hata = self.motor.switch_branch(hedef_dal)
            if basarili:
                self.konsol.yaz(self.t("msg_dal_degisti").format(hedef_dal))
                self.butonlari_guncelle() # Arayüzü ve commit loglarını tazelemek için
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_dal_hata").format(hata))
                self.dallari_guncelle()

    def yeni_dal_olustur(self):
        dal_adi, ok = QInputDialog.getText(self, self.t("dlg_yeni_dal_baslik"), self.t("dlg_yeni_dal_mesaj"))
        if ok and dal_adi.strip():
            dal_adi = dal_adi.strip().replace(" ", "-")
            basarili, hata = self.motor.create_and_switch_branch(dal_adi)
            if basarili:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_dal_olusturuldu").format(dal_adi))
                self.butonlari_guncelle()
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_dal_hata").format(hata))

    def dal_sil(self):
        dallar, aktif = self.motor.get_branches()
        silinebilir = [d for d in dallar if d != aktif]
        
        if not silinebilir:
            QMessageBox.warning(self, self.t("hata"), self.t("err_baska_dal_yok"))
            return
            
        secim, ok = QInputDialog.getItem(self, self.t("dlg_dal_sil_baslik"), self.t("dlg_dal_sil_mesaj"), silinebilir, 0, False)
        if ok and secim:
            basarili, hata = self.motor.delete_branch(secim)
            if basarili:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_dal_silindi").format(secim))
                self.dallari_guncelle()
            else:
                if hata == "not_merged":
                    cevap = QMessageBox.warning(self, self.t("emin_misiniz"), self.t("msg_dal_not_merged"), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if cevap == QMessageBox.Yes:
                        b2, h2 = self.motor.delete_branch(secim, force=True)
                        if b2:
                            QMessageBox.information(self, self.t("basarili"), self.t("msg_dal_silindi").format(secim))
                            self.dallari_guncelle()
                        else:
                            QMessageBox.critical(self, self.t("hata"), self.t("msg_dal_hata").format(h2))
                else:
                    QMessageBox.critical(self, self.t("hata"), self.t("msg_dal_hata").format(hata))

    def dal_birlestir(self):
        dallar, aktif = self.motor.get_branches()
        birlestirilebilir = [d for d in dallar if d != aktif]
        
        if not birlestirilebilir:
            QMessageBox.warning(self, self.t("hata"), "Birleştirilecek başka bir dal bulunmuyor.")
            return
            
        mesaj = self.t("dlg_merge_mesaj").format(aktif)
        
        secim, ok = QInputDialog.getItem(self, self.t("dlg_merge_baslik"), mesaj, birlestirilebilir, 0, False)
        if ok and secim:
            basarili, hata = self.motor.merge_branch(secim)
            if basarili:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_merge_basarili").format(secim))
            else:
                if hata == "conflict":
                    QMessageBox.warning(self, self.t("hata"), self.t("msg_merge_conflict"))
                else:
                    QMessageBox.critical(self, self.t("hata"), self.t("msg_dal_hata").format(hata))
            self.butonlari_guncelle()

    def git_sürüm_olustur(self):
        basarili, mevcut_taglar = self.motor.yerel_taglari_getir()

        dialog = QDialog(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose) # Fix Memory Leak
        dialog.setWindowTitle(self.t("dlg_tag_title"))
        dialog.resize(450, 350)
        dialog.setStyleSheet("QDialog { background-color: #1e1e24; } QLabel { color: #f5f5f7; }")
        
        layout = QVBoxLayout(dialog)

        if basarili and mevcut_taglar:
            lbl_mevcut = QLabel("📌 Mevcut Sürümler:")
            layout.addWidget(lbl_mevcut)
            
            txt_mevcut = QTextEdit()
            txt_mevcut.setReadOnly(True)
            txt_mevcut.setPlainText(mevcut_taglar)
            txt_mevcut.setStyleSheet("""
                QTextEdit { background-color: #2a2a32; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 4px; padding: 5px; }
            """)
            txt_mevcut.setMinimumHeight(100)
            layout.addWidget(txt_mevcut)

        lbl_msg = QLabel(self.t("dlg_tag_msg"))
        layout.addWidget(lbl_msg)

        input_tag = QLineEdit()
        input_tag.setStyleSheet("""
            QLineEdit { background-color: #2a2a32; color: white; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px; }
        """)
        input_tag.returnPressed.connect(dialog.accept)
        layout.addWidget(input_tag)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Tamam")
        btn_ok.setDefault(True) 
        btn_ok.setStyleSheet("QPushButton { background-color: #007acc; color: white; padding: 6px 15px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #005999; }")
        btn_cancel = QPushButton("İptal")
        btn_cancel.setStyleSheet("QPushButton { background-color: #3f3f46; color: white; padding: 6px 15px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #52525b; }")        
        
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

        if dialog.exec() != QDialog.Accepted:
            return
            
        tag_adi = input_tag.text().strip()
        if not tag_adi:
            return
            
        tag_adi = tag_adi.replace(" ", "-")
        
        aciklama, ok2 = QInputDialog.getText(self, self.t("dlg_tag_title"), self.t("dlg_tag_desc_msg"))
        if not ok2: return

        dosya_yolu = ""
        cevap = QMessageBox.question(
            self,
            self.t("dlg_add_file_title"),
            self.t("dlg_add_file_msg"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if cevap == QMessageBox.Yes:
            dosya_yolu, _ = QFileDialog.getOpenFileName(
                self,
                self.t("dlg_select_file"),
                self.motor.repo_path
            )

        self.lbl_durum.setText(self.t("msg_creating_tag"))
        self._set_ui_lock(False)
        QApplication.processEvents()

        self.surum_isci = SurumIscisi(self.motor.repo_path, tag_adi, aciklama, dosya_yolu)
        self.surum_isci.log_sinyali.connect(self.konsol.yaz)
        self.surum_isci.sonuc_sinyali.connect(lambda basarili, hata: self.surum_tamamlandi(basarili, hata, tag_adi))
        self.surum_isci.start()

    def surum_tamamlandi(self, basarili, hata, tag_adi):
        self.butonlari_guncelle() 
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_tag_basarili").format(tag_adi))
        else:
            QMessageBox.critical(self, self.t("hata"), f"{self.t('msg_tag_hata')}\n\n{hata}")

    def git_rebase(self):
        varsayilan_upstream = f"origin/{self.motor.get_active_branch()}" if self.motor.has_remotes() else "main"
        upstream, ok = QInputDialog.getText(self, self.t("dlg_rebase_title"), self.t("dlg_rebase_msg"), text=varsayilan_upstream)
        if not (ok and upstream.strip()): return
        upstream = upstream.strip()
        self.lbl_durum.setText(self.t("msg_rebase_bekle"))
        QApplication.processEvents()
        basarili, sebep = self.motor.git_rebase(upstream)
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_rebase_basarili"))
        else:
            if sebep == "conflict":
                QMessageBox.warning(self, self.t("hata"), self.t("msg_rebase_conflict"))
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_rebase_hata").format(sebep))
        self.butonlari_guncelle()

    def git_squash(self):
        cevap_warn = QMessageBox.warning(
            self, self.t("emin_misiniz"), self.t("dlg_squash_warn_msg"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if cevap_warn != QMessageBox.Yes: return
        commitler = self.motor.gecmis_getir(adet=50)
        if not commitler or len(commitler) < 2:
            QMessageBox.warning(self, self.t("hata"), self.t("err_squash_count"))
            return
        toplam_commit = len(commitler)
        adet, ok1 = QInputDialog.getInt(
            self, self.t("dlg_squash_count_title"), f"{self.t('dlg_squash_count_msg')} (Max: {toplam_commit})",
            value=2, minValue=2, maxValue=toplam_commit, step=1
        )
        if not ok1: return
        birlestirilen_mesajlar = "\n".join([f"- {c['mesaj']}" for c in commitler[:adet]])
        varsayilan_mesaj = f"Squashed {adet} commits:\n{birlestirilen_mesajlar}"
        yeni_mesaj, ok2 = QInputDialog.getMultiLineText(self, self.t("dlg_squash_msg_title"), self.t("dlg_squash_msg_msg"), text=varsayilan_mesaj)
        if not (ok2 and yeni_mesaj.strip()): return
        basarili, sonuc = self.motor.git_squash(adet, yeni_mesaj.strip())
        if basarili:
            if self.motor.has_remotes():
                cevap = QMessageBox.question(self, self.t("dlg_squash_force_push_title"), self.t("dlg_squash_force_push_msg"), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if cevap == QMessageBox.Yes:
                    self.lbl_durum.setStyleSheet("color: #60a5fa; border: none;")
                    self.lbl_durum.setText(self.t("msg_push_bekle"))
                    self._set_ui_lock(False)
                    QApplication.processEvents()
                    self.push_isci = PushIscisi(self.motor.repo_path, force=True)
                    self.push_isci.sonuc_sinyali.connect(self.force_push_tamamlandi)
                    self.push_isci.start()
                else:
                    QMessageBox.information(self, self.t("basarili"), self.t("msg_squash_basarili").format(adet))
            else:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_squash_basarili").format(adet))
        else:
            if sonuc == "working_tree_dirty":
                QMessageBox.warning(self, self.t("hata"), self.t("err_squash_dirty"))
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_squash_hata").format(sonuc))
        self.butonlari_guncelle()

    def git_tag_listele(self):
        self.lbl_durum.setText("Yerel etiketler getiriliyor...")
        QApplication.processEvents()

        basarili, sonuc = self.motor.yerel_taglari_getir()

        if basarili:
            self.konsol.yaz("--- YEREL ETİKETLER ---")
            self.konsol.yaz(sonuc)
            self.konsol.yaz("-----------------------")
            QMessageBox.information(self, "Yerel Etiketler", sonuc)
        else:
            QMessageBox.critical(self, self.t("hata"), f"Etiketler alınamadı:\n{sonuc}")

        self.butonlari_guncelle()

    def yonet_remotes(self):
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose) # Fix Memory Leak
        dialog.setWindowTitle(self.t("dlg_remotes_title"))
        dialog.resize(450, 300)
        layout = QVBoxLayout(dialog)

        liste = QListWidget()
        liste.setStyleSheet("""
            QListWidget { background-color: #2a2a32; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 4px; padding: 5px; }
            QListWidget::item:selected { background-color: #007acc; color: white; }
        """)
        layout.addWidget(liste)

        def listeyi_guncelle():
            liste.clear()
            for r in self.motor.get_remotes_list():
                liste.addItem(r)

        listeyi_guncelle()

        btn_layout = QHBoxLayout()
        btn_ekle = ModernButton(self.t("btn_remote_ekle"), "#28a745")
        btn_sil = ModernButton(self.t("btn_remote_sil"), "#dc3545")
        btn_layout.addWidget(btn_ekle)
        btn_layout.addWidget(btn_sil)
        layout.addLayout(btn_layout)

        def ekle():
            isim, ok = QInputDialog.getText(dialog, self.t("dlg_remotes_title"), self.t("msg_remote_isim"))
            if ok and isim.strip():
                url, ok2 = QInputDialog.getText(dialog, self.t("dlg_remotes_title"), self.t("msg_remote_url"))
                if ok2 and url.strip():
                    basarili, hata = self.motor.add_custom_remote(isim.strip(), url.strip())
                    if basarili:
                        QMessageBox.information(dialog, self.t("basarili"), self.t("msg_remote_basarili"))
                        listeyi_guncelle()
                    else:
                        QMessageBox.critical(dialog, self.t("hata"), hata)

        def sil():
            secili = liste.currentItem()
            if secili:
                isim = secili.text().split(" - ")[0].strip()
                cevap = QMessageBox.question(dialog, self.t("emin_misiniz"), self.t("msg_remote_sil_onay").format(isim), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if cevap == QMessageBox.Yes:
                    basarili, hata = self.motor.remove_remote(isim)
                    if basarili:
                        QMessageBox.information(dialog, self.t("basarili"), self.t("msg_remote_sil_basarili"))
                        listeyi_guncelle()
                    else:
                        QMessageBox.critical(dialog, self.t("hata"), hata)

        btn_ekle.clicked.connect(ekle)
        btn_sil.clicked.connect(sil)

        dialog.exec()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Git_Gui")
    app.setDesktopFileName("Git_Gui")
    
    # Tüm açılır pencereler ve standart widget'lar için global modern karanlık tema
    app.setStyleSheet("""
        QDialog, QMessageBox, QInputDialog, QFileDialog {
            background-color: #1e1e24;
            color: #f5f5f7;
        }
        QDialog QLabel, QMessageBox QLabel {
            color: #f5f5f7;
        }
        QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton {
            background-color: #3f3f46;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 15px;
            min-width: 60px;
            font-weight: bold;
        }
        QDialog QPushButton:hover, QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {
            background-color: #007acc;
        }
        QDialog QLineEdit, QInputDialog QLineEdit {
            background-color: #2a2a32;
            color: white;
            border: 1px solid #3f3f46;
            border-radius: 4px;
            padding: 6px;
        }
        QDialog QComboBox, QInputDialog QComboBox {
            background-color: #3f3f46;
            color: white;
            border: 1px solid #52525b;
            border-radius: 4px;
            padding: 4px;
        }
        QDialog QComboBox QAbstractItemView {
            background-color: #2a2a32;
            color: white;
            selection-background-color: #007acc;
        }
    """)

    font_yolu = str(PROJE_ANA_DIZINI / "font.ttf")
    if os.path.exists(font_yolu):
        font_id = QFontDatabase.addApplicationFont(font_yolu)
        if font_id >= 0:
            font_families = QFontDatabase.applicationFontFamilies(font_id)
            if font_families:
                custom_font = QFont(font_families[0])
                custom_font.setPointSize(12)
                app.setFont(custom_font)
    window = GitGUI()
    window.show()
    sys.exit(app.exec())
