# Technician Performance Profile - Codebase Analysis

## Executive Summary

This document analyzes the current state of both the ReactCRM frontend and react-crm-api backend codebases to understand what exists and what needs to be built for the Technician Performance Profile feature.

---

## Current State: Frontend (ReactCRM)

### Technician Detail Page

**Location:** `src/features/technicians/TechnicianDetailPage.tsx`

**Currently Displays:**
- Contact Information (email, phone)
- Skills & Certifications
- Home Location
- Assigned Work Orders (with 4 stat cards: Today, In Progress, Upcoming, Completed)
- Vehicle Information
- License & Payroll
- Record Info (ID, created/updated dates)
- AI Performance Coach panel

**What's Missing:**
- Total jobs completed (historical)
- Returns/revisits count
- Total revenue generated
- Revenue breakdown by job type (Pump Outs vs Repairs)
- Clickable drill-down sections for job details

### Key API Hooks Available

| Hook | Purpose |
|------|---------|
| `useTechnician(id)` | Fetch single technician |
| `useWorkOrders(filters)` | Fetch work orders list |
| `useInvoices(filters)` | Fetch invoices list |

### Current Work Order Attribution

The detail page currently fetches ALL work orders and filters client-side:
```typescript
const technicianName = technician?.first_name && technician?.last_name
  ? `${technician.first_name} ${technician.last_name}`
  : "";

const assignedWorkOrders = workOrders?.items?.filter(
  (wo) => wo.assigned_technician === technicianName
) || [];
```

**Problem:** This is inefficient and only works for active work orders in the current page.

---

## Current State: Backend (react-crm-api)

### Relevant Models

#### 1. Technician Model (`app/models/technician.py`)
- **ID:** VARCHAR(36) UUID
- **Key Fields:** first_name, last_name, skills[], hourly_rate
- **No relationships** defined to WorkOrder

#### 2. WorkOrder Model (`app/models/work_order.py`)
- **ID:** VARCHAR(36) UUID
- **Technician Link:**
  - `technician_id` (VARCHAR(36), FK to technicians)
  - `assigned_technician` (String - denormalized name)
- **Revenue:** `total_amount` (Numeric)
- **Job Type:** ENUM (pumping, inspection, repair, installation, emergency, maintenance, grease_trap, camera_inspection)
- **Status:** ENUM (draft, scheduled, confirmed, enroute, on_site, in_progress, completed, canceled, requires_followup)

#### 3. JobCost Model (`app/models/job_cost.py`)
- **ID:** UUID
- **Links:** work_order_id, technician_id
- **Cost Tracking:** cost_type (labor, materials, equipment, disposal, travel, subcontractor, other)
- **Revenue:** billable_amount, markup_percent

#### 4. Invoice Model (`app/models/invoice.py`)
- **ID:** UUID
- **Links:** customer_id, work_order_id
- **Revenue:** amount
- **Note:** Has ID type mismatches - requires manual joins

### Existing Endpoints

| Endpoint | What it Does |
|----------|--------------|
| `GET /technicians/{id}` | Basic technician info |
| `GET /work-orders?technician_id={id}` | Filter work orders by technician |
| `GET /job-costs?technician_id={id}` | Filter job costs by technician |

### What's Missing (Backend)

1. **No performance stats endpoint** - Need to aggregate:
   - Total completed jobs count
   - Total revenue (sum of total_amount from completed work orders)
   - Revenue breakdown by job_type

2. **No detailed job history endpoint** - Need:
   - Pump out details (gallons pumped, tank size, disposal info)
   - Repair details (parts used, labor hours, repair type)

3. **No revisit/return tracking** - Need to identify:
   - Work orders at same customer within 30 days of previous visit

---

## Data Flow Analysis

### Revenue Attribution Chain

```
WorkOrder (technician_id + total_amount + job_type)
    ↓
Filter by: status = 'completed', technician_id = {id}
    ↓
Aggregate: SUM(total_amount) grouped by job_type
    ↓
Performance Stats
```

### Job Types to Track

| Category | Job Types |
|----------|-----------|
| **Pump Outs** | pumping, grease_trap |
| **Repairs** | repair, maintenance |
| **Other** | inspection, installation, emergency, camera_inspection |

### WorkOrder Fields for Drill-Down

**For Pump Outs:**
- `scheduled_date` - When performed
- Customer name (via customer_id join)
- `service_location` - Address
- `notes` - May contain gallons pumped
- `total_amount` - Revenue
- Duration (actual_end_time - actual_start_time)

**For Repairs:**
- `scheduled_date` - When performed
- Customer name
- `service_location`
- `notes` - May contain repair details
- `total_amount` - Revenue
- Duration
- Related JobCost records for parts/labor breakdown

### Returns/Revisits Logic

A "return" is defined as:
- Same customer_id
- Scheduled within 30 days of a previous completed work order
- By the same technician

---

## Database Schema Analysis

### WorkOrder Table (relevant columns)

```sql
id              VARCHAR(36)  -- PK
customer_id     INTEGER      -- FK to customers
technician_id   VARCHAR(36)  -- FK to technicians
status          VARCHAR(20)  -- ENUM
job_type        VARCHAR(30)  -- ENUM
scheduled_date  DATE
total_amount    NUMERIC(10,2)
notes           TEXT
service_location TEXT
actual_start_time TIMESTAMP WITH TIME ZONE
actual_end_time   TIMESTAMP WITH TIME ZONE
```

### JobCost Table (for parts/labor breakdown)

```sql
id              UUID         -- PK
work_order_id   VARCHAR(36)  -- FK
technician_id   VARCHAR(36)  -- FK
cost_type       VARCHAR(50)  -- labor, materials, etc.
description     VARCHAR(500)
quantity        FLOAT
unit            VARCHAR(50)
unit_cost       FLOAT
total_cost      FLOAT
billable_amount FLOAT
```

---

## Gap Analysis

### What Exists vs What's Needed

| Feature | Exists? | Notes |
|---------|---------|-------|
| Technician basic info | Yes | Endpoint works |
| Work orders by technician | Partial | Filter exists, but no stats aggregation |
| Total jobs completed | No | Need to count completed WOs |
| Total revenue | No | Need to sum total_amount |
| Revenue by job type | No | Need GROUP BY job_type |
| Pump out details | Partial | WO data exists, no dedicated endpoint |
| Repair details | Partial | WO + JobCost data exists, no dedicated endpoint |
| Returns/revisits | No | Need window function or subquery |
| Fake historical data | No | Need seed script |

---

## Existing Technicians in Database

Based on the Playwright test results from earlier:
- **Terry Black** (existing)
- **Will Burns** (existing)
- **Test APITech2** (created during testing)
- **Playwright TestTech** (created during testing)

We need to seed fake historical data for Terry Black and Will Burns (the original technicians).

---

## Technical Decisions

### Backend Approach

1. **New Endpoint:** `GET /technicians/{id}/performance`
   - Returns aggregated stats
   - Uses raw SQL for efficiency (following existing pattern in technicians.py)

2. **Enhanced Endpoint:** `GET /technicians/{id}/jobs`
   - Query params: `job_type`, `page`, `page_size`
   - Returns detailed job list with customer info

3. **Seed Data Script:** `scripts/seed_technician_performance_data.py`
   - Creates fake completed work orders for existing technicians
   - Creates associated job costs
   - Realistic date distribution (past 12 months)

### Frontend Approach

1. **New Component:** `TechnicianPerformanceStats.tsx`
   - Displays revenue and job stats
   - Clickable sections for pump outs and repairs

2. **New Component:** `TechnicianJobsTable.tsx`
   - Paginated table for job details
   - Different columns for pump out vs repair

3. **New Hook:** `useTechnicianPerformance(id)`
   - Fetches performance stats

4. **New Hook:** `useTechnicianJobs(id, jobType)`
   - Fetches job details list

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| ID type mismatches in Invoice | Use WorkOrder.total_amount for revenue, not Invoice.amount |
| Large datasets affecting performance | Add proper pagination and DB indexes |
| Seed data conflicting with real data | Use distinct customer/WO IDs, prefix descriptions |
| Returns calculation complexity | Pre-calculate or use materialized view |

---

## Conclusion

The feature is buildable with:
- 2 new backend endpoints
- 1 seed data script
- 2 new frontend components
- 2 new API hooks
- Updates to TechnicianDetailPage.tsx

The main complexity is in the performance stats aggregation and the returns/revisits calculation. The drill-down tables are straightforward given existing data.

---

**Analysis Date:** 2026-01-15
**Status:** COMPLETE
