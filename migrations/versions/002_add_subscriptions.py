"""Add subscriptions and payments tables for monetization.

Revision ID: 002
Revises: 001_initial
Create Date: 2025-11-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade():
    # Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('tier', sa.String(length=50), nullable=False),
        sa.Column('price_in_stars', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('auto_renew', sa.Boolean(), nullable=False),
        sa.Column('summaries_per_month', sa.Integer(), nullable=False),
        sa.Column('summaries_used_this_month', sa.Integer(), nullable=False),
        sa.Column('summaries_reset_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='_subscriptions_user_id_uc')
    )
    op.create_index('idx_subscription_tier', 'subscriptions', ['tier'])
    op.create_index('idx_subscription_expires', 'subscriptions', ['expires_at'])
    op.create_index('idx_subscription_reset', 'subscriptions', ['summaries_reset_at'])

    # Create payments table
    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_payment_id', sa.String(length=255), nullable=False),
        sa.Column('tier', sa.String(length=50), nullable=False),
        sa.Column('amount_in_stars', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('invoice_id', sa.String(length=255), nullable=True),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('is_refunded', sa.Boolean(), nullable=False),
        sa.Column('refunded_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_payment_id', name='_payments_telegram_payment_id_uc')
    )
    op.create_index('idx_payment_user', 'payments', ['user_id'])
    op.create_index('idx_payment_status', 'payments', ['status'])
    op.create_index('idx_payment_created', 'payments', ['created_at'])
    op.create_index('idx_payment_tier', 'payments', ['tier'])
    op.create_index('idx_payment_invoice', 'payments', ['invoice_id'])


def downgrade():
    op.drop_index('idx_payment_invoice', table_name='payments')
    op.drop_index('idx_payment_tier', table_name='payments')
    op.drop_index('idx_payment_created', table_name='payments')
    op.drop_index('idx_payment_status', table_name='payments')
    op.drop_index('idx_payment_user', table_name='payments')
    op.drop_table('payments')

    op.drop_index('idx_subscription_reset', table_name='subscriptions')
    op.drop_index('idx_subscription_expires', table_name='subscriptions')
    op.drop_index('idx_subscription_tier', table_name='subscriptions')
    op.drop_table('subscriptions')
