"""Initial database schema with PostGIS tables and spatial indexes.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-05 14:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create PostGIS extension, core tables, constraints, and spatial indexes."""
    # Enable PostGIS and UUID extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";")

    # 1. Wards Table
    op.create_table(
        'wards',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ward_id', sa.String(length=20), nullable=False),
        sa.Column('ward_name', sa.String(length=100), nullable=False),
        sa.Column('city', sa.String(length=50), server_default='Mumbai', nullable=True),
        sa.Column('geom', Geometry(geometry_type='MULTIPOLYGON', srid=4326, spatial_index=False), nullable=False),
        sa.Column('area_sqkm', sa.Float(), nullable=True),
        sa.Column('population', sa.Integer(), nullable=True),
        sa.Column('is_coastal', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('avg_elevation_m', sa.Float(), nullable=True),
        sa.Column('drainage_index', sa.Float(), server_default='0.5', nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ward_id')
    )
    op.create_index('idx_wards_geom', 'wards', ['geom'], unique=False, postgresql_using='gist')

    # 2. Weather Snapshots Table
    op.create_table(
        'weather_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ward_id', sa.String(length=20), nullable=True),
        sa.Column('source', sa.String(length=30), nullable=True),
        sa.Column('rainfall_1h_mm', sa.Float(), nullable=True),
        sa.Column('rainfall_3h_mm', sa.Float(), nullable=True),
        sa.Column('rainfall_24h_mm', sa.Float(), nullable=True),
        sa.Column('wind_speed_kmh', sa.Float(), nullable=True),
        sa.Column('humidity_pct', sa.Float(), nullable=True),
        sa.Column('tide_height_m', sa.Float(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['ward_id'], ['wards.ward_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Ward Risk Scores Table
    op.create_table(
        'ward_risk_scores',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ward_id', sa.String(length=20), nullable=True),
        sa.Column('risk_score', sa.Float(), nullable=False),
        sa.Column('risk_class', sa.String(length=20), nullable=True),
        sa.Column('model_version', sa.String(length=20), nullable=True),
        sa.Column('inputs_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('risk_score >= 0.0 AND risk_score <= 1.0', name='chk_ward_risk_score_range'),
        sa.CheckConstraint("risk_class IN ('low', 'medium', 'high', 'critical')", name='chk_ward_risk_class'),
        sa.ForeignKeyConstraint(['ward_id'], ['wards.ward_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'idx_risk_ward_time',
        'ward_risk_scores',
        ['ward_id', sa.text('computed_at DESC')],
        unique=False
    )

    # 4. Citizen Reports Table
    op.create_table(
        'citizen_reports',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('report_id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('location', Geometry(geometry_type='POINT', srid=4326, spatial_index=False), nullable=False),
        sa.Column('ward_id', sa.String(length=20), nullable=True),
        sa.Column('flood_depth', sa.String(length=20), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('photo_url', sa.Text(), nullable=True),
        sa.Column('photo_verified', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('depth_est_m', sa.Float(), nullable=True),
        sa.Column('cv_confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=True),
        sa.Column('reported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'verified', 'rejected')", name='chk_citizen_report_status'),
        sa.ForeignKeyConstraint(['ward_id'], ['wards.ward_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_reports_location', 'citizen_reports', ['location'], unique=False, postgresql_using='gist')

    # 5. Social Signals Table
    op.create_table(
        'social_signals',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=True),
        sa.Column('post_id', sa.String(length=100), nullable=True),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('location', Geometry(geometry_type='POINT', srid=4326, spatial_index=False), nullable=True),
        sa.Column('ward_id', sa.String(length=20), nullable=True),
        sa.Column('urgency_class', sa.String(length=20), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('is_spam', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('extracted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint("urgency_class IN ('low', 'medium', 'critical')", name='chk_social_signal_urgency'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('post_id')
    )
    op.create_index('idx_social_location', 'social_signals', ['location'], unique=False, postgresql_using='gist')

    # 6. Alerts Dispatched Table
    op.create_table(
        'alerts_dispatched',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ward_id', sa.String(length=20), nullable=True),
        sa.Column('risk_score', sa.Float(), nullable=True),
        sa.Column('risk_class', sa.String(length=20), nullable=True),
        sa.Column('alert_text_en', sa.Text(), nullable=True),
        sa.Column('alert_text_mr', sa.Text(), nullable=True),
        sa.Column('alert_text_hi', sa.Text(), nullable=True),
        sa.Column('channels', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('recipient_count', sa.Integer(), nullable=True),
        sa.Column('dispatched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('cap_xml', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Drop tables in reverse dependency order and remove spatial indexes."""
    op.drop_table('alerts_dispatched')
    op.drop_index('idx_social_location', table_name='social_signals')
    op.drop_table('social_signals')
    op.drop_index('idx_reports_location', table_name='citizen_reports')
    op.drop_table('citizen_reports')
    op.drop_index('idx_risk_ward_time', table_name='ward_risk_scores')
    op.drop_table('ward_risk_scores')
    op.drop_table('weather_snapshots')
    op.drop_index('idx_wards_geom', table_name='wards')
    op.drop_table('wards')
