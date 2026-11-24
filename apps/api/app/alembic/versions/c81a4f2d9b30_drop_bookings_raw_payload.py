"""drop bookings.raw_payload

The column duplicated name, email, interview_date and interview_time and was
never read back.

Revision ID: c81a4f2d9b30
Revises: f020b77c13f4
Create Date: 2026-11-13 20:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c81a4f2d9b30"
down_revision: Union[str, Sequence[str], None] = "f020b77c13f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("bookings", "raw_payload")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "bookings",
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
