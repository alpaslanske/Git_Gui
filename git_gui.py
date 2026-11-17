#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import webbrowser
import re
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtGui import QIcon, QFont, QColor, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QFileDialog, QDialog,
    QInputDialog, QMessageBox, QTextEdit, QFrame, QSizePolicy, QComboBox, QScrollArea, QLineEdit
)

from git_motoru import GitMotoru
from lang import translate

def get_system_documents_dir():
    if "APPIMAGE" in os.environ:
        return Path(os.environ["APPIMAGE"]).parent
    else:
        return Path(os.path.realpath(__file__)).parent

LocationForDocs = get_system_documents_dir()
PROJE_ANA_DIZINI = LocationForDocs


# ==========================================
# İŞ PARÇACIKLARI (THREADS)
# ==========================================

class UsernameIscisi(QThread):
    sonuc_sinyali = Signal(str)

    def run(self):
        try:
            res = subprocess.run(["gh", "api", "user", "-q", ".login"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                self.sonuc_sinyali.emit(res.stdout.strip())
                return
        except Exception: pass
        try:
            res = subprocess.run(["git", "config", "--get", "github.user"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                self.sonuc_sinyali.emit(res.stdout.strip())
                return
        except Exception: pass
        self.sonuc_sinyali.emit("")

class SurumIscisi(QThread):
    sonuc_sinyali = Signal(bool, str)
    log_sinyali = Signal(str)

    def __init__(self, repo_path, tag_adi, aciklama, dosya_yolu, language="tr"):
        super().__init__()
        self.repo_path = repo_path
        self.tag_adi = tag_adi
        self.aciklama = aciklama
        self.dosya_yolu = dosya_yolu
        self.language = language

    def run(self):
        motor = GitMotoru(self.language)
        motor.set_path(self.repo_path)
        motor.log_callback = self.log_sinyali.emit
        basarili, hata = motor.git_tag_olustur(self.tag_adi, self.aciklama, self.dosya_yolu)
        self.sonuc_sinyali.emit(basarili, hata)

class KlonlamaIscisi(QThread):
    sonuc_sinyali = Signal(bool, str, str)
    log_sinyali = Signal(str)
    def __init__(self, url, hedef_yol, branch="", language="tr"):
        super().__init__()
        self.url = url
        self.hedef_yol = hedef_yol
        self.branch = branch
        self.language = language
    def run(self):
        motor = GitMotoru(self.language)
        motor.log_callback = self.log_sinyali.emit
        try:
            basarili, cikti = motor.git_clone(self.url, self.hedef_yol, self.branch)
            self.sonuc_sinyali.emit(basarili, cikti, self.hedef_yol)
        except Exception as e:
            self.sonuc_sinyali.emit(False, str(e), self.hedef_yol)

class UzakDalIscisi(QThread):
    sonuc_sinyali = Signal(bool, object, str)
    log_sinyali = Signal(str)

    def __init__(self, url, language="tr"):
        super().__init__()
        self.url = url
        self.language = language

    def run(self):
        motor = GitMotoru(self.language)
        motor.log_callback = self.log_sinyali.emit
        basarili, sonuc = motor.get_remote_branches(self.url)
        self.sonuc_sinyali.emit(basarili, sonuc, self.url)


class PushIscisi(QThread):
    sonuc_sinyali = Signal(bool, str)
    log_sinyali = Signal(str)

    def __init__(self, repo_path, force=False, language="tr"):
        super().__init__()
        self.repo_path = repo_path
        self.force = force
        self.language = language

    def run(self):
        motor = GitMotoru(self.language)
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

    def __init__(self, repo_path, language="tr"):
        super().__init__()
        self.repo_path = repo_path
        self.language = language

    def run(self):
        motor = GitMotoru(self.language)
        motor.set_path(self.repo_path)
        motor.log_callback = self.log_sinyali.emit
        basarili, sonuc = motor.git_fetch_kontrol()
        self.sonuc_sinyali.emit(basarili, sonuc)

class PullIscisi(QThread):
    sonuc_sinyali = Signal(bool, str)
    log_sinyali = Signal(str)

    def __init__(self, repo_path, language="tr"):
        super().__init__()
        self.repo_path = repo_path
        self.language = language

    def run(self):
        try:
            motor = GitMotoru(self.language)
            if not motor.set_path(self.repo_path):
                self.sonuc_sinyali.emit(False, translate(self.language, "msg_status_no_repo"))
                return
            res = subprocess.run(
                ["git", "pull"], cwd=self.repo_path, env=motor.get_git_env(),
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=300
            )
            if res.returncode == 0:
                self.sonuc_sinyali.emit(True, res.stdout.strip())
            else:
                self.sonuc_sinyali.emit(False, res.stderr.strip())
        except Exception as e:
            self.sonuc_sinyali.emit(False, str(e))

class GitOperationIscisi(QThread):
    sonuc_sinyali = Signal(bool, object)
    log_sinyali = Signal(str)

    def __init__(self, repo_path, operation, language="tr"):
        super().__init__()
        self.repo_path = repo_path
        self.operation = operation
        self.language = language

    def run(self):
        motor = GitMotoru(self.language)
        if not motor.set_path(self.repo_path):
            self.sonuc_sinyali.emit(False, translate(self.language, "msg_status_no_repo"))
            return
        motor.log_callback = self.log_sinyali.emit
        try:
            self.sonuc_sinyali.emit(True, self.operation(motor))
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
class ActionsTemizleIscisi(QThread):
    sonuc_sinyali = Signal(bool, str)
    log_sinyali = Signal(str)

    def __init__(self, repo_path, language="tr"):
        super().__init__()
        self.repo_path = repo_path
        self.language = language

    def t(self, key):
        return translate(self.language, key)

    def run(self):
        try:
            self.log_sinyali.emit(self.t("log_actions_scan"))
            res = subprocess.run(
                ["gh", "run", "list", "--status", "completed", "--limit", "500", "--json", "databaseId", "-q", ".[].databaseId"],
                cwd=self.repo_path, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            if res.returncode != 0:
                self.sonuc_sinyali.emit(False, res.stderr.strip() or self.t("msg_actions_cli_error"))
                return

            run_ids = [r.strip() for r in res.stdout.strip().splitlines() if r.strip()]
            if not run_ids:
                self.sonuc_sinyali.emit(True, "0")
                return

            silinen_sayisi = 0
            for run_id in run_ids:
                del_res = subprocess.run(
                    ["gh", "run", "delete", run_id],
                    cwd=self.repo_path, capture_output=True, text=True, encoding="utf-8", errors="replace"
                )
                if del_res.returncode == 0:
                    silinen_sayisi += 1
                    self.log_sinyali.emit(self.t("log_actions_deleted").format(run_id))

            self.sonuc_sinyali.emit(True, str(silinen_sayisi))
        except FileNotFoundError:
            self.sonuc_sinyali.emit(False, self.t("msg_gh_not_installed"))
        except Exception as e:
            self.sonuc_sinyali.emit(False, str(e))

# ==========================================
# ARAYÜZ (UI) BİLEŞENLERİ
# ==========================================

class ModernButton(QPushButton):
    def __init__(self, text, bg_color, text_color="white"):
        super().__init__(text)
        self.bg_color = bg_color
        self.text_color = text_color
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.update_style()

    def update_style(self):
        color_obj = QColor(self.bg_color)
        h, s, l, a = color_obj.getHsl()
        l = min(255, int(l * 1.15))
        hover_color = QColor.fromHsl(h, s, l, a).name()

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.bg_color};
                color: {self.text_color};
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

class CakismaCozucuDialog(QDialog):
    def __init__(self, parent=None, motor=None, lang_func=None):
        super().__init__(parent)
        self.motor = motor
        self.t = lang_func
        self.secili_dosya_yolu = None

        self.setWindowTitle(self.t("dlg_conflict_title"))
        self.resize(1000, 600)
        self.setModal(True)
        self.setObjectName("CardFlat")

        layout = QHBoxLayout(self)

        sol_layout = QVBoxLayout()
        lbl_dosyalar = QLabel(self.t("lbl_conflict_files"))
        lbl_dosyalar.setObjectName("SectionLabel")
        sol_layout.addWidget(lbl_dosyalar)

        self.list_dosyalar = QListWidget()
        self.list_dosyalar.itemClicked.connect(self.dosya_secildi)
        sol_layout.addWidget(self.list_dosyalar)

        self.btn_tamamla = ModernButton(self.t("btn_complete_merge"), "Primary")
        self.btn_tamamla.clicked.connect(self.birlestirmeyi_tamamla)
        self.btn_tamamla.setEnabled(False)
        sol_layout.addWidget(self.btn_tamamla)

        sag_layout = QVBoxLayout()
        buton_layout = QHBoxLayout()

        self.btn_mevcut_koru = ModernButton(self.t("btn_conflict_keep_current"), "Primary")
        self.btn_mevcut_koru.setStyleSheet("background-color: #059669; color: white;")
        self.btn_mevcut_koru.clicked.connect(lambda: self.kod_koru("mevcut"))

        self.btn_gelen_koru = ModernButton(self.t("btn_conflict_keep_incoming"), "Primary")
        self.btn_gelen_koru.setStyleSheet("background-color: #2563eb; color: white;")
        self.btn_gelen_koru.clicked.connect(lambda: self.kod_koru("gelen"))

        self.btn_ikisini_koru = ModernButton(self.t("btn_conflict_keep_both"), "Primary")
        self.btn_ikisini_koru.setStyleSheet("background-color: #7c3aed; color: white;")
        self.btn_ikisini_koru.clicked.connect(lambda: self.kod_koru("ikisi"))

        self.btn_cozuldu = ModernButton(self.t("btn_mark_resolved"), "Primary")
        self.btn_cozuldu.clicked.connect(self.cozuldu_isaretle)

        buton_layout.addWidget(self.btn_mevcut_koru)
        buton_layout.addWidget(self.btn_gelen_koru)
        buton_layout.addWidget(self.btn_ikisini_koru)
        buton_layout.addStretch()
        buton_layout.addWidget(self.btn_cozuldu)
        sag_layout.addLayout(buton_layout)

        self.kod_editor = QTextEdit()
        self.kod_editor.setLineWrapMode(QTextEdit.NoWrap)
        self.kod_editor.setStyleSheet("font-family: Consolas, monospace; font-size: 13px; background-color: #101419; color: #e1e6ea;")
        sag_layout.addWidget(self.kod_editor)

        layout.addLayout(sol_layout, 1)
        layout.addLayout(sag_layout, 3)

        self.cakismalari_yukle()

    def cakismalari_yukle(self):
        self.list_dosyalar.clear()
        dosyalar = self.motor.get_conflicted_files()
        if not dosyalar:
            self.btn_tamamla.setEnabled(True)
        else:
            for dosya in dosyalar:
                self.list_dosyalar.addItem(dosya)

    def dosya_secildi(self, item):
        self.secili_dosya_yolu = os.path.join(self.motor.repo_path, item.text())
        if os.path.exists(self.secili_dosya_yolu):
            with open(self.secili_dosya_yolu, 'r', encoding='utf-8', errors='replace') as f:
                icerik = f.read()
            self.kod_editor.setPlainText(icerik)
            self.renklendir()

    def renklendir(self):
        icerik = self.kod_editor.toPlainText()
        icerik = icerik.replace("<", "&lt;").replace(">", "&gt;")
        icerik = icerik.replace("&lt;&lt;&lt;&lt;&lt;&lt;&lt;", "<span style='background-color: #4A1620; color: white;'>&lt;&lt;&lt;&lt;&lt;&lt;&lt;")
        icerik = icerik.replace("=======", "</span><span style='background-color: #0E7490; color: white;'>=======")
        icerik = icerik.replace("&gt;&gt;&gt;&gt;&gt;&gt;&gt;", "</span><span style='background-color: #164E63; color: white;'>&gt;&gt;&gt;&gt;&gt;&gt;&gt;</span>")
        self.kod_editor.setHtml(icerik.replace("\n", "<br>"))

    def kod_koru(self, secim):
        icerik = self.kod_editor.toPlainText()
        pattern = r"<<<<<<<[^\n]*\n(.*?)=======\n(.*?)>>>>>>>[^\n]*(?:\n|$)"

        def replacer(match):
            mevcut = match.group(1)
            gelen = match.group(2)
            if secim == "mevcut":
                return mevcut
            elif secim == "gelen":
                return gelen
            else:
                return mevcut + gelen

        yeni_icerik = re.sub(pattern, replacer, icerik, flags=re.DOTALL)
        self.kod_editor.setPlainText(yeni_icerik)
    def cozuldu_isaretle(self):
        if not self.secili_dosya_yolu: return
        yeni_icerik = self.kod_editor.toPlainText()
        with open(self.secili_dosya_yolu, 'w', encoding='utf-8') as f:
            f.write(yeni_icerik)

        if not self.motor.mark_resolved(self.secili_dosya_yolu):
            QMessageBox.critical(self, self.t("hata"), self.t("msg_conflict_save_error"))
            return
        QMessageBox.information(self, "Git", self.t("msg_conflict_saved"))

        if self.list_dosyalar.currentRow() != -1:
            self.list_dosyalar.takeItem(self.list_dosyalar.currentRow())
        self.kod_editor.clear()

        if self.list_dosyalar.count() == 0:
            self.btn_tamamla.setEnabled(True)

    def birlestirmeyi_tamamla(self):
        QMessageBox.information(self, "Git", self.t("msg_all_resolved"))
        self.accept()

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
        self.resize(1300, 810)
        self.setStyleSheet("QMainWindow { background-color: #1e1e24; }")

        sistem_ikonu = QIcon.fromTheme("git", QIcon.fromTheme("vcs-git", QIcon.fromTheme("git-gui")))
        if sistem_ikonu.isNull():
            icon_path = PROJE_ANA_DIZINI / "icon.png"
            if icon_path.exists():
                sistem_ikonu = QIcon(str(icon_path))
        self.setWindowIcon(sistem_ikonu)

        self.motor = GitMotoru(self.aktif_lang)
        self.setup_ui()
        self.motor.log_callback = self.konsol.yaz

        self.ayarlari_yukle()
        self.metinleri_guncelle()
        self.konsol.yaz(self.t("konsol_hazir"))

    def t(self, anahtar):
        return translate(self.aktif_lang, anahtar)

    def ayarlari_yukle(self):
        if not self.settings_file.exists():
            self.butonlari_guncelle()
            return
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                ayarlar = json.load(f)
            kayitli_dil = ayarlar.get("language", "tr")
            self.aktif_lang = kayitli_dil
            self.motor.language = kayitli_dil
            self.combo_lang.blockSignals(True)
            self.combo_lang.setCurrentIndex(1 if kayitli_dil == "en" else 0)
            self.combo_lang.blockSignals(False)

            self.varsayilan_arama_dizini = ayarlar.get("default_search_path", "")

            self.github_kullanici_adi = ayarlar.get("github_username", "")
            if not self.github_kullanici_adi:
                self.otomatik_kullanici_adi_baslat()

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
            print(self.t("log_settings_load_error").format(e))
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
            print(self.t("log_settings_save_error").format(e))

    def otomatik_kullanici_adi_baslat(self):
        self.user_isci = UsernameIscisi()
        self.user_isci.sonuc_sinyali.connect(self.otomatik_kullanici_adi_tamamlandi)
        self.user_isci.finished.connect(self.arka_plan_durumu_guncelle)
        self.user_isci.start()
        self.arka_plan_durumu_guncelle()

    def otomatik_kullanici_adi_tamamlandi(self, username):
        if username:
            self.github_kullanici_adi = username
            self.ayarlari_kaydet()
    def otomatik_kullanici_adi_bul(self):
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
        return f"https://github.com{self.github_kullanici_adi}/{repo_adi}.git"

    def lang_degistir(self, index):
        self.aktif_lang = "tr" if index == 0 else "en"
        self.motor.language = self.aktif_lang
        self.metinleri_guncelle()
        self.ayarlari_kaydet()

    def metinleri_guncelle(self):
        self.setWindowTitle(self.t("pencere_baslik"))
        self.konsol.lbl_baslik.setText(self.t("lbl_konsol"))
        self.combo_repos.setItemText(0, self.t("combo_repo_history"))
        self.combo_branches.setItemText(0, self.t("combo_dal_sec"))
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
        self.btn_pull.setText(self.t("btn_pull"))
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
        self.btn_clean_actions.setText(self.t("btn_clean_actions"))

        self.btn_restore.setText(self.t("btn_restore"))
        self.btn_stash.setText(self.t("btn_stash"))
        self.btn_stash_pop.setText(self.t("btn_stash_pop"))


        self.arka_plan_durumu_guncelle()

        if self.combo_branches.count() == 1:
            self.combo_branches.setItemText(0, self.t("combo_dal_sec"))

        if not self.motor.repo_path:
            self.lbl_durum.setText(self.t("lbl_durum_bekleniyor"))
        else:
            self.butonlari_guncelle()

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange:
            if self.isActiveWindow():
                if hasattr(self, 'motor') and self.motor.repo_path:
                    self.butonlari_guncelle()
        super().changeEvent(event)

    def setup_ui(self):
        central_widget = QWidget()
        ana_yatay_layout = QHBoxLayout(central_widget)
        ana_yatay_layout.setContentsMargins(0, 0, 0, 0)
        ana_yatay_layout.setSpacing(0)

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
        top_layout.setContentsMargins(10, 10, 10, 6)
        top_layout.setSpacing(6)

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
        self.combo_repos.addItem(self.t("combo_repo_history"))
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
        self.combo_branches.addItem(self.t("combo_dal_sec"))
        self.combo_branches.currentIndexChanged.connect(self.dal_degistir)
        secim_layout.addWidget(self.combo_branches, 1)
        top_layout.addLayout(secim_layout)

        self.lbl_durum = QLabel("") # Ekrana eklenmiyor, sadece eski referansların hata vermemesi için

        self.lbl_bg_durum = QLabel("")
        bg_font = self.lbl_bg_durum.font()
        bg_font.setBold(True)
        bg_font.setPointSize(11)
        self.lbl_bg_durum.setFont(bg_font)
        self.lbl_bg_durum.setAlignment(Qt.AlignCenter)
        top_layout.addWidget(self.lbl_bg_durum, 0, Qt.AlignCenter)

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

        del_roll_layout = QHBoxLayout()
        del_roll_layout.setSpacing(10)
        self.btn_delete_commit = ModernButton("", "#b91c1c")
        self.btn_delete_commit.clicked.connect(self.git_commit_sil)
        del_roll_layout.addWidget(self.btn_delete_commit)

        self.btn_rollback = ModernButton("", "#dc3545")
        self.btn_rollback.clicked.connect(self.git_rollback)
        del_roll_layout.addWidget(self.btn_rollback)
        sol_layout.addLayout(del_roll_layout)

        branch_crud_layout = QHBoxLayout()
        branch_crud_layout.setSpacing(10)
        self.btn_yeni_dal = ModernButton("", "#10b981")
        self.btn_yeni_dal.clicked.connect(self.yeni_dal_olustur)
        branch_crud_layout.addWidget(self.btn_yeni_dal)

        self.btn_dal_sil = ModernButton("", "#f43f5e")
        self.btn_dal_sil.clicked.connect(self.dal_sil)
        branch_crud_layout.addWidget(self.btn_dal_sil)
        sol_layout.addLayout(branch_crud_layout)

        merge_restore_layout = QHBoxLayout()
        merge_restore_layout.setSpacing(10)

        self.btn_dal_birlestir = ModernButton("", "#8b5cf6")
        self.btn_dal_birlestir.clicked.connect(self.dal_birlestir)
        merge_restore_layout.addWidget(self.btn_dal_birlestir)

        self.btn_restore = ModernButton("", "#f59e0b", "#4D4D4D")
        self.btn_restore.clicked.connect(self.git_restore)
        merge_restore_layout.addWidget(self.btn_restore)

        sol_layout.addLayout(merge_restore_layout)

        rebase_squash_layout = QHBoxLayout()
        rebase_squash_layout.setSpacing(10)
        self.btn_rebase = ModernButton("", "#475569")
        self.btn_rebase.clicked.connect(self.git_rebase)
        rebase_squash_layout.addWidget(self.btn_rebase)

        self.btn_squash = ModernButton("", "#0891b2")
        self.btn_squash.clicked.connect(self.git_squash)
        rebase_squash_layout.addWidget(self.btn_squash)
        sol_layout.addLayout(rebase_squash_layout)

        # 7. Satır: Stash | Stash Pop (İkili)
        stash_layout = QHBoxLayout()
        stash_layout.setSpacing(10)
        self.btn_stash = ModernButton("", "#64748b")
        self.btn_stash.clicked.connect(self.git_stash_yap)
        stash_layout.addWidget(self.btn_stash)

        self.btn_stash_pop = ModernButton("", "#0d9488")
        self.btn_stash_pop.clicked.connect(self.git_stash_pop_yap)
        stash_layout.addWidget(self.btn_stash_pop)
        sol_layout.addLayout(stash_layout)


        orta_layout.addLayout(sol_layout, 1)

        sag_layout = QVBoxLayout()
        sag_layout.setSpacing(10)

        self.btn_login = ModernButton("", "#0284c7")
        self.btn_login.clicked.connect(self.github_login)
        sag_layout.addWidget(self.btn_login)

        remotes_delete_layout = QHBoxLayout()
        remotes_delete_layout.setSpacing(10)
        self.btn_remotes = ModernButton("", "#3b82f6")
        self.btn_remotes.clicked.connect(self.yonet_remotes)
        remotes_delete_layout.addWidget(self.btn_remotes)

        self.btn_delete_repo = ModernButton("", "#991b1b")
        self.btn_delete_repo.clicked.connect(self.repo_sil)
        remotes_delete_layout.addWidget(self.btn_delete_repo)
        sag_layout.addLayout(remotes_delete_layout)

        create_clone_layout = QHBoxLayout()
        create_clone_layout.setSpacing(10)
        self.btn_create_repo = ModernButton("", "#0f766e")
        self.btn_create_repo.clicked.connect(self.github_repo_olustur)
        create_clone_layout.addWidget(self.btn_create_repo)

        self.btn_clone = ModernButton("", "#0369a1")
        self.btn_clone.clicked.connect(self.github_repo_indir)
        create_clone_layout.addWidget(self.btn_clone)
        sag_layout.addLayout(create_clone_layout)

        fetch_pull_layout = QHBoxLayout()
        fetch_pull_layout.setSpacing(10)
        self.btn_fetch = ModernButton("", "#28a745")
        self.btn_fetch.clicked.connect(self.git_fetch_kontrol)
        fetch_pull_layout.addWidget(self.btn_fetch)

        self.btn_pull = ModernButton("", "#0ea5e9")
        self.btn_pull.clicked.connect(self.git_pull_baslat)
        fetch_pull_layout.addWidget(self.btn_pull)
        sag_layout.addLayout(fetch_pull_layout)

        tag_actions_layout = QHBoxLayout()
        tag_actions_layout.setSpacing(10)
        self.btn_tag = ModernButton("", "#4b5563")
        self.btn_tag.clicked.connect(self.git_sürüm_olustur)
        tag_actions_layout.addWidget(self.btn_tag)

        self.btn_clean_actions = ModernButton("", "#6366f1")
        self.btn_clean_actions.clicked.connect(self.actions_gecmisi_temizle)
        tag_actions_layout.addWidget(self.btn_clean_actions)
        sag_layout.addLayout(tag_actions_layout)

        self.btn_push = ModernButton("", "#8b5cf6")
        self.btn_push.clicked.connect(self.git_push)
        sag_layout.addWidget(self.btn_push)

        sag_layout.addStretch()

        orta_layout.addLayout(sag_layout, 1)
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
        from PySide6.QtCore import QSize
        baslangic_genislik = self.yan_panel.width()
        hedef_genislik = 250 if baslangic_genislik == 0 else 0
        fark = hedef_genislik - baslangic_genislik

        self.anim = QPropertyAnimation(self.yan_panel, b"minimumWidth")
        self.anim.setDuration(250)
        self.anim.setStartValue(baslangic_genislik)
        self.anim.setEndValue(hedef_genislik)
        self.anim.setEasingCurve(QEasingCurve.InOutQuart)

        self.anim_max = QPropertyAnimation(self.yan_panel, b"maximumWidth")
        self.anim_max.setDuration(250)
        self.anim_max.setStartValue(baslangic_genislik)
        self.anim_max.setEndValue(hedef_genislik)
        self.anim_max.setEasingCurve(QEasingCurve.InOutQuart)

        mevcut_boyut = self.size()
        hedef_boyut = QSize(mevcut_boyut.width() + fark, mevcut_boyut.height())

        self.anim_win = QPropertyAnimation(self, b"size")
        self.anim_win.setDuration(250)
        self.anim_win.setStartValue(mevcut_boyut)
        self.anim_win.setEndValue(hedef_boyut)
        self.anim_win.setEasingCurve(QEasingCurve.InOutQuart)

        self.anim.start()
        self.anim_max.start()
        self.anim_win.start()

    def yan_panel_guncelle(self):
        mevcut_buton_sayisi = self.scroll_layout.count()
        gecmis_sayisi = len(self.repo_history)

        for i in range(max(mevcut_buton_sayisi, gecmis_sayisi)):
            if i < gecmis_sayisi:
                repo_path = self.repo_history[i]
                if not repo_path or not os.path.exists(repo_path):
                    continue
                klasor_adi = os.path.basename(os.path.abspath(repo_path))

                if hasattr(self.motor, 'repo_path') and self.motor.repo_path == repo_path:
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
                            font-size: 14px;
                        }
                    """
                    gosterim_adi = f"📂 {klasor_adi}"
                else:
                    buton_stili = """
                        QPushButton {
                            background-color: transparent;
                            color: #a1a1aa;
                            border: none;
                            border-left: 4px solid transparent;
                            border-radius: 4px;
                            padding: 10px 15px;
                            text-align: left;
                            font-weight: bold;
                            font-size: 14px;
                        }
                        QPushButton:hover {
                            background-color: #04486e;
                            color: #f4f4f5;
                            border-left: 4px solid #71717a;
                        }
                    """
                    gosterim_adi = f"📁 {klasor_adi}"

                if i < mevcut_buton_sayisi:
                    btn = self.scroll_layout.itemAt(i).widget()
                    btn.setText(gosterim_adi)
                    btn.setToolTip(repo_path)
                    btn.setStyleSheet(buton_stili)
                    btn.show()
                    try: btn.clicked.disconnect()
                    except: pass
                    btn.clicked.connect(lambda checked=False, p=repo_path: self.yan_panelden_repo_sec(p))
                else:
                    btn = QPushButton(gosterim_adi)
                    btn.setToolTip(repo_path)
                    btn.setStyleSheet(buton_stili)
                    btn.setCursor(Qt.PointingHandCursor)
                    btn.clicked.connect(lambda checked=False, p=repo_path: self.yan_panelden_repo_sec(p))
                    self.scroll_layout.addWidget(btn)
            else:
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
            QMessageBox.warning(self, self.t("hata"), self.t("err_klasor_yok"))
            if repo_path in self.repo_history:
                self.repo_history.remove(repo_path)
                self.gecmise_repo_ekle(self.motor.repo_path if self.motor.repo_path else "")

    def butonlari_guncelle(self):
        self.combo_repos.setEnabled(True)
        self.btn_sec.setEnabled(True)
        self.btn_toggle_sidebar.setEnabled(True)
        self.yan_panel.setEnabled(True)
        if not self.motor.repo_path:
            self.lbl_banner.hide()
            self.lbl_durum.setText("")
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
            self.lbl_durum.setText("")

            if is_clean is None:
                self.lbl_banner.setStyleSheet("QLabel { background-color: #b45309; color: white; border-radius: 4px; padding: 6px; }")
                self.lbl_banner.setText(self.t("status_error"))
            elif is_clean:
                self.lbl_banner.setStyleSheet("QLabel { background-color: #22c55e; color: white; border-radius: 4px; padding: 6px; }")
                self.lbl_banner.setText(self.t("banner_clean"))
            else:
                self.lbl_banner.setStyleSheet("QLabel { background-color: #ef4444; color: white; border-radius: 4px; padding: 6px; }")
                self.lbl_banner.setText(self.t("banner_dirty"))
        else:
            self.lbl_banner.show()
            self.lbl_banner.setStyleSheet("QLabel { background-color: #64748b; color: white; border-radius: 4px; padding: 6px; }")
            self.lbl_banner.setText(self.t("banner_not_git"))
            self.lbl_durum.setText("")
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
        self.btn_pull.setEnabled(is_git)
        self.btn_push.setEnabled(is_git)
        self.btn_tag.setEnabled(is_git)
        self.btn_remotes.setEnabled(is_git)
        self.combo_branches.setEnabled(is_git)
        self.btn_yeni_dal.setEnabled(is_git)
        self.btn_dal_sil.setEnabled(is_git)
        self.btn_dal_birlestir.setEnabled(is_git)
        self.btn_clean_actions.setEnabled(is_git)
        self.btn_restore.setEnabled(is_git)
        self.btn_stash.setEnabled(is_git)
        self.btn_stash_pop.setEnabled(is_git)

    def _start_git_operation(self, operation, callback, status_text):
        self.lbl_durum.setText(status_text)
        self._set_ui_lock(False)
        self.btn_init.setEnabled(False)
        self.btn_clone.setEnabled(False)
        self.btn_sec.setEnabled(False)
        self.btn_toggle_sidebar.setEnabled(False)
        self.yan_panel.setEnabled(False)
        self.combo_repos.setEnabled(False)
        self.operation_isci = GitOperationIscisi(self.motor.repo_path, operation, self.aktif_lang)
        if not hasattr(self, "_git_operation_workers"):
            self._git_operation_workers = []
        self._git_operation_workers.append(self.operation_isci)
        self.operation_isci.log_sinyali.connect(self.konsol.yaz)
        self.operation_isci.sonuc_sinyali.connect(callback)
        self.operation_isci.finished.connect(
            lambda worker=self.operation_isci: self._git_operation_finished(worker)
        )
        self.operation_isci.finished.connect(self.arka_plan_durumu_guncelle)
        self.operation_isci.start()
        self.arka_plan_durumu_guncelle()

    def _git_operation_finished(self, worker):
        if hasattr(self, "_git_operation_workers") and worker in self._git_operation_workers:
            self._git_operation_workers.remove(worker)

    def git_fetch_kontrol(self):
        self.konsol.yaz(self.t("log_fetch_wait"))
        self._set_ui_lock(False)
        QApplication.processEvents()

        self.fetch_isci = FetchIscisi(self.motor.repo_path, self.aktif_lang)
        self.fetch_isci.log_sinyali.connect(self.konsol.yaz)
        self.fetch_isci.sonuc_sinyali.connect(self.fetch_tamamlandi)
        self.fetch_isci.finished.connect(self.arka_plan_durumu_guncelle)
        self.fetch_isci.start()
        self.arka_plan_durumu_guncelle()

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
                cevap = QMessageBox.question(
                    self, self.t("basarili"),
                    f"{self.t('fetch_geride').format(geri)}\n\n{self.t('msg_fetch_pull_prompt')}",
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
                cevap = QMessageBox.question(
                    self, self.t("basarili"),
                    f"{self.t('fetch_farkli').format(ileri, geri)}\n\n{self.t('msg_fetch_merge_prompt')}",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                )
                if cevap == QMessageBox.Yes:
                    self.git_pull_baslat()
                else:
                    self.butonlari_guncelle()

    def git_pull_baslat(self):
        cevap = QMessageBox.question(
            self,
            self.t("emin_misiniz"),
            self.t("msg_pull_onay"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if cevap != QMessageBox.Yes:
            return

        self.konsol.yaz(self.t("log_pull_start"))
        self._set_ui_lock(False)
        QApplication.processEvents()

        self.pull_isci = PullIscisi(self.motor.repo_path, self.aktif_lang)
        self.pull_isci.log_sinyali.connect(self.konsol.yaz)
        self.pull_isci.sonuc_sinyali.connect(self.pull_tamamlandi)
        self.pull_isci.finished.connect(self.arka_plan_durumu_guncelle)
        self.pull_isci.start()
        self.arka_plan_durumu_guncelle()

    def pull_tamamlandi(self, basarili, mesaj):
        self.butonlari_guncelle()
        if basarili:
            self.konsol.yaz(mesaj)
            QMessageBox.information(self, self.t("basarili"), self.t("msg_pull_success"))
        else:
            self.konsol.yaz(self.t("log_pull_error").format(mesaj))
            if self.motor.is_in_conflict():
                QMessageBox.warning(
                    self,
                    self.t("hata"),
                    self.t("msg_pull_conflict")
                )
                dialog = CakismaCozucuDialog(self, self.motor, self.t)
                dialog.exec()
                dialog.deleteLater()
                self.git_commit()
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_pull_error").format(mesaj))

    def gecmise_repo_ekle(self, path):
        if not hasattr(self, 'repo_history'):
            self.repo_history = []

        path = str(path)
        if not self.motor.git_klasoru_mu(path):
            return

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
                QMessageBox.warning(self, self.t("hata"), self.t("err_klasor_yok"))
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
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setMinimumSize(780, 600)
        dialog.resize(780, 600)
        dialog.setViewMode(QFileDialog.Detail)

        from PySide6.QtCore import QStorageInfo, QUrl
        kisayollar = dialog.sidebarUrls()

        for disk in QStorageInfo.mountedVolumes():
            if disk.isValid() and disk.isReady():
                fs_type = bytes(disk.fileSystemType()).decode("utf-8", errors="ignore")
                if fs_type not in ["tmpfs", "devtmpfs", "proc", "sysfs", "cgroup", "squashfs", "overlay", "efivarfs", "tracefs"]:
                    disk_url = QUrl.fromLocalFile(disk.rootPath())
                    if disk_url not in kisayollar:
                        kisayollar.append(disk_url)

        dialog.setSidebarUrls(kisayollar)

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
        turler = [self.t("visibility_public"), self.t("visibility_private")]
        gorunurluk, ok = QInputDialog.getItem(
            self, self.t("dlg_visibility_title"), self.t("dlg_visibility_msg"), turler, 0, False
        )
        if not ok: return
        tur = "public" if gorunurluk == self.t("visibility_public") else "private"
        self._pending_repo_creation_name = repo_adi
        self._start_git_operation(
            lambda motor: motor.github_repo_olustur(repo_adi, tur),
            self.github_repo_olusturma_tamamlandi,
            self.t("msg_creating_repo")
        )

    def github_repo_olusturma_tamamlandi(self, worker_ok, sonuc):
        if worker_ok:
            basarili, cikti = sonuc
        else:
            basarili, cikti = False, sonuc
        if basarili:
            QMessageBox.information(
                self, self.t("basarili"),
                self.t("msg_repo_created").format(self._pending_repo_creation_name)
            )
        else:
            QMessageBox.critical(self, self.t("hata"), self.t("err_repo_create").format(cikti))
            self.konsol.yaz(self.t("log_generic_error").format(cikti))
        self.butonlari_guncelle()

    def github_login(self):
        try:
            self.konsol.yaz(self.t("msg_baglaniliyor"))
            self._set_ui_lock(False)
            self.btn_login.setEnabled(False)
            QApplication.processEvents()
            self.login_isci = LoginIscisi()
            self.login_isci.kod_sinyali.connect(self.login_kod_goster)
            self.login_isci.sonuc_sinyali.connect(self.login_tamamlandi)
            self.login_isci.finished.connect(self.arka_plan_durumu_guncelle)
            self.login_isci.start()
            self.arka_plan_durumu_guncelle()

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
                QMessageBox.critical(self, self.t("hata"), self.t("msg_login_error").format(hata_kodu))
        self.butonlari_guncelle()

    def git_init(self):
        if self.motor.git_init():
            QMessageBox.information(self, self.t("basarili"), self.t("msg_init_basarili"))
            self.butonlari_guncelle()
            self.ayarlari_kaydet()

    def git_commit(self):
        commit_mesaji, ok = QInputDialog.getText(self, self.t("commit_baslik"), self.t("commit_soru"))
        if ok and commit_mesaji.strip():
            self._start_git_operation(
                lambda motor: motor.git_commit(commit_mesaji),
                self.commit_tamamlandi,
                self.t("msg_commit_bekle")
            )

    def commit_tamamlandi(self, worker_ok, sonuc):
        if worker_ok and sonuc:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_commit_basarili"))
        else:
            QMessageBox.critical(self, self.t("hata"), self.t("msg_commit_hata"))
        self.butonlari_guncelle()

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

            self.push_isci = PushIscisi(self.motor.repo_path, force=False, language=self.aktif_lang)
            self.push_isci.log_sinyali.connect(self.konsol.yaz)
            self.push_isci.sonuc_sinyali.connect(self.push_tamamlandi)
            self.push_isci.finished.connect(self.arka_plan_durumu_guncelle)
            self.push_isci.start()
            self.arka_plan_durumu_guncelle()

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
                    self.push_isci = PushIscisi(self.motor.repo_path, force=True, language=self.aktif_lang)
                    self.push_isci.log_sinyali.connect(self.konsol.yaz)
                    self.push_isci.sonuc_sinyali.connect(self.force_push_tamamlandi)
                    self.push_isci.finished.connect(self.arka_plan_durumu_guncelle)
                    self.push_isci.start()
                    self.arka_plan_durumu_guncelle()
            else:
                self._push_hata_goster(hata_mesaji)

    def force_push_tamamlandi(self, basarili, mesaj):
        self.butonlari_guncelle()
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_force_push_basarili"))
        else:
            self._push_hata_goster(str(mesaj), force=True)

    def _push_hata_goster(self, hata_mesaji, force=False):
        hata_kucuk = hata_mesaji.casefold()
        if "workflow" in hata_kucuk and "scope" in hata_kucuk:
            QMessageBox.warning(
                self, self.t("hata"), self.t("msg_workflow_scope_required")
            )
            self.konsol.yaz(hata_mesaji)
            return
        if force:
            QMessageBox.critical(
                self, self.t("hata"), self.t("msg_force_push_error").format(hata_mesaji)
            )
        else:
            QMessageBox.critical(
                self, self.t("hata"), self.t("msg_push_hata").format(hata_mesaji)
            )

    def git_restore(self):
        cevap = QMessageBox.warning(
            self,
            self.t("emin_misiniz"),
            self.t("msg_restore_onay"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if cevap == QMessageBox.Yes:
            self._start_git_operation(
                lambda motor: motor.git_restore_all(),
                self.restore_tamamlandi,
                self.t("msg_restore_bekle")
            )

    def restore_tamamlandi(self, worker_ok, sonuc):
        if worker_ok:
            basarili, hata = sonuc
        else:
            basarili, hata = False, sonuc
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_restore_basarili"))
        else:
            QMessageBox.critical(self, self.t("hata"), self.t("msg_cancel_failed").format(hata))
        self.butonlari_guncelle()

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
            self._start_git_operation(
                lambda motor: motor.git_rollback(hedef_hash),
                self.rollback_tamamlandi,
                self.t("msg_rollback_bekle")
            )

    def rollback_tamamlandi(self, worker_ok, sonuc):
        if worker_ok and sonuc:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_rollback_basarili"))
        else:
            hata = sonuc if not worker_ok else self.t("msg_rollback_hata")
            QMessageBox.critical(self, self.t("hata"), str(hata))
        self.butonlari_guncelle()
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
            self._start_git_operation(
                lambda motor: motor.git_commit_sil(hedef_hash),
                self.commit_sil_tamamlandi,
                self.t("msg_rebase_bekle")
            )

    def commit_sil_tamamlandi(self, worker_ok, sonuc):
        if not worker_ok:
            basarili, sebep = False, sonuc
        else:
            basarili, sebep = sonuc
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_delete_commit_basarili"))
        elif sebep == "root_commit":
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
            if not basarili: hatalar.append(self.t("msg_local_delete_error").format(err))
        elif secim == self.t("opt_delete_github_only"):
            basarili, err = self.motor.github_repo_sil(repo_adi, self.github_kullanici_adi)
            if not basarili: hatalar.append(self.t("msg_github_delete_error").format(err))
        elif secim == self.t("opt_delete_both"):
            basarili_gh, err_gh = self.motor.github_repo_sil(repo_adi, self.github_kullanici_adi)
            if not basarili_gh: hatalar.append(self.t("msg_github_delete_error").format(err_gh))
            basarili_loc, err_loc = self.motor.yerel_git_sil()
            if not basarili_loc: hatalar.append(self.t("msg_local_delete_error").format(err_loc))
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
        if not (ok and url.strip()):
            return
        url = url.strip()

        self.lbl_durum.setText(self.t("msg_fetching_branches"))
        self.konsol.yaz(f"> {self.t('msg_fetching_branches')}")
        self._set_ui_lock(False)
        self.btn_clone.setEnabled(False)
        QApplication.processEvents()

        self.uzak_dal_isci = UzakDalIscisi(url, self.aktif_lang)
        self.uzak_dal_isci.log_sinyali.connect(self.konsol.yaz)
        self.uzak_dal_isci.sonuc_sinyali.connect(self.uzak_dallar_tamamlandi)
        self.uzak_dal_isci.finished.connect(self.arka_plan_durumu_guncelle)
        self.uzak_dal_isci.start()
        self.arka_plan_durumu_guncelle()

    def uzak_dallar_tamamlandi(self, basarili_dal, sonuc_dal, url):
        self.lbl_durum.setText("")
        self.butonlari_guncelle()

        if not basarili_dal:
            QMessageBox.critical(self, self.t("hata"), self.t("err_clone_fail").format(sonuc_dal))
            return

        secilen_branch = ""
        if sonuc_dal:
            secenekler = [self.t("opt_default_branch"), self.t("opt_all_branches")] + sonuc_dal
            secim, ok_branch = QInputDialog.getItem(
                self, self.t("dlg_clone_title"), self.t("dlg_clone_branch_select"),
                secenekler, 0, False
            )
            if not ok_branch:
                return
            if secim == self.t("opt_all_branches"):
                secilen_branch = "__ALL__"
            elif secim != self.t("opt_default_branch"):
                secilen_branch = secim


        varsayilan_isim = url.split("/")[-1].replace(".git", "") if "/" in url else "yeni_proje"
        baslangic = self.varsayilan_arama_dizini if self.varsayilan_arama_dizini else str(Path.home())
        QMessageBox.information(self, self.t("dlg_clone_title"), self.t("msg_clone_target"))

        dialog = QFileDialog(self)
        dialog.setWindowTitle(self.t("secim_penceresi"))
        dialog.setDirectory(baslangic)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setMinimumSize(900, 600)
        dialog.resize(900, 600)
        dialog.setViewMode(QFileDialog.Detail)

        from PySide6.QtCore import QStorageInfo, QUrl
        kisayollar = dialog.sidebarUrls()
        for disk in QStorageInfo.mountedVolumes():
            if disk.isValid() and disk.isReady():
                fs_type = bytes(disk.fileSystemType()).decode("utf-8", errors="ignore")
                if fs_type not in ["tmpfs", "devtmpfs", "proc", "sysfs", "cgroup", "squashfs", "overlay", "efivarfs", "tracefs"]:
                    disk_url = QUrl.fromLocalFile(disk.rootPath())
                    if disk_url not in kisayollar:
                        kisayollar.append(disk_url)
        dialog.setSidebarUrls(kisayollar)

        if dialog.exec():
            secilen_yollar = dialog.selectedFiles()
            if secilen_yollar:
                ana_dizin = secilen_yollar[0]
                hedef_tam_yol = os.path.join(ana_dizin, varsayilan_isim)
                sayac = 1
                orjinal_yol = hedef_tam_yol
                while os.path.exists(hedef_tam_yol):
                    hedef_tam_yol = f"{orjinal_yol}_{sayac}"
                    sayac += 1
                self.lbl_durum.setText(self.t("msg_cloning"))
                dal_bilgisi = f" [Dal: {secilen_branch}]" if secilen_branch else ""
                self.konsol.yaz(self.t("log_clone_start").format(dal_bilgisi, url))
                self._set_ui_lock(False)
                self.btn_clone.setEnabled(False)
                QApplication.processEvents()
                self.isci = KlonlamaIscisi(url, hedef_tam_yol, secilen_branch, self.aktif_lang)
                self.isci.log_sinyali.connect(self.konsol.yaz)
                self.isci.sonuc_sinyali.connect(self.klonlama_tamamlandi)
                self.isci.finished.connect(self.arka_plan_durumu_guncelle)
                self.isci.start()
                self.arka_plan_durumu_guncelle()

    def klonlama_tamamlandi(self, basarili, cikti, hedef_yol):
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_clone_success"))
            self.motor.repo_path = hedef_yol
            self.gecmise_repo_ekle(hedef_yol)
            self.butonlari_guncelle()
            self.ayarlari_kaydet()
        else:
            QMessageBox.critical(self, self.t("hata"), self.t("err_clone_fail").format(cikti))
            self.lbl_durum.setText("")
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
                self.butonlari_guncelle()
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
            QMessageBox.warning(self, self.t("hata"), self.t("err_no_merge_branch"))
            return

        mesaj = self.t("dlg_merge_mesaj").format(aktif)

        secim, ok = QInputDialog.getItem(self, self.t("dlg_merge_baslik"), mesaj, birlestirilebilir, 0, False)
        if ok and secim:
            basarili, hata = self.motor.merge_branch(secim)
            if basarili:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_merge_basarili").format(secim))

                sil_cevap = QMessageBox.question(
                    self,
                    self.t("msg_branch_cleanup_title"),
                    self.t("msg_branch_cleanup_prompt").format(secim),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )

                if sil_cevap == QMessageBox.Yes:
                    sil_basarili, sil_hata = self.motor.delete_branch(secim)
                    if sil_basarili:
                        self.konsol.yaz(self.t("log_branch_cleanup_done").format(secim))
                    else:
                        QMessageBox.warning(self, self.t("hata"), self.t("msg_branch_delete_error").format(sil_hata))
            else:
                if hata == "conflict":
                    dialog = CakismaCozucuDialog(self, self.motor, self.t)
                    dialog.exec()
                    dialog.deleteLater()
                    self.git_commit()
                else:
                    QMessageBox.critical(self, self.t("hata"), self.t("msg_dal_hata").format(hata))

            self.dallari_guncelle()
            self.butonlari_guncelle()

    def git_sürüm_olustur(self):
        basarili, mevcut_taglar = self.motor.yerel_taglari_getir()
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("dlg_tag_title"))
        dialog.resize(450, 350)
        dialog.setStyleSheet("QDialog { background-color: #1e1e24; } QLabel { color: #f5f5f7; }")
        layout = QVBoxLayout(dialog)

        if basarili and mevcut_taglar:
            lbl_mevcut = QLabel(self.t("lbl_mevcut_surumler"))
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
        btn_ok = QPushButton(self.t("btn_tamam"))
        btn_ok.setDefault(True)
        btn_ok.setStyleSheet("QPushButton { background-color: #007acc; color: white; padding: 6px 15px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #005999; }")
        btn_cancel = QPushButton(self.t("btn_iptal"))
        btn_cancel.setStyleSheet("QPushButton { background-color: #3f3f46; color: white; padding: 6px 15px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #52525b; }")

        btn_ok.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

        if dialog.exec() != QDialog.Accepted:
            dialog.deleteLater()
            return

        tag_adi = input_tag.text().strip()
        dialog.deleteLater()
        if not tag_adi:
            return

        if not tag_adi.startswith("v"):
            QMessageBox.warning(self, self.t("hata"), self.t("msg_release_pronoun"))
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
            file_dialog = QFileDialog(self)
            file_dialog.setWindowTitle(self.t("dlg_select_file"))
            file_dialog.setDirectory(self.motor.repo_path)
            file_dialog.setFileMode(QFileDialog.ExistingFile)
            file_dialog.setOption(QFileDialog.DontUseNativeDialog, True)
            file_dialog.setMinimumSize(780, 600)
            file_dialog.resize(780, 600)
            file_dialog.setViewMode(QFileDialog.Detail)

            from PySide6.QtCore import QStorageInfo, QUrl
            kisayollar = file_dialog.sidebarUrls()
            for disk in QStorageInfo.mountedVolumes():
                if disk.isValid() and disk.isReady():
                    fs_type = bytes(disk.fileSystemType()).decode("utf-8", errors="ignore")
                    if fs_type not in ["tmpfs", "devtmpfs", "proc", "sysfs", "cgroup", "squashfs", "overlay", "efivarfs", "tracefs"]:
                        disk_url = QUrl.fromLocalFile(disk.rootPath())
                        if disk_url not in kisayollar:
                            kisayollar.append(disk_url)
            file_dialog.setSidebarUrls(kisayollar)

            if file_dialog.exec():
                secilenler = file_dialog.selectedFiles()
                if secilenler:
                    dosya_yolu = secilenler

        self.lbl_durum.setText(self.t("msg_creating_tag"))
        self._set_ui_lock(False)
        QApplication.processEvents()

        self.surum_isci = SurumIscisi(self.motor.repo_path, tag_adi, aciklama, dosya_yolu, self.aktif_lang)
        self.surum_isci.log_sinyali.connect(self.konsol.yaz)
        self.surum_isci.sonuc_sinyali.connect(lambda basarili, hata: self.surum_tamamlandi(basarili, hata, tag_adi))
        self.surum_isci.finished.connect(self.arka_plan_durumu_guncelle)
        self.surum_isci.start()
        self.arka_plan_durumu_guncelle()

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
        self._start_git_operation(
            lambda motor: motor.git_rebase(upstream),
            self.rebase_tamamlandi,
            self.t("msg_rebase_bekle")
        )

    def rebase_tamamlandi(self, worker_ok, sonuc):
        if not worker_ok:
            QMessageBox.critical(self, self.t("hata"), self.t("msg_rebase_hata").format(sonuc))
        else:
            basarili, sebep = sonuc
            if basarili:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_rebase_basarili"))
            elif sebep == "conflict":
                self.rebase_cakisma_coz()
                return
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_rebase_hata").format(sebep))
        self.butonlari_guncelle()

    def rebase_cakisma_coz(self):
        dialog = CakismaCozucuDialog(self, self.motor, self.t)
        cozme_sonucu = dialog.exec()
        dialog.deleteLater()
        if cozme_sonucu != QDialog.Accepted:
            self.konsol.yaz(self.t("log_rebase_left_open"))
            self.butonlari_guncelle()
        elif self.motor.is_in_conflict():
            QMessageBox.warning(self, self.t("hata"), self.t("err_rebase_unresolved"))
            self.butonlari_guncelle()
        else:
            self._start_git_operation(
                lambda motor: motor.git_rebase_continue(),
                self.rebase_continue_tamamlandi,
                self.t("msg_rebase_bekle")
            )

    def rebase_continue_tamamlandi(self, worker_ok, sonuc):
        if worker_ok and sonuc[0]:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_rebase_basarili"))
        else:
            hata = sonuc[1] if worker_ok else sonuc
            if self.motor.is_in_conflict():
                self.rebase_cakisma_coz()
                return
            QMessageBox.critical(self, self.t("hata"), self.t("msg_rebase_hata").format(hata))
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
            self, self.t("dlg_squash_count_title"), self.t("dlg_squash_count_prompt").format(toplam_commit),
            value=2, minValue=2, maxValue=toplam_commit, step=1
        )
        if not ok1: return
        birlestirilen_mesajlar = "\n".join([f"- {c['mesaj']}" for c in commitler[:adet]])
        varsayilan_mesaj = self.t("msg_squash_default").format(adet, birlestirilen_mesajlar)
        yeni_mesaj, ok2 = QInputDialog.getMultiLineText(self, self.t("dlg_squash_msg_title"), self.t("dlg_squash_msg_msg"), text=varsayilan_mesaj)
        if not (ok2 and yeni_mesaj.strip()): return
        self._pending_squash_count = adet
        self._start_git_operation(
            lambda motor: motor.git_squash(adet, yeni_mesaj.strip()),
            self.squash_tamamlandi,
            self.t("msg_squash_bekle")
        )

    def squash_tamamlandi(self, worker_ok, sonuc):
        adet = self._pending_squash_count
        if not worker_ok:
            basarili, mesaj = False, sonuc
        else:
            basarili, mesaj = sonuc
        if basarili:
            if self.motor.has_remotes():
                cevap = QMessageBox.question(self, self.t("dlg_squash_force_push_title"), self.t("dlg_squash_force_push_msg"), QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if cevap == QMessageBox.Yes:
                    self.push_isci = PushIscisi(self.motor.repo_path, force=True, language=self.aktif_lang)
                    self.push_isci.log_sinyali.connect(self.konsol.yaz)
                    self.push_isci.sonuc_sinyali.connect(self.force_push_tamamlandi)
                    self.push_isci.finished.connect(self.arka_plan_durumu_guncelle)
                    self.push_isci.start()
                    self.arka_plan_durumu_guncelle()
                    return
                else:
                    QMessageBox.information(self, self.t("basarili"), self.t("msg_squash_basarili").format(adet))
            else:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_squash_basarili").format(adet))
        else:
            if mesaj == "working_tree_dirty":
                QMessageBox.warning(self, self.t("hata"), self.t("err_squash_dirty"))
            elif mesaj == "status_error":
                QMessageBox.critical(self, self.t("hata"), self.t("err_status_unavailable"))
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_squash_hata").format(mesaj))
        self.butonlari_guncelle()

    def git_tag_listele(self):
        self.lbl_durum.setText(self.t("msg_get_tags"))
        QApplication.processEvents()

        basarili, sonuc = self.motor.yerel_taglari_getir()

        if basarili:
            self.konsol.yaz(self.t("lbl_local_tags_header"))
            self.konsol.yaz(sonuc)
            self.konsol.yaz("-----------------------")
            QMessageBox.information(self, self.t("lbl_local_tags"), sonuc)
        else:
            QMessageBox.critical(self, self.t("hata"), self.t("msg_tags_error").format(sonuc))

        self.butonlari_guncelle()

    def actions_gecmisi_temizle(self):
        if not self.motor.repo_path:
            return
        cevap = QMessageBox.question(
            self, self.t("dlg_actions_title"), self.t("msg_clean_actions_confirm"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if cevap != QMessageBox.Yes:
            return

        self._set_ui_lock(False)
        QApplication.processEvents()

        self.actions_isci = ActionsTemizleIscisi(self.motor.repo_path, self.aktif_lang)
        self.actions_isci.log_sinyali.connect(self.konsol.yaz)
        self.actions_isci.sonuc_sinyali.connect(self.actions_temizleme_tamamlandi)
        self.actions_isci.finished.connect(self.arka_plan_durumu_guncelle)
        self.actions_isci.start()
        self.arka_plan_durumu_guncelle()

    def actions_temizleme_tamamlandi(self, basarili, mesaj):
        self.butonlari_guncelle()
        if basarili:
            if mesaj == "0":
                QMessageBox.information(self, self.t("basarili"), self.t("msg_clean_actions_empty"))
            else:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_clean_actions_success").format(mesaj))
        else:
            QMessageBox.critical(self, self.t("hata"), mesaj)

    def yonet_remotes(self):
        dialog = QDialog(self)
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
        dialog.deleteLater()

    def arka_plan_durumu_guncelle(self):
        isciler = [
            "user_isci", "surum_isci", "isci", "push_isci",
            "fetch_isci", "pull_isci", "login_isci", "actions_isci",
            "uzak_dal_isci", "operation_isci"
        ]

        aktif_mi = False
        for isci_adi in isciler:
            isci = getattr(self, isci_adi, None)
            if isci is not None and isci.isRunning():
                aktif_mi = True
                break

        if aktif_mi:
            self.lbl_bg_durum.setText(self.t("bg_islem_var"))
            self.lbl_bg_durum.setStyleSheet("""
                background-color: #dc2626;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 4px 14px;
                font-weight: bold;
            """)
        else:
            self.lbl_bg_durum.setText(self.t("bg_islem_yok"))
            self.lbl_bg_durum.setStyleSheet("""
                background-color: transparent;
                color: #a1a1aa;
                border: none;
                padding: 4px 14px;
                font-weight: bold;
            """)

    def git_stash_yap(self):
        not_metni, ok = QInputDialog.getText(self, self.t("dlg_stash_title"), self.t("dlg_stash_msg"))
        if not ok:
            return
        basarili, sonuc = self.motor.git_stash_save(not_metni)
        if basarili:
            QMessageBox.information(self, self.t("basarili"), self.t("msg_stash_ok"))
            self.butonlari_guncelle()
        else:
            if sonuc == "empty":
                QMessageBox.information(self, "Git", self.t("msg_stash_empty"))
            elif sonuc == "status_error":
                QMessageBox.critical(self, self.t("hata"), self.t("err_status_unavailable"))
            else:
                QMessageBox.critical(self, self.t("hata"), self.t("msg_stash_error").format(sonuc))

    def git_stash_pop_yap(self):
        liste = self.motor.git_stash_list()
        if not liste:
            QMessageBox.information(self, "Git", self.t("msg_stash_pop_empty"))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("dlg_stash_select_title"))
        dialog.resize(550, 300)
        layout = QVBoxLayout(dialog)

        lbl = QLabel(self.t("dlg_stash_select_msg"))
        layout.addWidget(lbl)

        list_widget = QListWidget()
        list_widget.setStyleSheet("""
            QListWidget { background-color: #2a2a32; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 4px; padding: 5px; }
            QListWidget::item:selected { background-color: #007acc; color: white; }
        """)
        list_widget.addItems(liste)
        list_widget.setCurrentRow(0)
        layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()
        btn_pop = ModernButton(self.t("btn_stash_pop"), "#0d9488")
        btn_drop = ModernButton(self.t("btn_stash_drop"), "#dc3545")
        btn_cancel = ModernButton(self.t("btn_iptal"), "#3f3f46")

        btn_layout.addWidget(btn_pop)
        btn_layout.addWidget(btn_drop)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        def pop_tiklandi():
            secili = list_widget.currentItem()
            if not secili:
                return
            secilen_ref = secili.text().split(":", 1)[0].strip()
            dialog.accept()

            basarili, sonuc = self.motor.git_stash_pop(secilen_ref)
            if basarili:
                QMessageBox.information(self, self.t("basarili"), self.t("msg_stash_pop_ok"))
                self.butonlari_guncelle()
            else:
                if sonuc == "empty":
                    QMessageBox.information(self, "Git", self.t("msg_stash_pop_empty"))
                elif sonuc == "conflict":
                    QMessageBox.warning(self, self.t("hata"), self.t("msg_stash_conflict"))
                    c_dialog = CakismaCozucuDialog(self, self.motor, self.t)
                    c_dialog.exec()
                    c_dialog.deleteLater()
                    self.butonlari_guncelle()
                else:
                    QMessageBox.critical(self, self.t("hata"), self.t("msg_stash_pop_error").format(sonuc))

        def drop_tiklandi():
            secili = list_widget.currentItem()
            if not secili:
                return
            tam_metin = secili.text()
            secilen_ref = tam_metin.split(":", 1)[0].strip()
            cevap = QMessageBox.warning(
                dialog, self.t("emin_misiniz"),
                self.t("msg_stash_drop_confirm").format(tam_metin),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if cevap == QMessageBox.Yes:
                basarili, hata = self.motor.git_stash_drop(secilen_ref)
                if basarili:
                    QMessageBox.information(dialog, self.t("basarili"), self.t("msg_stash_drop_ok"))
                    yeni_liste = self.motor.git_stash_list()
                    list_widget.clear()
                    if not yeni_liste:
                        dialog.accept()
                    else:
                        list_widget.addItems(yeni_liste)
                        list_widget.setCurrentRow(0)
                else:
                    QMessageBox.critical(dialog, self.t("hata"), self.t("msg_stash_drop_error").format(hata))

        btn_pop.clicked.connect(pop_tiklandi)
        btn_drop.clicked.connect(drop_tiklandi)
        btn_cancel.clicked.connect(dialog.reject)

        dialog.exec()
        dialog.deleteLater()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Git_Gui")
    app.setDesktopFileName("Git_Gui")

    app.setStyleSheet("""
        QDialog, QMessageBox, QInputDialog {
            background-color: #1e1e24;
            color: #f5f5f7;
        }
        QFileDialog {
            background-color: #2a2a32;
            color: #f5f5f7;
        }
        QFileDialog QLabel, QFileDialog QPushButton, QFileDialog QCheckBox, QFileDialog QRadioButton {
            color: #f5f5f7;
        }
        QDialog QLabel, QMessageBox QLabel {
            color: #f5f5f7;
        }
        QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton, QFileDialog QPushButton {
            background-color: #3f3f46;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 15px;
            min-width: 60px;
            font-weight: bold;
        }
        QDialog QPushButton:hover, QMessageBox QPushButton:hover, QInputDialog QPushButton:hover, QFileDialog QPushButton:hover {
            background-color: #007acc;
        }
        QDialog QLineEdit, QInputDialog QLineEdit, QFileDialog QLineEdit {
            background-color: #1e1e24;
            color: white;
            border: 1px solid #3f3f46;
            border-radius: 4px;
            padding: 6px;
        }
        QDialog QComboBox, QInputDialog QComboBox, QFileDialog QComboBox {
            background-color: #3f3f46;
            color: white;
            border: 1px solid #52525b;
            border-radius: 4px;
            padding: 4px;
        }
        QDialog QComboBox QAbstractItemView, QFileDialog QComboBox QAbstractItemView {
            background-color: #2a2a32;
            color: white;
            selection-background-color: #007acc;
        }
        QTreeView, QListView {
            background-color: #1e1e24;
            color: #f5f5f7;
            border: 1px solid #3f3f46;
            border-radius: 4px;
        }
        QTreeView::item:selected, QListView::item:selected {
            background-color: #007acc;
            color: white;
        }
        QHeaderView::section {
            background-color: #3f3f46;
            color: white;
            border: 1px solid #1e1e24;
            padding: 4px;
        }
        QFileDialog QToolButton {
            background-color: #3f3f46;
            border-radius: 4px;
            margin: 2px;
            padding: 2px;
        }
        QFileDialog QToolButton:hover {
            background-color: #007acc;
        }
        QMenu {
            background-color: #2a2a32;
            color: #f5f5f7;
            border: 1px solid #3f3f46;
            border-radius: 4px;
            padding: 4px;
        }
        QMenu::item {
            padding: 6px 24px 6px 12px;
            background-color: transparent;
            border-radius: 4px;
            margin: 2px;
        }
        QMenu::item:selected {
            background-color: #007acc;
            color: white;
        }
        QMenu::separator {
            height: 1px;
            background-color: #3f3f46;
            margin: 4px 8px;
        }
    """)

    font_yolu = str(PROJE_ANA_DIZINI / "font.ttf")
    if os.path.exists(font_yolu):
        font_id = QFontDatabase.addApplicationFont(font_yolu)
        if font_id >= 0:
            font_families = QFontDatabase.applicationFontFamilies(font_id)
            if font_families:
                custom_font = QFont(font_families)
                custom_font.setPointSize(12)
                app.setFont(custom_font)
    window = GitGUI()
    window.show()
    sys.exit(app.exec())
