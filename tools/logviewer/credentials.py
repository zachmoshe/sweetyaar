"""Access tokens as the sweetyaar-admin service account, the identity of the
SweetYaar Admin app: it reads the logs in Firestore and the archived ELFs,
and keeps the notes in the admin resources bucket.

On Cloud Run the service runs as that account (K_SERVICE is set there) and
its own credentials are used. Elsewhere the gcloud CLI's login impersonates
it, so application-default credentials are not used (see "SweetYaar Admin"
in docs/engineering/logging-and-debugging.md).
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import threading

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
REFRESH_BEFORE = dt.timedelta(minutes=5)
GCLOUD_LIFETIME = dt.timedelta(minutes=50)  # gcloud's tokens last an hour


def account(project: str) -> str:
    return f"sweetyaar-admin@{project}.iam.gserviceaccount.com"


def on_cloud_run() -> bool:
    return bool(os.environ.get("K_SERVICE"))


class Credentials:
    def __init__(self, project: str, run=subprocess.run):
        self.project, self.account, self.run = project, account(project), run
        self._token: tuple[str, dt.datetime] | None = None
        self._lock = threading.Lock()

    def token(self, request=None, scopes=None) -> tuple[str, dt.datetime]:
        """A token and its expiry (naive UTC), reused until shortly before it
        expires. The arguments make it a google-auth refresh handler."""
        with self._lock:
            if self._token is None or self._token[1] - REFRESH_BEFORE <= now():
                self._token = self._service() if on_cloud_run() else self._gcloud()
            return self._token

    def access_token(self) -> str:
        return self.token()[0]

    def _service(self) -> tuple[str, dt.datetime]:
        import google.auth
        import google.auth.transport.requests
        credentials, _ = google.auth.default(scopes=[SCOPE])
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token, credentials.expiry

    def _gcloud(self) -> tuple[str, dt.datetime]:
        result = self.run(["gcloud", "auth", "print-access-token", f"--impersonate-service-account={self.account}"],
                          capture_output=True, text=True, timeout=60)
        lines = result.stdout.split()
        if result.returncode or not lines:
            reason = (result.stderr.strip().splitlines() or ["no output"])[-1]
            raise RuntimeError(f"gcloud could not get a {self.account} token: {reason}")
        return lines[-1], now() + GCLOUD_LIFETIME


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
