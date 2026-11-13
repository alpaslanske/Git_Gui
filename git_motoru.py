import os
import shutil
import subprocess

class GitMotoru:
    def __init__(self):
        self.repo_path = ""
        self.repo_exists = False
        self.log_callback = None

    def komut_logla(self, komut_metni):
        if self.log_callback:
            self.log_callback(komut_metni)

    def git_klasoru_mu(self, path):
        if not path or not os.path.exists(path):
            return False
        res = subprocess.run(
            ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
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
        env = os.environ.copy()
        if self.repo_exists:
            res = subprocess.run(
                ["git", "rev-parse", "--is-bare-repository"],
                cwd=self.repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace'
            )
            if res.stdout.strip() == "true":
                cfg_res = subprocess.run(
                    ["git", "config", "core.worktree"],
                    cwd=self.repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace'
                )
                work_tree = cfg_res.stdout.strip()
                if work_tree:
                    env["GIT_WORK_TREE"] = work_tree
                    env["GIT_DIR"] = self.repo_path
                else:
                    raise Exception("Bare (çıplak) depo kullanıyorsunuz ancak 'core.worktree' ayarı bulunamadı.")
        return env

    def get_active_branch(self):
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.repo_path, env=self.get_git_env(), capture_output=True, text=True, encoding='utf-8', errors='replace'
            )
            branch = res.stdout.strip()
            if branch and branch != "HEAD":
                return branch
        except Exception:
            pass

        res2 = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.repo_path, env=self.get_git_env(), capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        branch2 = res2.stdout.strip()
        return branch2 if branch2 else "main"

    def get_branches(self):
        if not self.repo_exists:
            return [], ""
        try:
            env = self.get_git_env()
            res = subprocess.run(["git", "branch"], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            branches = []
            active_branch = ""
            for line in res.stdout.splitlines():
                if line.startswith("*"):
                    name = line[1:].strip()
                    active_branch = name
                    branches.append(name)
                else:
                    branches.append(line.strip())
            return branches, active_branch
        except Exception as e:
            self.komut_logla(f"HATA (Branch List): {e}")
            return [], ""

    def create_and_switch_branch(self, branch_name):
        if not self.repo_exists: return False, "repo_yok"
        try:
            env = self.get_git_env()
            self.komut_logla(f"> git checkout -b {branch_name}")
            res = subprocess.run(["git", "checkout", "-b", branch_name], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if res.returncode == 0: return True, "ok"
            return False, res.stderr or res.stdout
        except Exception as e:
            return False, str(e)

    def switch_branch(self, branch_name):
        if not self.repo_exists: return False, "repo_yok"
        try:
            env = self.get_git_env()
            self.komut_logla(f"> git checkout {branch_name}")
            res = subprocess.run(["git", "checkout", branch_name], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if res.returncode == 0: return True, "ok"
            return False, res.stderr or res.stdout
        except Exception as e:
            return False, str(e)

    def delete_branch(self, branch_name, force=False):
        if not self.repo_exists: return False, "repo_yok"
        try:
            env = self.get_git_env()
            flag = "-D" if force else "-d"
            self.komut_logla(f"> git branch {flag} {branch_name}")
            res = subprocess.run(["git", "branch", flag, branch_name], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if res.returncode == 0: return True, "ok"
            if "not fully merged" in res.stderr.lower():
                return False, "not_merged"
            return False, res.stderr or res.stdout
        except Exception as e:
            return False, str(e)

    def merge_branch(self, target_branch):
        if not self.repo_exists: return False, "repo_yok"
        try:
            env = self.get_git_env()
            self.komut_logla(f"> git merge {target_branch}")
            res = subprocess.run(["git", "merge", target_branch], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if res.returncode == 0:
                return True, "ok"
            
            # Çift dikiş çakışma kontrolü (Redundancy)
            if self.is_in_conflict(res.stderr or res.stdout):
                return False, "conflict"
                
            return False, res.stderr or res.stdout
        except Exception as e:
            return False, str(e)

    def git_fetch_kontrol(self):
        if not self.repo_exists:
            return False, "repo_yok"
        try:
            env = self.get_git_env()
            if not self.has_remotes():
                return False, "no_remote"

            self.komut_logla("> git fetch origin")
            subprocess.run(["git", "fetch", "origin"], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')

            aktif_branch = self.get_active_branch()
            rev_kontrol = subprocess.run(
                ["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{aktif_branch}"],
                cwd=self.repo_path,
                env=env,
                capture_output=True,
                text=True,
                check=True, encoding='utf-8', errors='replace'
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
        if not self.repo_exists:
            return False, ""
        try:
            env = self.get_git_env()
            short_res = subprocess.run(["git", "status", "--short"], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            is_clean = len(short_res.stdout.strip()) == 0

            full_res = subprocess.run(["git", "status"], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            return is_clean, full_res.stdout
        except Exception as e:
            return False, f"Status okunamadı: {e}"

    def git_init(self):
        if self.repo_path:
            self.komut_logla(f"> git init {self.repo_path}")
            res = subprocess.run(["git", "init", self.repo_path], capture_output=True, text=True, encoding='utf-8', errors='replace')
            if res.returncode == 0:
                self.repo_exists = True
                return True
        return False

    def git_commit(self, mesaj):
        if self.repo_exists and mesaj:
            try:
                env = self.get_git_env()
                self.komut_logla("> git add -A")
                subprocess.run(["git", "add", "-A"], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')

                self.komut_logla(f'> git commit -m "{mesaj}"')
                result = subprocess.run(["git", "commit", "-m", mesaj], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')

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
        if not self.repo_path:
            return False, "Repo yolu tanımlı değil."
        try:
            env = self.get_git_env()
            cmd = ["gh", "repo", "create", repo_adi, f"--{visibility}", "--source", ".", "--remote", "origin"]
            self.komut_logla(f"> {' '.join(cmd)}")
            res = subprocess.run(cmd, cwd=self.repo_path, env=env, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
            return True, res.stdout
        except subprocess.CalledProcessError as e:
            return False, e.stderr or str(e)
        except Exception as e:
            return False, str(e)

    def has_remotes(self):
        if not self.repo_exists:
            return False
        res = subprocess.run(["git", "remote"], cwd=self.repo_path, env=self.get_git_env(), capture_output=True, text=True, encoding='utf-8', errors='replace')
        return len(res.stdout.strip()) > 0

    def get_remote_url(self):
        if not self.repo_exists:
            return ""
        res = subprocess.run(["git", "remote", "get-url", "origin"], cwd=self.repo_path, env=self.get_git_env(), capture_output=True, text=True, encoding='utf-8', errors='replace')
        return res.stdout.strip() if res.returncode == 0 else ""

    def add_remote(self, url):
        if self.repo_exists:
            self.komut_logla(f"> git remote add origin {url}")
            try:
                env = self.get_git_env()
                subprocess.run(["git", "remote", "add", "origin", url], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
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
                cmd.append("--force")

            self.komut_logla(f"> {' '.join(cmd)}")
            try:
                env = self.get_git_env()
                subprocess.run(cmd, cwd=self.repo_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
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
            rev_kontrol = subprocess.run(["git", "rev-parse", "--verify", f"{hedef_hash}^"], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if rev_kontrol.returncode != 0:
                return False, "root_commit"

            self.komut_logla(f"> git rebase --onto {hedef_hash}^ {hedef_hash}")
            res = subprocess.run(["git", "rebase", "--onto", f"{hedef_hash}^", hedef_hash], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
  
            if res.returncode != 0:
                hata_metni = (res.stderr or res.stdout)
                self.komut_logla(f"HATA (Rebase): {hata_metni}")
                
                if self.is_in_conflict(res.stderr or res.stdout):
                    subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, env=env, capture_output=True)
                    return False, "conflict"
                    
                subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, env=env, capture_output=True)
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
                subprocess.run(["git", "reset", "--hard", hedef_hash], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
                self.komut_logla("> git restore .")
                subprocess.run(["git", "restore", "."], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
                subprocess.run(["git", "checkout", "."], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
                return True
            except subprocess.CalledProcessError as e:
                self.komut_logla(f"HATA: (Rollback) {e.stderr or str(e)}")
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
                ["git", "log", "-n", str(adet), f"--pretty=format:{format_str}", "--date=format:%Y-%m-%d %H:%M"],
                cwd=self.repo_path,
                env=env,
                capture_output=True,
                text=True,
                check=True, encoding='utf-8', errors='replace'
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
        try:
            hedef = f"{kullanici_adi}/{repo_adi}" if kullanici_adi else repo_adi
            cmd = ["gh", "repo", "delete", hedef, "--yes"]
            self.komut_logla(f"> {' '.join(cmd)}")
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
            return True, res.stdout
        except subprocess.CalledProcessError as e:
            hata = e.stderr or e.stdout
            self.komut_logla(f"HATA (GitHub Sil): {hata}")
            return False, hata
        except Exception as e:
            self.komut_logla(f"HATA (GitHub Sil): {e}")
            return False, str(e)

    def git_clone(self, url, hedef_dizin):
        try:
            self.komut_logla(f"> git clone {url} '{hedef_dizin}'")
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            res = subprocess.run(
                ["git", "clone", url, hedef_dizin],
                capture_output=True, text=True, env=env, check=True, encoding='utf-8', errors='replace'
            )
            self.repo_path = hedef_dizin
            self.repo_exists = True
            return True, res.stdout
        except subprocess.CalledProcessError as e:
            hata = e.stderr or e.stdout or str(e)
            self.komut_logla(f"HATA (Clone): {hata}")
            if os.path.exists(hedef_dizin):
                try: shutil.rmtree(hedef_dizin)
                except Exception: pass
            return False, hata
        except Exception as e:
            self.komut_logla(f"HATA (Clone Genel): {str(e)}")
            if os.path.exists(hedef_dizin):
                try: shutil.rmtree(hedef_dizin)
                except Exception: pass
            return False, str(e)

    def git_tag_olustur(self, tag_adi, aciklama="", dosya_yolu=""):
        if not self.repo_exists:
            return False, "repo_yok"

        env = self.get_git_env()
        yerel_tag_olustu = False
        uzak_tag_olustu = False

        try:
            # 1. Yerel Etiketi Oluştur
            if aciklama.strip():
                cmd_tag = ["git", "tag", "-a", tag_adi, "-m", aciklama]
            else:
                cmd_tag = ["git", "tag", tag_adi]

            self.komut_logla(f"> {' '.join(cmd_tag)}")
            subprocess.run(cmd_tag, cwd=self.repo_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            yerel_tag_olustu = True

            if self.has_remotes():
                # 2. Etiketi GitHub'a İt
                self.komut_logla(f"> git push origin {tag_adi}")
                subprocess.run(["git", "push", "origin", tag_adi], cwd=self.repo_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
                uzak_tag_olustu = True

                # 3. GitHub Release Oluştur ve Dosya Yükle
                self.komut_logla(f"> gh release create {tag_adi}")
                gh_cmd = ["gh", "release", "create", tag_adi]
                if aciklama.strip():
                    gh_cmd.extend(["--title", tag_adi, "--notes", aciklama])
                else:
                    gh_cmd.extend(["--title", tag_adi, "--generate-notes"])

                if dosya_yolu and os.path.exists(dosya_yolu):
                    gh_cmd.append(dosya_yolu)

                subprocess.run(gh_cmd, cwd=self.repo_path, env=env, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')

            return True, "ok"

        except subprocess.CalledProcessError as e:
            hata = e.stderr or e.stdout or str(e)
            self.komut_logla(f"HATA (Sürüm): {hata}")

            # --- TEMİZLİK (ROLLBACK) İŞLEMİ ---
            if uzak_tag_olustu:
                self.komut_logla(f"> İşlem iptal ediliyor... Uzak sunucudaki '{tag_adi}' etiketi temizleniyor.")
                subprocess.run(["git", "push", "--delete", "origin", tag_adi], cwd=self.repo_path, env=env, capture_output=True)
            if yerel_tag_olustu:
                self.komut_logla(f"> İşlem iptal ediliyor... Yereldeki '{tag_adi}' etiketi temizleniyor.")
                subprocess.run(["git", "tag", "-d", tag_adi], cwd=self.repo_path, env=env, capture_output=True)

            return False, hata

        except Exception as e:
            self.komut_logla(f"HATA (Sürüm Genel): {str(e)}")

            # --- TEMİZLİK (ROLLBACK) İŞLEMİ ---
            if uzak_tag_olustu:
                self.komut_logla(f"> İşlem iptal ediliyor... Uzak sunucudaki '{tag_adi}' etiketi temizleniyor.")
                subprocess.run(["git", "push", "--delete", "origin", tag_adi], cwd=self.repo_path, env=env, capture_output=True)
            if yerel_tag_olustu:
                self.komut_logla(f"> İşlem iptal ediliyor... Yereldeki '{tag_adi}' etiketi temizleniyor.")
                subprocess.run(["git", "tag", "-d", tag_adi], cwd=self.repo_path, env=env, capture_output=True)

            return False, str(e)

    def git_rebase(self, upstream_dal):
        if not self.repo_exists:
            return False, "repo_yok"
        try:
            env = self.get_git_env()
            self.komut_logla(f"> git rebase {upstream_dal}")
            res = subprocess.run(
                ["git", "rebase", upstream_dal],
                cwd=self.repo_path,
                env=env,
                capture_output=True,
                text=True, encoding='utf-8', errors='replace'
            )
            
            if res.returncode != 0:
                hata_metni = (res.stderr or res.stdout)
                self.komut_logla(f"HATA (Rebase): {hata_metni}")
                
                if self.is_in_conflict(res.stderr or res.stdout):
                    subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, env=env, capture_output=True)
                    return False, "conflict"
                    
                subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, env=env, capture_output=True)
                return False, hata_metni                    
                    
                return False, res.stderr or res.stdout
            return True, "ok"
        except Exception as e:
            self.komut_logla(f"HATA: {e}")
            subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, env=self.get_git_env(), capture_output=True)
            return False, str(e)

    def git_squash(self, commit_adedi, yeni_mesaj):
        if not self.repo_exists:
            return False, "repo_yok"
        try:
            is_clean, _ = self.get_status()
            if not is_clean:
                return False, "working_tree_dirty"

            env = self.get_git_env()
            self.komut_logla(f"> git reset --soft HEAD~{commit_adedi}")
            subprocess.run(
                ["git", "reset", "--soft", f"HEAD~{commit_adedi}"],
                cwd=self.repo_path,
                env=env,
                capture_output=True,
                text=True,
                check=True, encoding='utf-8', errors='replace'
            )
            self.komut_logla(f'> git commit -m "{yeni_mesaj}"')
            subprocess.run(
                ["git", "commit", "-m", yeni_mesaj],
                cwd=self.repo_path,
                env=env,
                capture_output=True,
                text=True,
                check=True, encoding='utf-8', errors='replace'
            )
            return True, "ok"
        except subprocess.CalledProcessError as e:
            hata = e.stderr or e.stdout or str(e)
            self.komut_logla(f"HATA (Squash): {hata}")
            return False, hata
        except Exception as e:
            self.komut_logla(f"HATA (Squash): {e}")
            return False, str(e)

    def yerel_taglari_getir(self):
        if not self.repo_exists:
            return False, "repo_yok"
        try:
            env = self.get_git_env()
            self.komut_logla("> git tag -n")
            res = subprocess.run(["git", "tag", "-n"], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if res.returncode == 0:
                taglar = res.stdout.strip()
                return True, taglar if taglar else "Yerelde henüz bir etiket (tag) bulunmuyor."
            return False, res.stderr or res.stdout
        except Exception as e:
            self.komut_logla(f"HATA (Tag Listeleme): {e}")
            return False, str(e)

    def get_remotes_list(self):
        if not self.repo_exists:
            return []
        try:
            res = subprocess.run(["git", "remote", "-v"], cwd=self.repo_path, env=self.get_git_env(), capture_output=True, text=True, encoding='utf-8', errors='replace')
            if res.returncode != 0:
                return []
            remotes = set()
            for satir in res.stdout.strip().splitlines():
                if satir:
                    parcalar = satir.split()
                    if len(parcalar) >= 2:
                        remotes.add(f"{parcalar[0]} - {parcalar[1]}")
            return sorted(list(remotes))
        except Exception:
            return []

    def add_custom_remote(self, isim, url):
        if not self.repo_exists:
            return False, "repo_yok"
        self.komut_logla(f"> git remote add {isim} {url}")
        try:
            subprocess.run(["git", "remote", "add", isim, url], cwd=self.repo_path, env=self.get_git_env(), check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            return True, "ok"
        except subprocess.CalledProcessError as e:
            self.komut_logla(f"HATA: {e.stderr}")
            return False, e.stderr or "Bilinmeyen Hata"

    def remove_remote(self, isim):
        if not self.repo_exists:
            return False, "repo_yok"
        self.komut_logla(f"> git remote remove {isim}")
        try:
            subprocess.run(["git", "remote", "remove", isim], cwd=self.repo_path, env=self.get_git_env(), check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            return True, "ok"
        except subprocess.CalledProcessError as e:
            self.komut_logla(f"HATA: {e.stderr}")
            return False, e.stderr or "Unknown error"
            
    def get_conflicted_files(self):
        if not self.repo_exists: return []
        try:
            env = self.get_git_env()
            # U harfi (Unmerged/Çakışmış) dosyaları getirir
            res = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=self.repo_path, env=env, capture_output=True, text=True, encoding='utf-8')
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception as e:
            self.komut_logla(f"HATA (Conflict List): {e}")
            return []

    def mark_resolved(self, dosya_yolu):
        if not self.repo_exists: return False
        try:
            env = self.get_git_env()
            self.komut_logla(f"> git add {dosya_yolu}")
            subprocess.run(["git", "add", dosya_yolu], cwd=self.repo_path, env=env, check=True)
            return True
        except Exception as e:
            self.komut_logla(f"HATA (Resolve): {e}")
            return False

    def is_in_conflict(self, git_ciktisi=""):
        # 1. Yöntem (Yedek Sensör): Çıktıdan kelime avı
        hata_metni = str(git_ciktisi).lower()
        if "conflict" in hata_metni or "çakışma" in hata_metni:
            return True
            
        # 2. Yöntem (Ana Sensör): Git'in çekirdeğine sorma
        if not self.repo_exists: return False
        try:
            res = subprocess.run(
                ["git", "ls-files", "-u"], 
                cwd=self.repo_path, 
                env=self.get_git_env(),
                capture_output=True, 
                text=True, 
                encoding='utf-8', 
                errors='replace'
            )
            return len(res.stdout.strip()) > 0
        except Exception as e:
            self.komut_logla(f"HATA (Conflict Kontrol): {e}")
            return False
