"""JIRA Exporter — attaches the generated PDF to a JIRA issue and leaves a comment."""

import logging
import os

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class JiraExporter:
    def __init__(self, url: str, user: str, token: str):
        self.base_url = url.rstrip("/")
        self.auth = HTTPBasicAuth(user, token)

    def attach_and_comment(
        self,
        issue_key: str,
        pdf_path: str,
        platform: str,
        pr_number,
        version: str,
    ) -> None:
        self._attach(issue_key, pdf_path, platform, pr_number)
        self._comment(issue_key, platform, pr_number, version)
        logger.info("JIRA: allegato PDF e commento aggiunti su %s", issue_key)

    def _attach(self, issue_key: str, pdf_path: str, platform: str, pr_number) -> None:
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/attachments"
        filename = f"release_notes_{platform.replace('/', '_')}_PR{pr_number}.pdf"
        with open(pdf_path, "rb") as f:
            resp = requests.post(
                url,
                headers={"X-Atlassian-Token": "no-check"},
                files={"file": (filename, f, "application/pdf")},
                auth=self.auth,
                timeout=30,
            )
        if not resp.ok:
            raise ValueError(
                f"JIRA attachment fallito ({resp.status_code}): {resp.text}"
            )
        logger.info("JIRA: allegato %s su %s", filename, issue_key)

    def _comment(
        self, issue_key: str, platform: str, pr_number, version: str
    ) -> None:
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/comment"
        body = (
            f"Release notes generate automaticamente per *PR #{pr_number}* "
            f"({platform}) — versione *{version}*.\n\n"
            f"Il documento è allegato a questo ticket."
        )
        resp = requests.post(
            url,
            json={"body": body},
            auth=self.auth,
            timeout=15,
        )
        if not resp.ok:
            raise ValueError(
                f"JIRA comment fallito ({resp.status_code}): {resp.text}"
            )
