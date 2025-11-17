"""Initial migration - Create tables for groups, messages, and summaries.

Revision ID: 001_initial
Revises: 
Create Date: 2025-11-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database schema."""
    
    # Create groups table
    op.create_table(
        'groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('member_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('bot_added_at', sa.DateTime(), nullable=True),
        sa.Column('bot_removed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', name='uq_groups_group_id'),
    )
    
    # Create indexes for groups
    op.create_index('idx_group_active_deleted', 'groups', ['is_active', 'deleted_at'])
    op.create_index('idx_group_created', 'groups', ['created_at'])
    op.create_index('idx_group_id', 'groups', ['group_id'])
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(255), nullable=True),
        sa.Column('first_name', sa.String(255), nullable=True),
        sa.Column('last_name', sa.String(255), nullable=True),
        sa.Column('opt_out', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('opt_out_reason', sa.String(500), nullable=True),
        sa.Column('opt_out_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_users_user_id'),
    )
    
    # Create indexes for users
    op.create_index('idx_user_opt_out', 'users', ['opt_out'])
    op.create_index('idx_user_active', 'users', ['deleted_at'])
    op.create_index('idx_user_id', 'users', ['user_id'])
    
    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('sentiment', sa.String(50), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('dominant_emotion', sa.String(50), nullable=True),
        sa.Column('emotion_data', sa.Text(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.group_id'], name='fk_messages_group_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], name='fk_messages_user_id'),
        sa.UniqueConstraint('group_id', 'message_id', name='uq_message_unique_per_group'),
    )
    
    # Create indexes for messages
    op.create_index('idx_message_timestamp', 'messages', ['timestamp'])
    op.create_index('idx_message_sentiment', 'messages', ['sentiment'])
    op.create_index('idx_message_group_timestamp', 'messages', ['group_id', 'timestamp'])
    op.create_index('idx_message_user_group', 'messages', ['user_id', 'group_id'])
    op.create_index('idx_message_deleted', 'messages', ['deleted_at'])
    op.create_index('idx_message_group_id', 'messages', ['group_id'])
    op.create_index('idx_message_user_id', 'messages', ['user_id'])
    
    # Create summaries table
    op.create_table(
        'summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('summary_id', sa.String(255), nullable=False),
        sa.Column('group_id', sa.BigInteger(), nullable=False),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=False),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('participant_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('dominant_sentiment', sa.String(50), nullable=True),
        sa.Column('key_topics', sa.Text(), nullable=True),
        sa.Column('key_decisions', sa.Text(), nullable=True),
        sa.Column('action_items', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('processing_time_seconds', sa.Float(), nullable=True),
        sa.Column('language', sa.String(10), nullable=False, server_default='en'),
        sa.Column('model_used', sa.String(50), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('is_ai_generated', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.group_id'], name='fk_summaries_group_id'),
        sa.UniqueConstraint('summary_id', name='uq_summaries_summary_id'),
    )
    
    # Create indexes for summaries
    op.create_index('idx_summary_period', 'summaries', ['period_start', 'period_end'])
    op.create_index('idx_summary_group_period', 'summaries', ['group_id', 'period_start', 'period_end'])
    op.create_index('idx_summary_created', 'summaries', ['created_at'])
    op.create_index('idx_summary_sentiment', 'summaries', ['dominant_sentiment'])
    op.create_index('idx_summary_deleted', 'summaries', ['deleted_at'])
    op.create_index('idx_summary_id', 'summaries', ['summary_id'])
    op.create_index('idx_summary_group_id', 'summaries', ['group_id'])
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(50), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    
    # Create indexes for audit_logs
    op.create_index('idx_audit_action_entity', 'audit_logs', ['action', 'entity_type'])
    op.create_index('idx_audit_created', 'audit_logs', ['created_at'])
    op.create_index('idx_audit_user_id', 'audit_logs', ['user_id'])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_index('idx_audit_user_id', table_name='audit_logs')
    op.drop_index('idx_audit_created', table_name='audit_logs')
    op.drop_index('idx_audit_action_entity', table_name='audit_logs')
    op.drop_table('audit_logs')
    
    op.drop_index('idx_summary_group_id', table_name='summaries')
    op.drop_index('idx_summary_id', table_name='summaries')
    op.drop_index('idx_summary_deleted', table_name='summaries')
    op.drop_index('idx_summary_sentiment', table_name='summaries')
    op.drop_index('idx_summary_created', table_name='summaries')
    op.drop_index('idx_summary_group_period', table_name='summaries')
    op.drop_index('idx_summary_period', table_name='summaries')
    op.drop_table('summaries')
    
    op.drop_index('idx_message_user_id', table_name='messages')
    op.drop_index('idx_message_group_id', table_name='messages')
    op.drop_index('idx_message_deleted', table_name='messages')
    op.drop_index('idx_message_user_group', table_name='messages')
    op.drop_index('idx_message_group_timestamp', table_name='messages')
    op.drop_index('idx_message_sentiment', table_name='messages')
    op.drop_index('idx_message_timestamp', table_name='messages')
    op.drop_table('messages')
    
    op.drop_index('idx_user_id', table_name='users')
    op.drop_index('idx_user_active', table_name='users')
    op.drop_index('idx_user_opt_out', table_name='users')
    op.drop_table('users')
    
    op.drop_index('idx_group_id', table_name='groups')
    op.drop_index('idx_group_created', table_name='groups')
    op.drop_index('idx_group_active_deleted', table_name='groups')
    op.drop_table('groups')
