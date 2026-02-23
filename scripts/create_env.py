#!/usr/bin/env python3
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path


def random_secret() -> str:
    return secrets.token_urlsafe(48)


def prompt_with_default(prompt: str, default: str, non_interactive: bool) -> str:
    if non_interactive:
        return default
    raw = input(f"{prompt} [{default}]: ").strip()
    return raw if raw else default


def prompt_required(prompt: str, fallback: str, non_interactive: bool) -> str:
    if non_interactive:
        return fallback
    while True:
        raw = input(f"{prompt}: ").strip()
        if raw:
            return raw
        print("[env] Value is required.")


def prompt_yes_no(prompt: str, default: bool, non_interactive: bool) -> bool:
    if non_interactive:
        return default

    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"{prompt} {suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("[env] Please answer y or n.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a .env file for codePost API deployment.",
    )
    parser.add_argument(
        "--output",
        default=".env",
        help="Output file path (default: .env)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing file",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use defaults/placeholders without prompts",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        print(f"[env] {output_path} already exists. Use --force to overwrite.")
        return 1

    print(f"[env] Creating {output_path}")

    default_secret_key = random_secret()
    default_field_key = random_secret()
    default_worker_secret = random_secret()

    debug = "False"
    secret_key = prompt_with_default("SECRET_KEY", default_secret_key, args.non_interactive)
    field_encryption_key = prompt_with_default(
        "FIELD_ENCRYPTION_KEY", default_field_key, args.non_interactive
    )

    db_hostname = prompt_with_default(
        "DB_HOSTNAME (Data VM hostname/IP)", "codepost-database", args.non_interactive
    )
    db_name = prompt_with_default("DB_NAME", "codepost", args.non_interactive)
    db_user = prompt_with_default("DB_USER (compat only)", "codepost_user", args.non_interactive)
    db_password = prompt_required("DB_PASSWORD", "<secure_db_password>", args.non_interactive)
    root_db_password = prompt_required(
        "ROOT_DATABASE_PASSWORD", "<secure_root_password>", args.non_interactive
    )

    api_user = prompt_with_default("API_USER", "admin_user", args.non_interactive)
    api_password = prompt_required("API_PASSWORD", "<secure_admin_password>", args.non_interactive)

    api_url = prompt_with_default("API_URL", "https://api.yourdomain.com", args.non_interactive)
    client_url = prompt_with_default("CLIENT_URL", "https://yourdomain.com", args.non_interactive)

    email_host = prompt_with_default("EMAIL_HOST", "smtp.yourprovider.com", args.non_interactive)
    default_email_from = prompt_with_default(
        "DEFAULT_EMAIL_FROM", "no-reply@yourdomain.com", args.non_interactive
    )

    celery_concurrency = prompt_with_default("CELERY_CONCURRENCY", "4", args.non_interactive)
    host_dataset_root = prompt_with_default("HOST_DATASET_ROOT", "/mnt/datasets", args.non_interactive)
    autograder_auto_execute = (
        "true"
        if prompt_yes_no("Enable AUTOGRADER_AUTO_EXECUTE?", True, args.non_interactive)
        else "false"
    )

    worker_shell_ws_url = prompt_with_default("WORKER_SHELL_WS_URL (optional)", "", args.non_interactive)
    worker_shell_shared_secret = prompt_with_default(
        "WORKER_SHELL_SHARED_SECRET", default_worker_secret, args.non_interactive
    )
    worker_shell_redis_url = prompt_with_default(
        "WORKER_SHELL_REDIS_URL (optional, defaults to redis://DB_HOSTNAME:6379)",
        f"redis://{db_hostname}:6379",
        args.non_interactive,
    )
    worker_shell_worker_id = prompt_with_default(
        "WORKER_SHELL_WORKER_ID (optional)", "", args.non_interactive
    )

    nfs_enabled = prompt_yes_no("Enable NFS-backed DB volume?", True, args.non_interactive)
    if nfs_enabled:
        nfs_server_ip = prompt_required("NFS_SERVER_IP", "<nfs_server_ip>", args.non_interactive)
        nfs_share_path = prompt_required("NFS_SHARE_PATH", "<nfs_share_path>", args.non_interactive)
    else:
        nfs_server_ip = ""
        nfs_share_path = ""

    env_text = f"""# Debugging
DEBUG={debug}

# Security & Encryption
SECRET_KEY={secret_key}
FIELD_ENCRYPTION_KEY={field_encryption_key}

# Database Configuration
DB_HOSTNAME={db_hostname}
DB_NAME={db_name}
DB_USER={db_user}
DB_PASSWORD={db_password}
ROOT_DATABASE_PASSWORD={root_db_password}

# API Admin User (created on startup if not exists)
API_USER={api_user}
API_PASSWORD={api_password}

# URLs (Important for CORS and emails)
API_URL={api_url}
CLIENT_URL={client_url}

# Email Settings
EMAIL_HOST={email_host}
DEFAULT_EMAIL_FROM={default_email_from}

# Celery / Redis
CELERY_CONCURRENCY={celery_concurrency}

# Storage Paths (Host)
HOST_DATASET_ROOT={host_dataset_root}

# Auto-Grader Settings for running submissions automatically.
AUTOGRADER_AUTO_EXECUTE={autograder_auto_execute}

# Worker shell relay (API -> worker)
# Example internal WS URL: ws://codepost-worker-shell:8001
WORKER_SHELL_WS_URL={worker_shell_ws_url}
WORKER_SHELL_SHARED_SECRET={worker_shell_shared_secret}

# Worker shell relay (Redis)
# Example: redis://codepost-redis:6379/0
WORKER_SHELL_REDIS_URL={worker_shell_redis_url}
WORKER_SHELL_WORKER_ID={worker_shell_worker_id}

# NFS-backed DB volume toggle (used by deployment scripts/docs)
NFS_ENABLED={str(nfs_enabled).lower()}

# Required when using NFS-backed database volume in docker-compose-data.yml
NFS_SERVER_IP={nfs_server_ip}
NFS_SHARE_PATH={nfs_share_path}
"""

    output_path.write_text(env_text, encoding="utf-8")

    print(f"[env] Wrote {output_path}")
    if not nfs_enabled:
        print("[env] NFS is disabled in this .env (NFS_ENABLED=false).")
        print("[env] Note: current docker-compose-data.yml uses NFS driver options for db-data.")
        print("[env]       If running without NFS, update docker-compose-data.yml volume driver options accordingly.")
    elif not nfs_server_ip or not nfs_share_path:
        print("[env] Note: NFS_SERVER_IP/NFS_SHARE_PATH are blank. Fill them if your Data VM uses NFS-backed DB volume.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
