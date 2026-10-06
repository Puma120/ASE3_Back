"""quiet hours in user_settings

Revision ID: b7c2d9e41a05
Revises: 8f4ed91ce343
Create Date: 2026-10-04 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c2d9e41a05'
down_revision: Union[str, None] = '8f4ed91ce343'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default para que las filas existentes queden con silencio apagado.
    op.add_column('user_settings', sa.Column('quiet_hours_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('user_settings', sa.Column('quiet_start_hour', sa.Integer(), nullable=False, server_default='22'))
    op.add_column('user_settings', sa.Column('quiet_end_hour', sa.Integer(), nullable=False, server_default='8'))


def downgrade() -> None:
    op.drop_column('user_settings', 'quiet_end_hour')
    op.drop_column('user_settings', 'quiet_start_hour')
    op.drop_column('user_settings', 'quiet_hours_enabled')
