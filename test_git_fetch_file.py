import re
import unittest
import subprocess
import tempfile
import os
import shutil
import configparser


class TestArgumentParser(unittest.TestCase):
    def test_argparse_argumentparser(self):
        """
        Test for `argparse.ArgumentParser`.
        """
        script_path = subprocess.check_output(
            ["git", "config", "alias.fetch-file"], text=True
        ).strip()
        # remove any leading "!something " prefix
        script_path = re.sub(r"^!\S+\s+", "", script_path)
        # when this is actually git-bash.exe, the path may need to be translated
        if os.name == 'nt' and script_path.startswith('/'):
            script_path = script_path[1] + ':' + script_path[2:]
        with open(script_path, "r") as f:
            source = f.read()
        self.assertIn("argparse.ArgumentParser", source, "failed to find argparse.ArgumentParser")


class TestGitRepository(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.oldpwd = os.getcwd()
        os.chdir(self.tmpdir)
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)

    def tearDown(self):
        os.chdir(self.oldpwd)
        shutil.rmtree(self.tmpdir)


class TestAdd(TestGitRepository):
    def test_add(self):
        """Test `git fetch-file add <repository> <path>`."""
        subprocess.run(["git", "fetch-file", "add", "https://github.com/octocat/Hello-World.git", "README"], check=True)
        config = configparser.ConfigParser()
        config.read(".git-remote-files")
        section = 'file "README" from "https://github.com/octocat/Hello-World.git"'
        self.assertIn(section, config.sections(), "section not found in .git-remote-files")


class TestPull(TestGitRepository):
    def test_pull(self):
        """Test `git fetch-file pull`."""
        subprocess.run(["git", "fetch-file", "add", "https://github.com/octocat/Hello-World.git", "README"], check=True)
        subprocess.run(["git", "fetch-file", "pull"], check=True)
        self.assertTrue(os.path.exists("README"), "README not found after pull")

    def test_pull_from_subdirectory(self):
        """Test `git fetch-file pull` from a subdirectory with target directory."""
        # Add a file with a target directory
        subprocess.run(["git", "fetch-file", "add", "https://github.com/octocat/Hello-World.git", "README", ".local/bin"], check=True)
        
        # Create subdirectory and change into it
        os.makedirs(".local/bin", exist_ok=True)
        original_dir = os.getcwd()
        try:
            os.chdir(".local/bin")
            
            # Pull from subdirectory
            subprocess.run(["git", "fetch-file", "pull"], check=True)
        finally:
            # Always restore to original directory
            os.chdir(original_dir)
        
        # Verify file is in correct location (relative to repo root)
        expected_path = os.path.join(self.tmpdir, ".local/bin/README")
        self.assertTrue(os.path.exists(expected_path), f"README not found at {expected_path}")
        
        # Verify file is NOT in the wrong location (double-nested path)
        wrong_path = os.path.join(self.tmpdir, ".local/bin/.local/bin/README")
        self.assertFalse(os.path.exists(wrong_path), f"README incorrectly created at {wrong_path}")


class TestWorktree(unittest.TestCase):
    def setUp(self):
        self.oldpwd = os.getcwd()
        # Create source repo with a file to fetch
        self.source_dir = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self.source_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.source_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.source_dir, check=True)
        with open(os.path.join(self.source_dir, "hello.txt"), "w") as f:
            f.write("hello worktree\n")
        subprocess.run(["git", "add", "hello.txt"], cwd=self.source_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.source_dir, check=True, capture_output=True)

        # Create main repo (needs an initial commit for worktree add)
        self.main_dir = tempfile.mkdtemp()
        subprocess.run(["git", "init"], cwd=self.main_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.main_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.main_dir, check=True)
        with open(os.path.join(self.main_dir, "README.md"), "w") as f:
            f.write("main\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.main_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.main_dir, check=True, capture_output=True)

        # Create worktree
        self.worktree_parent = tempfile.mkdtemp()
        self.worktree_dir = os.path.join(self.worktree_parent, "wt")
        subprocess.run(
            ["git", "worktree", "add", self.worktree_dir, "-b", "wt-branch"],
            cwd=self.main_dir,
            check=True,
            capture_output=True,
        )

    def tearDown(self):
        os.chdir(self.oldpwd)
        # Remove worktree registration (ignore errors if already gone)
        subprocess.run(
            ["git", "worktree", "remove", "--force", self.worktree_dir],
            cwd=self.main_dir,
            capture_output=True,
        )
        shutil.rmtree(self.worktree_parent, ignore_errors=True)
        shutil.rmtree(self.main_dir, ignore_errors=True)
        shutil.rmtree(self.source_dir, ignore_errors=True)

    def test_fetch_file_in_worktree(self):
        """Test `git fetch-file` works inside a git worktree."""
        os.chdir(self.worktree_dir)

        # Worktree .git should be a file, not a directory
        self.assertTrue(os.path.isfile(os.path.join(self.worktree_dir, ".git")))

        subprocess.run(["git", "fetch-file", "add", self.source_dir, "hello.txt"], check=True)

        # Manifest should be in worktree, not main repo
        worktree_manifest = os.path.join(self.worktree_dir, ".git-remote-files")
        main_manifest = os.path.join(self.main_dir, ".git-remote-files")
        self.assertTrue(os.path.exists(worktree_manifest), ".git-remote-files not found in worktree")
        self.assertFalse(os.path.exists(main_manifest), ".git-remote-files incorrectly created in main repo")

        config = configparser.ConfigParser()
        config.read(worktree_manifest)
        section = f'file "hello.txt" from "{self.source_dir}"'
        self.assertIn(section, config.sections(), "section not found in worktree .git-remote-files")

        subprocess.run(["git", "fetch-file", "pull"], check=True)

        # File should appear in worktree with correct content
        hello_path = os.path.join(self.worktree_dir, "hello.txt")
        self.assertTrue(os.path.exists(hello_path), "hello.txt not found in worktree after pull")
        with open(hello_path) as f:
            self.assertEqual(f.read(), "hello worktree\n")

        # File should not have been created in main repo
        self.assertFalse(os.path.exists(os.path.join(self.main_dir, "hello.txt")))


if __name__ == "__main__":
    unittest.main()
