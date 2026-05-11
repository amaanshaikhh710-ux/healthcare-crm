# Clinical Follow-Up Management System - Documentation

## Overview

A comprehensive follow-up management system integrated into LeadFlow CRM. Track, schedule, and monitor patient follow-ups with intelligent overdue detection and role-based access control.

---

## Features

### ✓ Core Features

- **Automatic Overdue Detection**: Follow-ups past their due date automatically marked as overdue
- **Role-Based Access**: DOCTOR sees only their follow-ups; ADMIN sees all
- **Status Tracking**: PENDING → DONE state transitions
- **Datetime Management**: Proper formatting and timezone handling
- **Professional UI**: SaaS-quality dashboard with summary cards and filtering

### ✓ Smart Features

- **Overdue Follow-Ups**: Quick identification of late follow-ups
- **Status Filtering**: Filter by PENDING or DONE
- **Date Range Filtering**: Show follow-ups from specific dates onwards
- **Overdue-Only View**: Toggle to show only overdue follow-ups
- **Summary Statistics**: Total, Pending, Completed, Overdue counts

---

## Database Schema

### Table: `followups`

```sql
CREATE TABLE followups (
    followup_id INT AUTO_INCREMENT PRIMARY KEY,
    appointment_id INT NOT NULL,
    doctor_id INT NOT NULL,
    followup_date DATE NOT NULL,
    notes TEXT DEFAULT NULL,
    status ENUM('PENDING', 'DONE') DEFAULT 'PENDING',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME DEFAULT NULL,
    
    CONSTRAINT fk_followup_appointment FOREIGN KEY (appointment_id) 
        REFERENCES appointments(appointment_id) ON DELETE CASCADE,
    CONSTRAINT fk_followup_doctor FOREIGN KEY (doctor_id) 
        REFERENCES doctors(doctor_id) ON DELETE CASCADE
) ENGINE=InnoDB;
```

**Columns**:
- `followup_id`: Unique identifier
- `appointment_id`: Link to appointment (FK)
- `doctor_id`: Doctor responsible (FK)
- `followup_date`: When the follow-up should occur
- `notes`: Clinical notes or observations
- `status`: PENDING or DONE
- `created_at`: When scheduled
- `completed_at`: When marked as done

---

## Flask Endpoints

### 1. List Follow-Ups

**GET** `/followups`

Returns professional dashboard with follow-up list.

**Parameters**:
- `status` (optional): Filter by 'PENDING' or 'DONE'
- `date` (optional): Show follow-ups from this date (YYYY-MM-DD)
- `overdue` (optional): Set to 'on' to show only overdue

**Response Data**:
```python
{
    'followups': [
        {
            'followup_id': 1,
            'appointment_id': 5,
            'doctor_id': 2,
            'followup_date': datetime(2026, 03, 10),
            'notes': 'Check wound healing',
            'status': 'PENDING',
            'is_overdue': 0,
            'patient_name': 'John Doe',
            'doctor_name': 'Dr. Smith',
            'appointment_date': datetime(2026, 02, 25),
            'service': 'Surgery Follow-Up'
        }
    ],
    'stats': {
        'total_followups': 15,
        'pending': 8,
        'completed': 7,
        'overdue': 2
    }
}
```

**Security**: DOCTOR role sees only their follow-ups; ADMIN sees all

---

### 2. Add Follow-Up

**GET/POST** `/add-followup/<int:appointment_id>`

Shows form and creates new follow-up.

**GET**: Display form (requires DOCTOR or ADMIN)

**POST**: Create follow-up

**Form Fields**:
- `followup_date` (required): Date for follow-up (YYYY-MM-DD)
- `notes` (optional): Clinical notes

**Validation**:
- Appointment must exist
- User must be DOCTOR (own appointment) or ADMIN
- Date must be in valid format

**Response**:
- Success: Redirects to `/appointments` with success flash
- Error: Redirects back with error message

**Security**:
- DOCTOR: Can only create for their own appointments
- ADMIN/STAFF: Can create for any appointment

---

### 3. Complete Follow-Up

**POST** `/complete-followup/<int:followup_id>`

Mark a follow-up as DONE.

**Updates**:
- `status` ← 'DONE'
- `completed_at` ← NOW()

**Response**:
- Success: Redirects to `/followups` with success flash
- Error: Redirects back with error message

**Security**:
- DOCTOR: Can only complete their own follow-ups
- ADMIN/STAFF: Can complete any follow-up

---

## Integration Points

### 1. Appointment Completion Flow

After marking an appointment as COMPLETED:
```
Appointment Completed
├── Generate Invoice (Optional)
└── Add Follow-Up (Optional)
```

**From Appointments Page**:
- Action button: "📋 Follow-Up" appears on COMPLETED appointments
- Opens `/add-followup/<appointment_id>` form

### 2. Dashboard Integration

Follow-ups page shows:
- Summary cards (Total, Pending, Completed, Overdue)
- Professional table with filtering
- Overdue detection and highlighting
- Quick actions (Mark as Done)

### 3. Template Integration

**appointments.html**: Added follow-up button for completed appointments
**followups.html**: Professional SaaS dashboard
**add-followup.html**: Form for scheduling new follow-ups

---

## UI Components

### Summary Cards

```
┌─────────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐
│ Total Follow-Ups│  │   Pending    │  │  Completed   │  │  Overdue   │
│       15        │  │      8       │  │      7       │  │     2      │
│       📋        │  │      ⏳       │  │      ✓       │  │     🔴     │
└─────────────────┘  └──────────────┘  └──────────────┘  └────────────┘
```

### Status Badges

- **PENDING** (⏳ Amber): Follow-up scheduled but not completed
- **DONE** (✓ Green): Follow-up completed
- **OVERDUE** (🔴 Red): Pending follow-up past due date

### Filters

- Status filter (All, Pending, Done)
- Date range filter (from date)
- Overdue checkbox (show only late follow-ups)

---

## Data Display

### Follow-Up Table Columns

| Column | Description | Format |
|--------|-------------|--------|
| ID | Unique identifier | #1, #2, etc |
| Patient | Patient name | Name |
| Doctor | Responsible doctor | Dr. Name |
| Appointment | Original appointment | dd-mm-yyyy |
| Follow-Up Date | Scheduled date | dd-mm-yyyy (red if overdue) |
| Service | Service type | Text |
| Status | PENDING/DONE | Colored badge |
| Notes | Clinical notes | Truncated text |
| Actions | Quick actions | Complete button |

---

## Smart Logic

### Overdue Calculation

Follow-up is marked **overdue** when:
```
followup_date < TODAY AND status = 'PENDING'
```

Computed field in query:
```sql
CASE WHEN f.followup_date < CURDATE() AND f.status = 'PENDING' 
     THEN 1 ELSE 0 END AS is_overdue
```

### Statistics Query

```sql
SELECT 
    COUNT(*) AS total,
    COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending,
    COUNT(CASE WHEN status = 'DONE' THEN 1 END) AS completed,
    COUNT(CASE WHEN followup_date < CURDATE() AND status = 'PENDING' THEN 1 END) AS overdue
FROM followups
WHERE doctor_id = %s  -- If DOCTOR role
```

---

## Error Handling

### Validation

```python
# Appointment validation
if not appointment:
    flash('Appointment not found.', 'danger')

# Role validation
if user_role == 'DOCTOR' and doctor_id != appointment.doctor_id:
    flash('Access denied.', 'danger')

# Date validation
try:
    datetime.strptime(followup_date, '%Y-%m-%d')
except ValueError:
    flash('Invalid date format.', 'warning')
```

### Exception Handling

All routes use try/except/finally:
```python
try:
    # Execute query
except Error as e:
    app.logger.exception('Database error: %s', e)
    flash('Error...', 'danger')
finally:
    cursor.close()
    conn.close()
```

---

## Setup Instructions

### 1. Database Setup

Run the schema script:
```bash
mysql -u root -p healthcare_crm < FOLLOWUP_SCHEMA.sql
```

### 2. Verify Table

```sql
DESCRIBE followups;
```

### 3. Test Queries

```sql
-- Find all pending follow-ups
SELECT * FROM followups WHERE status = 'PENDING' ORDER BY followup_date ASC;

-- Find overdue follow-ups
SELECT * FROM followups 
WHERE followup_date < CURDATE() AND status = 'PENDING'
ORDER BY followup_date ASC;

-- Doctor's follow-ups
SELECT * FROM followups 
WHERE doctor_id = 2 
ORDER BY followup_date ASC;
```

### 4. Start Flask App

```bash
python app.py
```

### 5. Navigate to Follow-Ups

1. Go to: http://localhost:5000/followups
2. Create appointment if needed
3. Mark as COMPLETED
4. Click "📋 Follow-Up" button
5. Schedule follow-up
6. Manage follow-ups on /followups page

---

## Best Practices

### For Doctors

✓ Schedule follow-ups immediately after completing appointments
✓ Add detailed clinical notes for continuity of care
✓ Check overdue follow-ups regularly
✓ Mark follow-ups as done once completed

### For Admins

✓ Monitor overdue follow-ups
✓ Ensure doctors complete scheduled follow-ups
✓ Use filtering for specific date ranges
✓ Track completion statistics

### Code Quality

✓ All datetime fields properly formatted
✓ Null safety checks before formatting
✓ Role-based access control enforced
✓ Clean exception handling with proper logging
✓ Database connections properly closed

---

## Performance Considerations

### Indexes

The schema includes optimized indexes:
- `idx_appointment`: Fast appointment lookups
- `idx_doctor`: Filter by doctor
- `idx_status`: Filter by status
- `idx_followup_date`: Sort by date
- `idx_pending_followups`: Quick pending queries
- `idx_overdue_followups`: Fast overdue detection

### Query Optimization

```sql
-- Optimized query with proper indexing
SELECT f.*, p.name AS patient_name, d.name AS doctor_name
FROM followups f
LEFT JOIN appointments a ON f.appointment_id = a.appointment_id
LEFT JOIN patients p ON a.patient_id = p.patient_id
LEFT JOIN doctors d ON f.doctor_id = d.doctor_id
WHERE f.doctor_id = %s 
  AND f.status = 'PENDING'
  AND f.followup_date < CURDATE()
ORDER BY f.followup_date ASC;
```

---

## Troubleshooting

### No Follow-Ups Showing

✓ Check if appointments exist and are marked COMPLETED
✓ Verify DOCTOR role sees only their follow-ups
✓ Check filters aren't hiding results

### Overdue Not Showing

✓ Verify `followup_date` is in the past and status is PENDING
✓ Check date format in database
✓ Run overdue query directly in MySQL

### Access Denied

✓ Verify user role (DOCTOR, ADMIN, STAFF)
✓ DOCTOR should only see own appointments
✓ Check `get_user_doctor_id()` returns correct ID

---

## Changelog

**Version 1.0** - February 2026
- Initial release
- Full CRUD for follow-ups
- Role-based access control
- Overdue detection
- Professional SaaS UI
- Database schema with indexes
- Comprehensive documentation
