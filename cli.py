#!/usr/bin/env python3
"""CLI utility for importing/exporting data from files.

Usage:
    python cli.py import --file data.csv                        # auto-detect type
    python cli.py import --file data.json --type measurements   # explicit type
    python cli.py import --file data.json --type measurements --mode insert
    python cli.py export --type measurements --format csv       # export to stdout
    python cli.py export --type measurements --format json --out data.json
    python cli.py export --full --out backup.json               # full backup
    python cli.py template --type measurements --format csv     # download template

Requires: DATABASE_URL env var set (or uses .env), user authenticated via token.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure we can import app modules
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


def get_token_from_env() -> str | None:
    """Try to get a token: CLI_TOKEN env var or generate one via API."""
    return os.getenv("CLI_TOKEN")


async def cmd_template(args: argparse.Namespace) -> None:
    """Print a template to stdout."""
    from app.api.import_data import TEMPLATES

    if args.type not in TEMPLATES:
        print(f"Unknown template type: {args.type}", file=sys.stderr)
        print(f"Available: {list(TEMPLATES)}", file=sys.stderr)
        sys.exit(1)

    tmpl = TEMPLATES[args.type]
    if args.format == "csv":
        print(tmpl["csv_headers"])
        if tmpl.get("example_csv"):
            print(tmpl["example_csv"])
    else:
        print(json.dumps(tmpl.get("json_schema", {}), indent=2))


async def cmd_import(args: argparse.Namespace) -> None:
    """Import data from a file into the database."""
    from sqlalchemy import select as sa_select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.models.user import User

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    content = filepath.read_text(encoding="utf-8")

    # Connect to DB
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        # Find user
        token = args.token or get_token_from_env()
        user = None

        if token:
            from jose import jwt as jose_jwt

            try:
                payload = jose_jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
                uid = payload.get("sub")
                if uid:
                    result = await db.execute(sa_select(User).where(User.id == uid))
                    user = result.scalar_one_or_none()
            except Exception:
                pass

        if not user:
            # Fallback: first user
            result = await db.execute(sa_select(User).limit(1))
            user = result.scalar_one_or_none()

        if not user:
            print("No user found. Register a user first or set CLI_TOKEN.", file=sys.stderr)
            sys.exit(1)

        print(f"👤 Importing as: {user.email}")

        # Import
        from app.api.import_data import _import_csv, _import_json

        if filepath.suffix == ".csv":
            result = await _import_csv(content, db, user)
        elif filepath.suffix == ".json":
            data = json.loads(content)
            if args.type:
                data["import_type"] = args.type
            if args.mode:
                data["mode"] = args.mode
            result = await _import_json(data, db, user, mode=args.mode or "upsert")
        else:
            print(f"Unsupported file format: {filepath.suffix}", file=sys.stderr)
            sys.exit(1)

        print(json.dumps(result, indent=2))
        print(f"\n✅ Imported {result.get('imported', 0)} records ({result.get('skipped', 0)} skipped)")


async def cmd_export(args: argparse.Namespace) -> None:
    """Export data to stdout or file."""
    from sqlalchemy import select as sa_select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.api.import_data import EXPORT_TYPES, _model_to_dict, _rows_to_csv
    from app.config import settings
    from app.models.user import User

    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        # Find user
        token = args.token or get_token_from_env()
        user = None
        if token:
            from jose import jwt as jose_jwt

            try:
                payload = jose_jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
                uid = payload.get("sub")
                if uid:
                    result = await db.execute(sa_select(User).where(User.id == uid))
                    user = result.scalar_one_or_none()
            except Exception:
                pass
        if not user:
            result = await db.execute(sa_select(User).limit(1))
            user = result.scalar_one_or_none()
        if not user:
            print("No user found.", file=sys.stderr)
            sys.exit(1)

        if args.full:
            # Full backup
            from app.gamification.handler import get_or_create_progress

            full: dict = {
                "exported_at": datetime.now(UTC).isoformat(),
                "version": "0.5.0",
                "user": {"email": user.email},
            }
            for etype, info in EXPORT_TYPES.items():
                result = await db.execute(
                    sa_select(info["model"])
                    .where(info["model"].user_id == user.id)
                    .order_by(info["model"].created_at.desc())
                    .limit(5000)
                )
                rows = result.scalars().all()
                full[etype] = {"count": len(rows), "data": [_model_to_dict(r) for r in rows]}
            progress = await get_or_create_progress(db, user.id)
            full["progress"] = {"xp": progress.xp, "level": progress.level}
            output = json.dumps(full, indent=2, ensure_ascii=False, default=str)
        else:
            if args.type not in EXPORT_TYPES:
                print(f"Unknown export type: {args.type}", file=sys.stderr)
                print(f"Available: {list(EXPORT_TYPES)}", file=sys.stderr)
                sys.exit(1)

            info = EXPORT_TYPES[args.type]
            result = await db.execute(
                sa_select(info["model"])
                .where(info["model"].user_id == user.id)
                .order_by(info["model"].created_at.desc())
                .limit(args.limit)
            )
            rows = result.scalars().all()

            if args.format == "csv":
                csv_resp = _rows_to_csv(rows, info["csv_headers"], args.type)
                output = csv_resp.body.decode("utf-8")
            else:
                data = {"export_type": args.type, "count": len(rows), "data": [_model_to_dict(r) for r in rows]}
                output = json.dumps(data, indent=2, ensure_ascii=False, default=str)

        if args.out:
            Path(args.out).write_text(output, encoding="utf-8")
            print(f"✅ Exported to {args.out}")
        else:
            print(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Practice Loop CLI — Import/Export data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py import --file data.csv
  python cli.py export --type measurements --format json --out backup.json
  python cli.py export --full --out full_backup.json
  python cli.py template --type inventory --format csv
        """,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # import
    p_import = sub.add_parser("import", help="Import data from file")
    p_import.add_argument("--file", required=True, help="Path to .csv or .json file")
    p_import.add_argument("--type", help="Import type (if not auto-detected)")
    p_import.add_argument("--mode", default="upsert", choices=["upsert", "insert", "replace"])
    p_import.add_argument("--token", help="JWT access token")

    # export
    p_export = sub.add_parser("export", help="Export data")
    p_export.add_argument("--type", help="Data type to export")
    p_export.add_argument("--full", action="store_true", help="Full backup (all types)")
    p_export.add_argument("--format", default="json", choices=["json", "csv"])
    p_export.add_argument("--out", help="Output file (default: stdout)")
    p_export.add_argument("--limit", type=int, default=10000)
    p_export.add_argument("--token", help="JWT access token")

    # template
    p_tpl = sub.add_parser("template", help="Download template")
    p_tpl.add_argument("--type", required=True, help="Template type")
    p_tpl.add_argument("--format", default="csv", choices=["csv", "json"])

    args = parser.parse_args()

    if args.command == "import":
        asyncio.run(cmd_import(args))
    elif args.command == "export":
        asyncio.run(cmd_export(args))
    elif args.command == "template":
        asyncio.run(cmd_template(args))


if __name__ == "__main__":
    main()
