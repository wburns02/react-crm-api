"""Create base tables (customers, work_orders, messages)

Revision ID: 000_create_base_tables
Revises:
Create Date: 2024-12-28

Note: These are the core tables that other tables depend on.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '000_create_base_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create base tables."""
    conn = op.get_bind()

    # Create customers table
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'customers')"
    ))
    if not result.scalar():
        op.create_table(
            'customers',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('first_name', sa.String(100)),
            sa.Column('last_name', sa.String(100)),
            sa.Column('email', sa.String(255), index=True),
            sa.Column('phone', sa.String(20)),
            sa.Column('mobile_phone', sa.String(20)),
            sa.Column('company_name', sa.String(255)),
            sa.Column('address_line1', sa.String(255)),
            sa.Column('address_line2', sa.String(255)),
            sa.Column('city', sa.String(100)),
            sa.Column('state', sa.String(50)),
            sa.Column('postal_code', sa.String(20)),
            sa.Column('latitude', sa.Float()),
            sa.Column('longitude', sa.Float()),
            sa.Column('customer_type', sa.String(50)),
            sa.Column('lead_source', sa.String(100)),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('notes', sa.Text()),
            # Septic system info
            sa.Column('tank_size_gallons', sa.Integer()),
            sa.Column('number_of_tanks', sa.Integer(), default=1),
            sa.Column('system_type', sa.String(100)),
            sa.Column('last_service_date', sa.Date()),
            sa.Column('next_service_date', sa.Date()),
            sa.Column('service_interval_months', sa.Integer()),
            sa.Column('subdivision', sa.String(255)),
            # Timestamps
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )

    # Create enums using DO block with exception handling (works with async drivers)
    enums = [
        ("work_order_status_enum", ['scheduled', 'in_progress', 'completed', 'cancelled', 'on_hold', 'pending']),
        ("work_order_priority_enum", ['low', 'medium', 'high', 'urgent']),
        ("work_order_job_type_enum", ['pumping', 'repair', 'inspection', 'installation', 'maintenance', 'emergency', 'other']),
    ]

    for enum_name, values in enums:
        values_str = ", ".join([f"'{v}'" for v in values])
        # Use DO block with exception handling - this is idempotent
        conn.execute(text(f"""
            DO $$
            BEGIN
                CREATE TYPE {enum_name} AS ENUM ({values_str});
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
        """))

    # Create technicians table first (work_orders references it)
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'technicians')"
    ))
    if not result.scalar():
        op.create_table(
            'technicians',
            sa.Column('id', sa.String(36), primary_key=True, index=True),
            sa.Column('first_name', sa.String(100), nullable=False),
            sa.Column('last_name', sa.String(100), nullable=False),
            sa.Column('email', sa.String(255), index=True),
            sa.Column('phone', sa.String(20)),
            sa.Column('employee_id', sa.String(50), unique=True, index=True),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('home_region', sa.String(100)),
            sa.Column('home_address', sa.String(255)),
            sa.Column('home_city', sa.String(100)),
            sa.Column('home_state', sa.String(50)),
            sa.Column('home_postal_code', sa.String(20)),
            sa.Column('home_latitude', sa.Float()),
            sa.Column('home_longitude', sa.Float()),
            sa.Column('skills', sa.ARRAY(sa.String())),
            sa.Column('assigned_vehicle', sa.String(100)),
            sa.Column('vehicle_capacity_gallons', sa.Integer()),
            sa.Column('license_number', sa.String(100)),
            sa.Column('license_expiry', sa.Date()),
            sa.Column('hourly_rate', sa.Float()),
            sa.Column('overtime_rate', sa.Numeric()),
            sa.Column('double_time_rate', sa.Numeric()),
            sa.Column('travel_rate', sa.Numeric()),
            sa.Column('pay_type', sa.String(50)),
            sa.Column('salary_amount', sa.Numeric()),
            sa.Column('default_hours_per_week', sa.Numeric()),
            sa.Column('overtime_threshold', sa.Numeric()),
            sa.Column('pto_balance_hours', sa.Numeric()),
            sa.Column('pto_accrual_rate', sa.Numeric()),
            sa.Column('hire_date', sa.Date()),
            sa.Column('hired_date', sa.Date()),
            sa.Column('department', sa.String(100)),
            sa.Column('external_payroll_id', sa.String(100)),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )

    # Create work_orders table
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'work_orders')"
    ))
    if not result.scalar():
        op.create_table(
            'work_orders',
            sa.Column('id', sa.String(36), primary_key=True, index=True),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False, index=True),
            sa.Column('technician_id', sa.String(36), sa.ForeignKey('technicians.id'), nullable=True, index=True),
            sa.Column('job_type', sa.Enum('pumping', 'repair', 'inspection', 'installation', 'maintenance', 'emergency', 'other', name='work_order_job_type_enum', create_type=False), nullable=False),
            sa.Column('priority', sa.Enum('low', 'medium', 'high', 'urgent', name='work_order_priority_enum', create_type=False)),
            sa.Column('status', sa.Enum('scheduled', 'in_progress', 'completed', 'cancelled', 'on_hold', 'pending', name='work_order_status_enum', create_type=False)),
            sa.Column('scheduled_date', sa.Date()),
            sa.Column('time_window_start', sa.Time()),
            sa.Column('time_window_end', sa.Time()),
            sa.Column('estimated_duration_hours', sa.Float()),
            sa.Column('service_address_line1', sa.String(255)),
            sa.Column('service_address_line2', sa.String(255)),
            sa.Column('service_city', sa.String(100)),
            sa.Column('service_state', sa.String(50)),
            sa.Column('service_postal_code', sa.String(20)),
            sa.Column('service_latitude', sa.Float()),
            sa.Column('service_longitude', sa.Float()),
            sa.Column('estimated_gallons', sa.Integer()),
            sa.Column('notes', sa.Text()),
            sa.Column('internal_notes', sa.Text()),
            sa.Column('is_recurring', sa.Boolean(), default=False),
            sa.Column('recurrence_frequency', sa.String(50)),
            sa.Column('next_recurrence_date', sa.Date()),
            sa.Column('checklist', sa.JSON()),
            sa.Column('assigned_vehicle', sa.String(100)),
            sa.Column('assigned_technician', sa.String(100)),
            sa.Column('total_amount', sa.Numeric()),
            sa.Column('actual_start_time', sa.DateTime(timezone=True)),
            sa.Column('actual_end_time', sa.DateTime(timezone=True)),
            sa.Column('travel_start_time', sa.DateTime(timezone=True)),
            sa.Column('travel_end_time', sa.DateTime(timezone=True)),
            sa.Column('break_minutes', sa.Integer()),
            sa.Column('total_labor_minutes', sa.Integer()),
            sa.Column('total_travel_minutes', sa.Integer()),
            sa.Column('is_clocked_in', sa.Boolean(), default=False),
            sa.Column('clock_in_gps_lat', sa.Numeric()),
            sa.Column('clock_in_gps_lon', sa.Numeric()),
            sa.Column('clock_out_gps_lat', sa.Numeric()),
            sa.Column('clock_out_gps_lon', sa.Numeric()),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )

    # Create messages table
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'messages')"
    ))
    if not result.scalar():
        op.create_table(
            'messages',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), index=True),
            sa.Column('work_order_id', sa.String(36), sa.ForeignKey('work_orders.id'), index=True),
            sa.Column('message_type', sa.String(20), nullable=False),
            sa.Column('direction', sa.String(20), nullable=False),
            sa.Column('status', sa.String(20), default='pending'),
            sa.Column('from_number', sa.String(20)),
            sa.Column('to_number', sa.String(20)),
            sa.Column('from_email', sa.String(255)),
            sa.Column('to_email', sa.String(255)),
            sa.Column('subject', sa.String(500)),
            sa.Column('content', sa.Text()),
            sa.Column('template_id', sa.String(100)),
            sa.Column('external_id', sa.String(100)),
            sa.Column('error_message', sa.Text()),
            sa.Column('sent_at', sa.DateTime(timezone=True)),
            sa.Column('delivered_at', sa.DateTime(timezone=True)),
            sa.Column('read_at', sa.DateTime(timezone=True)),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True)),
        )

    # Create activities table
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'activities')"
    ))
    if not result.scalar():
        op.create_table(
            'activities',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), index=True),
            sa.Column('work_order_id', sa.String(36), sa.ForeignKey('work_orders.id'), index=True),
            sa.Column('activity_type', sa.String(50), nullable=False),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('description', sa.Text()),
            sa.Column('user_id', sa.Integer()),
            sa.Column('metadata', sa.JSON()),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade():
    """Drop base tables."""
    conn = op.get_bind()
    tables = ['activities', 'messages', 'work_orders', 'technicians', 'customers']
    for table in tables:
        result = conn.execute(text(
            f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}')"
        ))
        if result.scalar():
            op.drop_table(table)
