import os
import shutil
import subprocess

class GitMotoru:
    def __init__(self):
        self.repo_path = ""
        self.repo_exists = False
        self.log_callback = None

    def komut_logla(self, komut_metni):
        """Çalıştırılan komutu konsol bileşenine gönderir."""
        if self.log_callback:
            self.log_callback(komut_metni)

    def git_klasoru_mu(self, path):
        if not path or not os.path.exists(path):
            return False
        res = subprocess.run(
            ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True
        )
        return res.returncode == 0

    def set_path(self, path):
        self.repo_path = path
        if self.git_klasoru_mu(path):
            self.repo_exists = True
            return True
        self.repo_exists = False
        return False

    def get_git_env(self):
        """Bare depo kullanılıyorsa asıl projenin yerini (work tree) bulup sisteme tanıtır."""
        env = os.environ.copy()
        if self.repo_exists:
            res = subprocess.run(
                ["git", "rev-parse", "--is-bare-repository"],
                cwd=self.repo_path, capture_output=True, text=True
            )
            if res.stdout.strip() == "true":
                cfg_res = subprocess.run(
                    ["git", "config", "core.worktree"],
                    cwd=self.repo_path, capture_output=True, text=True
                )
                work_tree = cfg_res.stdout.strip()
                if work_tree:
                    env["GIT_WORK_TREE"] = work_tree
                    env["GIT_DIR"] = self.repo_path
                else:
                    raise Exception(
                        "Bare (çıplak) depo kullanıyorsunuz ancak 'core.worktree' ayarı bulunamadı.\n"
                        "Lütfen terminalde depo klasörünüze gidip projenizin yerini belirtin:\n"
                        "git config core.worktree /asil/projenizin/yolu"
                    )
        return env

    def get_active_branch(self):
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.repo_path, env=self.get_git_env(), capture_output=True, text=True
        )
        branch = res.stdout.strip()
        return branch if branch else "main"

    def git_fetch_kontrol(self):
        """GitHub'dan son durumu fetch eder ve yerel ile farkı kontrol eder."""
        if not self.repo_exists:
            return False, "repo_yok"
        try:
            env = self.get_git_env()
            if not self.has_remotes():
                return False, "no_remote"

            self.komut_logla("> git fetch origin")
            subprocess.run(["git", "fetch", "origin"], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True)

            aktif_branch = self.get_active_branch()
            rev_kontrol = subprocess.run(
                ["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{aktif_branch}"],
                cwd=self.repo_path,
                env=env,
                capture_output=True,
                text=True,
                check=True
            )

            sayilar = rev_kontrol.stdout.strip().split()
            if len(sayilar) == 2:
                return True, {"ileri": int(sayilar[0]), "geri": int(sayilar[1])}

            return True, {"ileri": 0, "geri": 0}
        except subprocess.CalledProcessError as e:
            self.komut_logla(f"HATA (Fetch): {e.stderr or str(e)}")
            return False, e.stderr or str(e)
        except Exception as e:
            self.komut_logla(f"HATA (Fetch): {e}")
            return False, str(e)

    def get_status(self):
        """Deponun statüsünü kontrol eder. (Temiz mi?, Konsol Çıktısı) döndürür."""
        if not self.repo_exists:
            return False, ""
        try:
            env = self.get_git_env()
            short_res = subprocess.run(["git", "status", "--short"], cwd=self.repo_path, env=env, capture_output=True, text=True)
            is_clean = len(short_res.stdout.strip()) == 0

            full_res = subprocess.run(["git", "status"], cwd=self.repo_path, env=env, capture_output=True, text=True)
            return is_clean, full_res.stdout
        except Exception as e:
            return False, f"Status okunamadı: {e}"

    def git_init(self):
        if self.repo_path:
            self.komut_logla(f"> git init {self.repo_path}")
            res = subprocess.run(["git", "init", self.repo_path], capture_output=True, text=True)
            if res.returncode == 0:
                self.repo_exists = True
                return True
        return False

    def git_commit(self, mesaj):
        if self.repo_exists and mesaj:
            try:
                env = self.get_git_env()
                self.komut_logla("> git add -A")
                subprocess.run(["git", "add", "-A"], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True)

                self.komut_logla(f'> git commit -m "{mesaj}"')
                result = subprocess.run(["git", "commit", "-m", mesaj], cwd=self.repo_path, env=env, capture_output=True, text=True)

                if result.returncode != 0:
                    if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                        self.komut_logla("Bilgi: Kaydedilecek yeni bir değişiklik yok.")
                        return True
                    self.komut_logla(f"HATA: {result.stderr or result.stdout}")
                    return False

                return True
            except subprocess.CalledProcessError as e:
                self.komut_logla(f"HATA: (git add) {e.stderr or str(e)}")
                return False
            except Exception as e:
                self.komut_logla(f"HATA: {e}")
                return False
        return False

    def github_repo_olustur(self, repo_adi, visibility="public"):
        """gh CLI kullanarak GitHub'da yeni depo açar ve origin olarak bağlar."""
        if not self.repo_path:
            return False, "Repo yolu tanımlı değil."
        try:
            env = self.get_git_env()
            cmd = ["gh", "repo", "create", repo_adi, f"--{visibility}", "--source", ".", "--remote", "origin"]
            self.komut_logla(f"> {' '.join(cmd)}")
            res = subprocess.run(cmd, cwd=self.repo_path, env=env, capture_output=True, text=True, check=True)
            return True, res.stdout
        except subprocess.CalledProcessError as e:
            return False, e.stderr or str(e)
        except Exception as e:
            return False, str(e)

    def has_remotes(self):
        if not self.repo_exists:
            return False
        res = subprocess.run(["git", "remote"], cwd=self.repo_path, env=self.get_git_env(), capture_output=True, text=True)
        return len(res.stdout.strip()) > 0

    def add_remote(self, url):
        if self.repo_exists:
            self.komut_logla(f"> git remote add origin {url}")
            try:
                env = self.get_git_env()
                subprocess.run(["git", "remote", "add", "origin", url], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                if "already exists" in e.stderr:
                    self.komut_logla("> 'origin' zaten mevcut, URL güncelleniyor...")
                    subprocess.run(["git", "remote", "set-url", "origin", url], cwd=self.repo_path, env=env, check=True)
                else:
                    self.komut_logla(f"HATA (Remote Ekleme): {e.stderr}")
                    raise Exception(e.stderr)

    def git_push(self, force=False):
        if self.repo_exists:
            aktif_branch = self.get_active_branch()
            cmd = ["git", "push", "-u", "origin", aktif_branch]
            if force:
                cmd.append("--force") # Güvenli force yerine mutlak force kullanıyoruz.

            self.komut_logla(f"> {' '.join(cmd)}")
            try:
                env = self.get_git_env()
                subprocess.run(cmd, cwd=self.repo_path, env=env, check=True, capture_output=True, text=True)
                return aktif_branch
            except subprocess.CalledProcessError as e:
                hata_detay = e.stderr or e.stdout
                self.komut_logla(f"HATA (Push): {hata_detay}")
                raise Exception(hata_detay)
        return None

    def git_commit_sil(self, hedef_hash):
        if not self.repo_exists:
            return False, "repo_yok"
        try:
            env = self.get_git_env()
            rev_kontrol = subprocess.run(["git", "rev-parse", "--verify", f"{hedef_hash}^"], cwd=self.repo_path, env=env, capture_output=True, text=True)
            if rev_kontrol.returncode != 0:
                return False, "root_commit"

            self.komut_logla(f"> git rebase --onto {hedef_hash}^ {hedef_hash}")
            res = subprocess.run(["git", "rebase", "--onto", f"{hedef_hash}^", hedef_hash], cwd=self.repo_path, env=env, capture_output=True, text=True)
            if res.returncode != 0:
                hata_metni = (res.stderr or res.stdout).lower()
                self.komut_logla(f"HATA (Rebase): {res.stderr or res.stdout}")
                subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, env=env, capture_output=True)

                if "conflict" in hata_metni or "çakışma" in hata_metni:
                    return False, "conflict"
                return False, "hata"

            return True, "ok"
        except Exception as e:
            self.komut_logla(f"HATA: {e}")
            subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, env=self.get_git_env(), capture_output=True)
            return False, "hata"

    def git_rollback(self, hedef_hash="HEAD"):
        if self.repo_exists:
            self.komut_logla(f"> git reset --hard {hedef_hash}")
            try:
                env = self.get_git_env()
                subprocess.run(["git", "reset", "--hard", hedef_hash], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True)
                return True
            except subprocess.CalledProcessError as e:
                self.komut_logla(f"HATA: {e.stderr or str(e)}")
                return False
            except Exception as e:
                self.komut_logla(f"HATA: {e}")
                return False
        return False

    def gecmis_getir(self, adet=20):
        if not self.repo_exists:
            return []
        try:
            self.komut_logla(f"> git log --oneline -n {adet}")
            env = self.get_git_env()
            format_str = "%h|%cd|%s"
            sonuc = subprocess.run(
                ["git", "log", f"-n {adet}", f"--pretty=format:{format_str}", "--date=format:%Y-%m-%d %H:%M"],
                cwd=self.repo_path,
                env=env,
                capture_output=True,
                text=True,
                check=True
            )

            satirlar = sonuc.stdout.strip().splitlines()
            if not satirlar or satirlar == [""]:
                return []

            commitler = []
            for satir in satirlar:
                parcalar = satir.split("|", 2)
                if len(parcalar) == 3:
                    commitler.append({
                        "hash": parcalar[0],
                        "tarih": parcalar[1],
                        "mesaj": parcalar[2]
                    })
            return commitler
        except subprocess.CalledProcessError as e:
            if "does not have any commits" in e.stderr or "fatal: your current branch" in e.stderr:
                return []
            self.komut_logla(f"HATA (Geçmiş): {e.stderr}")
            return None
        except Exception as e:
            self.komut_logla(f"HATA (Geçmiş): {e}")
            return None

    def yerel_git_sil(self):
        """Yerel klasördeki .git dizinini silerek depoyu normal klasöre dönüştürür."""
        if not self.repo_path:
            return False, "repo_yok"
        try:
            git_klasoru = os.path.join(self.repo_path, ".git")
            if os.path.exists(git_klasoru):
                shutil.rmtree(git_klasoru)
                self.komut_logla(f"> rm -rf {git_klasoru}")
                self.repo_exists = False
                return True, "ok"
            return False, ".git klasörü bulunamadı."
        except Exception as e:
            self.komut_logla(f"HATA (Yerel Sil): {e}")
            return False, str(e)

    def github_repo_sil(self, repo_adi, kullanici_adi=""):
        """GitHub CLI kullanarak uzak GitHub deposunu siler."""
        try:
            hedef = f"{kullanici_adi}/{repo_adi}" if kullanici_adi else repo_adi
            cmd = ["gh", "repo", "delete", hedef, "--yes"]
            self.komut_logla(f"> {' '.join(cmd)}")
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True, res.stdout
        except subprocess.CalledProcessError as e:
            hata = e.stderr or e.stdout
            self.komut_logla(f"HATA (GitHub Sil): {hata}")
            return False, hata
        except Exception as e:
            self.komut_logla(f"HATA (GitHub Sil): {e}")
            return False, str(e)
