"""inbox messages, inbox blocks, task attachments

Revision ID: a7b8c9d0e1f2
Revises: f5a6b7c8d9e0
Create Date: 2026-11-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('task_files',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('file_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['file_id'], ['room_files.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_id', 'file_id', name='uq_task_file')
    )
    with op.batch_alter_table('task_files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_files_file_id'), ['file_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_files_task_id'), ['task_id'], unique=False)

    op.create_table('inbox_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('from_user_id', sa.Integer(), nullable=False),
    sa.Column('to_user_id', sa.Integer(), nullable=False),
    sa.Column('subject', sa.String(length=120), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reply_to_id', sa.Integer(), nullable=True),
    sa.Column('archived', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('deleted_by_sender', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('deleted_by_recipient', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['reply_to_id'], ['inbox_messages.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['to_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('inbox_messages', schema=None) as batch_op:
        batch_op.create_index('ix_inbox_from_id', ['from_user_id', 'id'], unique=False)
        batch_op.create_index('ix_inbox_to_id', ['to_user_id', 'id'], unique=False)

    op.create_table('inbox_blocks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('blocker_id', sa.Integer(), nullable=False),
    sa.Column('blocked_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['blocked_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['blocker_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('blocker_id', 'blocked_id', name='uq_inbox_block')
    )
    with op.batch_alter_table('inbox_blocks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inbox_blocks_blocker_id'), ['blocker_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('inbox_blocks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inbox_blocks_blocker_id'))
    op.drop_table('inbox_blocks')

    with op.batch_alter_table('inbox_messages', schema=None) as batch_op:
        batch_op.drop_index('ix_inbox_to_id')
        batch_op.drop_index('ix_inbox_from_id')
    op.drop_table('inbox_messages')

    with op.batch_alter_table('task_files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_files_task_id'))
        batch_op.drop_index(batch_op.f('ix_task_files_file_id'))
    op.drop_table('task_files')
