"""CSV Import Service - Validate and import data from CSV files.

Supports:
- Customer import
- Work order import
- Technician import
- Equipment import
- Inventory import
- Assets import (company vehicles, tools, etc.)
- Call logs import
"""

import csv
import io
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, time
from pydantic import BaseModel, ValidationError, EmailStr, field_validator
from enum import Enum
import re


class ImportType(str, Enum):
    CUSTOMERS = "customers"
    WORK_ORDERS = "work_orders"
    TECHNICIANS = "technicians"
    EQUIPMENT = "equipment"
    INVENTORY = "inventory"
    ASSETS = "assets"
    CALL_LOGS = "call_logs"


class ImportResult(BaseModel):
    success: bool
    total_rows: int
    imported_count: int
    skipped_count: int
    error_count: int
    errors: List[Dict[str, Any]]
    warnings: List[str]


# ========================
# Validation Schemas
# ========================


class CustomerImportRow(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    customer_type: str = "residential"
    tags: Optional[str] = None  # Comma-separated
    notes: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if v and "@" not in v:
            raise ValueError("Invalid email format")
        return v

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v):
        if v:
            # Remove non-numeric chars
            digits = re.sub(r"\D", "", v)
            if len(digits) == 10:
                return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
            elif len(digits) == 11 and digits[0] == "1":
                return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        return v


class WorkOrderImportRow(BaseModel):
    customer_name: str
    customer_email: Optional[str] = None
    service_address: str
    job_type: str
    scheduled_date: Optional[str] = None
    status: str = "draft"
    priority: str = "normal"
    description: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("job_type")
    @classmethod
    def validate_job_type(cls, v):
        valid_types = ["pumping", "inspection", "repair", "installation", "maintenance", "emergency"]
        if v.lower() not in valid_types:
            raise ValueError(f"Invalid job type. Must be one of: {', '.join(valid_types)}")
        return v.lower()


class TechnicianImportRow(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    skills: Optional[str] = None  # Comma-separated
    hourly_rate: Optional[float] = None
    license_number: Optional[str] = None


class EquipmentImportRow(BaseModel):
    name: str
    equipment_type: str
    serial_number: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    purchase_date: Optional[str] = None
    condition: str = "good"
    notes: Optional[str] = None


class InventoryImportRow(BaseModel):
    name: str
    sku: Optional[str] = None
    category: Optional[str] = None
    quantity: int = 0
    unit: str = "each"
    unit_cost: Optional[float] = None
    reorder_point: Optional[int] = None
    supplier: Optional[str] = None


class AssetImportRow(BaseModel):
    name: str
    asset_type: str = "vehicle"
    asset_tag: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    year: Optional[int] = None
    purchase_price: Optional[float] = None
    status: str = "available"
    condition: str = "good"
    odometer_miles: Optional[float] = None
    notes: Optional[str] = None

    @field_validator("year", mode="before")
    @classmethod
    def parse_year(cls, v):
        if v is None or v == "":
            return None
        try:
            return int(float(str(v)))
        except (ValueError, TypeError):
            return None

    @field_validator("purchase_price", "odometer_miles", mode="before")
    @classmethod
    def parse_float(cls, v):
        if v is None or v == "":
            return None
        try:
            return float(str(v).replace(",", ""))
        except (ValueError, TypeError):
            return None


class CallLogImportRow(BaseModel):
    caller_number: Optional[str] = None
    called_number: Optional[str] = None
    direction: str = "inbound"
    call_date: Optional[str] = None
    call_time: Optional[str] = None
    duration_seconds: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("duration_seconds", mode="before")
    @classmethod
    def parse_duration(cls, v):
        if v is None or v == "":
            return None
        try:
            return int(float(str(v)))
        except (ValueError, TypeError):
            return None


# ========================
# Template Generators
# ========================

TEMPLATES = {
    ImportType.CUSTOMERS: [
        "name",
        "email",
        "phone",
        "address",
        "city",
        "state",
        "zip_code",
        "customer_type",
        "tags",
        "notes",
    ],
    ImportType.WORK_ORDERS: [
        "customer_name",
        "customer_email",
        "service_address",
        "job_type",
        "scheduled_date",
        "status",
        "priority",
        "description",
        "notes",
    ],
    ImportType.TECHNICIANS: [
        "first_name",
        "last_name",
        "email",
        "phone",
        "employee_id",
        "skills",
        "hourly_rate",
        "license_number",
    ],
    ImportType.EQUIPMENT: [
        "name",
        "equipment_type",
        "serial_number",
        "model",
        "manufacturer",
        "purchase_date",
        "condition",
        "notes",
    ],
    ImportType.INVENTORY: ["name", "sku", "category", "quantity", "unit", "unit_cost", "reorder_point", "supplier"],
    ImportType.ASSETS: [
        "name",
        "asset_type",
        "asset_tag",
        "make",
        "model",
        "serial_number",
        "year",
        "purchase_price",
        "status",
        "condition",
        "odometer_miles",
        "notes",
    ],
    ImportType.CALL_LOGS: [
        "caller_number",
        "called_number",
        "direction",
        "call_date",
        "call_time",
        "duration_seconds",
        "notes",
    ],
}


def generate_csv_template(import_type: ImportType) -> str:
    """Generate a CSV template with headers for the given import type."""
    headers = TEMPLATES.get(import_type, [])
    return ",".join(headers) + "\n"


def generate_template_with_examples(import_type: ImportType) -> str:
    """Generate a CSV template with example data."""
    headers = TEMPLATES.get(import_type, [])
    template = ",".join(headers) + "\n"

    examples = {
        ImportType.CUSTOMERS: 'John Doe,john@example.com,(555) 123-4567,123 Main St,Austin,TX,78701,residential,"septic,regular",First time customer',
        ImportType.WORK_ORDERS: "John Doe,john@example.com,123 Main St Austin TX 78701,pumping,2025-01-15,scheduled,normal,Annual pumping service,Access through back gate",
        ImportType.TECHNICIANS: 'Mike,Smith,mike@company.com,(555) 987-6543,EMP001,"pumping,repair",25.00,LIC-12345',
        ImportType.EQUIPMENT: "Vacuum Truck 1,truck,VT-2024-001,ProVac 3000,ProVac Inc,2024-01-15,good,Primary pump truck",
        ImportType.INVENTORY: "4 inch PVC Pipe,PVC-4IN-10,Pipes and Fittings,50,feet,2.50,20,ABC Plumbing Supply",
        ImportType.ASSETS: "2022 Ford F-550,vehicle,MAC-001,Ford,F-550,1FDUF5HT8NED12345,2022,65000,in_use,good,45230,Primary vacuum truck",
        ImportType.CALL_LOGS: "(615) 555-1234,(615) 345-2544,inbound,2025-01-14,09:30:00,180,Customer inquiry about pumping service",
    }

    return template + examples.get(import_type, "")


# ========================
# Validation Functions
# ========================


def validate_row(
    row: Dict[str, str], import_type: ImportType, row_num: int
) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """Validate a single row and return (is_valid, validated_data, error_message)."""
    try:
        if import_type == ImportType.CUSTOMERS:
            validated = CustomerImportRow(**row)
        elif import_type == ImportType.WORK_ORDERS:
            validated = WorkOrderImportRow(**row)
        elif import_type == ImportType.TECHNICIANS:
            validated = TechnicianImportRow(**row)
        elif import_type == ImportType.EQUIPMENT:
            validated = EquipmentImportRow(**row)
        elif import_type == ImportType.INVENTORY:
            validated = InventoryImportRow(**row)
        elif import_type == ImportType.ASSETS:
            validated = AssetImportRow(**row)
        elif import_type == ImportType.CALL_LOGS:
            validated = CallLogImportRow(**row)
        else:
            return False, None, f"Unknown import type: {import_type}"

        return True, validated.model_dump(), None
    except ValidationError as e:
        errors = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
        return False, None, f"Row {row_num}: {errors}"


def parse_csv_content(content: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Parse CSV content and return headers and rows."""
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    rows = list(reader)
    return headers, rows


def validate_headers(headers: List[str], import_type: ImportType) -> Tuple[bool, List[str]]:
    """Validate that required headers are present."""
    expected = set(TEMPLATES.get(import_type, []))
    actual = set(h.strip().lower() for h in headers)

    # Normalize headers
    normalized = [h.strip().lower().replace(" ", "_") for h in headers]

    # Required fields for each type
    required_fields = {
        ImportType.CUSTOMERS: ["name"],
        ImportType.WORK_ORDERS: ["customer_name", "service_address", "job_type"],
        ImportType.TECHNICIANS: ["first_name", "last_name"],
        ImportType.EQUIPMENT: ["name", "equipment_type"],
        ImportType.INVENTORY: ["name"],
        ImportType.ASSETS: ["name"],
        ImportType.CALL_LOGS: [],
    }

    missing = []
    for field in required_fields.get(import_type, []):
        if field not in normalized:
            missing.append(field)

    if missing:
        return False, [f"Missing required columns: {', '.join(missing)}"]

    # Check for unknown columns (warnings)
    warnings = []
    for h in normalized:
        if h and h not in expected:
            warnings.append(f"Unknown column '{h}' will be ignored")

    return True, warnings


async def validate_csv_file(content: str, import_type: ImportType) -> ImportResult:
    """Validate a CSV file without importing."""
    headers, rows = parse_csv_content(content)

    # Validate headers
    headers_valid, header_warnings = validate_headers(headers, import_type)
    if not headers_valid:
        return ImportResult(
            success=False,
            total_rows=0,
            imported_count=0,
            skipped_count=0,
            error_count=1,
            errors=[{"row": 0, "error": header_warnings[0]}],
            warnings=[],
        )

    # Validate each row
    errors = []
    valid_count = 0
    for i, row in enumerate(rows, start=2):  # Start at 2 (1 for header, 1 for 1-indexed)
        # Normalize row keys
        normalized_row = {k.strip().lower().replace(" ", "_"): v for k, v in row.items()}

        is_valid, _, error = validate_row(normalized_row, import_type, i)
        if is_valid:
            valid_count += 1
        else:
            errors.append({"row": i, "error": error})

    return ImportResult(
        success=len(errors) == 0,
        total_rows=len(rows),
        imported_count=0,  # Validation only
        skipped_count=0,
        error_count=len(errors),
        errors=errors[:50],  # Limit errors returned
        warnings=header_warnings,
    )


def _split_name(full_name: str) -> Tuple[str, str]:
    """Split 'First Last' into (first_name, last_name)."""
    parts = full_name.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return full_name.strip(), ""


async def process_import(
    content: str,
    import_type: ImportType,
    db_session: Any,
    user_email: str,
    skip_errors: bool = False,
) -> ImportResult:
    """Process a CSV import and save to database."""
    from app.models.customer import Customer
    # Import other models as needed

    headers, rows = parse_csv_content(content)

    # Validate headers first
    headers_valid, header_warnings = validate_headers(headers, import_type)
    if not headers_valid:
        return ImportResult(
            success=False,
            total_rows=0,
            imported_count=0,
            skipped_count=0,
            error_count=1,
            errors=[{"row": 0, "error": header_warnings[0]}],
            warnings=[],
        )

    errors = []
    imported = 0
    skipped = 0

    for i, row in enumerate(rows, start=2):
        # Normalize row keys
        normalized_row = {k.strip().lower().replace(" ", "_"): v for k, v in row.items()}

        is_valid, data, error = validate_row(normalized_row, import_type, i)

        if not is_valid:
            if skip_errors:
                errors.append({"row": i, "error": error})
                skipped += 1
                continue
            else:
                return ImportResult(
                    success=False,
                    total_rows=len(rows),
                    imported_count=imported,
                    skipped_count=skipped,
                    error_count=len(errors) + 1,
                    errors=errors + [{"row": i, "error": error}],
                    warnings=header_warnings,
                )

        # Create database record
        try:
            if import_type == ImportType.CUSTOMERS:
                # Parse tags from comma-separated string
                tags = ""
                if data.get("tags"):
                    tags = data["tags"]

                # Split name into first_name / last_name
                first_name, last_name = _split_name(data["name"])

                customer = Customer(
                    first_name=first_name,
                    last_name=last_name,
                    email=data.get("email"),
                    phone=data.get("phone"),
                    address_line1=data.get("address"),
                    city=data.get("city"),
                    state=data.get("state"),
                    postal_code=data.get("zip_code"),
                    customer_type=data.get("customer_type", "residential"),
                    tags=tags,
                    lead_notes=data.get("notes"),
                )
                db_session.add(customer)
                imported += 1

            elif import_type == ImportType.TECHNICIANS:
                from app.models.technician import Technician
                import uuid

                skills = []
                if data.get("skills"):
                    skills = [s.strip() for s in data["skills"].split(",")]

                tech = Technician(
                    id=str(uuid.uuid4()),
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                    email=data.get("email"),
                    phone=data.get("phone"),
                    employee_id=data.get("employee_id"),
                    skills=skills,
                    hourly_rate=data.get("hourly_rate"),
                    license_number=data.get("license_number"),
                )
                db_session.add(tech)
                imported += 1

            elif import_type == ImportType.WORK_ORDERS:
                from app.models.work_order import WorkOrder
                from sqlalchemy import select
                import uuid

                # Look up customer by name or email
                customer_id = None
                if data.get("customer_email"):
                    result = await db_session.execute(
                        select(Customer.id).where(Customer.email == data["customer_email"]).limit(1)
                    )
                    row_result = result.scalar_one_or_none()
                    if row_result:
                        customer_id = row_result

                if not customer_id and data.get("customer_name"):
                    first, last = _split_name(data["customer_name"])
                    result = await db_session.execute(
                        select(Customer.id).where(
                            Customer.first_name == first,
                            Customer.last_name == last,
                        ).limit(1)
                    )
                    row_result = result.scalar_one_or_none()
                    if row_result:
                        customer_id = row_result

                if not customer_id:
                    # Create stub customer
                    first, last = _split_name(data["customer_name"])
                    stub = Customer(
                        first_name=first,
                        last_name=last,
                        email=data.get("customer_email"),
                        address_line1=data.get("service_address"),
                    )
                    db_session.add(stub)
                    await db_session.flush()
                    customer_id = stub.id

                scheduled = None
                if data.get("scheduled_date"):
                    try:
                        scheduled = datetime.strptime(data["scheduled_date"], "%Y-%m-%d").date()
                    except ValueError:
                        pass

                wo = WorkOrder(
                    id=uuid.uuid4(),
                    customer_id=customer_id,
                    job_type=data["job_type"],
                    service_address_line1=data.get("service_address"),
                    scheduled_date=scheduled,
                    status=data.get("status", "draft"),
                    priority=data.get("priority", "normal"),
                    notes=data.get("notes"),
                    internal_notes=data.get("description"),
                    source="import",
                )
                db_session.add(wo)
                imported += 1

            elif import_type == ImportType.ASSETS:
                from app.models.asset import Asset
                import uuid

                asset = Asset(
                    id=uuid.uuid4(),
                    name=data["name"],
                    asset_type=data.get("asset_type", "vehicle"),
                    asset_tag=data.get("asset_tag") or None,
                    make=data.get("make") or None,
                    model=data.get("model") or None,
                    serial_number=data.get("serial_number") or None,
                    year=data.get("year"),
                    purchase_price=data.get("purchase_price"),
                    status=data.get("status", "available"),
                    condition=data.get("condition", "good"),
                    odometer_miles=data.get("odometer_miles"),
                    notes=data.get("notes"),
                )
                db_session.add(asset)
                imported += 1

            elif import_type == ImportType.CALL_LOGS:
                from sqlalchemy import text
                import uuid

                call_date_val = None
                if data.get("call_date"):
                    try:
                        call_date_val = datetime.strptime(data["call_date"], "%Y-%m-%d").date()
                    except ValueError:
                        pass

                call_time_val = None
                if data.get("call_time"):
                    try:
                        call_time_val = datetime.strptime(data["call_time"], "%H:%M:%S").time()
                    except ValueError:
                        pass

                dur = data.get("duration_seconds")
                if dur is not None:
                    try:
                        dur = int(dur)
                    except (ValueError, TypeError):
                        dur = None

                log_id = uuid.uuid4()
                caller = data.get("caller_number") or ""
                called = data.get("called_number") or ""
                await db_session.execute(
                    text("""
                        INSERT INTO call_logs (id, rc_account_id, rc_call_id, rc_session_id,
                            caller_number, called_number, from_number, to_number,
                            user_id, direction, status, call_disposition,
                            call_date, call_time, duration_seconds, notes, external_system)
                        VALUES (:id, :rc_account_id, :rc_call_id, :rc_session_id,
                            :caller_number, :called_number, :from_number, :to_number,
                            :user_id, :direction, :status, :call_disposition,
                            :call_date, :call_time, :duration_seconds, :notes, :external_system)
                    """),
                    {
                        "id": log_id,
                        "rc_account_id": uuid.uuid4(),
                        "rc_call_id": f"import-{log_id}",
                        "rc_session_id": f"import-{log_id}",
                        "caller_number": caller,
                        "called_number": called,
                        "from_number": caller,
                        "to_number": called,
                        "user_id": "1",
                        "direction": data.get("direction", "inbound"),
                        "call_date": call_date_val,
                        "call_time": call_time_val,
                        "duration_seconds": dur,
                        "status": "completed",
                        "call_disposition": "completed",
                        "notes": data.get("notes"),
                        "external_system": "onedrive_import",
                    },
                )
                imported += 1

        except Exception as e:
            if skip_errors:
                errors.append({"row": i, "error": str(e)})
                skipped += 1
            else:
                raise

    # Commit if successful
    if imported > 0:
        await db_session.commit()

    return ImportResult(
        success=len(errors) == 0 or (skip_errors and imported > 0),
        total_rows=len(rows),
        imported_count=imported,
        skipped_count=skipped,
        error_count=len(errors),
        errors=errors[:50],
        warnings=header_warnings,
    )
