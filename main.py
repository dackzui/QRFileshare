#!/usr/bin/env python3

import argparse
import sys
from datetime import timezone

from version_info import get_app_info

from config import (
    BASE_URL,
    MAX_EXPIRY_DAYS,
    MIN_EXPIRY_MINUTES,
    QR_OUTPUT_DIR,
)
from database import LinkStore
from expiry import ExpiryError, format_duration, validate_expiry
from qr_generator import build_share_url
from share_service import create_share, format_expiry, format_time_remaining, process_expired_shares, revoke_share
from desktop import run_desktop
from server import run_server


def _fmt_dt(dt) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def cmd_create(args: argparse.Namespace) -> int:
    store = LinkStore()
    if args.minutes is not None:
        try:
            duration = validate_expiry(args.minutes, "minutes")
            value, unit = args.minutes, "minutes"
        except ExpiryError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    elif args.hours is not None:
        try:
            duration = validate_expiry(args.hours, "hours")
            value, unit = args.hours, "hours"
        except ExpiryError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        days = args.days if args.days is not None else store.get_default_expiry()[0]
        if args.days is None and store.get_default_expiry()[1] != "days":
            value, unit = store.get_default_expiry()
        else:
            value, unit = days, "days"
        try:
            duration = validate_expiry(value, unit)
        except ExpiryError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    result = create_share(
        store,
        target_url=args.url,
        label=args.label or "",
        expiry_duration=duration,
        base_url=args.base_url or BASE_URL,
    )
    link = result.link
    share_url = result.share_url
    qr_path = args.output or result.qr_path

    print("Share link created successfully.\n")
    print(f"  Label:        {link.label or '(none)'}")
    print(f"  Target URL:   {link.target_url}")
    print(f"  Share URL:    {share_url}")
    print(f"  Expires:      {_fmt_dt(link.expires_at)} ({format_duration(value, unit)})")
    print(f"  QR image:     {qr_path}")
    print("\nStart the app so scans resolve:")
    print("  python main.py")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from cloud_service import CloudService

    store = LinkStore()
    cloud = CloudService(store)
    process_expired_shares(store, cloud)
    links = store.list_links(include_inactive=args.all)

    if not links:
        print("No share links found.")
        return 0

    base = args.base_url or BASE_URL
    for link in links:
        status = "active" if link.is_available else "unavailable"
        print(f"{link.id}  [{status}]")
        print(f"  label:      {link.label or '(none)'}")
        print(f"  share:      {build_share_url(base, link.id)}")
        print(f"  target:     {link.target_url}")
        print(f"  created:    {_fmt_dt(link.created_at)}")
        print(f"  expires:    {_fmt_dt(link.expires_at)} ({format_time_remaining(link)})")
        print()
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    from cloud_service import CloudService

    store = LinkStore()
    cloud = CloudService(store)
    try:
        message = revoke_share(store, cloud, args.id)
        print(message)
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def cmd_cleanup(args: argparse.Namespace) -> int:
    from cloud_service import CloudService

    store = LinkStore()
    cloud = CloudService(store)
    count = process_expired_shares(store, cloud)
    print(f"Processed {count} expired share(s).")
    return 0


def cmd_desktop(_: argparse.Namespace) -> int:
    return run_desktop()


def cmd_serve(_: argparse.Namespace) -> int:
    run_server()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate QR codes for Google Drive or other cloud folder links "
            "that automatically stop working after a set time."
        ),
    )
    parser.add_argument(
        "--base-url",
        help=f"Public URL for QR codes (default: {BASE_URL})",
    )
    sub = parser.add_subparsers(dest="command")

    desktop = sub.add_parser("desktop", help="Run as standalone desktop app (default)")
    desktop.set_defaults(func=cmd_desktop)

    create = sub.add_parser("create", help="Create an expiring share link and QR image")
    create.add_argument(
        "url",
        help="Cloud storage URL (Google Drive, Dropbox, OneDrive, etc.)",
    )
    create.add_argument(
        "--days",
        type=int,
        help=f"Days until link expires (default from settings, max: {MAX_EXPIRY_DAYS})",
    )
    create.add_argument(
        "--hours",
        type=int,
        help=f"Hours until link expires (max: {MAX_EXPIRY_DAYS * 24})",
    )
    create.add_argument(
        "--minutes",
        type=int,
        help=f"Minutes until link expires (min: {MIN_EXPIRY_MINUTES})",
    )
    create.add_argument("--label", help="Optional label printed under the QR code")
    create.add_argument(
        "--output",
        type=str,
        help=f"QR image output path (default: {QR_OUTPUT_DIR}/share_<id>.png)",
    )
    create.set_defaults(func=cmd_create)

    list_cmd = sub.add_parser("list", help="List share links")
    list_cmd.add_argument("--all", action="store_true", help="Include inactive/expired links")
    list_cmd.set_defaults(func=cmd_list)

    revoke = sub.add_parser("revoke", help="Deactivate a share link immediately")
    revoke.add_argument("id", help="Share link ID")
    revoke.set_defaults(func=cmd_revoke)

    cleanup = sub.add_parser("cleanup", help="Deactivate all expired links")
    cleanup.set_defaults(func=cmd_cleanup)

    serve = sub.add_parser("serve", help="Run in browser mode (development)")
    serve.set_defaults(func=cmd_serve)

    parser.set_defaults(func=cmd_desktop)

    return parser


def main() -> int:
    info = get_app_info()
    __doc__ = f"{info['app_name']} v{info['app_version']} — © {info['app_year']} {info['app_author']}"
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "func", None) is None:
        return cmd_desktop(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
