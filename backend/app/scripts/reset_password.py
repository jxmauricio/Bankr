"""Reset a user's password by hand -- the stand-in for a "forgot password"
flow while the beta is small enough for the operator to do it.

    python -m app.scripts.reset_password friend@example.com
    python -m app.scripts.reset_password friend@example.com --prompt

By default a random temporary password is generated and printed once, for
you to send the user; --prompt asks for one instead (input hidden). Runs
against whatever DATABASE_URL points at, so on Render use the service's
Shell tab to reset a production account.
"""

import argparse
import getpass
import secrets
import sys

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.db.base import SessionLocal
from app.db.models import User

MIN_PASSWORD_LENGTH = 8  # same rule as POST /auth/signup


class ResetError(Exception):
    pass


def reset_password(db: Session, email: str, new_password: str) -> User:
    """Set a new password for the account with this email (case-insensitive)."""
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise ResetError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    users = db.query(User).filter(func.lower(User.email) == email.strip().lower()).all()
    if not users:
        raise ResetError(f"No account found for {email}")
    if len(users) > 1:
        raise ResetError(f"More than one account matches {email} ignoring case; fix that by hand first")

    user = users[0]
    user.password_hash = hash_password(new_password)
    db.commit()
    return user


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(12)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset a Bankr user's password.")
    parser.add_argument("email")
    parser.add_argument("--prompt", action="store_true", help="type the new password instead of generating one")
    args = parser.parse_args(argv)

    if args.prompt:
        new_password = getpass.getpass("New password: ")
        if getpass.getpass("Repeat it: ") != new_password:
            print("Passwords didn't match; nothing changed.", file=sys.stderr)
            return 1
    else:
        new_password = generate_temporary_password()

    with SessionLocal() as db:
        try:
            user = reset_password(db, args.email, new_password)
        except ResetError as exc:
            print(f"{exc}; nothing changed.", file=sys.stderr)
            return 1

    print(f"Password reset for {user.email}.")
    if not args.prompt:
        print(f"Temporary password: {new_password}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
