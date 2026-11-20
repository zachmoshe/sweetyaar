#!/usr/bin/env python3
"""Builds and deploys SweetYaar Admin (the log viewer over the cloud uploads)
to Cloud Run, behind IAP, as the sweetyaar-admin service account.

  deploy_admin.py [--users a@x,b@y] [--region europe-west1] [--dry-run]
  deploy_admin.py --local      (build the image with Docker only)

Each deploy also applies the IAP OAuth client from Secret Manager and makes
the IAP allow list exactly --users (default: the gcloud account deploying).
The one-time project setup is in "SweetYaar Admin" in
docs/engineering/logging-and-debugging.md.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICE = "sweetyaar-admin"
OAUTH_SECRET = "sweetyaar-admin-oauth"  # the IAP OAuth client JSON, as the console downloads it
ACCESSOR = "roles/iap.httpsResourceAccessor"
# The image's context, at the paths the code expects (devlog.ROOT).
CONTEXT = {"cloud/admin/Dockerfile": "Dockerfile", "cloud/admin/requirements.txt": "requirements.txt",
           "tools/devlog.py": "tools/devlog.py", "tools/logviewer": "tools/logviewer",
           "firmware/esp32/src/DevLogEvents.h": "firmware/esp32/src/DevLogEvents.h"}


def stage(folder: pathlib.Path) -> None:
    for source, target in CONTEXT.items():
        path, out = ROOT / source, folder / target
        out.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, out, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(path, out)


def gcloud(*args: str, dry_run: bool = False, capture: bool = False) -> str:
    command = ["gcloud", *args]
    print("$ " + " ".join(command), flush=True)
    if dry_run:
        return ""
    result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE if capture else None)
    return result.stdout or ""


def access_members(project: str, region: str) -> set[str]:
    policy = json.loads(gcloud("iap", "web", "get-iam-policy", f"--project={project}", "--resource-type=cloud-run",
                               f"--region={region}", f"--service={SERVICE}", "--format=json", capture=True) or "{}")
    return {member for binding in policy.get("bindings", []) if binding["role"] == ACCESSOR
            for member in binding["members"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default="sweetyaar")
    parser.add_argument("--region", default="europe-west1")
    parser.add_argument("--users", help="comma-separated Google accounts allowed in (default: the gcloud account)")
    parser.add_argument("--local", action="store_true", help="only build the image with Docker, as sweetyaar-admin:local")
    parser.add_argument("--dry-run", action="store_true", help="print the gcloud commands without running them")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as folder:
        context = pathlib.Path(folder)
        stage(context)
        if args.local:
            subprocess.run(["docker", "build", "--platform=linux/amd64", "-t", f"{SERVICE}:local", str(context)],
                           check=True)
            return 0
        users = args.users or gcloud("config", "get-value", "account", capture=True).strip()
        wanted = {f"user:{user.strip()}" for user in users.split(",") if user.strip()}
        if not wanted and not args.dry_run:
            sys.exit("No users to allow: pass --users")
        where = [f"--project={args.project}", f"--region={args.region}"]
        account = f"{SERVICE}@{args.project}.iam.gserviceaccount.com"
        gcloud("run", "deploy", SERVICE, *where, f"--source={context}", f"--service-account={account}",
               "--no-allow-unauthenticated", "--iap", "--cpu-boost", "--min-instances=0", "--max-instances=1",
               "--memory=1Gi", "--timeout=300", "--quiet", dry_run=args.dry_run)

    number = gcloud("projects", "describe", args.project, "--format=value(projectNumber)", capture=True,
                    dry_run=args.dry_run).strip() or "PROJECT_NUMBER"
    gcloud("run", "services", "add-iam-policy-binding", SERVICE, *where,
           f"--member=serviceAccount:service-{number}@gcp-sa-iap.iam.gserviceaccount.com", "--role=roles/run.invoker",
           "--quiet", dry_run=args.dry_run, capture=True)

    # The OAuth client lets Gmail accounts sign in (the project has no organisation).
    client = json.loads(gcloud("secrets", "versions", "access", "latest", f"--secret={OAUTH_SECRET}",
                               f"--project={args.project}", capture=True, dry_run=args.dry_run) or "{}")
    client = client.get("web", client)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as settings:
        json.dump({"accessSettings": {"oauthSettings": {"clientId": client.get("client_id", "CLIENT_ID"),
                                                        "clientSecret": client.get("client_secret", "SECRET")}}},
                  settings)
    try:
        os.chmod(settings.name, 0o600)
        gcloud("iap", "settings", "set", settings.name, f"--project={args.project}", "--resource-type=cloud-run",
               f"--region={args.region}", f"--service={SERVICE}", "--quiet", dry_run=args.dry_run, capture=True)
    finally:
        os.unlink(settings.name)

    current = set() if args.dry_run else access_members(args.project, args.region)
    for member in sorted(wanted - current):
        gcloud("iap", "web", "add-iam-policy-binding", f"--member={member}", f"--role={ACCESSOR}", *where,
               "--resource-type=cloud-run", f"--service={SERVICE}", "--quiet", dry_run=args.dry_run, capture=True)
    for member in sorted(current - wanted):
        gcloud("iap", "web", "remove-iam-policy-binding", f"--member={member}", f"--role={ACCESSOR}", *where,
               "--resource-type=cloud-run", f"--service={SERVICE}", "--quiet", dry_run=args.dry_run, capture=True)
    url = gcloud("run", "services", "describe", SERVICE, *where, "--format=value(status.url)", capture=True,
                 dry_run=args.dry_run).strip()
    print(f"SweetYaar Admin: {url or '(dry run)'}, open to {', '.join(sorted(wanted)) or '(no one)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
