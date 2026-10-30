"""room files can live in R2

Revision ID: d41e7c90a5f2
Revises: b3a3d8ba1280
Create Date: 2026-10-30 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd41e7c90a5f2'
down_revision: Union[str, Sequence[str], None] = 'b3a3d8ba1280'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add storage_key (where the file is in R2) and let `data` be empty for files kept in R2."""
    with op.batch_alter_table('room_files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('storage_key', sa.String(length=200), nullable=True))
        batch_op.alter_column('data', existing_type=sa.LargeBinary(), nullable=True)


def downgrade() -> None:
    """Only works while every file is still stored in `data` (files kept in R2 have no data to put back)."""
    with op.batch_alter_table('room_files', schema=None) as batch_op:
        batch_op.alter_column('data', existing_type=sa.LargeBinary(), nullable=False)
        batch_op.drop_column('storage_key')
