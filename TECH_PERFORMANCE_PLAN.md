# Technician Performance Profile - Implementation Plan

## Overview

Build a complete Technician Performance Profile feature that shows:
1. Total jobs completed, returns/revisits, total revenue
2. Revenue split: Pump Outs vs Repairs
3. Clickable drill-down to detailed job lists
4. Real data flow when new jobs are completed

---

## Phase 1: Backend Implementation

### 1.1 New Endpoint: Performance Stats

**Endpoint:** `GET /api/v2/technicians/{technician_id}/performance`

**Response Schema:**
```python
class TechnicianPerformanceStats(BaseModel):
    technician_id: str
    total_jobs_completed: int
    total_revenue: float
    returns_count: int  # Jobs at same customer within 30 days of previous

    # Pump Out stats (job_type in: pumping, grease_trap)
    pump_out_jobs: int
    pump_out_revenue: float

    # Repair stats (job_type in: repair, maintenance)
    repair_jobs: int
    repair_revenue: float

    # Other stats (inspection, installation, emergency, camera_inspection)
    other_jobs: int
    other_revenue: float
```

**SQL Query:**
```sql
WITH completed_jobs AS (
    SELECT
        id, customer_id, job_type, total_amount, scheduled_date
    FROM work_orders
    WHERE technician_id = :tech_id
      AND status = 'completed'
),
returns AS (
    SELECT COUNT(*) as return_count
    FROM completed_jobs c1
    WHERE EXISTS (
        SELECT 1 FROM completed_jobs c2
        WHERE c1.customer_id = c2.customer_id
          AND c1.id != c2.id
          AND c1.scheduled_date - c2.scheduled_date BETWEEN 1 AND 30
    )
)
SELECT
    COUNT(*) as total_jobs,
    COALESCE(SUM(total_amount), 0) as total_revenue,
    COUNT(*) FILTER (WHERE job_type IN ('pumping', 'grease_trap')) as pump_out_jobs,
    COALESCE(SUM(total_amount) FILTER (WHERE job_type IN ('pumping', 'grease_trap')), 0) as pump_out_revenue,
    COUNT(*) FILTER (WHERE job_type IN ('repair', 'maintenance')) as repair_jobs,
    COALESCE(SUM(total_amount) FILTER (WHERE job_type IN ('repair', 'maintenance')), 0) as repair_revenue,
    COUNT(*) FILTER (WHERE job_type NOT IN ('pumping', 'grease_trap', 'repair', 'maintenance')) as other_jobs,
    COALESCE(SUM(total_amount) FILTER (WHERE job_type NOT IN ('pumping', 'grease_trap', 'repair', 'maintenance')), 0) as other_revenue,
    (SELECT return_count FROM returns) as returns_count
FROM completed_jobs;
```

**File:** `app/api/v2/technicians.py` (add to existing router)

---

### 1.2 New Endpoint: Job Details List

**Endpoint:** `GET /api/v2/technicians/{technician_id}/jobs`

**Query Parameters:**
- `job_category`: `pump_outs` | `repairs` | `all` (default: `all`)
- `page`: int (default: 1)
- `page_size`: int (default: 20, max: 100)

**Response Schema:**
```python
class TechnicianJobDetail(BaseModel):
    id: str
    scheduled_date: str
    completed_date: Optional[str]
    customer_id: int
    customer_name: str
    service_location: Optional[str]
    job_type: str
    status: str
    total_amount: float
    duration_minutes: Optional[int]
    notes: Optional[str]

    # For pump outs
    gallons_pumped: Optional[int]  # Extracted from notes or custom field
    tank_size: Optional[str]

    # For repairs
    labor_hours: Optional[float]
    parts_cost: Optional[float]  # From job_costs where cost_type='materials'

class TechnicianJobsResponse(BaseModel):
    items: list[TechnicianJobDetail]
    total: int
    page: int
    page_size: int
    job_category: str
```

**SQL Query:**
```sql
SELECT
    wo.id, wo.scheduled_date, wo.actual_end_time as completed_date,
    wo.customer_id, c.first_name || ' ' || c.last_name as customer_name,
    wo.service_location, wo.job_type, wo.status,
    wo.total_amount, wo.total_labor_minutes as duration_minutes, wo.notes,
    -- Parts cost from job_costs
    (SELECT COALESCE(SUM(total_cost), 0) FROM job_costs
     WHERE work_order_id = wo.id AND cost_type = 'materials') as parts_cost,
    -- Labor hours from job_costs
    (SELECT COALESCE(SUM(quantity), 0) FROM job_costs
     WHERE work_order_id = wo.id AND cost_type = 'labor' AND unit = 'hour') as labor_hours
FROM work_orders wo
LEFT JOIN customers c ON wo.customer_id = c.id
WHERE wo.technician_id = :tech_id
  AND wo.status = 'completed'
  AND (:job_category = 'all' OR
       (:job_category = 'pump_outs' AND wo.job_type IN ('pumping', 'grease_trap')) OR
       (:job_category = 'repairs' AND wo.job_type IN ('repair', 'maintenance')))
ORDER BY wo.scheduled_date DESC
LIMIT :page_size OFFSET :offset;
```

**File:** `app/api/v2/technicians.py` (add to existing router)

---

### 1.3 Schema Additions

**File:** `app/schemas/technician.py`

Add the following schemas:
- `TechnicianPerformanceStats`
- `TechnicianJobDetail`
- `TechnicianJobsResponse`

---

### 1.4 Seed Data Script

**File:** `scripts/seed_technician_performance_data.py`

**Purpose:** Generate realistic fake historical data for existing technicians ONLY.

**Logic:**
1. Query database for existing technician IDs (skip any created today)
2. Query for existing customer IDs to assign fake jobs to
3. For each existing technician, create:
   - 50-100 completed work orders over past 12 months
   - Mix: 60% pumping, 15% grease_trap, 15% repair, 10% maintenance
   - Revenue range: $150-$800 for pump outs, $200-$2000 for repairs
   - Some jobs at same customer (to create "returns")
4. For repair jobs, create associated job_costs records:
   - Labor: 1-6 hours at $75-150/hr
   - Materials: $50-$500 for parts
5. Mark all created records with a special note: "[SEED DATA]"

**Data Distribution:**
- Past 12 months, weighted toward recent months
- 5-15 jobs per month per technician
- Some weekend jobs, mostly weekdays
- Some emergency jobs with higher revenue

---

## Phase 2: Frontend Implementation

### 2.1 New API Hook: useTechnicianPerformance

**File:** `src/api/hooks/useTechnicians.ts` (add to existing file)

```typescript
export function useTechnicianPerformance(technicianId: string | undefined) {
  return useQuery({
    queryKey: technicianKeys.performance(technicianId!),
    queryFn: async () => {
      const response = await apiClient.get<TechnicianPerformanceStats>(
        `/technicians/${technicianId}/performance`
      );
      return response.data;
    },
    enabled: !!technicianId,
    staleTime: 30_000,
  });
}
```

### 2.2 New API Hook: useTechnicianJobs

**File:** `src/api/hooks/useTechnicians.ts` (add to existing file)

```typescript
export function useTechnicianJobs(
  technicianId: string | undefined,
  jobCategory: 'pump_outs' | 'repairs' | 'all' = 'all',
  page: number = 1,
  pageSize: number = 20
) {
  return useQuery({
    queryKey: technicianKeys.jobs(technicianId!, jobCategory, page),
    queryFn: async () => {
      const response = await apiClient.get<TechnicianJobsResponse>(
        `/technicians/${technicianId}/jobs`,
        { params: { job_category: jobCategory, page, page_size: pageSize } }
      );
      return response.data;
    },
    enabled: !!technicianId,
    staleTime: 30_000,
  });
}
```

### 2.3 New Type Definitions

**File:** `src/api/types/technician.ts` (add to existing file)

```typescript
export interface TechnicianPerformanceStats {
  technician_id: string;
  total_jobs_completed: number;
  total_revenue: number;
  returns_count: number;
  pump_out_jobs: number;
  pump_out_revenue: number;
  repair_jobs: number;
  repair_revenue: number;
  other_jobs: number;
  other_revenue: number;
}

export interface TechnicianJobDetail {
  id: string;
  scheduled_date: string;
  completed_date: string | null;
  customer_id: number;
  customer_name: string;
  service_location: string | null;
  job_type: string;
  status: string;
  total_amount: number;
  duration_minutes: number | null;
  notes: string | null;
  gallons_pumped: number | null;
  tank_size: string | null;
  labor_hours: number | null;
  parts_cost: number | null;
}

export interface TechnicianJobsResponse {
  items: TechnicianJobDetail[];
  total: number;
  page: number;
  page_size: number;
  job_category: string;
}
```

### 2.4 New Component: TechnicianPerformanceStats

**File:** `src/features/technicians/components/TechnicianPerformanceStats.tsx`

**Layout:**
```
┌─────────────────────────────────────────────────────────────────┐
│ PERFORMANCE OVERVIEW                                             │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│ Total Jobs   │ Total Revenue│ Returns      │                    │
│    127       │   $45,230    │    8         │                    │
├──────────────┴──────────────┴──────────────┴────────────────────┤
│                                                                  │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐│
│  │ 🚛 PUMP OUTS        [→]    │  │ 🔧 REPAIRS          [→]    ││
│  │ 98 jobs | $32,450          │  │ 29 jobs | $12,780          ││
│  └─────────────────────────────┘  └─────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**Features:**
- Stats cards for total jobs, revenue, returns
- Clickable "Pump Outs" card with job count and revenue
- Clickable "Repairs" card with job count and revenue
- Loading skeleton while fetching
- Empty state for new technicians (all zeros)

### 2.5 New Component: TechnicianJobsModal

**File:** `src/features/technicians/components/TechnicianJobsModal.tsx`

**Layout:**
```
┌─────────────────────────────────────────────────────────────────┐
│ Pump Out Jobs for [Technician Name]                      [X]    │
├─────────────────────────────────────────────────────────────────┤
│ Date       │ Customer    │ Location    │ Gallons │ Revenue     │
├────────────┼─────────────┼─────────────┼─────────┼─────────────┤
│ 01/10/2026 │ John Smith  │ 123 Main St │ 1,200   │ $350.00     │
│ 01/08/2026 │ Jane Doe    │ 456 Oak Ave │ 800     │ $275.00     │
│ ...        │             │             │         │             │
├─────────────────────────────────────────────────────────────────┤
│ < Prev  Page 1 of 5  Next >                                     │
└─────────────────────────────────────────────────────────────────┘
```

**Columns for Pump Outs:**
- Date (scheduled_date)
- Customer Name
- Location
- Gallons Pumped
- Duration
- Revenue

**Columns for Repairs:**
- Date
- Customer Name
- Location
- Job Type (repair/maintenance)
- Labor Hours
- Parts Cost
- Revenue

### 2.6 Update TechnicianDetailPage

**File:** `src/features/technicians/TechnicianDetailPage.tsx`

**Changes:**
1. Import new components and hooks
2. Add state for jobs modal: `jobsModalCategory`, `isJobsModalOpen`
3. Call `useTechnicianPerformance(id)` hook
4. Add `TechnicianPerformanceStats` component after AI Coach panel
5. Add `TechnicianJobsModal` component
6. Pass click handlers to performance stats

**Insertion Point:** After line 189 (after TechnicianCoachPanel):
```tsx
{/* Performance Stats */}
<div className="mb-6">
  <TechnicianPerformanceStats
    technicianId={id}
    onPumpOutsClick={() => openJobsModal('pump_outs')}
    onRepairsClick={() => openJobsModal('repairs')}
  />
</div>
```

---

## Phase 3: Seed Data Execution

### 3.1 Run Seed Script

```bash
cd react-crm-api
python scripts/seed_technician_performance_data.py
```

### 3.2 Verify Data

```sql
-- Check total seeded work orders
SELECT COUNT(*) FROM work_orders WHERE notes LIKE '%[SEED DATA]%';

-- Check per-technician distribution
SELECT
    t.first_name || ' ' || t.last_name as name,
    COUNT(*) as jobs,
    SUM(wo.total_amount) as revenue
FROM work_orders wo
JOIN technicians t ON wo.technician_id = t.id
WHERE wo.notes LIKE '%[SEED DATA]%'
GROUP BY t.id, t.first_name, t.last_name;
```

---

## Phase 4: Playwright Test Suite

### 4.1 Test File

**File:** `tests/technician-performance.e2e.spec.ts`

### 4.2 Test Cases

| # | Test Case | Actions | Assertions |
|---|-----------|---------|------------|
| 1 | Login | Navigate to login, enter credentials, submit | Dashboard loads |
| 2 | Navigate to Technicians | Click Technicians in nav | Technicians list visible |
| 3 | Click existing technician | Click Terry Black or Will Burns | Detail page loads |
| 4 | Verify performance stats | Read stats cards | Jobs > 0, Revenue > 0 |
| 5 | Click Pump Outs | Click pump outs card | Modal opens with table |
| 6 | Verify pump out data | Read table rows | Multiple rows, gallons visible |
| 7 | Click Repairs | Close modal, click repairs card | Modal opens with table |
| 8 | Verify repair data | Read table rows | Multiple rows, labor hours visible |
| 9 | Create new technician | Add Technician, fill form, submit | New tech in list |
| 10 | Verify new tech stats | Click new tech, read stats | All zeros initially |
| 11 | Create work order | Navigate to WO, create, assign to new tech | WO created |
| 12 | Complete work order | Change status to completed | Status updated |
| 13 | Generate invoice | Create invoice for WO | Invoice created |
| 14 | Verify new tech stats | Return to new tech profile | Stats show 1 job |
| 15 | No console errors | Check console throughout | No errors |
| 16 | No network failures | Monitor network | All 2xx responses |

### 4.3 Test Data Cleanup

After tests:
- Delete test technician
- Delete test work order
- Delete test invoice

---

## Implementation Order

### Step 1: Backend - Performance Endpoint
- Add schema to `app/schemas/technician.py`
- Add endpoint to `app/api/v2/technicians.py`
- Test with curl

### Step 2: Backend - Jobs Endpoint
- Add schema to `app/schemas/technician.py`
- Add endpoint to `app/api/v2/technicians.py`
- Test with curl

### Step 3: Backend - Seed Script
- Create `scripts/seed_technician_performance_data.py`
- Run and verify data

### Step 4: Frontend - Types and Hooks
- Add types to `src/api/types/technician.ts`
- Add hooks to `src/api/hooks/useTechnicians.ts`

### Step 5: Frontend - Components
- Create `TechnicianPerformanceStats.tsx`
- Create `TechnicianJobsModal.tsx`

### Step 6: Frontend - Integration
- Update `TechnicianDetailPage.tsx`

### Step 7: Playwright Tests
- Write comprehensive test suite
- Run and verify all pass

---

## Success Criteria

1. ✅ Existing technicians (Terry Black, Will Burns) show realistic stats from seeded data
2. ✅ Pump Outs section clickable → shows detailed table with gallons, revenue
3. ✅ Repairs section clickable → shows detailed table with labor hours, parts cost
4. ✅ New technicians start with zero stats
5. ✅ Creating and completing a work order updates the technician's stats
6. ✅ All Playwright tests pass
7. ✅ No console errors or network failures

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Seeded data looks fake | Use realistic names, amounts, dates |
| Performance issues with large datasets | Add pagination, indexes |
| Type mismatches (UUID vs VARCHAR) | Use raw SQL with explicit casts |
| Frontend doesn't refresh after job completion | Invalidate query cache |

---

**Plan Date:** 2026-01-15
**Status:** READY FOR IMPLEMENTATION
