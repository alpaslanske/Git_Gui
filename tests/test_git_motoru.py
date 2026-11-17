import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from git_motoru import GitMotoru


class GitMotoruTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name) / "repo"
        self.repo_path.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.com")
        self.motor = GitMotoru()
        self.assertTrue(self.motor.set_path(str(self.repo_path)))

    def tearDown(self):
        self.temp_dir.cleanup()

    def git(self, *args, check=True):
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            check=check,
            capture_output=True,
            text=True,
        )

    def commit_file(self, contents, message):
        (self.repo_path / "tracked.txt").write_text(contents, encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("commit", "-m", message)

    def test_status_command_failure_is_not_reported_as_clean(self):
        failed = subprocess.CompletedProcess(
            ["git", "status", "--short"], 128, stdout="", stderr="permission denied"
        )
        with patch("git_motoru.subprocess.run", return_value=failed):
            is_clean, status = self.motor.get_status()

        self.assertIsNone(is_clean)
        self.assertEqual(status, "permission denied")

    def test_rebase_conflict_remains_available_for_resolution(self):
        self.commit_file("base\n", "base")
        self.git("checkout", "-b", "upstream")
        self.commit_file("upstream\n", "upstream change")
        self.git("checkout", "-b", "feature", "main")
        self.commit_file("feature\n", "feature change")

        success, reason = self.motor.git_rebase("upstream")

        self.assertFalse(success)
        self.assertEqual(reason, "conflict")
        self.assertTrue(self.git("ls-files", "-u").stdout.strip())
        (self.repo_path / "tracked.txt").write_text("resolved\n", encoding="utf-8")
        self.git("add", "tracked.txt")

        continue_success, _ = self.motor.git_rebase_continue()

        self.assertTrue(continue_success)
        self.assertEqual(self.git("branch", "--show-current").stdout.strip(), "feature")

    def test_failed_squash_restores_original_head(self):
        self.commit_file("one\n", "one")
        self.commit_file("two\n", "two")
        original_head = self.git("rev-parse", "HEAD").stdout.strip()
        hook = self.repo_path / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)

        success, _ = self.motor.git_squash(2, "combined")

        self.assertFalse(success)
        self.assertEqual(self.git("rev-parse", "HEAD").stdout.strip(), original_head)
        self.assertEqual(self.git("status", "--short").stdout, "")

    def test_force_push_uses_lease_protection(self):
        self.motor.repo_exists = True
        self.motor.repo_path = str(self.repo_path)
        self.motor.get_active_branch = lambda: "main"
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch.object(self.motor, "get_git_env", return_value=os.environ.copy()):
            with patch("git_motoru.subprocess.run", return_value=completed) as run:
                self.motor.git_push(force=True)

        command = run.call_args.args[0]
        self.assertIn("--force-with-lease", command)
        self.assertNotIn("--force", command)

    def test_clone_does_not_remove_existing_target(self):
        target = self.repo_path.parent / "existing-target"
        target.mkdir()
        sentinel = target / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")

        success, _ = self.motor.git_clone("https://example.invalid/repo.git", str(target))

        self.assertFalse(success)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
