"""
Self-contained, lightweight Atlassian Jira Cloud REST API v2 client.
Handles validation, fetching ticket fields, and posting status comments.
"""
import os
import logging
import requests
from requests.auth import HTTPBasicAuth

log = logging.getLogger(__name__)


class JiraClient:
    def __init__(self):
        self.base_url = os.getenv("JIRA_BASE_URL", "https://seedtag.atlassian.net").rstrip("/")
        self.email = os.getenv("JIRA_EMAIL", "").strip()
        self.token = os.getenv("JIRA_API_TOKEN", "").strip()
        self.project_key = os.getenv("JIRA_PROJECT_KEY", "SDS").strip()

        # Jira client is optional; if credentials aren't set, it runs in dummy/disabled mode.
        self.enabled = bool(self.email and self.token)
        if not self.enabled:
            log.warning("Jira Client: JIRA_EMAIL or JIRA_API_TOKEN is missing. Jira comments/detection will be disabled.")

    def _get_auth(self):
        return HTTPBasicAuth(self.email, self.token)

    def get_issue_fields(self, ticket_key: str) -> dict:
        """
        Fetches the ticket summary plus custom fields for Operator Entity and Industry.
        Summary: campo `summary`
        Operator Entity (Country): customfield_14324
        Industry (Category): customfield_15831
        """
        if not self.enabled:
            log.info("Jira Client: disabled. Skipping field retrieval.")
            return {"country": None, "category": None, "summary": None}

        # Security check: only SDS issues (or whatever JIRA_PROJECT_KEY is)
        if not ticket_key.startswith(self.project_key + "-"):
            log.warning(f"Jira Client: ticket {ticket_key} is not from project {self.project_key}. Rejecting.")
            return {"country": None, "category": None, "summary": None}

        url = f"{self.base_url}/rest/api/2/issue/{ticket_key}"
        try:
            r = requests.get(
                url,
                auth=self._get_auth(),
                timeout=10,
                headers={"Accept": "application/json"}
            )
            if r.status_code == 404:
                log.warning(f"Jira Client: ticket {ticket_key} not found.")
                return {"country": None, "category": None, "summary": None}
            if r.status_code != 200:
                log.error(f"Jira Client: failed to fetch ticket {ticket_key} (HTTP {r.status_code})")
                return {"country": None, "category": None, "summary": None}

            issue = r.json()
            fields = issue.get("fields", {})
            summary_val = fields.get("summary")

            # Parse customfield_14324 (Operator Entity/Country)
            raw_country = fields.get("customfield_14324")
            country_val = None
            if isinstance(raw_country, dict):
                country_val = raw_country.get("value")
            elif isinstance(raw_country, str):
                country_val = raw_country

            # Parse customfield_15831 (Industry/Category)
            raw_category = fields.get("customfield_15831")
            category_val = None
            if isinstance(raw_category, dict):
                category_val = raw_category.get("value")
            elif isinstance(raw_category, str):
                category_val = raw_category

            log.info(f"Jira Client: fetched metadata for {ticket_key} — country={country_val}, category={category_val}")
            return {"country": country_val, "category": category_val, "summary": summary_val}

        except Exception as e:
            log.exception(f"Jira Client: exception fetching {ticket_key}: {e}")
            return {"country": None, "category": None, "summary": None}

    def add_comment(self, ticket_key: str, comment_text: str) -> bool:
        """
        Adds a plain text / markdown comment to the Jira issue.
        """
        if not self.enabled:
            log.info("Jira Client: disabled. Skipping comment creation.")
            return False

        if not ticket_key.startswith(self.project_key + "-"):
            log.warning(f"Jira Client: ticket {ticket_key} is not from project {self.project_key}. Cannot comment.")
            return False

        url = f"{self.base_url}/rest/api/2/issue/{ticket_key}/comment"
        try:
            r = requests.post(
                url,
                auth=self._get_auth(),
                json={"body": comment_text},
                timeout=10,
                headers={"Content-Type": "application/json", "Accept": "application/json"}
            )
            if r.status_code in (200, 201):
                log.info(f"Jira Client: successfully commented on {ticket_key}")
                return True
            else:
                log.error(f"Jira Client: failed to comment on {ticket_key} (HTTP {r.status_code}): {r.text[:300]}")
                return False
        except Exception as e:
            log.exception(f"Jira Client: exception commenting on {ticket_key}: {e}")
            return False
