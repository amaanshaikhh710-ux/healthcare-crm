# Code Reference: Appointment to Invoice Integration

## Quick Code Reference

### 1. Enhanced Appointment List Query

**Location:** `app.py`, line 905-920

**Purpose:** Fetch appointments with invoice status flag

```python
base_query = """
    SELECT 
        a.appointment_id,
        a.lead_id,
        a.doctor_id,
        a.service,
        a.appointment_date,
        a.appointment_time,
        a.status,
        a.notes,
        a.created_at,
        l.name AS patient_name,
        d.name AS doctor_name,
        CASE WHEN i.invoice_id IS NOT NULL THEN 1 ELSE 0 END AS invoice_exists
    FROM appointments a
    LEFT JOIN leads l ON a.lead_id = l.lead_id
    LEFT JOIN doctors d ON a.doctor_id = d.doctor_id
    LEFT JOIN invoices i ON a.appointment_id = i.appointment_id
"""
```

**Key Points:**
- `LEFT JOIN invoices` to get invoice status
- `CASE WHEN i.invoice_id IS NOT NULL THEN 1 ELSE 0 END` to convert to boolean
- Returns all appointment data + invoice_exists flag
- Single query instead of multiple (efficient)

---

### 2. Invoice Exists Flag Processing

**Location:** `app.py`, line 961-963

**Purpose:** Convert database 0/1 to Python boolean

```python
# Convert invoice_exists from 0/1 to boolean
for appt in appointments_list:
    appt['invoice_exists'] = bool(appt.get('invoice_exists', 0))
```

**Why:** 
- Templates work better with Python booleans
- Safe with `.get()` in case key missing
- Default to `False` (0) if missing

---

### 3. Generate Invoice Route Definition

**Location:** `app.py`, line 1075-1092

```python
@app.route('/generate-invoice/<int:appointment_id>')
@login_required
def generate_invoice(appointment_id):
    """
    Generate invoice from a completed appointment.
    
    Security:
    - DOCTOR: Can generate invoice only for their own appointments
    - ADMIN: Can generate invoice for any appointment
    - Appointment must be COMPLETED
    - Invoice must not already exist for this appointment
    """
    user_role = session.get('role')
    user_email = session.get('user')
    
    conn = None
    cursor = None
```

**Route Details:**
- URL parameter: Appointment ID (integer)
- Auth requirement: Must be logged in
- Returns: Redirect (never renders template)

---

### 4. Fetch Appointment with Patient Info

**Location:** `app.py`, line 1104-1122

```python
# ===== STEP 1: Fetch appointment details with JOIN to get patient info =====
fetch_query = """
    SELECT 
        a.appointment_id,
        a.lead_id,
        a.doctor_id,
        a.service,
        a.status,
        l.name AS patient_name
    FROM appointments a
    LEFT JOIN leads l ON a.lead_id = l.lead_id
    WHERE a.appointment_id = %s
"""
cursor.execute(fetch_query, (appointment_id,))
appointment = cursor.fetchone()

# Validate appointment exists
if not appointment:
    flash('Appointment not found.', 'danger')
    return redirect(url_for('appointments'))

# Validate appointment is COMPLETED
if appointment['status'] != 'COMPLETED':
    flash('Invoice can only be generated for COMPLETED appointments.', 'warning')
    return redirect(url_for('appointments'))
```

**Validations:**
1. Check appointment exists
2. Check status is COMPLETED (not SCHEDULED/CANCELLED)
3. Provides clear error messages

---

### 5. DOCTOR Role Security Check

**Location:** `app.py`, line 1130-1145

```python
# ===== STEP 2: Security check - Role-based access =====
if user_role == 'DOCTOR':
    # DOCTOR: Can only generate invoice for their own appointments
    cursor.execute("SELECT doctor_id FROM users WHERE email = %s", (user_email,))
    doctor_data = cursor.fetchone()
    
    if not doctor_data or doctor_data['doctor_id'] != appointment['doctor_id']:
        flash('Access denied. You can only generate invoices for your own appointments.', 'danger')
        return redirect(url_for('appointments'))

elif user_role not in ['ADMIN', 'STAFF']:
    flash('Access denied. Invalid user role.', 'danger')
    return redirect(url_for('appointments'))
```

**Security Logic:**
- DOCTOR: Fetch their doctor_id, compare with appointment's doctor_id
- ADMIN/STAFF: No check, grant access
- Others: Deny access
- Uses parameterized query: `%s` placeholder

---

### 6. Duplicate Invoice Prevention

**Location:** `app.py`, line 1151-1161

```python
# ===== STEP 3: Check if invoice already exists =====
check_query = "SELECT invoice_id FROM invoices WHERE appointment_id = %s"
cursor.execute(check_query, (appointment_id,))
existing_invoice = cursor.fetchone()

if existing_invoice:
    flash('Invoice already generated for this appointment.', 'info')
    return redirect(url_for('invoices'))
```

**Duplicate Prevention:**
1. Query database using appointment_id
2. UNIQUE constraint enforces 1 invoice max
3. If found, show message and redirect
4. No insertion attempt if duplicate detected

---

### 7. Amount Calculation

**Location:** `app.py`, line 1170-1175

```python
# ===== STEP 5: Calculate amounts =====
amount = 2000.00  # Default amount
tax = round(amount * 0.18, 2)  # 18% tax
total_amount = amount + tax
```

**Calculations:**
- Base amount: ₹2,000.00 (hardcoded)
- Tax: 18% = 2000 × 0.18 = ₹360.00
- Total: 2000 + 360 = ₹2,360.00
- `round()` prevents floating-point errors

**To modify:**
```python
amount = 5000.00  # Change base amount
tax_rate = 0.12   # Change tax rate (12% = 0.12)
tax = round(amount * tax_rate, 2)
total_amount = amount + tax
```

---

### 8. Invoice Insert Query

**Location:** `app.py`, line 1181-1209

```python
# ===== STEP 6: Insert invoice into database =====
insert_query = """
    INSERT INTO invoices 
    (appointment_id, patient_id, doctor_id, service, amount, tax, total_amount, status, created_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
"""

cursor.execute(
    insert_query,
    (
        appointment_id,
        patient_id,
        appointment['doctor_id'],
        appointment['service'],
        amount,
        tax,
        total_amount,
        'UNPAID'
    )
)
conn.commit()
```

**Parameterized Query:**
- 8 `%s` placeholders
- All values passed as tuple
- mysql.connector handles escaping
- `NOW()` - MySQL function for timestamp

**Fields Inserted:**
1. `appointment_id` - Links to appointment
2. `patient_id` - From appointment's lead_id
3. `doctor_id` - From appointment data
4. `service` - From appointment data
5. `amount` - Calculated value
6. `tax` - Calculated value
7. `total_amount` - Calculated value
8. `status` - Default 'UNPAID'
9. `created_at` - Auto-generated by MySQL

---

### 9. Logging & Redirect

**Location:** `app.py`, line 1212-1227

```python
# ===== STEP 7: Log success and redirect =====
app.logger.info(
    f"Invoice generated: Appointment_ID={appointment_id}, "
    f"Amount={amount}, Tax={tax}, Total={total_amount}, "
    f"User={user_email}, Role={user_role}"
)

flash(
    f'Invoice generated successfully! Amount: ₹{total_amount:,.2f} (₹{amount:,.2f} + 18% tax ₹{tax:,.2f})',
    'success'
)
return redirect(url_for('invoices'))
```

**Logging:**
- Records invoice creation for audit trail
- Includes: ID, amounts, user, role
- Used for debugging and compliance

**Flash Message:**
- Shows success notification
- Displays amount breakdown
- Currency symbol: ₹ (Rupee)
- Format: `,` for thousands separator
- `.2f` for 2 decimal places

**Redirect:**
- Takes user to invoices page
- Shows newly created invoice

---

### 10. Error Handling Block

**Location:** `app.py`, line 1229-1245

```python
except Error as e:
    if conn:
        try:
            conn.rollback()
        except Exception:
            pass
    app.logger.error(f"Database error in generate_invoice: {e}")
    flash('Error generating invoice. Please try again.', 'danger')
    return redirect(url_for('appointments'))

finally:
    try:
        if cursor:
            cursor.close()
    except Exception:
        pass
    try:
        if conn:
            conn.close()
    except Exception:
        pass
```

**Error Handling:**
- Catches database errors
- Rollbacks failed transaction
- Logs error for debugging
- Shows user-friendly message
- Redirects to appointments

**Resource Cleanup:**
- Finally block ensures cleanup
- Closes cursor if open
- Closes connection if open
- Safe exception handling (no cascading errors)

---

### 11. Template Invoice Button

**Location:** `templates/appointments.html`, line 74-76

```html
{% if appt.status == 'COMPLETED' and not appt.invoice_exists %}
    <a href="{{ url_for('generate_invoice', appointment_id=appt.appointment_id) }}" 
       class="text-xs bg-blue-500 hover:bg-blue-600 text-white px-2 py-1 rounded inline-block"
       title="Generate invoice for this appointment">💰 Invoice</a>
{% endif %}
```

**Template Logic:**
- Condition 1: `appt.status == 'COMPLETED'` - Status check
- Condition 2: `not appt.invoice_exists` - No existing invoice
- Both conditions must be TRUE to show button

**HTML:**
- `url_for('generate_invoice', ...)` - Flask route helper
- `appointment_id=appt.appointment_id` - Pass appointment ID
- `class=...` - Tailwind CSS styling
- `title=...` - Tooltip on hover
- `💰` emoji - Money bag icon

---

### 12. Template Invoice Badge

**Location:** `templates/appointments.html`, line 78-80

```html
{% if appt.status == 'COMPLETED' and appt.invoice_exists %}
    <span class="text-xs bg-gray-300 text-gray-700 px-2 py-1 rounded inline-block"
          title="Invoice already created">✓ Invoice</span>
{% endif %}
```

**Badge Logic:**
- Shows if status COMPLETED AND invoice exists
- Non-clickable span (not a link)
- Gray styling indicates disabled state
- ✓ checkmark indicates completion
- Tooltip shows "Invoice already created"

---

## SQL Queries Summary

| Query | Purpose | Location | Parameterized |
|-------|---------|----------|---|
| SELECT appointments with invoices | List with status | appointed() | ✅ |
| SELECT doctor_id FROM users | Verify DOCTOR | generate_invoice() | ✅ |
| SELECT invoice_id FROM invoices | Check duplicate | generate_invoice() | ✅ |
| INSERT INTO invoices | Create invoice | generate_invoice() | ✅ |

**All queries use `%s` placeholders = SQL injection safe ✅**

---

## Database Field Mappings

```
appointments table:
├── appointment_id → invoices.appointment_id (PK)
├── lead_id → invoices.patient_id (FK)
├── doctor_id → invoices.doctor_id (FK)
├── service → invoices.service
├── status → Used for validation (must be = 'COMPLETED')
└── ...other fields...

leads table:
├── lead_id → Used as patient_id in invoices
├── name → Used as patient_name in display
└── ...other fields...

doctors table:
├── doctor_id → Used in invoices
├── name → Used for display
└── ...other fields...

users table:
├── email → Used for authentication (from session)
├── doctor_id → Used for DOCTOR role verification
└── role → Used for authorization

invoices table:
├── invoice_id (PK)
├── appointment_id (UNIQUE) ← From appointment
├── patient_id ← From leads.lead_id
├── doctor_id ← From appointments.doctor_id
├── service ← From appointments.service
├── amount ← Calculated (2000.00)
├── tax ← Calculated (360.00)
├── total_amount ← Calculated (2360.00)
├── status ← Default 'UNPAID'
└── created_at ← Auto timestamp
```

---

## Common Modifications

### Change Default Invoice Amount
```python
# Location: app.py, line 1150
amount = 5000.00  # Changed from 2000.00
```

### Change Tax Rate
```python
# Location: app.py, line 1151
tax = round(amount * 0.12, 2)  # Changed from 0.18 (12% tax)
```

### Change Default Invoice Status
```python
# Location: app.py, line 1184
'PAID'  # Changed from 'UNPAID'
```

### Add New Flash Message
```python
# Location: Any error scenario
flash('Your custom message here', 'success')  # success/danger/warning/info
```

---

## Function Call Chain

```
User clicks 💰 Invoice button
    ↓
Browser GET /generate-invoice/123
    ↓
Flask routes to generate_invoice(123)
    ↓
@login_required check → Allow if logged in
    ↓
Get user role & email from session
    ↓
Connect to database
    ↓
Step 1: Fetch appointment details
    Query: SELECT from appointments + leads JOIN
    Validate: Exists? Status = COMPLETED?
    ↓
Step 2: Role security check
    If DOCTOR: Verify owns this appointment
    If ADMIN: Grant access
    ↓
Step 3: Duplicate check
    Query: SELECT from invoices WHERE appointment_id
    If exists: Redirect with message
    ↓
Step 4: Calculate amounts
    amount = 2000.00
    tax = 360.00
    total = 2360.00
    ↓
Step 5: Insert invoice
    Query: INSERT into invoices
    Commit transaction
    ↓
Step 6: Log & redirect
    Log: "Invoice generated: ID=123, Amount=2360..."
    Flash: Success message with breakdown
    Redirect: → /invoices page
    ↓
User sees invoices page with new invoice
```

---

## Test SQL Queries

```sql
-- Check if invoice exists for appointment #123
SELECT * FROM invoices WHERE appointment_id = 123;

-- View all invoices with appointment details
SELECT i.invoice_id, i.appointment_id, a.status, 
       i.amount, i.tax, i.total_amount, i.created_at
FROM invoices i
JOIN appointments a ON i.appointment_id = a.appointment_id
ORDER BY i.created_at DESC;

-- Check invoice uniqueness constraint
SHOW INDEXES FROM invoices;
-- Should show: UNIQUE KEY `appointment_id` on (appointment_id)

-- View completed appointments without invoices
SELECT a.appointment_id, l.name, a.service, a.status
FROM appointments a
LEFT JOIN leads l ON a.lead_id = l.lead_id
LEFT JOIN invoices i ON a.appointment_id = i.appointment_id
WHERE a.status = 'COMPLETED' AND i.invoice_id IS NULL;
```

---

## Debugging Tips

**Issue:** Button doesn't appear
```python
# Check 1: Is appointment status COMPLETED?
SELECT appointment_id, status FROM appointments WHERE appointment_id = 123;

# Check 2: Does invoice already exist?
SELECT invoice_id FROM invoices WHERE appointment_id = 123;

# Check 3: Is appointment_id in appointments?
SELECT COUNT(*) FROM appointments WHERE appointment_id = 123;
```

**Issue:** "Access denied" error for DOCTOR
```python
# Check: Does user have doctor_id mapping?
SELECT doctor_id FROM users WHERE email = 'doctor@hospital.com';

# Check: Does appointment belong to this doctor?
SELECT doctor_id FROM appointments WHERE appointment_id = 123;
```

**Issue:** Invoice not created (silent failure)
```python
# Enable logging to see error
# Check: app.logger.error() messages
# Check: Database connection works
python -c "import mysql.connector; conn = mysql.connector.connect(...); print('OK')"
```

---

**Reference Version:** 1.0  
**Last Updated:** February 24, 2026  
**For Questions:** See INVOICE_GENERATION_GUIDE.md or INVOICE_QUICK_START.md
