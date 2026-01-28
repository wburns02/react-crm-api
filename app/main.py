"""
React CRM API - Main Application

SECURITY FEATURES:
- Conditional API docs (disabled in production by default)
- Structured logging without sensitive data
- Production-hardened configuration
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import traceback

from app.api.v2.router import api_router
from app.api.public.router import public_router
from app.webhooks.twilio import twilio_router
from app.config import settings
from app.database import init_db
from app.api.v2.ringcentral import start_auto_sync, stop_auto_sync
# Import all models to register them with SQLAlchemy metadata before init_db()
from app.models import (
    # Core models
    Customer, WorkOrder, Message, User, Technician,
    Invoice, Payment, Quote, SMSConsent, SMSConsentAudit, Activity,
    Ticket, Equipment, InventoryItem,
    # Phase 1: AI
    AIEmbedding, AIConversation, AIMessage,
    # Phase 2: RingCentral
    CallLog, CallDisposition,
    # Phase 3: E-Signatures
    SignatureRequest, Signature, SignedDocument,
    # Phase 4: Pricing
    ServiceCatalog, PricingZone, PricingRule, CustomerPricingTier,
    # Phase 5: AI Agents
    AIAgent, AgentConversation, AgentMessage, AgentTask,
    # Phase 6: Predictions
    LeadScore, ChurnPrediction, RevenueForecast, DealHealth, PredictionModel,
    # Phase 7: Marketing
    MarketingCampaign, MarketingWorkflow, WorkflowEnrollment, EmailTemplate, SMSTemplate,
    # Phase 10: Payroll
    PayrollPeriod, TimeEntry, Commission, TechnicianPayRate,
    # Phase 11: Compliance
    License, Certification, Inspection,
    # Phase 12: Contracts
    Contract, ContractTemplate,
    # Phase 13: Job Costing
    JobCost,
    # Enterprise Customer Success Platform
    HealthScore, HealthScoreEvent,
    Segment, CustomerSegment,
    Journey, JourneyStep, JourneyEnrollment, JourneyStepExecution,
    Playbook, PlaybookStep, PlaybookExecution,
    CSTask, Touchpoint,
    # Demo Mode Role Switching
    RoleView, UserRoleSession,
    # Work Order Photos
    WorkOrderPhoto,
    # National Septic OCR Permit System
    State, County, SepticSystemType, SourcePortal,
    SepticPermit, PermitVersion, PermitDuplicate, PermitImportBatch,
)
# OAuth models for public API
from app.models.oauth import APIClient, APIToken

# Configure secure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to trust X-Forwarded-* headers from reverse proxies like Railway.

    This fixes the issue where FastAPI's trailing slash redirect (307) generates
    HTTP URLs instead of HTTPS when behind a reverse proxy.
    """

    async def dispatch(self, request: Request, call_next):
        # Trust X-Forwarded-Proto header from Railway's edge proxy
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto:
            # Update the scope to reflect the actual client protocol
            request.scope["scheme"] = forwarded_proto
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting React CRM API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    # SECURITY: Don't log full database URL, just prefix
    if settings.DATABASE_URL:
        logger.info(f"Database URL prefix: {settings.DATABASE_URL[:30]}...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        # SECURITY: Don't log full exception details which may contain credentials
        logger.error(f"Database initialization failed: {type(e).__name__}")
        logger.warning("App starting without database - some features may not work")

    # Start RingCentral auto-sync background task
    try:
        start_auto_sync()
        logger.info("RingCentral auto-sync started")
    except Exception as e:
        logger.warning(f"Failed to start RingCentral auto-sync: {e}")

    yield

    # Shutdown
    logger.info("Shutting down React CRM API...")
    stop_auto_sync()


# SECURITY: Conditionally enable docs based on settings
docs_url = "/docs" if settings.DOCS_ENABLED else None
redoc_url = "/redoc" if settings.DOCS_ENABLED else None

app = FastAPI(
    title="React CRM API",
    description="API for React CRM - Nationwide Septic Service Management. Includes Public API with OAuth2 authentication.",
    version="2.4.0",  # Added demo mode role switching
    docs_url=docs_url,
    redoc_url=redoc_url,
    lifespan=lifespan,
)

# Proxy headers middleware (must be added before CORS)
# This ensures redirects use HTTPS when behind Railway's edge proxy
app.add_middleware(ProxyHeadersMiddleware)

# CORS middleware
# SECURITY: Restrict origins to known frontend URLs
allowed_origins = [
    settings.FRONTEND_URL,
    "https://react.ecbtx.com",  # Production ReactCRM frontend
]

# Allow localhost origins for development/testing
# These are safe to include since they can only be accessed locally
allowed_origins.extend([
    "http://localhost:5173",  # Vite dev server
    "http://localhost:5174",  # Vite dev server (alternate port)
    "http://localhost:5175",  # Vite dev server (alternate port)
    "http://localhost:3000",  # Alternative dev port
])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router, prefix="/api/v2")
app.include_router(public_router, prefix="/api/public/v1", tags=["Public API"])
app.include_router(twilio_router, prefix="/webhooks/twilio", tags=["webhooks"])


@app.get("/")
async def root():
    """Root endpoint - API info."""
    response = {
        "name": "React CRM API",
        "version": "2.1.0",
        "health": "/health",
        "api_v2": "/api/v2",
        "public_api": "/api/public/v1",
    }
    # Only include docs link if enabled
    if settings.DOCS_ENABLED:
        response["docs"] = "/docs"
    return response


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "2.6.6",  # Fixed invoice creation ENUM case mismatch
        "environment": settings.ENVIRONMENT,
        "features": ["public_api", "oauth2", "demo_roles", "cs_platform", "journey_status", "technician_performance", "call_intelligence"],
    }


@app.get("/health/db")
async def database_health_check():
    """Database connectivity and schema check endpoint."""
    from sqlalchemy import text
    from app.database import async_session_maker

    checks = {
        "database_connected": False,
        "api_users_table_exists": False,
        "api_users_columns": [],
        "all_tables": [],
        "core_tables_missing": [],
        "errors": []
    }

    # Core tables that should exist
    core_tables = [
        "api_users", "customers", "work_orders", "invoices", "technicians",
        "payments", "quotes", "messages", "activities"
    ]

    try:
        async with async_session_maker() as session:
            # Test connection
            result = await session.execute(text("SELECT 1"))
            checks["database_connected"] = True

            # Get all tables
            result = await session.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            checks["all_tables"] = [row[0] for row in result.fetchall()]

            # Check core tables
            for table in core_tables:
                if table not in checks["all_tables"]:
                    checks["core_tables_missing"].append(table)

            # Check if api_users table exists
            if "api_users" in checks["all_tables"]:
                checks["api_users_table_exists"] = True

                # Get columns
                result = await session.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'api_users'
                    ORDER BY ordinal_position
                """))
                checks["api_users_columns"] = [row[0] for row in result.fetchall()]
            else:
                checks["errors"].append("api_users table does not exist")

    except Exception as e:
        checks["errors"].append(f"{type(e).__name__}: {str(e)}")

    return checks


@app.post("/health/db/migrate")
async def run_database_migrations():
    """Reset alembic and run migrations from scratch."""
    from sqlalchemy import text
    from app.database import async_session_maker
    import subprocess
    import os

    results = {
        "alembic_reset": False,
        "alembic_run": False,
        "tables_before": [],
        "tables_after": [],
        "errors": []
    }

    try:
        # Get tables before
        async with async_session_maker() as session:
            result = await session.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """))
            results["tables_before"] = [row[0] for row in result.fetchall()]

            # Get current alembic version
            try:
                result = await session.execute(text("SELECT version_num FROM alembic_version"))
                results["current_version"] = result.scalar_one_or_none()
            except:
                results["current_version"] = None

            # Delete alembic_version to reset state
            await session.execute(text("DELETE FROM alembic_version"))
            await session.commit()
            results["alembic_reset"] = True

        # Run alembic upgrade head
        os.chdir("/app")
        proc = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            timeout=300
        )
        results["alembic_run"] = proc.returncode == 0
        if proc.stdout:
            results["alembic_stdout"] = proc.stdout[-2000:]  # Last 2000 chars
        if proc.stderr:
            results["alembic_stderr"] = proc.stderr[-2000:]

        # Get tables after
        async with async_session_maker() as session:
            result = await session.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """))
            results["tables_after"] = [row[0] for row in result.fetchall()]

        results["new_tables"] = [t for t in results["tables_after"] if t not in results["tables_before"]]

    except Exception as e:
        results["errors"].append(f"{type(e).__name__}: {str(e)}")

    return results


@app.post("/health/db/create-admin")
async def create_admin_user():
    """Create or reset admin user for testing."""
    from sqlalchemy import text
    from app.database import async_session_maker
    import bcrypt

    password = "admin123"  # Simple password without special chars
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        async with async_session_maker() as session:
            # Check if user exists
            result = await session.execute(text(
                "SELECT id FROM api_users WHERE email = 'admin@macseptic.com'"
            ))
            user_id = result.scalar()

            if user_id:
                # Update existing user's password
                await session.execute(text("""
                    UPDATE api_users SET hashed_password = :hashed WHERE email = 'admin@macseptic.com'
                """), {"hashed": hashed})
                await session.commit()
                return {"status": "password_reset", "email": "admin@macseptic.com", "password": password}

            # Create user
            await session.execute(text("""
                INSERT INTO api_users (email, hashed_password, first_name, last_name, is_active, is_superuser, created_at)
                VALUES ('admin@macseptic.com', :hashed, 'Admin', 'User', TRUE, TRUE, NOW())
            """), {"hashed": hashed})
            await session.commit()

            return {"status": "created", "email": "admin@macseptic.com", "password": password}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/health/db/fix-invoices")
async def fix_invoices_table():
    """Recreate invoices table with correct UUID types and create job_costs table."""
    from sqlalchemy import text
    from app.database import async_session_maker

    results = {"actions": [], "errors": []}

    try:
        async with async_session_maker() as session:
            # Create invoice_status_enum if not exists
            try:
                await session.execute(text("""
                    DO $$
                    BEGIN
                        CREATE TYPE invoice_status_enum AS ENUM ('draft', 'sent', 'paid', 'overdue', 'void', 'partial');
                    EXCEPTION
                        WHEN duplicate_object THEN NULL;
                    END $$;
                """))
                results["actions"].append("invoice_status_enum: created or already exists")
            except Exception as e:
                results["errors"].append(f"invoice_status_enum: {str(e)}")

            # Drop old invoices table and recreate with UUID types
            try:
                await session.execute(text("DROP TABLE IF EXISTS invoices CASCADE"))
                await session.execute(text("""
                    CREATE TABLE invoices (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        customer_id UUID NOT NULL,
                        work_order_id UUID,
                        invoice_number VARCHAR(50) UNIQUE,
                        issue_date DATE,
                        due_date DATE,
                        paid_date DATE,
                        amount NUMERIC(10,2),
                        paid_amount NUMERIC(10,2),
                        currency VARCHAR(3) DEFAULT 'USD',
                        status invoice_status_enum DEFAULT 'draft',
                        line_items JSONB DEFAULT '[]',
                        notes TEXT,
                        external_payment_link VARCHAR(255),
                        quickbooks_invoice_id VARCHAR(100),
                        pdf_url VARCHAR(255),
                        pdf_generated_at TIMESTAMP,
                        last_sent_at TIMESTAMP,
                        sent_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE
                    )
                """))
                await session.execute(text("CREATE INDEX IF NOT EXISTS idx_invoices_customer_id ON invoices(customer_id)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number ON invoices(invoice_number)"))
                results["actions"].append("invoices table: recreated with UUID types")
            except Exception as e:
                results["errors"].append(f"invoices table: {str(e)}")

            # Create job_costs table
            try:
                result = await session.execute(text(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'job_costs')"
                ))
                if not result.scalar():
                    await session.execute(text("""
                        CREATE TABLE job_costs (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            work_order_id VARCHAR(36) NOT NULL,
                            cost_type VARCHAR(50) NOT NULL,
                            category VARCHAR(100),
                            description VARCHAR(500) NOT NULL,
                            notes TEXT,
                            quantity FLOAT DEFAULT 1.0,
                            unit VARCHAR(20) DEFAULT 'each',
                            unit_cost FLOAT NOT NULL,
                            total_cost FLOAT NOT NULL,
                            markup_percent FLOAT DEFAULT 0.0,
                            billable_amount FLOAT,
                            technician_id VARCHAR(36),
                            technician_name VARCHAR(255),
                            cost_date DATE NOT NULL,
                            is_billable BOOLEAN DEFAULT TRUE,
                            is_billed BOOLEAN DEFAULT FALSE,
                            invoice_id VARCHAR(36),
                            vendor_name VARCHAR(255),
                            vendor_invoice VARCHAR(100),
                            receipt_url VARCHAR(500),
                            created_by VARCHAR(100),
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            updated_at TIMESTAMP WITH TIME ZONE
                        )
                    """))
                    await session.execute(text("CREATE INDEX IF NOT EXISTS idx_job_costs_work_order_id ON job_costs(work_order_id)"))
                    await session.execute(text("CREATE INDEX IF NOT EXISTS idx_job_costs_cost_date ON job_costs(cost_date)"))
                    results["actions"].append("job_costs table: created")
                else:
                    results["actions"].append("job_costs table: already exists")
            except Exception as e:
                results["errors"].append(f"job_costs table: {str(e)}")

            await session.commit()

    except Exception as e:
        results["errors"].append(f"General error: {str(e)}")

    return results


@app.post("/health/db/fix-activities")
async def fix_activities_table():
    """Recreate activities table with correct UUID type and schema."""
    from sqlalchemy import text
    from app.database import async_session_maker

    results = {"actions": [], "errors": []}

    try:
        async with async_session_maker() as session:
            # Drop old activities table and recreate with UUID id
            try:
                await session.execute(text("DROP TABLE IF EXISTS activities CASCADE"))
                await session.execute(text("""
                    CREATE TABLE activities (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        customer_id INTEGER NOT NULL,
                        activity_type VARCHAR(20) NOT NULL,
                        description TEXT NOT NULL,
                        activity_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        created_by VARCHAR(100),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE
                    )
                """))
                await session.execute(text("CREATE INDEX IF NOT EXISTS idx_activities_customer_id ON activities(customer_id)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS idx_activities_activity_type ON activities(activity_type)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS idx_activities_activity_date ON activities(activity_date DESC)"))
                results["actions"].append("activities table: recreated with UUID id")
            except Exception as e:
                results["errors"].append(f"activities table: {str(e)}")

            await session.commit()

    except Exception as e:
        results["errors"].append(f"General error: {str(e)}")

    return results


@app.post("/health/db/fix-schema")
async def fix_table_schema():
    """Add missing columns to existing tables."""
    from sqlalchemy import text
    from app.database import async_session_maker

    results = {"columns_added": [], "errors": []}

    # Columns to add to each table (column_name, type)
    missing_columns = {
        "activities": [
            ("created_by", "VARCHAR(100)"),
            ("activity_date", "TIMESTAMP WITH TIME ZONE"),
            ("updated_at", "TIMESTAMP WITH TIME ZONE"),
        ],
        "customers": [
            ("lead_notes", "TEXT"),
            ("prospect_stage", "VARCHAR(50)"),
            ("assigned_sales_rep", "VARCHAR(100)"),
            ("estimated_value", "FLOAT"),
            ("manufacturer", "VARCHAR(100)"),
            ("installer_name", "VARCHAR(100)"),
            ("system_issued_date", "DATE"),
            ("tags", "VARCHAR(500)"),
            ("utm_source", "VARCHAR(255)"),
            ("utm_medium", "VARCHAR(255)"),
            ("utm_campaign", "VARCHAR(255)"),
            ("utm_term", "VARCHAR(255)"),
            ("utm_content", "VARCHAR(255)"),
            ("gclid", "VARCHAR(255)"),
            ("landing_page", "VARCHAR(500)"),
            ("first_touch_ts", "TIMESTAMP"),
            ("last_touch_ts", "TIMESTAMP"),
            ("default_payment_terms", "VARCHAR(50)"),
            ("quickbooks_customer_id", "VARCHAR(100)"),
            ("hubspot_contact_id", "VARCHAR(100)"),
            ("servicenow_ticket_ref", "VARCHAR(100)"),
            ("next_follow_up_date", "DATE"),
        ],
        "payments": [
            ("work_order_id", "VARCHAR(36) REFERENCES work_orders(id)"),
            ("currency", "VARCHAR(3) DEFAULT 'USD'"),
            ("status", "VARCHAR(30) DEFAULT 'pending'"),
            ("stripe_payment_intent_id", "VARCHAR(255)"),
            ("stripe_charge_id", "VARCHAR(255)"),
            ("stripe_customer_id", "VARCHAR(255)"),
            ("description", "TEXT"),
            ("receipt_url", "VARCHAR(500)"),
            ("failure_reason", "TEXT"),
            ("refund_amount", "NUMERIC(10,2)"),
            ("refund_reason", "TEXT"),
            ("refunded", "BOOLEAN DEFAULT FALSE"),
            ("refund_id", "VARCHAR(255)"),
            ("refunded_at", "TIMESTAMP"),
            ("processed_at", "TIMESTAMP"),
        ],
        "quotes": [
            ("title", "VARCHAR(255)"),
            ("description", "TEXT"),
            ("discount", "NUMERIC(10,2) DEFAULT 0"),
            ("signature_data", "TEXT"),
            ("signed_at", "TIMESTAMP WITH TIME ZONE"),
            ("signed_by", "VARCHAR(150)"),
            ("approval_status", "VARCHAR(30)"),
            ("approved_by", "VARCHAR(100)"),
            ("approved_at", "TIMESTAMP WITH TIME ZONE"),
            ("converted_to_work_order_id", "VARCHAR(36) REFERENCES work_orders(id)"),
            ("converted_at", "TIMESTAMP WITH TIME ZONE"),
            ("sent_at", "TIMESTAMP WITH TIME ZONE"),
        ],
    }

    try:
        async with async_session_maker() as session:
            for table_name, columns in missing_columns.items():
                for col_name, col_type in columns:
                    try:
                        # Check if column exists
                        result = await session.execute(text(f"""
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = '{table_name}' AND column_name = '{col_name}'
                        """))
                        if not result.scalar():
                            await session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
                            results["columns_added"].append(f"{table_name}.{col_name}")
                    except Exception as e:
                        results["errors"].append(f"{table_name}.{col_name}: {str(e)}")

            await session.commit()

    except Exception as e:
        results["errors"].append(str(e))

    return results


@app.post("/health/db/create-tables")
async def create_core_tables():
    """Create core CRM tables directly using raw SQL (bypasses alembic async issues)."""
    from sqlalchemy import text
    from app.database import async_session_maker

    results = {
        "tables_created": [],
        "tables_skipped": [],
        "errors": []
    }

    # SQL to create all core tables
    table_definitions = {
        "customers": """
            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                email VARCHAR(255),
                phone VARCHAR(20),
                mobile_phone VARCHAR(20),
                company_name VARCHAR(255),
                address_line1 VARCHAR(255),
                address_line2 VARCHAR(255),
                city VARCHAR(100),
                state VARCHAR(50),
                postal_code VARCHAR(20),
                latitude FLOAT,
                longitude FLOAT,
                customer_type VARCHAR(50),
                lead_source VARCHAR(100),
                is_active BOOLEAN DEFAULT TRUE,
                notes TEXT,
                tank_size_gallons INTEGER,
                number_of_tanks INTEGER DEFAULT 1,
                system_type VARCHAR(100),
                last_service_date DATE,
                next_service_date DATE,
                service_interval_months INTEGER,
                subdivision VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """,
        "technicians": """
            CREATE TABLE IF NOT EXISTS technicians (
                id VARCHAR(36) PRIMARY KEY,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                email VARCHAR(255),
                phone VARCHAR(20),
                employee_id VARCHAR(50) UNIQUE,
                is_active BOOLEAN DEFAULT TRUE,
                home_region VARCHAR(100),
                home_address VARCHAR(255),
                home_city VARCHAR(100),
                home_state VARCHAR(50),
                home_postal_code VARCHAR(20),
                home_latitude FLOAT,
                home_longitude FLOAT,
                skills TEXT[],
                assigned_vehicle VARCHAR(100),
                vehicle_capacity_gallons INTEGER,
                license_number VARCHAR(100),
                license_expiry DATE,
                hourly_rate FLOAT,
                overtime_rate NUMERIC,
                double_time_rate NUMERIC,
                travel_rate NUMERIC,
                pay_type VARCHAR(50),
                salary_amount NUMERIC,
                default_hours_per_week NUMERIC,
                overtime_threshold NUMERIC,
                pto_balance_hours NUMERIC,
                pto_accrual_rate NUMERIC,
                hire_date DATE,
                hired_date DATE,
                department VARCHAR(100),
                external_payroll_id VARCHAR(100),
                notes TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """,
        "work_orders": """
            CREATE TABLE IF NOT EXISTS work_orders (
                id VARCHAR(36) PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                technician_id VARCHAR(36) REFERENCES technicians(id),
                job_type VARCHAR(50) NOT NULL,
                priority VARCHAR(20),
                status VARCHAR(20),
                scheduled_date DATE,
                time_window_start TIME,
                time_window_end TIME,
                estimated_duration_hours FLOAT,
                service_address_line1 VARCHAR(255),
                service_address_line2 VARCHAR(255),
                service_city VARCHAR(100),
                service_state VARCHAR(50),
                service_postal_code VARCHAR(20),
                service_latitude FLOAT,
                service_longitude FLOAT,
                estimated_gallons INTEGER,
                notes TEXT,
                internal_notes TEXT,
                is_recurring BOOLEAN DEFAULT FALSE,
                recurrence_frequency VARCHAR(50),
                next_recurrence_date DATE,
                checklist JSONB,
                assigned_vehicle VARCHAR(100),
                assigned_technician VARCHAR(100),
                total_amount NUMERIC,
                actual_start_time TIMESTAMP WITH TIME ZONE,
                actual_end_time TIMESTAMP WITH TIME ZONE,
                travel_start_time TIMESTAMP WITH TIME ZONE,
                travel_end_time TIMESTAMP WITH TIME ZONE,
                break_minutes INTEGER,
                total_labor_minutes INTEGER,
                total_travel_minutes INTEGER,
                is_clocked_in BOOLEAN DEFAULT FALSE,
                clock_in_gps_lat NUMERIC,
                clock_in_gps_lon NUMERIC,
                clock_out_gps_lat NUMERIC,
                clock_out_gps_lon NUMERIC,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """,
        "invoices": """
            CREATE TABLE IF NOT EXISTS invoices (
                id SERIAL PRIMARY KEY,
                invoice_number VARCHAR(50) UNIQUE NOT NULL,
                customer_id INTEGER REFERENCES customers(id) NOT NULL,
                work_order_id VARCHAR(36) REFERENCES work_orders(id),
                status VARCHAR(20) DEFAULT 'draft' NOT NULL,
                line_items JSONB DEFAULT '[]',
                subtotal FLOAT DEFAULT 0,
                tax_rate FLOAT DEFAULT 0,
                tax FLOAT DEFAULT 0,
                total FLOAT DEFAULT 0,
                due_date VARCHAR(20),
                paid_date VARCHAR(20),
                notes TEXT,
                terms TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """,
        "payments": """
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                invoice_id INTEGER REFERENCES invoices(id),
                customer_id INTEGER REFERENCES customers(id),
                amount FLOAT NOT NULL,
                payment_method VARCHAR(50),
                payment_date DATE,
                reference_number VARCHAR(100),
                notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """,
        "quotes": """
            CREATE TABLE IF NOT EXISTS quotes (
                id SERIAL PRIMARY KEY,
                quote_number VARCHAR(50) UNIQUE,
                customer_id INTEGER REFERENCES customers(id),
                work_order_id VARCHAR(36) REFERENCES work_orders(id),
                status VARCHAR(20) DEFAULT 'draft',
                line_items JSONB DEFAULT '[]',
                subtotal FLOAT DEFAULT 0,
                tax_rate FLOAT DEFAULT 0,
                tax FLOAT DEFAULT 0,
                total FLOAT DEFAULT 0,
                valid_until DATE,
                notes TEXT,
                terms TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """,
        "messages": """
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                work_order_id VARCHAR(36) REFERENCES work_orders(id),
                message_type VARCHAR(20) NOT NULL,
                direction VARCHAR(20) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                from_number VARCHAR(20),
                to_number VARCHAR(20),
                from_email VARCHAR(255),
                to_email VARCHAR(255),
                subject VARCHAR(500),
                content TEXT,
                template_id VARCHAR(100),
                external_id VARCHAR(100),
                error_message TEXT,
                sent_at TIMESTAMP WITH TIME ZONE,
                delivered_at TIMESTAMP WITH TIME ZONE,
                read_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """,
        "activities": """
            CREATE TABLE IF NOT EXISTS activities (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                work_order_id VARCHAR(36) REFERENCES work_orders(id),
                activity_type VARCHAR(50) NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                user_id INTEGER,
                metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """,
        "payroll_periods": """
            CREATE TABLE IF NOT EXISTS payroll_periods (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                period_type VARCHAR(20) DEFAULT 'biweekly',
                status VARCHAR(20) DEFAULT 'open',
                total_regular_hours FLOAT DEFAULT 0.0,
                total_overtime_hours FLOAT DEFAULT 0.0,
                total_gross_pay FLOAT DEFAULT 0.0,
                total_commissions FLOAT DEFAULT 0.0,
                technician_count INTEGER DEFAULT 0,
                approved_by VARCHAR(100),
                approved_at TIMESTAMP WITH TIME ZONE,
                processed_at TIMESTAMP WITH TIME ZONE,
                export_file_url VARCHAR(500),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """,
        "time_entries": """
            CREATE TABLE IF NOT EXISTS time_entries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                technician_id VARCHAR(36) NOT NULL,
                work_order_id VARCHAR(36),
                payroll_period_id UUID,
                entry_date DATE NOT NULL,
                clock_in TIMESTAMP WITH TIME ZONE NOT NULL,
                clock_out TIMESTAMP WITH TIME ZONE,
                regular_hours FLOAT DEFAULT 0.0,
                overtime_hours FLOAT DEFAULT 0.0,
                break_minutes INTEGER DEFAULT 0,
                clock_in_lat FLOAT,
                clock_in_lon FLOAT,
                clock_out_lat FLOAT,
                clock_out_lon FLOAT,
                entry_type VARCHAR(20) DEFAULT 'work',
                status VARCHAR(20) DEFAULT 'pending',
                approved_by VARCHAR(100),
                approved_at TIMESTAMP WITH TIME ZONE,
                notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """,
        "commissions": """
            CREATE TABLE IF NOT EXISTS commissions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                technician_id VARCHAR(36) NOT NULL,
                work_order_id VARCHAR(36),
                invoice_id VARCHAR(36),
                payroll_period_id UUID,
                commission_type VARCHAR(50) NOT NULL,
                base_amount FLOAT NOT NULL,
                rate FLOAT NOT NULL,
                rate_type VARCHAR(20) DEFAULT 'percent',
                commission_amount FLOAT NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                description TEXT,
                earned_date DATE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """,
        "technician_pay_rates": """
            CREATE TABLE IF NOT EXISTS technician_pay_rates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                technician_id VARCHAR(36) NOT NULL,
                hourly_rate FLOAT NOT NULL,
                overtime_multiplier FLOAT DEFAULT 1.5,
                job_commission_rate FLOAT DEFAULT 0.0,
                upsell_commission_rate FLOAT DEFAULT 0.0,
                weekly_overtime_threshold FLOAT DEFAULT 40.0,
                effective_date DATE NOT NULL,
                end_date DATE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """
    }

    try:
        async with async_session_maker() as session:
            # Get existing tables
            result = await session.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
            """))
            existing_tables = {row[0] for row in result.fetchall()}

            # Create tables in order (respecting foreign key dependencies)
            table_order = ["customers", "technicians", "work_orders", "invoices", "payments", "quotes", "messages", "activities", "payroll_periods", "time_entries", "commissions", "technician_pay_rates"]

            for table_name in table_order:
                if table_name in existing_tables:
                    results["tables_skipped"].append(table_name)
                else:
                    try:
                        await session.execute(text(table_definitions[table_name]))
                        results["tables_created"].append(table_name)
                    except Exception as e:
                        results["errors"].append(f"{table_name}: {type(e).__name__}: {str(e)}")

            await session.commit()

            # Get final table list
            result = await session.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """))
            results["all_tables"] = [row[0] for row in result.fetchall()]

    except Exception as e:
        results["errors"].append(f"{type(e).__name__}: {str(e)}")

    return results


# For running with uvicorn directly (development only)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=5001,
        reload=settings.DEBUG,
    )


# Global exception handler to ensure CORS headers on 500 errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with proper CORS headers."""
    logger.error(f"Unhandled exception: {type(exc).__name__}: {str(exc)}")
    # Always log traceback for debugging production issues
    logger.error(traceback.format_exc())

    origin = request.headers.get("origin", "")

    # Preserve HTTPException details instead of masking them
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        detail = exc.detail
    else:
        status_code = 500
        detail = "Internal server error"

    response = JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )

    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"

    return response
