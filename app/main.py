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
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import traceback

from starlette.middleware.gzip import GZipMiddleware

from app.api.v2.router import api_router
from app.exceptions import CRMException, create_exception_handlers
from app.core.sentry import init_sentry
from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.metrics import MetricsMiddleware
from app.middleware.cache_headers import CacheHeadersMiddleware
from app.middleware.timing import ServerTimingMiddleware
from app.api.public.router import public_router
from app.webhooks.twilio import twilio_router
from app.config import settings
from app.database import init_db
from app.api.v2.ringcentral import start_auto_sync, stop_auto_sync
from app.tasks.reminder_scheduler import start_reminder_scheduler, stop_reminder_scheduler
from app.tasks.calendar_sync import start_calendar_sync, stop_calendar_sync
from app.tasks.email_poller import start_email_poller, stop_email_poller
from app.tasks.bookings_sync import start_bookings_sync, stop_bookings_sync
# followup_scheduler and auto_dispatch don't have start/stop functions yet
# from app.tasks.followup_scheduler import start_followup_scheduler, stop_followup_scheduler
# from app.tasks.auto_dispatch import start_auto_dispatch, stop_auto_dispatch
from app.tasks.marketing_report import start_marketing_report_scheduler, stop_marketing_report_scheduler

# Import all models to register them with SQLAlchemy metadata before init_db()
from app.models import (
    # Core models
    Customer,
    WorkOrder,
    Message,
    User,
    Technician,
    Invoice,
    Payment,
    Quote,
    SMSConsent,
    SMSConsentAudit,
    Activity,
    Ticket,
    Equipment,
    InventoryItem,
    # Phase 1: AI
    AIEmbedding,
    AIConversation,
    AIMessage,
    # Phase 2: RingCentral
    CallLog,
    CallDisposition,
    # Phase 3: E-Signatures
    SignatureRequest,
    Signature,
    SignedDocument,
    # Phase 4: Pricing
    ServiceCatalog,
    PricingZone,
    PricingRule,
    CustomerPricingTier,
    # Phase 5: AI Agents
    AIAgent,
    AgentConversation,
    AgentMessage,
    AgentTask,
    # Phase 6: Predictions
    LeadScore,
    ChurnPrediction,
    RevenueForecast,
    DealHealth,
    PredictionModel,
    # Phase 7: Marketing
    MarketingCampaign,
    MarketingWorkflow,
    WorkflowEnrollment,
    EmailTemplate,
    SMSTemplate,
    # Phase 10: Payroll
    PayrollPeriod,
    TimeEntry,
    Commission,
    TechnicianPayRate,
    # Phase 11: Compliance
    License,
    Certification,
    Inspection,
    # Phase 12: Contracts
    Contract,
    ContractTemplate,
    # Phase 13: Job Costing
    JobCost,
    # Enterprise Customer Success Platform
    HealthScore,
    HealthScoreEvent,
    Segment,
    CustomerSegment,
    Journey,
    JourneyStep,
    JourneyEnrollment,
    JourneyStepExecution,
    Playbook,
    PlaybookStep,
    PlaybookExecution,
    CSTask,
    Touchpoint,
    # Demo Mode Role Switching
    RoleView,
    UserRoleSession,
    # Work Order Photos
    WorkOrderPhoto,
    # National Septic OCR Permit System
    State,
    County,
    SepticSystemType,
    SourcePortal,
    SepticPermit,
    PermitVersion,
    PermitDuplicate,
    PermitImportBatch,
)

# OAuth models for public API
from app.models.oauth import APIClient, APIToken

# MFA models for authentication (CRITICAL: must be imported for User.mfa_settings relationship)
from app.models.mfa import UserMFASettings, UserBackupCode, MFASession

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


async def ensure_work_order_photos_table():
    """Ensure work_order_photos table exists.

    Creates the table if it doesn't exist. This is a runtime fix for
    the migration that may have failed silently.

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    async with async_session_maker() as session:
        try:
            # Check if table exists
            result = await session.execute(
                text(
                    """SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'work_order_photos'
                )"""
                )
            )
            table_exists = result.scalar()

            if not table_exists:
                logger.info("Creating missing work_order_photos table...")
                await session.execute(
                    text("""
                    CREATE TABLE work_order_photos (
                        id VARCHAR(36) PRIMARY KEY,
                        work_order_id VARCHAR(36) NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
                        photo_type VARCHAR(50) NOT NULL,
                        data TEXT NOT NULL,
                        thumbnail TEXT,
                        timestamp TIMESTAMPTZ NOT NULL,
                        device_info VARCHAR(255),
                        gps_lat FLOAT,
                        gps_lng FLOAT,
                        gps_accuracy FLOAT,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ
                    )
                """)
                )
                await session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_work_order_photos_work_order_id ON work_order_photos(work_order_id)"
                    )
                )
                await session.commit()
                logger.info("Created work_order_photos table successfully")
            else:
                logger.debug("work_order_photos table already exists")

        except Exception as e:
            logger.warning(f"Could not ensure work_order_photos table: {type(e).__name__}: {e}")


async def ensure_pay_rate_columns():
    """Ensure technician_pay_rates table has required columns.

    This is a runtime fix for missing database columns that should have been
    added by migration 025. Runs on startup to ensure columns exist.

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    async with async_session_maker() as session:
        try:
            # Check if pay_type column exists
            result = await session.execute(
                text(
                    """SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'technician_pay_rates' AND column_name = 'pay_type'
                )"""
                )
            )
            pay_type_exists = result.scalar()

            if not pay_type_exists:
                logger.info("Adding missing pay_type column to technician_pay_rates...")
                await session.execute(
                    text("ALTER TABLE technician_pay_rates ADD COLUMN pay_type VARCHAR(20) DEFAULT 'hourly' NOT NULL")
                )
                await session.commit()
                logger.info("Added pay_type column successfully")

            # Check if salary_amount column exists
            result = await session.execute(
                text(
                    """SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'technician_pay_rates' AND column_name = 'salary_amount'
                )"""
                )
            )
            salary_exists = result.scalar()

            if not salary_exists:
                logger.info("Adding missing salary_amount column to technician_pay_rates...")
                await session.execute(text("ALTER TABLE technician_pay_rates ADD COLUMN salary_amount FLOAT"))
                await session.commit()
                logger.info("Added salary_amount column successfully")

            # Check if hourly_rate needs to be made nullable
            result = await session.execute(
                text(
                    """SELECT is_nullable FROM information_schema.columns
                   WHERE table_name = 'technician_pay_rates' AND column_name = 'hourly_rate'"""
                )
            )
            row = result.fetchone()
            if row and row[0] == "NO":
                logger.info("Making hourly_rate column nullable...")
                await session.execute(text("ALTER TABLE technician_pay_rates ALTER COLUMN hourly_rate DROP NOT NULL"))
                await session.commit()
                logger.info("Made hourly_rate nullable successfully")

        except Exception as e:
            logger.warning(f"Could not ensure pay_rate columns: {type(e).__name__}: {e}")


async def ensure_messages_columns():
    """Ensure messages table has required columns.

    This is a runtime fix for missing database columns that should have been
    added by migration 036. Runs on startup to ensure columns exist.

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    async with async_session_maker() as session:
        try:
            # Check if type column exists
            result = await session.execute(
                text(
                    """SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'messages' AND column_name = 'type'
                )"""
                )
            )
            type_exists = result.scalar()

            if not type_exists:
                logger.info("Adding missing columns to messages table...")

                # Create enum types if they don't exist
                await session.execute(
                    text("""
                        DO $$ BEGIN
                            CREATE TYPE messagetype AS ENUM ('sms', 'email', 'call', 'note');
                        EXCEPTION
                            WHEN duplicate_object THEN null;
                        END $$;
                    """)
                )
                await session.execute(
                    text("""
                        DO $$ BEGIN
                            CREATE TYPE messagedirection AS ENUM ('inbound', 'outbound');
                        EXCEPTION
                            WHEN duplicate_object THEN null;
                        END $$;
                    """)
                )
                await session.execute(
                    text("""
                        DO $$ BEGIN
                            CREATE TYPE messagestatus AS ENUM ('pending', 'queued', 'sent', 'delivered', 'failed', 'received');
                        EXCEPTION
                            WHEN duplicate_object THEN null;
                        END $$;
                    """)
                )

                # Add type column
                await session.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS type messagetype"))
                await session.execute(text("UPDATE messages SET type = 'sms' WHERE type IS NULL"))
                await session.execute(text("ALTER TABLE messages ALTER COLUMN type SET NOT NULL"))

                # Add direction column
                await session.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS direction messagedirection"))
                await session.execute(text("UPDATE messages SET direction = 'outbound' WHERE direction IS NULL"))
                await session.execute(text("ALTER TABLE messages ALTER COLUMN direction SET NOT NULL"))

                # Add status column
                await session.execute(
                    text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS status messagestatus DEFAULT 'sent'")
                )

                # Add other columns
                await session.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS subject VARCHAR(255)"))
                await session.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS from_address VARCHAR(255)"))
                await session.execute(
                    text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'react'")
                )
                await session.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ"))
                await session.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ"))
                await session.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"))

                await session.commit()
                logger.info("Added missing columns to messages table successfully")
            else:
                logger.debug("messages table already has required columns")

        except Exception as e:
            logger.warning(f"Could not ensure messages columns: {type(e).__name__}: {e}")


async def ensure_email_templates_table():
    """
    Ensure email_templates table exists.

    This table was added by migration 037. Runs on startup to ensure table exists.

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    async with async_session_maker() as session:
        try:
            # Check if table exists
            result = await session.execute(
                text(
                    """SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'email_templates'
                )"""
                )
            )
            exists = result.scalar()

            if not exists:
                logger.info("Creating email_templates table...")
                await session.execute(
                    text(
                        """
                    CREATE TABLE IF NOT EXISTS email_templates (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        name VARCHAR(255) NOT NULL,
                        subject VARCHAR(255) NOT NULL,
                        body_html TEXT NOT NULL,
                        body_text TEXT,
                        variables JSONB,
                        category VARCHAR(50),
                        is_active BOOLEAN DEFAULT TRUE,
                        created_by INTEGER,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ
                    )
                """
                    )
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_email_templates_category ON email_templates(category)")
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_email_templates_is_active ON email_templates(is_active)")
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_email_templates_name ON email_templates(name)")
                )
                await session.commit()
                logger.info("email_templates table created successfully")
            else:
                logger.info("email_templates table already exists")

        except Exception as e:
            logger.warning(f"Could not ensure email_templates table: {type(e).__name__}: {e}")


async def ensure_work_order_number_column():
    """
    Ensure work_orders table has work_order_number column and backfill existing rows.

    This column provides human-readable work order numbers in WO-NNNNNN format.

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    async with async_session_maker() as session:
        try:
            # Check if column exists
            result = await session.execute(
                text(
                    """SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'work_orders' AND column_name = 'work_order_number'"""
                )
            )
            exists = result.fetchone()

            if not exists:
                logger.info("Adding work_order_number column to work_orders table...")
                await session.execute(
                    text("ALTER TABLE work_orders ADD COLUMN work_order_number VARCHAR(20)")
                )
                await session.commit()
                logger.info("Added work_orders.work_order_number column")

                # Backfill existing work orders with sequential numbers
                logger.info("Backfilling work order numbers...")
                await session.execute(
                    text("""
                        WITH numbered AS (
                            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at NULLS LAST, id) as rn
                            FROM work_orders
                            WHERE work_order_number IS NULL
                        )
                        UPDATE work_orders wo
                        SET work_order_number = 'WO-' || LPAD(n.rn::text, 6, '0')
                        FROM numbered n
                        WHERE wo.id = n.id
                    """)
                )
                await session.commit()
                logger.info("Backfilled work order numbers")

                # Add unique constraint and index
                try:
                    await session.execute(
                        text("CREATE UNIQUE INDEX IF NOT EXISTS ix_work_orders_number ON work_orders(work_order_number)")
                    )
                    await session.commit()
                except Exception:
                    pass  # Index may conflict, that's okay

            logger.info("Work order number column verified")

        except Exception as e:
            logger.warning(f"Could not ensure work_order_number column: {type(e).__name__}: {e}")


async def ensure_is_admin_column():
    """
    Ensure api_users table has is_admin column.

    This column is needed for RBAC admin role detection.
    Added by migration 043 but may not have run on Railway.

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    async with async_session_maker() as session:
        try:
            # Check if is_admin column exists
            result = await session.execute(
                text(
                    """SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'api_users' AND column_name = 'is_admin'
                )"""
                )
            )
            column_exists = result.scalar()

            if not column_exists:
                logger.info("Adding missing is_admin column to api_users...")
                await session.execute(
                    text("ALTER TABLE api_users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT false")
                )
                # Promote will@macseptic.com to admin
                await session.execute(
                    text("UPDATE api_users SET is_admin = true WHERE email = 'will@macseptic.com'")
                )
                await session.commit()
                logger.info("Added is_admin column and promoted admin user")
            else:
                logger.debug("is_admin column already exists")

        except Exception as e:
            logger.warning(f"Could not ensure is_admin column: {type(e).__name__}: {e}")


async def ensure_commissions_columns():
    """
    Ensure commissions table has auto-calculation columns.

    These columns are needed for auto-commission creation on work order completion.
    Added by migration 026/039 but may not have run on Railway.

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    async with async_session_maker() as session:
        try:
            # Check if commissions table exists first
            table_check = await session.execute(
                text("""SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'commissions'
                )""")
            )
            if not table_check.scalar():
                logger.info("Commissions table does not exist, skipping column ensures")
                return

            # Check which columns exist
            result = await session.execute(
                text(
                    """SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'commissions'"""
                )
            )
            existing_columns = {row[0] for row in result}

            # Columns to ensure exist
            columns_to_add = [
                ("dump_site_id", "UUID"),
                ("job_type", "VARCHAR(50)"),
                ("gallons_pumped", "INTEGER"),
                ("dump_fee_per_gallon", "FLOAT"),
                ("dump_fee_amount", "FLOAT"),
                ("commissionable_amount", "FLOAT"),
            ]

            for col_name, col_type in columns_to_add:
                if col_name not in existing_columns:
                    logger.info(f"Adding column commissions.{col_name}...")
                    await session.execute(
                        text(f"ALTER TABLE commissions ADD COLUMN {col_name} {col_type}")
                    )
                    logger.info(f"Added commissions.{col_name}")

            await session.commit()

            # Create index on job_type if not exists
            try:
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_commissions_job_type ON commissions(job_type)")
                )
                await session.commit()
            except Exception:
                pass  # Index may already exist

            logger.info("Commissions table columns verified")

        except Exception as e:
            logger.warning(f"Could not ensure commissions columns: {type(e).__name__}: {e}")


async def ensure_work_order_audit_columns():
    """Ensure work_orders has audit trail columns and audit log table exists (migration 068).

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    async with async_session_maker() as session:
        try:
            # Add audit columns to work_orders if missing
            # FIX (2026-02-26): Replaced f-string interpolation in information_schema
            # query with bound parameters. Although the values come from a hard-coded
            # list (not user input), defense-in-depth requires parameterized queries.
            # The ALTER TABLE DDL still uses f-strings because DDL does not support
            # bind parameters for column names/types, but the values are hard-coded.
            for col, col_type, default in [
                ("created_by", "VARCHAR(100)", None),
                ("updated_by", "VARCHAR(100)", None),
                ("source", "VARCHAR(50)", "'crm'"),
            ]:
                result = await session.execute(
                    text("SELECT 1 FROM information_schema.columns WHERE table_name = :table AND column_name = :col"),
                    {"table": "work_orders", "col": col},
                )
                if not result.scalar():
                    default_clause = f" DEFAULT {default}" if default else ""
                    await session.execute(text(f"ALTER TABLE work_orders ADD COLUMN {col} {col_type}{default_clause}"))
                    logger.info(f"Added work_orders.{col} column")

            # Fix created_at/updated_at to have proper defaults
            await session.execute(text(
                "ALTER TABLE work_orders ALTER COLUMN created_at SET DEFAULT NOW()"
            ))
            await session.execute(text(
                "ALTER TABLE work_orders ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'"
            ))

            # Backfill NULL created_at
            await session.execute(text(
                "UPDATE work_orders SET created_at = scheduled_date::timestamp WHERE created_at IS NULL AND scheduled_date IS NOT NULL"
            ))
            await session.execute(text(
                "UPDATE work_orders SET created_at = NOW() WHERE created_at IS NULL"
            ))
            await session.execute(text(
                "UPDATE work_orders SET source = 'crm' WHERE source IS NULL"
            ))

            # Create audit log table if missing
            result = await session.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='work_order_audit_log')"
            ))
            if not result.scalar():
                logger.info("Creating work_order_audit_log table...")
                await session.execute(text("""
                    CREATE TABLE work_order_audit_log (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        work_order_id UUID NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
                        action VARCHAR(30) NOT NULL,
                        description TEXT,
                        user_email VARCHAR(100),
                        user_name VARCHAR(200),
                        source VARCHAR(50),
                        ip_address VARCHAR(45),
                        user_agent VARCHAR(500),
                        changes JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_wo_audit_work_order_id ON work_order_audit_log(work_order_id)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_wo_audit_action ON work_order_audit_log(action)"))
                await session.execute(text("CREATE INDEX IF NOT EXISTS ix_wo_audit_created_at ON work_order_audit_log(created_at)"))
                logger.info("work_order_audit_log table created")

            await session.commit()
            logger.info("Work order audit columns ensured")
        except Exception as e:
            await session.rollback()
            logger.warning(f"Could not ensure work order audit columns: {type(e).__name__}: {e}")


async def ensure_user_activity_table():
    """Ensure user_activity_log table exists (migration 069).

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    async with async_session_maker() as session:
        try:
            result = await session.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='user_activity_log')"
            ))
            if not result.scalar():
                logger.info("Creating user_activity_log table...")
                await session.execute(text("""
                    CREATE TABLE user_activity_log (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id INTEGER,
                        user_email VARCHAR(100),
                        user_name VARCHAR(200),
                        category VARCHAR(30) NOT NULL,
                        action VARCHAR(50) NOT NULL,
                        description TEXT,
                        ip_address VARCHAR(45),
                        user_agent VARCHAR(500),
                        source VARCHAR(50),
                        resource_type VARCHAR(50),
                        resource_id VARCHAR(100),
                        endpoint VARCHAR(200),
                        http_method VARCHAR(10),
                        status_code INTEGER,
                        response_time_ms INTEGER,
                        session_id VARCHAR(50),
                        entity_id VARCHAR(100),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """))
                await session.execute(text("CREATE INDEX ix_ual_user_id ON user_activity_log(user_id)"))
                await session.execute(text("CREATE INDEX ix_ual_category ON user_activity_log(category)"))
                await session.execute(text("CREATE INDEX ix_ual_action ON user_activity_log(action)"))
                await session.execute(text("CREATE INDEX ix_ual_created_at ON user_activity_log(created_at)"))
                await session.execute(text("CREATE INDEX ix_ual_user_created ON user_activity_log(user_id, created_at)"))
                await session.execute(text("CREATE INDEX ix_ual_category_created ON user_activity_log(category, created_at)"))
                logger.info("user_activity_log table created")
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.warning(f"Could not ensure user_activity_log table: {type(e).__name__}: {e}")


async def ensure_missing_indexes():
    """Ensure critical indexes exist (migration 070). Idempotent.

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    indexes = [
        ("ix_customers_entity_id", "customers", "entity_id"),
        ("ix_work_orders_entity_id", "work_orders", "entity_id"),
        ("ix_payments_entity_id", "payments", "entity_id"),
        ("ix_invoices_entity_id", "invoices", "entity_id"),
        ("ix_technicians_entity_id", "technicians", "entity_id"),
        ("ix_payments_invoice_id", "payments", "invoice_id"),
        ("ix_work_orders_customer_id", "work_orders", "customer_id"),
        ("ix_time_entries_payroll_period", "time_entries", "payroll_period_id"),
    ]
    async with async_session_maker() as session:
        try:
            for idx_name, table, column in indexes:
                await session.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})"
                ))
            await session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_work_orders_scheduled_date_status "
                "ON work_orders(scheduled_date, status)"
            ))
            # GIN trigram index for customer search
            await session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_customers_name_trgm "
                "ON customers USING gin ((first_name || ' ' || last_name) gin_trgm_ops)"
            ))
            await session.commit()
            logger.info("Missing indexes ensured (migration 077)")
        except Exception as e:
            await session.rollback()
            logger.warning(f"Could not ensure indexes: {type(e).__name__}: {e}")


async def ensure_ms365_columns():
    """Ensure MS365 integration columns exist (migrations 072-075).

    NOTE: Safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    # (table, column, type, extra)
    columns = [
        ("api_users", "microsoft_id", "VARCHAR(255) UNIQUE", "072"),
        ("api_users", "microsoft_email", "VARCHAR(255)", "072"),
        ("work_orders", "outlook_event_id", "VARCHAR(255)", "073"),
        ("technicians", "microsoft_user_id", "VARCHAR(255)", "073"),
        ("technicians", "microsoft_email", "VARCHAR(255)", "073"),
        ("work_orders", "sharepoint_item_id", "VARCHAR(255)", "074"),
        ("customers", "sharepoint_folder_url", "VARCHAR(500)", "074"),
        ("work_orders", "ms_booking_appointment_id", "VARCHAR(255)", "078"),
        ("work_orders", "booking_source", "VARCHAR(50)", "078"),
    ]

    async with async_session_maker() as session:
        try:
            # FIX (2026-02-26): Replaced f-string in information_schema query
            # with bound parameters. DDL (ALTER TABLE) still uses f-strings
            # because SQL DDL does not support bind params for identifiers,
            # but the values come from the hard-coded list above.
            for table, column, col_type, migration in columns:
                result = await session.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = :table AND column_name = :col)"
                    ),
                    {"table": table, "col": column},
                )
                if not result.scalar():
                    logger.info(f"Adding {table}.{column} (migration {migration})...")
                    await session.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                    ))

            # Ensure inbound_emails table (migration 075)
            result = await session.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name='inbound_emails')"
            ))
            if not result.scalar():
                logger.info("Creating inbound_emails table (migration 075)...")
                await session.execute(text("""
                    CREATE TABLE inbound_emails (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        message_id VARCHAR(500) UNIQUE NOT NULL,
                        sender_email VARCHAR(255) NOT NULL,
                        sender_name VARCHAR(255),
                        subject VARCHAR(500),
                        body_preview TEXT,
                        received_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
                        action_taken VARCHAR(50) DEFAULT 'none',
                        entity_id UUID,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await session.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_inbound_emails_sender ON inbound_emails(sender_email)"
                ))
                await session.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_inbound_emails_received ON inbound_emails(received_at DESC)"
                ))

            await session.commit()
            logger.info("MS365 columns and tables ensured")
        except Exception as e:
            await session.rollback()
            logger.warning(f"Could not ensure MS365 columns: {type(e).__name__}: {e}")


async def ensure_mfa_tables():
    """
    Ensure MFA tables exist for authentication.

    These tables are needed for the User.mfa_settings relationship.
    Added by migration 038 but may not have run on Railway.

    NOTE: Migrated to Alembic 071. Kept as safety net for deployments that skip migrations.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    async with async_session_maker() as session:
        try:
            # Check if user_mfa_settings table exists
            result = await session.execute(
                text(
                    """SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'user_mfa_settings'
                )"""
                )
            )
            table_exists = result.scalar()

            if not table_exists:
                logger.info("Creating MFA tables (migration 038 may not have run)...")

                # Create user_mfa_settings table
                await session.execute(
                    text("""
                    CREATE TABLE IF NOT EXISTS user_mfa_settings (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL UNIQUE REFERENCES api_users(id),
                        totp_secret VARCHAR(32),
                        totp_enabled BOOLEAN DEFAULT FALSE,
                        totp_verified BOOLEAN DEFAULT FALSE,
                        mfa_enabled BOOLEAN DEFAULT FALSE,
                        mfa_enforced BOOLEAN DEFAULT FALSE,
                        backup_codes_count INTEGER DEFAULT 0,
                        backup_codes_generated_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ,
                        last_used_at TIMESTAMPTZ
                    )
                """)
                )

                # Create user_backup_codes table
                await session.execute(
                    text("""
                    CREATE TABLE IF NOT EXISTS user_backup_codes (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES api_users(id),
                        mfa_settings_id INTEGER NOT NULL REFERENCES user_mfa_settings(id),
                        code_hash VARCHAR(255) NOT NULL,
                        used BOOLEAN DEFAULT FALSE,
                        used_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                )

                # Create mfa_sessions table
                await session.execute(
                    text("""
                    CREATE TABLE IF NOT EXISTS mfa_sessions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id INTEGER NOT NULL REFERENCES api_users(id),
                        session_token_hash VARCHAR(255) NOT NULL UNIQUE,
                        challenge_type VARCHAR(20) DEFAULT 'totp',
                        attempts INTEGER DEFAULT 0,
                        max_attempts INTEGER DEFAULT 3,
                        expires_at TIMESTAMPTZ NOT NULL,
                        verified_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                )

                # Create indexes
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_user_mfa_settings_user_id ON user_mfa_settings(user_id)")
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_user_backup_codes_user_id ON user_backup_codes(user_id)")
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_mfa_sessions_user_id ON mfa_sessions(user_id)")
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_mfa_sessions_expires_at ON mfa_sessions(expires_at)")
                )

                await session.commit()
                logger.info("MFA tables created successfully")
            else:
                logger.debug("MFA tables already exist")

        except Exception as e:
            logger.warning(f"Could not ensure MFA tables: {type(e).__name__}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting React CRM API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Initialize Sentry for error tracking
    init_sentry()
    # SECURITY: Don't log full database URL, just prefix
    if settings.DATABASE_URL:
        logger.info(f"Database URL prefix: {settings.DATABASE_URL[:30]}...")
    try:
        await init_db()
        logger.info("Database initialized successfully")

        # Ensure pay_rate columns exist (fix for migration 025 not running)
        await ensure_pay_rate_columns()

        # Ensure work_order_photos table exists (fix for migration 032 not running)
        await ensure_work_order_photos_table()

        # Ensure messages columns exist (fix for migration 036 not running)
        await ensure_messages_columns()

        # Ensure email_templates table exists (fix for migration 037 not running)
        await ensure_email_templates_table()

        # Ensure commissions table has auto-calc columns (fix for migration 039 not running)
        await ensure_commissions_columns()

        # Ensure work_orders table has work_order_number column
        await ensure_work_order_number_column()

        # Ensure api_users table has is_admin column (fix for migration 043 not running)
        await ensure_is_admin_column()

        # Ensure MFA tables exist (fix for migration 038 not running)
        await ensure_mfa_tables()

        await ensure_work_order_audit_columns()
        await ensure_user_activity_table()
        await ensure_missing_indexes()

        # Ensure MS365 integration columns exist (migrations 072-075)
        await ensure_ms365_columns()
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

    # Start service reminder scheduler
    try:
        start_reminder_scheduler()
        logger.info("Service reminder scheduler started")
    except Exception as e:
        logger.warning(f"Failed to start reminder scheduler: {e}")

    # Start Samsara feed poller background task
    try:
        from app.api.v2.samsara import start_feed_poller, stop_feed_poller
        start_feed_poller()
        logger.info("Samsara feed poller started")
    except Exception as e:
        logger.warning(f"Failed to start Samsara feed poller: {e}")

    # Start MS365 calendar sync scheduler
    try:
        start_calendar_sync()
    except Exception as e:
        logger.warning(f"Failed to start calendar sync: {e}")

    # Start MS365 email poller
    try:
        start_email_poller()
    except Exception as e:
        logger.warning(f"Failed to start email poller: {e}")

    # Start MS365 bookings sync
    try:
        start_bookings_sync()
    except Exception as e:
        logger.warning(f"Failed to start bookings sync: {e}")

    # Start marketing daily report scheduler (7 AM)
    try:
        start_marketing_report_scheduler()
    except Exception as e:
        logger.warning(f"Failed to start marketing report scheduler: {e}")

    # Background task watchdog — restarts crashed tasks every 5 minutes

    # Follow-up scheduler and auto-dispatch — TODO: add start/stop functions
    # try:
    #     start_followup_scheduler()
    # except Exception as e:
    #     logger.warning(f"Failed to start follow-up scheduler: {e}")
    # try:
    #     start_auto_dispatch()
    # except Exception as e:
    #     logger.warning(f"Failed to start auto-dispatch scheduler: {e}")
    import asyncio

    async def _watchdog():
        while True:
            await asyncio.sleep(300)
            # Check RingCentral sync
            try:
                from app.api.v2.ringcentral import _sync_task
                if _sync_task and _sync_task.done():
                    logger.warning("Watchdog: RingCentral sync task died — restarting")
                    start_auto_sync()
            except Exception as e:
                logger.debug(f"Watchdog RingCentral check failed: {e}")
            # Check Samsara feed poller
            try:
                from app.api.v2.samsara import _feed_poller_task, start_feed_poller as restart_samsara
                if _feed_poller_task and _feed_poller_task.done():
                    logger.warning("Watchdog: Samsara feed poller died — restarting")
                    restart_samsara()
            except Exception as e:
                logger.debug(f"Watchdog Samsara check failed: {e}")
            # Check APScheduler
            try:
                from app.tasks.reminder_scheduler import scheduler as _sched
                if _sched and not _sched.running:
                    logger.warning("Watchdog: Reminder scheduler stopped — restarting")
                    _sched.start()
            except Exception as e:
                logger.debug(f"Watchdog scheduler check failed: {e}")

    _watchdog_task = asyncio.create_task(_watchdog())

    # Pre-warm database connection pool for faster first request
    logger.info("Pre-warming database connections...")
    try:
        from sqlalchemy import text
        from app.database import async_session_maker

        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Database connection pool warmed successfully")
    except Exception as e:
        logger.warning(f"Database warmup failed (non-fatal): {e}")

    # Pre-warm Redis connection if available
    logger.info("Pre-warming Redis connection...")
    try:
        from app.services.cache_service import cache_service

        await cache_service.set("warmup:ping", "ok", ttl=60)
        result = await cache_service.get("warmup:ping")
        if result == "ok":
            logger.info("Redis connection warmed successfully (set+get verified)")
        else:
            logger.info("Redis connection warmed (set succeeded, get returned %s)", result)
    except Exception as e:
        logger.debug(f"Redis warmup skipped: {e}")

    yield

    # Shutdown
    logger.info("Shutting down React CRM API...")
    _watchdog_task.cancel()
    stop_auto_sync()
    stop_reminder_scheduler()
    try:
        stop_feed_poller()
    except Exception:
        pass
    stop_calendar_sync()
    stop_email_poller()
    stop_bookings_sync()
    stop_marketing_report_scheduler()
    # stop_followup_scheduler()
    # stop_auto_dispatch()


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

# GZip compression middleware - compress responses > 500 bytes
# This can reduce response sizes by 60-80% for JSON payloads
app.add_middleware(GZipMiddleware, minimum_size=500)

# User Activity Tracking middleware - logs authenticated API actions
# Runs AFTER response (fire-and-forget async task), ~0ms overhead
from app.middleware.activity import ActivityTrackingMiddleware
app.add_middleware(ActivityTrackingMiddleware)

# Server-Timing middleware - adds performance timing headers
# Visible in browser DevTools for debugging TTFB
app.add_middleware(ServerTimingMiddleware)

# Cache-Control headers middleware - browser caching for public endpoints
app.add_middleware(CacheHeadersMiddleware)

# Proxy headers middleware (must be added before CORS)
# This ensures redirects use HTTPS when behind Railway's edge proxy
app.add_middleware(ProxyHeadersMiddleware)

# Correlation ID middleware for distributed tracing
# Extracts/generates X-Correlation-ID and X-Request-ID for request tracking
app.add_middleware(CorrelationIdMiddleware)

# Metrics middleware for Prometheus monitoring
# Automatically tracks request counts and latency
app.add_middleware(MetricsMiddleware)

# CORS middleware
# SECURITY: Restrict origins to known frontend URLs
allowed_origins = [
    settings.FRONTEND_URL,
    "https://react.ecbtx.com",  # Production ReactCRM frontend
]

# Allow localhost origins for development/testing
# These are safe to include since they can only be accessed locally
allowed_origins.extend(
    [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:5174",  # Vite dev server (alternate port)
        "http://localhost:5175",  # Vite dev server (alternate port)
        "http://localhost:3000",  # Alternative dev port
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Correlation-ID",
        "X-Request-ID",
        "X-CSRF-Token",
        "X-Entity-ID",
        "Accept",
    ],
    expose_headers=["X-Correlation-ID", "X-Request-ID"],  # Allow frontend to read correlation headers
    max_age=3600,  # Cache preflight responses for 1 hour
)

# Include routers
app.include_router(api_router, prefix="/api/v2")
app.include_router(public_router, prefix="/api/public/v1", tags=["Public API"])
app.include_router(twilio_router, prefix="/webhooks/twilio", tags=["webhooks"])

# Serve static assets (logos, etc.) — no auth required
from starlette.staticfiles import StaticFiles
import pathlib
_static_dir = pathlib.Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
async def root():
    """Root endpoint - API info."""
    response = {
        "name": "React CRM API",
        "version": settings.VERSION,
        "health": "/health",
        "api_v2": "/api/v2",
        "public_api": "/api/public/v1",
    }
    # Only include docs link if enabled
    if settings.DOCS_ENABLED:
        response["docs"] = "/docs"
    return response


@app.get("/ping")
async def ping():
    """Ultra-lightweight ping endpoint for load balancer keepalives.

    Use this instead of /health for Railway health checks to minimize
    cold start latency. The full /health endpoint validates features.
    """
    return {"status": "ok"}


@app.get("/health")
async def health_check():
    """Health check endpoint with DB latency measurement."""
    import time as _time
    warnings = []
    if not settings.RATE_LIMIT_REDIS_ENABLED:
        warnings.append("rate_limiting_not_distributed")

    # Measure DB latency
    db_status = "healthy"
    db_latency_ms = None
    try:
        from app.database import async_session_maker
        from sqlalchemy import text
        start = _time.monotonic()
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        db_latency_ms = round((_time.monotonic() - start) * 1000, 1)
        if db_latency_ms > 5000:
            warnings.append("db_latency_high")
    except Exception as e:
        db_status = "unhealthy"
        warnings.append(f"db_error: {str(e)[:100]}")

    overall_status = "healthy" if db_status == "healthy" else "degraded"

    return {
        "status": overall_status,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "rate_limiting": "redis" if settings.RATE_LIMIT_REDIS_ENABLED else "memory",
        "database": {
            "status": db_status,
            "latency_ms": db_latency_ms,
        },
        "features": [
            "public_api",
            "oauth2",
            "demo_roles",
            "cs_platform",
            "journey_status",
            "technician_performance",
            "call_intelligence",
            "email_crm",
            "rbac_admin_role",
        ],
        "warnings": warnings,
    }


@app.post("/health/reset-rate-limits")
async def reset_rate_limits_endpoint(request: Request):
    """Reset in-memory rate limit state. Requires admin auth cookie."""
    from app.core.rate_limit import reset_rate_limits
    # Verify admin auth via cookie JWT
    from app.api.deps import get_current_user
    from app.database import async_session_maker
    try:
        async with async_session_maker() as session:
            user = await get_current_user(request=request, db=session)
            if not user.is_superuser:
                raise HTTPException(status_code=403, detail="Admin only")
    except Exception:
        # Also allow via query param secret for emergency use
        secret = request.query_params.get("secret")
        if secret != settings.SECRET_KEY[:16]:
            raise HTTPException(status_code=403, detail="Unauthorized")
    result = reset_rate_limits()
    return result


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
        "errors": [],
    }

    # Core tables that should exist
    core_tables = [
        "api_users",
        "customers",
        "work_orders",
        "invoices",
        "technicians",
        "payments",
        "quotes",
        "messages",
        "activities",
    ]

    try:
        async with async_session_maker() as session:
            # Test connection
            result = await session.execute(text("SELECT 1"))
            checks["database_connected"] = True

            # Get all tables
            result = await session.execute(
                text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            )
            checks["all_tables"] = [row[0] for row in result.fetchall()]

            # Check core tables
            for table in core_tables:
                if table not in checks["all_tables"]:
                    checks["core_tables_missing"].append(table)

            # Check if api_users table exists
            if "api_users" in checks["all_tables"]:
                checks["api_users_table_exists"] = True

                # Get columns
                result = await session.execute(
                    text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'api_users'
                    ORDER BY ordinal_position
                """)
                )
                checks["api_users_columns"] = [row[0] for row in result.fetchall()]
            else:
                checks["errors"].append("api_users table does not exist")

    except Exception as e:
        checks["errors"].append(f"{type(e).__name__}: {str(e)}")

    return checks


@app.post("/health/db/migrate-entities")
async def run_entities_migration():
    """Run migration 063: create company_entities table and add entity_id columns."""
    from sqlalchemy import text
    from app.database import async_session_maker

    results = {"steps": [], "errors": []}

    async with async_session_maker() as session:
        try:
            # 1. Create company_entities table if not exists
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS company_entities (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(100) NOT NULL,
                    short_code VARCHAR(10) UNIQUE,
                    tax_id VARCHAR(20),
                    address_line1 VARCHAR(255),
                    address_line2 VARCHAR(255),
                    city VARCHAR(100),
                    state VARCHAR(50),
                    postal_code VARCHAR(20),
                    phone VARCHAR(20),
                    email VARCHAR(255),
                    logo_url VARCHAR(500),
                    invoice_prefix VARCHAR(10),
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    is_default BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ
                )
            """))
            results["steps"].append("company_entities table ensured")

            # 2. Seed default entity if empty
            r = await session.execute(text("SELECT count(*) FROM company_entities"))
            if r.scalar() == 0:
                await session.execute(text("""
                    INSERT INTO company_entities (id, name, short_code, invoice_prefix, is_active, is_default, state)
                    VALUES (gen_random_uuid(), 'Mac Septic, LLC', 'MACLLC', 'MACLLC', TRUE, TRUE, 'SC')
                """))
                results["steps"].append("seeded default entity")

            # 3. Add entity_id columns to core tables
            tables_with_entity = [
                "customers", "work_orders", "invoices", "payments",
                "technicians", "clover_oauth_tokens", "qbo_oauth_tokens"
            ]
            for table in tables_with_entity:
                r = await session.execute(text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = 'entity_id'"
                ), {"t": table})
                if r.fetchone() is None:
                    await session.execute(text(
                        f'ALTER TABLE {table} ADD COLUMN entity_id UUID REFERENCES company_entities(id)'
                    ))
                    await session.execute(text(
                        f'CREATE INDEX IF NOT EXISTS ix_{table}_entity_id ON {table}(entity_id)'
                    ))
                    results["steps"].append(f"added entity_id to {table}")
                else:
                    results["steps"].append(f"{table}.entity_id already exists")

            # 4. Add default_entity_id to api_users
            r = await session.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'api_users' AND column_name = 'default_entity_id'"
            ))
            if r.fetchone() is None:
                await session.execute(text(
                    'ALTER TABLE api_users ADD COLUMN default_entity_id UUID REFERENCES company_entities(id)'
                ))
                results["steps"].append("added default_entity_id to api_users")
            else:
                results["steps"].append("api_users.default_entity_id already exists")

            await session.commit()
            results["success"] = True
        except Exception as e:
            results["errors"].append(f"{type(e).__name__}: {str(e)}")
            results["success"] = False

    return results


@app.post("/health/db/migrate")
async def run_database_migrations():
    """Reset alembic and run migrations from scratch."""
    from sqlalchemy import text
    from app.database import async_session_maker
    import subprocess
    import os

    results = {"alembic_reset": False, "alembic_run": False, "tables_before": [], "tables_after": [], "errors": []}

    try:
        # Get tables before
        async with async_session_maker() as session:
            result = await session.execute(
                text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """)
            )
            results["tables_before"] = [row[0] for row in result.fetchall()]

            # Get current alembic version
            try:
                result = await session.execute(text("SELECT version_num FROM alembic_version"))
                results["current_version"] = result.scalar_one_or_none()
            except Exception:
                results["current_version"] = None

            # Delete alembic_version to reset state
            await session.execute(text("DELETE FROM alembic_version"))
            await session.commit()
            results["alembic_reset"] = True

        # Run alembic upgrade head
        os.chdir("/app")
        proc = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True, timeout=300)
        results["alembic_run"] = proc.returncode == 0
        if proc.stdout:
            results["alembic_stdout"] = proc.stdout[-2000:]  # Last 2000 chars
        if proc.stderr:
            results["alembic_stderr"] = proc.stderr[-2000:]

        # Get tables after
        async with async_session_maker() as session:
            result = await session.execute(
                text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """)
            )
            results["tables_after"] = [row[0] for row in result.fetchall()]

        results["new_tables"] = [t for t in results["tables_after"] if t not in results["tables_before"]]

    except Exception as e:
        results["errors"].append(f"{type(e).__name__}: {str(e)}")

    return results


@app.post("/health/db/migrate-083")
async def run_migration_083():
    """Fix permit schema issues: customer_id column, status width, changed_fields type."""
    from sqlalchemy import text
    from app.database import async_session_maker

    results = {"success": False, "steps": []}
    try:
        async with async_session_maker() as session:
            # 1. Add customer_id if missing
            check = await session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'septic_permits' AND column_name = 'customer_id'"
            ))
            if check.scalar_one_or_none():
                results["steps"].append("customer_id column already exists")
            else:
                await session.execute(text(
                    "ALTER TABLE septic_permits ADD COLUMN customer_id UUID "
                    "REFERENCES customers(id) ON DELETE SET NULL"
                ))
                await session.execute(text(
                    "CREATE INDEX idx_septic_permits_customer_id ON septic_permits(customer_id)"
                ))
                results["steps"].append("Added customer_id column + index")

            # 2. Widen permit_import_batches.status if needed
            col_info = await session.execute(text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name = 'permit_import_batches' AND column_name = 'status'"
            ))
            max_len = col_info.scalar_one_or_none()
            if max_len and max_len < 50:
                await session.execute(text(
                    "ALTER TABLE permit_import_batches ALTER COLUMN status TYPE VARCHAR(50)"
                ))
                results["steps"].append(f"Widened permit_import_batches.status from {max_len} to 50")
            else:
                results["steps"].append("permit_import_batches.status already wide enough")

            # 3. Fix changed_fields column: text[] → json (model expects JSON)
            cf_type = await session.execute(text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'permit_versions' AND column_name = 'changed_fields'"
            ))
            cf_dtype = cf_type.scalar_one_or_none()
            if cf_dtype and cf_dtype == "ARRAY":
                await session.execute(text(
                    "ALTER TABLE permit_versions "
                    "ALTER COLUMN changed_fields TYPE JSON "
                    "USING to_json(changed_fields)"
                ))
                results["steps"].append(f"Converted permit_versions.changed_fields from {cf_dtype} to JSON")
            else:
                results["steps"].append(f"permit_versions.changed_fields already {cf_dtype}")

            # 4. Stamp alembic
            await session.execute(text("DELETE FROM alembic_version"))
            await session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('083')"))
            results["steps"].append("Stamped alembic at 083")

            await session.commit()
            results["success"] = True

    except Exception as e:
        results["error"] = f"{type(e).__name__}: {str(e)}"

    return results


@app.post("/health/db/migrate-uuid")
async def run_uuid_migrations():
    """Stamp alembic at 045 then upgrade to head (runs 046-049 UUID migrations)."""
    from sqlalchemy import text
    from app.database import async_session_maker
    import subprocess
    import os

    results = {"stamp": False, "upgrade": False, "errors": []}

    try:
        # Step 1: Check current alembic version
        async with async_session_maker() as session:
            try:
                result = await session.execute(text("SELECT version_num FROM alembic_version"))
                results["version_before"] = result.scalar_one_or_none()
            except Exception:
                results["version_before"] = None

        # Step 2: Detect actual DB state and handle accordingly
        os.chdir("/app")
        current = results.get("version_before")

        # Check if migrations already ran (customer PK is UUID)
        already_migrated = False
        async with async_session_maker() as session:
            try:
                col_type = await session.execute(text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'customers' AND column_name = 'id'"
                ))
                dtype = col_type.scalar_one_or_none()
                already_migrated = dtype == "uuid"
                results["customer_id_type"] = dtype
            except Exception:
                pass

        if already_migrated:
            # DB is already at 049 schema - just fix alembic version
            proc = subprocess.run(["alembic", "stamp", "049"], capture_output=True, text=True, timeout=60)
            results["stamp"] = proc.returncode == 0
            results["upgrade"] = True
            results["skipped"] = "DB already migrated (customer.id is UUID), stamped to 049"
        elif current and current >= "049":
            results["stamp"] = True
            results["upgrade"] = True
            results["skipped"] = "Already at migration 049 or later"
        else:
            proc = subprocess.run(["alembic", "stamp", "045"], capture_output=True, text=True, timeout=60)
            results["stamp"] = proc.returncode == 0
            if proc.stderr:
                results["stamp_stderr"] = proc.stderr[-1000:]

            if not results["stamp"]:
                results["errors"].append("alembic stamp 045 failed")
                return results

            # Step 3: Upgrade from 045 to head (runs 046, 047, 048, 049)
            proc = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True, timeout=600)
            results["upgrade"] = proc.returncode == 0
            if proc.stdout:
                results["upgrade_stdout"] = proc.stdout[-2000:]
            if proc.stderr:
                results["upgrade_stderr"] = proc.stderr[-2000:]

        # Step 4: Check version after
        async with async_session_maker() as session:
            try:
                result = await session.execute(text("SELECT version_num FROM alembic_version"))
                results["version_after"] = result.scalar_one_or_none()
            except Exception:
                results["version_after"] = None

    except Exception as e:
        results["errors"].append(f"{type(e).__name__}: {str(e)}")

    return results


@app.post("/health/db/fix-alembic")
async def fix_alembic_version():
    """Fix alembic_version table: widen version_num column and stamp to head (065)."""
    from sqlalchemy import text
    from app.database import async_session_maker
    import subprocess
    import os

    results = {"errors": [], "steps": []}

    try:
        async with async_session_maker() as session:
            # Step 1: Widen alembic_version.version_num to VARCHAR(128)
            await session.execute(text(
                "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"
            ))
            await session.commit()
            results["steps"].append("widened version_num to VARCHAR(128)")

            # Step 2: Clear current version (might be partial from failed run)
            await session.execute(text("DELETE FROM alembic_version"))
            await session.commit()
            results["steps"].append("cleared alembic_version table")

        # Step 3: Stamp to head revision (065)
        os.chdir("/app")
        proc = subprocess.run(
            ["alembic", "stamp", "065"],
            capture_output=True, text=True, timeout=60
        )
        results["stamp_returncode"] = proc.returncode
        if proc.stdout:
            results["stamp_stdout"] = proc.stdout[-500:]
        if proc.stderr:
            results["stamp_stderr"] = proc.stderr[-500:]

        if proc.returncode == 0:
            results["steps"].append("stamped alembic to revision 065")
        else:
            results["errors"].append("alembic stamp 065 failed")

        # Step 4: Verify
        async with async_session_maker() as session:
            result = await session.execute(text("SELECT version_num FROM alembic_version"))
            results["current_version"] = result.scalar_one_or_none()

        results["success"] = len(results["errors"]) == 0

    except Exception as e:
        results["errors"].append(f"{type(e).__name__}: {str(e)}")
        results["success"] = False

    return results


@app.post("/health/db/run-migration-065")
async def run_migration_065():
    """Run migration 065: change payments.invoice_id from INTEGER to UUID.

    The alembic_version was stamped to 065 but the actual DDL never ran.
    This endpoint applies the migration SQL directly.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    results = {"errors": [], "steps": []}

    try:
        async with async_session_maker() as session:
            # Check current column type
            col_result = await session.execute(text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'payments' AND column_name = 'invoice_id'"
            ))
            current_type = col_result.scalar_one_or_none()
            results["invoice_id_type_before"] = current_type

            if current_type == "uuid":
                results["steps"].append("invoice_id already UUID — no action needed")
                results["success"] = True
                return results

            # Drop old INTEGER column and add UUID column
            await session.execute(text("ALTER TABLE payments DROP COLUMN IF EXISTS invoice_id"))
            results["steps"].append("dropped old invoice_id column")

            await session.execute(text(
                "ALTER TABLE payments ADD COLUMN invoice_id UUID"
            ))
            results["steps"].append("added invoice_id as UUID column")

            await session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_payments_invoice_id ON payments (invoice_id)"
            ))
            results["steps"].append("created index on invoice_id")

            await session.commit()

            # Verify
            col_result = await session.execute(text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'payments' AND column_name = 'invoice_id'"
            ))
            results["invoice_id_type_after"] = col_result.scalar_one_or_none()

        results["success"] = True

    except Exception as e:
        results["errors"].append(f"{type(e).__name__}: {str(e)}")
        results["success"] = False

    return results


@app.post("/health/db/create-admin")
async def create_admin_user():
    """Create or reset admin user for development.

    SECURITY: Password is never returned in the response.
    The default password is 'admin123' -- change it immediately after creation.
    """
    from sqlalchemy import text
    from app.database import async_session_maker
    import bcrypt
    import os

    # Only allow in non-production environments
    if os.environ.get("ENVIRONMENT", "").lower() == "production":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Endpoint disabled in production")

    password = "admin123"  # nosec B105 - Dev-only password, never returned to client
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        async with async_session_maker() as session:
            # Check if user exists
            result = await session.execute(text("SELECT id FROM api_users WHERE email = 'admin@macseptic.com'"))
            user_id = result.scalar()

            if user_id:
                # Update existing user's password
                await session.execute(
                    text("""
                    UPDATE api_users SET hashed_password = :hashed WHERE email = 'admin@macseptic.com'
                """),
                    {"hashed": hashed},
                )
                await session.commit()
                return {"status": "password_reset", "email": "admin@macseptic.com"}

            # Create user
            await session.execute(
                text("""
                INSERT INTO api_users (email, hashed_password, first_name, last_name, is_active, is_superuser, created_at)
                VALUES ('admin@macseptic.com', :hashed, 'Admin', 'User', TRUE, TRUE, NOW())
            """),
                {"hashed": hashed},
            )
            await session.commit()

            return {"status": "created", "email": "admin@macseptic.com"}
    except Exception as e:
        logger.error(f"Admin creation error: {type(e).__name__}: {e}")
        return {"status": "error", "error": "An internal error occurred"}


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
                await session.execute(
                    text("""
                    DO $$
                    BEGIN
                        CREATE TYPE invoice_status_enum AS ENUM ('draft', 'sent', 'paid', 'overdue', 'void', 'partial');
                    EXCEPTION
                        WHEN duplicate_object THEN NULL;
                    END $$;
                """)
                )
                results["actions"].append("invoice_status_enum: created or already exists")
            except Exception as e:
                results["errors"].append(f"invoice_status_enum: {str(e)}")

            # Drop old invoices table and recreate with UUID types
            try:
                await session.execute(text("DROP TABLE IF EXISTS invoices CASCADE"))
                await session.execute(
                    text("""
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
                """)
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_invoices_customer_id ON invoices(customer_id)")
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number ON invoices(invoice_number)")
                )
                results["actions"].append("invoices table: recreated with UUID types")
            except Exception as e:
                results["errors"].append(f"invoices table: {str(e)}")

            # Create job_costs table
            try:
                result = await session.execute(
                    text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'job_costs')")
                )
                if not result.scalar():
                    await session.execute(
                        text("""
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
                    """)
                    )
                    await session.execute(
                        text("CREATE INDEX IF NOT EXISTS idx_job_costs_work_order_id ON job_costs(work_order_id)")
                    )
                    await session.execute(
                        text("CREATE INDEX IF NOT EXISTS idx_job_costs_cost_date ON job_costs(cost_date)")
                    )
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
                await session.execute(
                    text("""
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
                """)
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_activities_customer_id ON activities(customer_id)")
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_activities_activity_type ON activities(activity_type)")
                )
                await session.execute(
                    text("CREATE INDEX IF NOT EXISTS idx_activities_activity_date ON activities(activity_date DESC)")
                )
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
        "api_users": [
            ("is_admin", "BOOLEAN DEFAULT FALSE"),
        ],
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
                        # FIX (2026-02-26): Replaced f-string with bound parameters
                        result = await session.execute(
                            text("SELECT 1 FROM information_schema.columns "
                                 "WHERE table_name = :table AND column_name = :col"),
                            {"table": table_name, "col": col_name},
                        )
                        if not result.scalar():
                            await session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
                            results["columns_added"].append(f"{table_name}.{col_name}")
                    except Exception as e:
                        results["errors"].append(f"{table_name}.{col_name}: {str(e)}")

            await session.commit()

    except Exception as e:
        results["errors"].append(str(e))

    return results


@app.post("/health/db/fix-api-users")
async def fix_api_users_table():
    """
    Explicitly add missing columns to api_users table.

    This endpoint is designed to fix the is_admin column issue that
    causes login to fail with ProgrammingError.
    """
    from sqlalchemy import text
    from app.database import async_session_maker

    results = {
        "existing_columns": [],
        "columns_added": [],
        "errors": [],
        "actions": []
    }

    try:
        async with async_session_maker() as session:
            # First, get current columns
            result = await session.execute(
                text("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'api_users'
                    ORDER BY ordinal_position
                """)
            )
            columns = result.fetchall()
            results["existing_columns"] = [{"name": c[0], "type": c[1]} for c in columns]
            existing_names = {c[0] for c in columns}

            # Columns that should exist in api_users
            required_columns = [
                ("is_admin", "BOOLEAN NOT NULL DEFAULT FALSE"),
            ]

            for col_name, col_def in required_columns:
                if col_name not in existing_names:
                    try:
                        results["actions"].append(f"Adding column: {col_name}")
                        await session.execute(
                            text(f"ALTER TABLE api_users ADD COLUMN {col_name} {col_def}")
                        )
                        results["columns_added"].append(col_name)
                        results["actions"].append(f"Successfully added: {col_name}")
                    except Exception as add_err:
                        results["errors"].append(f"Failed to add {col_name}: {type(add_err).__name__}: {str(add_err)}")
                else:
                    results["actions"].append(f"Column {col_name} already exists")

            # Promote will@macseptic.com to admin if is_admin was just added
            if "is_admin" in results["columns_added"]:
                try:
                    await session.execute(
                        text("UPDATE api_users SET is_admin = true WHERE email = 'will@macseptic.com'")
                    )
                    results["actions"].append("Promoted will@macseptic.com to admin")
                except Exception as promo_err:
                    results["errors"].append(f"Failed to promote admin: {str(promo_err)}")

            await session.commit()

    except Exception as e:
        results["errors"].append(f"General error: {type(e).__name__}: {str(e)}")

    return results


@app.post("/health/db/create-tables")
async def create_core_tables():
    """Create core CRM tables directly using raw SQL (bypasses alembic async issues)."""
    from sqlalchemy import text
    from app.database import async_session_maker

    results = {"tables_created": [], "tables_skipped": [], "errors": []}

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
        """,
        "dump_sites": """
            CREATE TABLE IF NOT EXISTS dump_sites (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                address_line1 VARCHAR(255),
                address_city VARCHAR(100),
                address_state VARCHAR(2) NOT NULL,
                address_postal_code VARCHAR(20),
                latitude FLOAT,
                longitude FLOAT,
                fee_per_gallon FLOAT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                notes TEXT,
                contact_name VARCHAR(100),
                contact_phone VARCHAR(20),
                hours_of_operation VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """,
    }

    try:
        async with async_session_maker() as session:
            # Get existing tables
            result = await session.execute(
                text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
            )
            existing_tables = {row[0] for row in result.fetchall()}

            # Create tables in order (respecting foreign key dependencies)
            table_order = [
                "customers",
                "technicians",
                "work_orders",
                "invoices",
                "payments",
                "quotes",
                "messages",
                "activities",
                "payroll_periods",
                "time_entries",
                "commissions",
                "technician_pay_rates",
                "dump_sites",
            ]

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
            result = await session.execute(
                text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """)
            )
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


# RFC 7807 Exception Handlers
# Create handlers with CORS support
_exception_handlers = create_exception_handlers(allowed_origins)

# Register exception handlers
app.add_exception_handler(CRMException, _exception_handlers["crm"])
app.add_exception_handler(StarletteHTTPException, _exception_handlers["http"])
app.add_exception_handler(RequestValidationError, _exception_handlers["validation"])
app.add_exception_handler(Exception, _exception_handlers["generic"])

