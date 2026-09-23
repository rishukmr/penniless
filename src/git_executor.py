"""
git_executor.py — Fully autonomous Git & GitHub operations.

Handles:
  1. Forking target repository to user's account (`gh repo fork --clone`)
  2. Creating feature branch
  3. Writing/modifying target files
  4. Committing and pushing to remote fork
  5. Creating Pull Request via GitHub CLI (`gh pr create`)
  6. Returning live PR URL for ledger logging
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()

_PROJECT_ROOT = Path(__file__).parent.parent
_WORKSPACES_DIR = _PROJECT_ROOT / "workspaces"


def _run_cmd(cmd: list[str], cwd: Optional[Path] = None, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run shell command and return CompletedProcess, raising on failure."""
    cmd_str = " ".join(cmd)
    try:
        res = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=(sys.platform == "win32"),
            encoding="utf-8",
            errors="replace",
        )
        return res
    except Exception as e:
        raise RuntimeError(f"Command failed [{cmd_str}]: {e}")


def normalize_repo_name(raw_url: str) -> str:
    """Extract 'owner/repo' from URL or string."""
    raw = raw_url.strip().rstrip("/")
    if "github.com/" in raw:
        raw = raw.split("github.com/")[-1]
    # Remove .git suffix if present
    if raw.endswith(".git"):
        raw = raw[:-4]
    # Format should be owner/repo
    parts = [p for p in raw.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return raw


class GitExecutor:
    """Automates GitHub fork, branch, commit, push, and PR submission."""

    def __init__(self, workspaces_dir: Path = _WORKSPACES_DIR) -> None:
        self.workspaces_dir = workspaces_dir
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)

    def fork_and_clone(self, target_repo: str) -> Path:
        """
        Fork target_repo using gh CLI and clone it into workspaces directory.
        Returns the local Path to the cloned repository.
        """
        repo_slug = normalize_repo_name(target_repo)
        safe_name = repo_slug.replace("/", "_")
        repo_dir = self.workspaces_dir / safe_name

        if repo_dir.exists() and (repo_dir / ".git").exists():
            console.print(f"  [dim]Repository workspace already exists at {repo_dir.name}[/dim]")
            return repo_dir

        console.print(f"  [cyan]Forking & cloning {repo_slug} into workspaces...[/cyan]")
        
        # Try gh repo fork --clone
        cmd = ["gh", "repo", "fork", repo_slug, "--clone=true", f"--{repo_dir}"]
        res = _run_cmd(["gh", "repo", "fork", repo_slug, "--clone", str(repo_dir)], timeout=180)
        
        if res.returncode != 0:
            console.print(f"  [yellow]Notice from gh fork: {res.stderr.strip() or res.stdout.strip()}[/yellow]")
            # Fallback: if already forked, try cloning the user's fork or target directly
            if not repo_dir.exists():
                console.print(f"  [cyan]Cloning target repo directly...[/cyan]")
                res_clone = _run_cmd(["git", "clone", f"https://github.com/{repo_slug}.git", str(repo_dir)], timeout=180)
                if res_clone.returncode != 0:
                    raise RuntimeError(f"Failed to clone repository {repo_slug}: {res_clone.stderr}")

        return repo_dir

    def create_branch(self, repo_dir: Path, branch_name: str) -> None:
        """Create and checkout a new git branch."""
        # Sanitize branch name
        clean_branch = re.sub(r"[^a-zA-Z0-9_\-\.]", "-", branch_name).strip("-")
        if not clean_branch:
            clean_branch = "fix-bounty-patch"

        console.print(f"  [dim]Checking out branch: {clean_branch}[/dim]")
        # Checkout clean default branch first (main or master)
        _run_cmd(["git", "checkout", "main"], cwd=repo_dir)
        _run_cmd(["git", "checkout", "master"], cwd=repo_dir)
        # Create branch
        res = _run_cmd(["git", "checkout", "-b", clean_branch], cwd=repo_dir)
        if res.returncode != 0:
            # If already exists, switch to it
            _run_cmd(["git", "checkout", clean_branch], cwd=repo_dir)

    def write_files(self, repo_dir: Path, file_changes: dict[str, str]) -> list[str]:
        """
        Write new contents to files in repo_dir.
        file_changes: {relative_path: file_content_str}
        Returns list of modified file paths.
        """
        modified: list[str] = []
        for rel_path, content in file_changes.items():
            if not rel_path or not content:
                continue
            clean_rel = rel_path.strip().lstrip("/\\")
            target_file = repo_dir / clean_rel
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content, encoding="utf-8")
            modified.append(clean_rel)
            console.print(f"  [green]✓ Updated {clean_rel}[/green]")
        return modified

    def commit_and_push(self, repo_dir: Path, branch_name: str, commit_msg: str) -> None:
        """Stage all changes, commit, and push to origin."""
        console.print(f"  [dim]Committing: {commit_msg[:60]}...[/dim]")
        _run_cmd(["git", "add", "."], cwd=repo_dir)
        
        res_commit = _run_cmd(["git", "commit", "-m", commit_msg], cwd=repo_dir)
        if res_commit.returncode != 0 and "nothing to commit" not in (res_commit.stdout + res_commit.stderr).lower():
            console.print(f"  [yellow]Commit note: {res_commit.stdout.strip()}[/yellow]")

        console.print(f"  [cyan]Pushing branch {branch_name} to origin...[/cyan]")
        res_push = _run_cmd(["git", "push", "-u", "origin", branch_name], cwd=repo_dir, timeout=120)
        if res_push.returncode != 0:
            # Try force push or push with explicit refspec
            console.print(f"  [yellow]Standard push notice: {res_push.stderr.strip()}[/yellow]")
            _run_cmd(["git", "push", "origin", branch_name], cwd=repo_dir, timeout=120)

    def create_pr(
        self,
        repo_dir: Path,
        target_repo: str,
        branch_name: str,
        pr_title: str,
        pr_body: str,
    ) -> str:
        """
        Submit Pull Request using gh CLI.
        Returns the live PR URL.
        """
        repo_slug = normalize_repo_name(target_repo)
        console.print(f"  [bold cyan]Submitting PR to {repo_slug}...[/bold cyan]")

        # Prepare body file to avoid shell quoting issues
        temp_body = repo_dir / ".pr_body.txt"
        temp_body.write_text(pr_body, encoding="utf-8")

        try:
            cmd = [
                "gh", "pr", "create",
                "--repo", repo_slug,
                "--title", pr_title,
                "--body-file", str(temp_body),
            ]
            res = _run_cmd(cmd, cwd=repo_dir, timeout=120)
            output = (res.stdout + "\n" + res.stderr).strip()

            # Extract PR URL from output
            match = re.search(r"https://github\.com/[^\s]+/pull/\d+", output)
            if match:
                pr_url = match.group(0)
                console.print(f"  [bold green]🚀 Pull Request Live: {pr_url}[/bold green]")
                return pr_url
            
            # Check if PR already exists
            match_exists = re.search(r"https://github\.com/[^\s]+/pull/\d+", output)
            if "already exists" in output.lower():
                console.print(f"  [yellow]PR already exists: {output}[/yellow]")
                return output
            
            console.print(f"  [yellow]gh pr create output: {output}[/yellow]")
            return output
        finally:
            if temp_body.exists():
                try:
                    temp_body.unlink()
                except Exception:
                    pass

    def execute_complete_pr(
        self,
        target_repo: str,
        branch_name: str,
        file_changes: dict[str, str],
        pr_title: str,
        pr_body: str,
    ) -> str:
        """
        Full zero-touch automated workflow:
        Fork ➔ Clone ➔ Branch ➔ Write Files ➔ Commit ➔ Push ➔ Submit PR.
        """
        repo_dir = self.fork_and_clone(target_repo)
        self.create_branch(repo_dir, branch_name)
        self.write_files(repo_dir, file_changes)
        self.commit_and_push(repo_dir, branch_name, pr_title)
        pr_url = self.create_pr(repo_dir, target_repo, branch_name, pr_title, pr_body)
        return pr_url


# Global executor instance
git_exec = GitExecutor()
