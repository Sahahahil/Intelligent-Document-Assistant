"""bookings: the row is the booking - drop the status column

A booking row is only ever created after the user confirms, so a stored row
was already a confirmed booking. The status column existed for one reason:
cancelling kept the row but had to release the slot, which made the slot
index partial.

Cancelling now removes the row, so the slot index is a plain unique index
and the column has no job left.

Revision ID: b8c4e1d90a76
Revises: d5e7a9b1c3f2
Create Date: 2026-11-14 12:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c4e1d90a76"
down_revision: Union[str, Sequence[str], None] = "d5e7a9b1c3f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """One booking per slot, no status column."""
    # The index goes first: it is partial on `status`, so dropping the column
    # would take it with it.
    op.drop_index("uq_bookings_slot", table_name="bookings")
    # A cancelled booking is now the same thing as no booking at all, so it
    # goes before the column that marked it disappears.
    op.execute("DELETE FROM bookings WHERE status = 'cancelled'")
    op.drop_column("bookings", "status")
    op.create_index(
        "uq_bookings_slot",
        "bookings",
        ["interview_date", "interview_time"],
        unique=True,
    )


def downgrade() -> None:
    """Back to a status column and a partial slot index."""
    op.add_column(
        "bookings",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="confirmed"),
    )
    op.create_check_constraint(
        "ck_bookings_status", "bookings", "status IN ('confirmed', 'cancelled')"
    )
    op.drop_index("uq_bookings_slot", table_name="bookings")
    op.create_index(
        "uq_bookings_slot",
        "bookings",
        ["interview_date", "interview_time"],
        unique=True,
        postgresql_where=sa.text("status = 'confirmed'"),
    )
