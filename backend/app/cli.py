"""
Management CLI. Run with: python -m app.cli <command>

Usage:
    python -m app.cli create-admin --email admin@example.com --phone +15551234567 --password secret
"""

import argparse
import asyncio

from sqlalchemy import func, select

from app.db import AsyncSessionLocal
from app.models.user import User
from app.schemas.target import normalize_phone
from app.services.auth import hash_password, validate_password_strength


async def _create_admin(email: str, phone: str, password: str) -> None:
    email = email.strip().lower()

    # Same canonical form the API stores, so an admin created here can be found
    # by the number they give and can be sent a password-reset code.
    try:
        phone = normalize_phone(phone)
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    try:
        validate_password_strength(password)
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(func.lower(User.email) == email))
        if existing.scalar_one_or_none():
            print(f"Error: user with email {email} already exists.")
            return

        user = User(
            email=email,
            name="Admin",
            phone=phone,
            hashed_password=hash_password(password),
            role="admin",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Admin created: {user.email} (id={user.id})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Powerline management CLI")
    subparsers = parser.add_subparsers(dest="command")

    create_admin = subparsers.add_parser("create-admin", help="Create an admin user")
    create_admin.add_argument("--email", required=True)
    create_admin.add_argument("--phone", required=True, help="E.164 phone number, e.g. +15551234567")
    create_admin.add_argument("--password", required=True)

    args = parser.parse_args()

    if args.command == "create-admin":
        asyncio.run(_create_admin(args.email, args.phone, args.password))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
