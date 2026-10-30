"""MCP connector: OAuth clients, grants, authorization codes, and proposals

Revision ID: f2a9c6e1b754
Revises: c3a9f1e8b247
Create Date: 2026-10-30 12:00:00.000000

Lets Claude/ChatGPT connect over OAuth 2.1 (app/mcp_oauth.py) with a read
or read + write grant the user can revoke, and stores what a write-scope
client proposes until the user confirms it in Bankr.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "f2a9c6e1b754"
down_revision: Union[str, None] = "c3a9f1e8b247"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(), primary_key=True),
        sa.Column("client_name", sa.String(), nullable=True),
        sa.Column("redirect_uris", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mcp_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("client_name", sa.String(), nullable=False),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mcp_grants_user_id", "mcp_grants", ["user_id"])
    op.create_table(
        "oauth_authorizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("client_name", sa.String(), nullable=False),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=True),
        sa.Column("code_challenge", sa.String(), nullable=False),
        sa.Column("requested_scope", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("grant_id", sa.Uuid(), sa.ForeignKey("mcp_grants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("code_hash", sa.String(), nullable=True, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "mcp_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grant_id", sa.Uuid(), sa.ForeignKey("mcp_grants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mcp_proposals_user_id", "mcp_proposals", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_mcp_proposals_user_id", "mcp_proposals")
    op.drop_table("mcp_proposals")
    op.drop_table("oauth_authorizations")
    op.drop_index("ix_mcp_grants_user_id", "mcp_grants")
    op.drop_table("mcp_grants")
    op.drop_table("oauth_clients")
