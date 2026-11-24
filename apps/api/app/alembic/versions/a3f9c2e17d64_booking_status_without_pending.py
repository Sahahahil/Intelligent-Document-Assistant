"""bookings.status without 'pending'

Rows are only written after the user confirms, so 'pending' never occurred.
Any legacy pending row is a confirmed booking that was written without a
status.

Revision ID: a3f9c2e17d64
Revises: c81a4f2d9b30
Create Date: 2026-11-13 21:05:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f9c2e17d64"
down_revision: Union[str, Sequence[str], None] = "c81a4f2d9b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE bookings SET status = 'confirmed' WHERE status = 'pending'")
    op.drop_constraint("ck_bookings_status", "bookings", type_="check")
    op.create_check_constraint(
        "ck_bookings_status", "bookings", "status IN ('confirmed', 'cancelled')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_bookings_status", "bookings", type_="check")
    op.create_check_constraint(
        "ck_bookings_status", "bookings", "status IN ('pending', 'confirmed', 'cancelled')"
    )
