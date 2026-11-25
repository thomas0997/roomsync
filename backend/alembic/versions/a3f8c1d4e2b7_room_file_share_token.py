"""room file share token

Revision ID: a3f8c1d4e2b7
Revises: 846e122aa2ed
Create Date: 2026-11-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f8c1d4e2b7'
down_revision: Union[str, Sequence[str], None] = '846e122aa2ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('room_files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('share_token', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_room_files_share_token'), ['share_token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('room_files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_room_files_share_token'))
        batch_op.drop_column('share_token')
