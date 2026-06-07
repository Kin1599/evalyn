"""add rule engine fields to assignments

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assignments",
        sa.Column("check_mode", sa.String(length=16), nullable=False, server_default="llm"),
    )
    op.add_column(
        "assignments",
        sa.Column("rule_config_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assignments", "rule_config_json")
    op.drop_column("assignments", "check_mode")
