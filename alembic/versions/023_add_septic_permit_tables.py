"""Add septic permit tables for National Septic OCR system

Revision ID: 023_add_septic_permit_tables
Revises: 022_add_call_intelligence_columns
Create Date: 2026-01-19 14:30:00.000000

This migration creates:
- states: US state reference table
- counties: County reference table
- septic_system_types: System type enumeration
- source_portals: Scraper source tracking
- septic_permits: Main permit table (designed for 7M+ records)
- permit_versions: Audit trail for changes
- permit_duplicates: Duplicate detection tracking
- permit_import_batches: Batch import tracking

Extensions enabled:
- pg_trgm: Trigram similarity for fuzzy text matching
- (pgvector: Optional - for semantic search embeddings)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '023_add_septic_permit_tables'
down_revision: Union[str, Sequence[str], None] = '022_add_call_intelligence_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - create septic permit tables."""

    # ===== ENABLE EXTENSIONS =====
    # pg_trgm for fuzzy text matching
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    # pgvector for semantic search (optional - fails gracefully if not available)
    op.execute("""
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS vector;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'pgvector extension not available - semantic search will use fallback';
        END $$;
    """)

    # ===== CREATE STATES TABLE =====
    op.create_table(
        'states',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('code', sa.String(2), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('fips_code', sa.String(2), nullable=True),
        sa.Column('region', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    )
    op.create_index('idx_states_code', 'states', ['code'])

    # ===== CREATE COUNTIES TABLE =====
    op.create_table(
        'counties',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('state_id', sa.Integer, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('normalized_name', sa.String(100), nullable=False),
        sa.Column('fips_code', sa.String(5), nullable=True),
        sa.Column('population', sa.Integer, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['state_id'], ['states.id'], name='fk_counties_state_id'),
        sa.UniqueConstraint('state_id', 'normalized_name', name='uq_county_state_name')
    )
    op.create_index('idx_counties_state', 'counties', ['state_id'])
    op.create_index('idx_counties_normalized_name', 'counties', ['normalized_name'])

    # ===== CREATE SEPTIC_SYSTEM_TYPES TABLE =====
    op.create_table(
        'septic_system_types',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    )

    # ===== CREATE SOURCE_PORTALS TABLE =====
    op.create_table(
        'source_portals',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('code', sa.String(100), nullable=False, unique=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('state_id', sa.Integer, nullable=True),
        sa.Column('platform', sa.String(50), nullable=True),
        sa.Column('base_url', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('last_scraped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_records_scraped', sa.Integer, default=0),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['state_id'], ['states.id'], name='fk_source_portals_state_id')
    )

    # ===== CREATE SEPTIC_PERMITS TABLE (MAIN TABLE - 7M+ RECORDS) =====
    op.create_table(
        'septic_permits',
        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),

        # Core identification
        sa.Column('permit_number', sa.String(100), nullable=True),
        sa.Column('state_id', sa.Integer, nullable=False),
        sa.Column('county_id', sa.Integer, nullable=True),

        # Address fields (for deduplication)
        sa.Column('address', sa.Text, nullable=True),
        sa.Column('address_normalized', sa.Text, nullable=True),
        sa.Column('address_hash', sa.String(64), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('zip_code', sa.String(20), nullable=True),

        # Parcel and geo
        sa.Column('parcel_number', sa.String(100), nullable=True),
        sa.Column('latitude', sa.Float, nullable=True),
        sa.Column('longitude', sa.Float, nullable=True),

        # Owner/applicant information
        sa.Column('owner_name', sa.String(255), nullable=True),
        sa.Column('owner_name_normalized', sa.String(255), nullable=True),
        sa.Column('applicant_name', sa.String(255), nullable=True),
        sa.Column('contractor_name', sa.String(255), nullable=True),

        # Dates
        sa.Column('install_date', sa.Date, nullable=True),
        sa.Column('permit_date', sa.Date, nullable=True),
        sa.Column('expiration_date', sa.Date, nullable=True),

        # System specifications
        sa.Column('system_type_id', sa.Integer, nullable=True),
        sa.Column('system_type_raw', sa.String(200), nullable=True),
        sa.Column('tank_size_gallons', sa.Integer, nullable=True),
        sa.Column('drainfield_size_sqft', sa.Integer, nullable=True),
        sa.Column('bedrooms', sa.SmallInteger, nullable=True),
        sa.Column('daily_flow_gpd', sa.Integer, nullable=True),

        # Document links
        sa.Column('pdf_url', sa.Text, nullable=True),
        sa.Column('permit_url', sa.Text, nullable=True),

        # Source tracking
        sa.Column('source_portal_id', sa.Integer, nullable=True),
        sa.Column('source_portal_code', sa.String(100), nullable=True),
        sa.Column('scraped_at', sa.DateTime(timezone=True), nullable=False),

        # Raw data storage
        sa.Column('raw_data', postgresql.JSON, nullable=True),

        # Search optimization (embeddings stored as float array)
        sa.Column('embedding', postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column('embedding_model', sa.String(100), nullable=True),
        sa.Column('embedding_updated_at', sa.DateTime(timezone=True), nullable=True),

        # Full-text search vector
        sa.Column('search_vector', postgresql.TSVECTOR, nullable=True),

        # Combined searchable text
        sa.Column('searchable_text', sa.Text, nullable=True),

        # Record metadata
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('data_quality_score', sa.SmallInteger, nullable=True),
        sa.Column('duplicate_of_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('version', sa.Integer, nullable=False, default=1),
        sa.Column('record_hash', sa.String(64), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        # Foreign keys
        sa.ForeignKeyConstraint(['state_id'], ['states.id'], name='fk_septic_permits_state_id'),
        sa.ForeignKeyConstraint(['county_id'], ['counties.id'], name='fk_septic_permits_county_id'),
        sa.ForeignKeyConstraint(['system_type_id'], ['septic_system_types.id'], name='fk_septic_permits_system_type_id'),
        sa.ForeignKeyConstraint(['source_portal_id'], ['source_portals.id'], name='fk_septic_permits_source_portal_id')
    )

    # Basic indexes
    op.create_index('idx_septic_permits_permit_number', 'septic_permits', ['permit_number'])
    op.create_index('idx_septic_permits_state_id', 'septic_permits', ['state_id'])
    op.create_index('idx_septic_permits_county_id', 'septic_permits', ['county_id'])
    op.create_index('idx_septic_permits_address_hash', 'septic_permits', ['address_hash'])
    op.create_index('idx_septic_permits_city', 'septic_permits', ['city'])
    op.create_index('idx_septic_permits_zip_code', 'septic_permits', ['zip_code'])
    op.create_index('idx_septic_permits_parcel_number', 'septic_permits', ['parcel_number'])
    op.create_index('idx_septic_permits_install_date', 'septic_permits', ['install_date'])
    op.create_index('idx_septic_permits_permit_date', 'septic_permits', ['permit_date'])
    op.create_index('idx_septic_permits_scraped_at', 'septic_permits', ['scraped_at'])

    # Composite indexes for common queries
    op.create_index('idx_septic_permits_state_county', 'septic_permits', ['state_id', 'county_id'])
    op.create_index('idx_septic_permits_state_county_date', 'septic_permits', ['state_id', 'county_id', 'permit_date'])

    # GIN index for full-text search
    op.execute("""
        CREATE INDEX idx_septic_permits_search_vector
        ON septic_permits USING gin(search_vector)
    """)

    # Trigram index for fuzzy address search
    op.execute("""
        CREATE INDEX idx_septic_permits_address_trgm
        ON septic_permits USING gin(address_normalized gin_trgm_ops)
    """)

    # Partial unique indexes for deduplication (only active records)
    op.execute("""
        CREATE UNIQUE INDEX idx_septic_permits_dedup_address
        ON septic_permits(address_hash, county_id, state_id)
        WHERE address_hash IS NOT NULL AND is_active = TRUE
    """)

    op.execute("""
        CREATE UNIQUE INDEX idx_septic_permits_dedup_permit
        ON septic_permits(permit_number, state_id)
        WHERE permit_number IS NOT NULL AND is_active = TRUE
    """)

    # Trigger to auto-update search_vector on insert/update
    op.execute("""
        CREATE OR REPLACE FUNCTION update_septic_permit_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.permit_number, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.address, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.owner_name, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.city, '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.applicant_name, '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(NEW.contractor_name, '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(NEW.system_type_raw, '')), 'D');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trig_septic_permits_search_vector
        BEFORE INSERT OR UPDATE ON septic_permits
        FOR EACH ROW EXECUTE FUNCTION update_septic_permit_search_vector();
    """)

    # ===== CREATE PERMIT_VERSIONS TABLE =====
    op.create_table(
        'permit_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('permit_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('permit_data', postgresql.JSON, nullable=False),
        sa.Column('changed_fields', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('change_source', sa.String(50), nullable=False),
        sa.Column('change_reason', sa.Text, nullable=True),
        sa.Column('source_portal_id', sa.Integer, nullable=True),
        sa.Column('scraped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['permit_id'], ['septic_permits.id'], ondelete='CASCADE', name='fk_permit_versions_permit_id'),
        sa.ForeignKeyConstraint(['source_portal_id'], ['source_portals.id'], name='fk_permit_versions_source_portal_id'),
        sa.UniqueConstraint('permit_id', 'version', name='uq_permit_version')
    )
    op.create_index('idx_permit_versions_permit', 'permit_versions', ['permit_id'])
    op.create_index('idx_permit_versions_created', 'permit_versions', ['created_at'])

    # ===== CREATE PERMIT_DUPLICATES TABLE =====
    op.create_table(
        'permit_duplicates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('permit_id_1', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('permit_id_2', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('detection_method', sa.String(50), nullable=False),
        sa.Column('confidence_score', sa.Float, nullable=True),
        sa.Column('matching_fields', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('canonical_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.String(255), nullable=True),
        sa.Column('resolution_notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['permit_id_1'], ['septic_permits.id'], name='fk_permit_duplicates_permit1'),
        sa.ForeignKeyConstraint(['permit_id_2'], ['septic_permits.id'], name='fk_permit_duplicates_permit2'),
        sa.UniqueConstraint('permit_id_1', 'permit_id_2', name='uq_permit_duplicate_pair'),
        sa.CheckConstraint('permit_id_1 < permit_id_2', name='ck_permit_id_ordering')
    )
    op.create_index('idx_permit_duplicates_permit1', 'permit_duplicates', ['permit_id_1'])
    op.create_index('idx_permit_duplicates_permit2', 'permit_duplicates', ['permit_id_2'])
    op.create_index('idx_permit_duplicates_status', 'permit_duplicates', ['status'])

    # ===== CREATE PERMIT_IMPORT_BATCHES TABLE =====
    op.create_table(
        'permit_import_batches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('source_portal_id', sa.Integer, nullable=True),
        sa.Column('source_name', sa.String(100), nullable=False),
        sa.Column('total_records', sa.Integer, nullable=False),
        sa.Column('inserted', sa.Integer, default=0),
        sa.Column('updated', sa.Integer, default=0),
        sa.Column('skipped', sa.Integer, default=0),
        sa.Column('errors', sa.Integer, default=0),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_time_seconds', sa.Float, nullable=True),
        sa.Column('error_details', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['source_portal_id'], ['source_portals.id'], name='fk_import_batches_source_portal_id')
    )

    # ===== SEED REFERENCE DATA =====
    # Insert US states
    op.execute("""
        INSERT INTO states (code, name, fips_code, region) VALUES
        ('AL', 'Alabama', '01', 'South'),
        ('AK', 'Alaska', '02', 'West'),
        ('AZ', 'Arizona', '04', 'West'),
        ('AR', 'Arkansas', '05', 'South'),
        ('CA', 'California', '06', 'West'),
        ('CO', 'Colorado', '08', 'West'),
        ('CT', 'Connecticut', '09', 'Northeast'),
        ('DE', 'Delaware', '10', 'South'),
        ('FL', 'Florida', '12', 'South'),
        ('GA', 'Georgia', '13', 'South'),
        ('HI', 'Hawaii', '15', 'West'),
        ('ID', 'Idaho', '16', 'West'),
        ('IL', 'Illinois', '17', 'Midwest'),
        ('IN', 'Indiana', '18', 'Midwest'),
        ('IA', 'Iowa', '19', 'Midwest'),
        ('KS', 'Kansas', '20', 'Midwest'),
        ('KY', 'Kentucky', '21', 'South'),
        ('LA', 'Louisiana', '22', 'South'),
        ('ME', 'Maine', '23', 'Northeast'),
        ('MD', 'Maryland', '24', 'South'),
        ('MA', 'Massachusetts', '25', 'Northeast'),
        ('MI', 'Michigan', '26', 'Midwest'),
        ('MN', 'Minnesota', '27', 'Midwest'),
        ('MS', 'Mississippi', '28', 'South'),
        ('MO', 'Missouri', '29', 'Midwest'),
        ('MT', 'Montana', '30', 'West'),
        ('NE', 'Nebraska', '31', 'Midwest'),
        ('NV', 'Nevada', '32', 'West'),
        ('NH', 'New Hampshire', '33', 'Northeast'),
        ('NJ', 'New Jersey', '34', 'Northeast'),
        ('NM', 'New Mexico', '35', 'West'),
        ('NY', 'New York', '36', 'Northeast'),
        ('NC', 'North Carolina', '37', 'South'),
        ('ND', 'North Dakota', '38', 'Midwest'),
        ('OH', 'Ohio', '39', 'Midwest'),
        ('OK', 'Oklahoma', '40', 'South'),
        ('OR', 'Oregon', '41', 'West'),
        ('PA', 'Pennsylvania', '42', 'Northeast'),
        ('RI', 'Rhode Island', '44', 'Northeast'),
        ('SC', 'South Carolina', '45', 'South'),
        ('SD', 'South Dakota', '46', 'Midwest'),
        ('TN', 'Tennessee', '47', 'South'),
        ('TX', 'Texas', '48', 'South'),
        ('UT', 'Utah', '49', 'West'),
        ('VT', 'Vermont', '50', 'Northeast'),
        ('VA', 'Virginia', '51', 'South'),
        ('WA', 'Washington', '53', 'West'),
        ('WV', 'West Virginia', '54', 'South'),
        ('WI', 'Wisconsin', '55', 'Midwest'),
        ('WY', 'Wyoming', '56', 'West'),
        ('DC', 'District of Columbia', '11', 'South'),
        ('PR', 'Puerto Rico', '72', 'Other'),
        ('VI', 'Virgin Islands', '78', 'Other'),
        ('GU', 'Guam', '66', 'Other'),
        ('AS', 'American Samoa', '60', 'Other'),
        ('MP', 'Northern Mariana Islands', '69', 'Other')
        ON CONFLICT (code) DO NOTHING;
    """)

    # Insert common septic system types
    op.execute("""
        INSERT INTO septic_system_types (code, name, category, description) VALUES
        ('CONVENTIONAL', 'Conventional Septic System', 'Standard', 'Traditional gravity-fed septic tank with drainfield'),
        ('ATU', 'Aerobic Treatment Unit', 'Alternative', 'Uses oxygen to break down waste'),
        ('MOUND', 'Mound System', 'Alternative', 'Elevated drainfield for high water table areas'),
        ('SAND_FILTER', 'Sand Filter System', 'Alternative', 'Uses sand bed for additional treatment'),
        ('DRIP', 'Drip Distribution System', 'Alternative', 'Low-pressure drip irrigation'),
        ('CHAMBER', 'Chamber System', 'Alternative', 'Plastic chambers instead of gravel'),
        ('CONSTRUCTED_WETLAND', 'Constructed Wetland', 'Alternative', 'Natural treatment using wetland plants'),
        ('CLUSTER', 'Cluster/Community System', 'Community', 'Serves multiple properties'),
        ('CESSPOOL', 'Cesspool', 'Legacy', 'Older pit system (no longer permitted in most areas)'),
        ('HOLDING_TANK', 'Holding Tank', 'Temporary', 'Requires regular pumping'),
        ('GRAY_WATER', 'Gray Water System', 'Alternative', 'Separate treatment for gray water'),
        ('COMPOSTING', 'Composting Toilet System', 'Alternative', 'Waterless composting system'),
        ('EVAPOTRANSPIRATION', 'Evapotranspiration System', 'Alternative', 'ET bed for arid climates'),
        ('RECIRCULATING', 'Recirculating Sand Filter', 'Alternative', 'Multi-pass sand filter treatment'),
        ('UNKNOWN', 'Unknown/Unspecified', 'Other', 'System type not specified')
        ON CONFLICT (code) DO NOTHING;
    """)


def downgrade() -> None:
    """Downgrade schema - drop septic permit tables."""
    # Drop trigger first
    op.execute('DROP TRIGGER IF EXISTS trig_septic_permits_search_vector ON septic_permits')
    op.execute('DROP FUNCTION IF EXISTS update_septic_permit_search_vector()')

    # Drop tables in reverse dependency order
    op.drop_table('permit_import_batches')
    op.drop_table('permit_duplicates')
    op.drop_table('permit_versions')
    op.drop_table('septic_permits')
    op.drop_table('source_portals')
    op.drop_table('septic_system_types')
    op.drop_table('counties')
    op.drop_table('states')
