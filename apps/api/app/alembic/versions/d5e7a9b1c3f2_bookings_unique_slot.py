"""bookings: one interview per slot, not one per slot per person

The slot is the scarce resource: two people cannot sit in the same
interview at the same time. The old index only stopped the *same* person
from booking a slot twice, so two different people could take it.

Only confirmed bookings occupy a slot - a cancelled one must not block a
rebooking, which is why the index stays partial.

Revision ID: d5e7a9b1c3f2
Revises: a3f9c2e17d64
Create Date: 2026-11-14 10:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e7a9b1c3f2"
down_revision: Union[str, Sequence[str], None] = "a3f9c2e17d64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """One confirmed booking per slot."""
    op.drop_index("uq_bookings_slot", table_name="bookings")
    op.create_index(
        "uq_bookings_slot",
        "bookings",
        ["interview_date", "interview_time"],
        unique=True,
        postgresql_where=sa.text("status = 'confirmed'"),
    )


def downgrade() -> None:
    """Back to one confirmed booking per slot per person."""
    op.drop_index("uq_bookings_slot", table_name="bookings")
    op.create_index(
        "uq_bookings_slot",
        "bookings",
        ["email", "interview_date", "interview_time"],
        unique=True,
        postgresql_where=sa.text("status = 'confirmed'"),
    )
