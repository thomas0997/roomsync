"""room folders

Revision ID: f1c2d3e4a5b6
Revises: a3f8c1d4e2b7
Create Date: 2026-11-25 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1c2d3e4a5b6'
down_revision: Union[str, Sequence[str], None] = 'a3f8c1d4e2b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'room_folders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('room_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('share_token', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('room_folders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_room_folders_room_id'), ['room_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_room_folders_share_token'), ['share_token'], unique=True)

    with op.batch_alter_table('room_files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('folder_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_room_files_folder_id'), ['folder_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_room_files_folder_id', 'room_folders', ['folder_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('room_files', schema=None) as batch_op:
        batch_op.drop_constraint('fk_room_files_folder_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_room_files_folder_id'))
        batch_op.drop_column('folder_id')

    with op.batch_alter_table('room_folders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_room_folders_share_token'))
        batch_op.drop_index(batch_op.f('ix_room_folders_room_id'))
    op.drop_table('room_folders')
