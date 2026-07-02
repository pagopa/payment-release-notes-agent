"""GitHub API Tools"""

import logging
import re
from github import Github, GithubException
from typing import Tuple, Dict, List, Optional
from src.models import FileChange

logger = logging.getLogger(__name__)


class GitHubTools:
    """GitHub API interaction tools"""
    
    def __init__(self, token: str):
        """Initialize GitHub tools"""
        self.token = token
        self.github = Github(token)
    
    def extract_repo_and_pr_from_url(self, url: str) -> Tuple[str, str, int]:
        """Extract repository and PR number from GitHub URL"""
        pattern = r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)'
        match = re.match(pattern, url)
        
        if not match:
            raise ValueError(f"Invalid GitHub PR URL: {url}")
        
        owner, repo, pr_number = match.groups()
        return owner, repo, int(pr_number)
    
    def get_pr_details(self, owner: str, repo: str, pr_number: int) -> Dict:
        """Get PR details from GitHub"""
        try:
            repository = self.github.get_user(owner).get_repo(repo)
            pr = repository.get_pull(pr_number)
            
            return {
                "number": pr.number,
                "title": pr.title,
                "body": pr.body or "",
                "author": pr.user.login,
                "url": pr.html_url,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "changed_files": pr.changed_files,
                "state": pr.state,
                "created_at": pr.created_at,
                "merged_at": pr.merged_at,
                "head_branch": pr.head.ref,
                "base_branch": pr.base.ref,
                "repo_full_name": pr.base.repo.full_name,
                "labels": [label.name for label in pr.labels],
                "draft": pr.draft,
            }
        except Exception as e:
            logger.error(f"Error fetching PR details: {e}")
            raise
    
    def get_pr_commits(self, owner: str, repo: str, pr_number: int) -> List[Dict]:
        """Get commits from a PR"""
        try:
            repository = self.github.get_user(owner).get_repo(repo)
            pr = repository.get_pull(pr_number)
            
            commits = []
            for commit in pr.get_commits():
                commits.append({
                    "sha": commit.commit.sha,
                    "message": commit.commit.message,
                    "author": commit.commit.author.name,
                    "date": commit.commit.author.date,
                })
            
            logger.info(f"Retrieved {len(commits)} commits from PR #{pr_number}")
            return commits
        except Exception as e:
            logger.error(f"Error fetching PR commits: {e}")
            raise
    
    def get_pr_files(self, owner: str, repo: str, pr_number: int) -> List[FileChange]:
        """Get files changed in a PR with details"""
        try:
            repository = self.github.get_user(owner).get_repo(repo)
            pr = repository.get_pull(pr_number)
            
            files = []
            for file in pr.get_files():
                file_change = FileChange(
                    path=file.filename,
                    status=file.status,
                    additions=file.additions,
                    deletions=file.deletions,
                    changes=file.changes,
                    patch=file.patch if hasattr(file, 'patch') else None,
                )
                files.append(file_change)
            
            logger.info(f"Retrieved {len(files)} files from PR #{pr_number}")
            return files
        except Exception as e:
            logger.error(f"Error fetching PR files: {e}")
            raise
    
    def get_pr_files_dict(self, owner: str, repo: str, pr_number: int) -> List[Dict]:
        """Get files changed in a PR (dict format for backward compatibility)"""
        files = self.get_pr_files(owner, repo, pr_number)
        return [f.to_dict() for f in files]

    _CODEOWNERS_PATHS = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")

    def get_codeowners(self, owner: str, repo: str) -> Optional[str]:
        """Fetch the raw CODEOWNERS file content, checking the standard locations."""
        try:
            repository = self.github.get_user(owner).get_repo(repo)
        except Exception as e:
            logger.warning(f"Could not open repository {owner}/{repo} for CODEOWNERS lookup: {e}")
            return None

        for path in self._CODEOWNERS_PATHS:
            try:
                f = repository.get_contents(path)
                if isinstance(f, list):
                    continue
                return f.decoded_content.decode("utf-8", errors="replace")
            except GithubException:
                continue
        return None
