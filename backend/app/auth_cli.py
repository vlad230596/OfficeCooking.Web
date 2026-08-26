import argparse
import asyncio
import getpass
import re
import sys

from sqlalchemy import select

from app.authentication import hash_password, revoke_user_sessions
from app.config import get_settings
from app.database import create_engine, create_session_factory
from app.models import User


async def _list_users() -> int:
    engine = create_engine(get_settings())
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            users = (await session.execute(select(User).order_by(User.legacy_id))).scalars().all()
            for user in users:
                state = "enabled" if user.auth_enabled else "disabled"
                print(
                    f"{user.legacy_id}\t{user.name}\t{user.username or '-'}\t{user.role}\t{state}"
                )
        return 0
    finally:
        await engine.dispose()


async def _set_user(args: argparse.Namespace) -> int:
    username = args.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,100}", username):
        print(
            "Username must be 3-100 ASCII letters, digits, dots, dashes, or underscores.",
            file=sys.stderr,
        )
        return 2
    password = (
        sys.stdin.readline().rstrip("\r\n")
        if args.password_stdin
        else getpass.getpass("Password (minimum 12 characters): ")
    )
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    engine = create_engine(get_settings())
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            user = (
                await session.execute(select(User).where(User.legacy_id == args.legacy_id))
            ).scalar_one_or_none()
            if user is None:
                print(f"No user has legacy id {args.legacy_id}.", file=sys.stderr)
                return 1
            user.username = username
            user.password_hash = password_hash
            user.role = args.role
            user.auth_enabled = True
            await revoke_user_sessions(session, user.id)
            await session.commit()
            print(f"Access enabled for {user.name} as {user.username} ({user.role}).")
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Manage OfficeCooking login accounts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list-users")
    set_user = subparsers.add_parser("set-user")
    set_user.add_argument("--legacy-id", required=True, type=int)
    set_user.add_argument("--username", required=True)
    set_user.add_argument("--role", choices=("viewer", "editor", "admin"), required=True)
    set_user.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(_list_users() if args.command == "list-users" else _set_user(args))
    raise SystemExit(result)


if __name__ == "__main__":
    main()
