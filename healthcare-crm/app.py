# ============================================================================
# LeadFlow CRM - Flask Application
# Production-Ready SaaS Architecture
# ============================================================================

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file, Response
import os
from functools import wraps
import psycopg2
from psycopg2 import Error, IntegrityError
import io
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from services.invoice_service import toggle_payment as svc_toggle_payment, get_invoice_by_id
from services.finance_service import get_finance_dashboard, get_doctor_earnings, get_analytics

# PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import random
import datetime
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Use a secure random key for session management

SCHEMA_CACHE = {}
# ============================================================================
# NOTE: All static data removed. System now uses MySQL exclusively.
# ============================================================================

# Referrals Data
REFERRALS_DATA = [
    {'id': 1, 'patient': 'Sarah Johnson', 'referred_by': 'Dr. Smith', 'referred_to': 'Dr. Sharma', 'date': '2024-02-15', 'reason': 'Hair treatment specialist', 'status': 'Pending'},
    {'id': 2, 'patient': 'Michael Brown', 'referred_by': 'Dr. Lee', 'referred_to': 'Dr. Johnson', 'date': '2024-02-10', 'reason': 'Anti-aging specialist', 'status': 'Completed'},
]

# Followups Data
FOLLOWUPS_DATA = [
    {'id': 1, 'patient': 'Sarah Johnson', 'assign_to': 'Dr. Smith', 'date': '2024-02-20', 'notes': 'Check acne improvement', 'status': 'Pending'},
    {'id': 2, 'patient': 'Priya Patel', 'assign_to': 'Dr. Sharma', 'date': '2024-02-18', 'notes': 'Review hair treatment progress', 'status': 'Completed'},
]

# ============= AUTH ROUTES =============

@app.route('/')
def index():
    """Home/Login page"""
    if 'user' in session:
        return redirect(url_for('leads'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user and user['password'] == password:
            session['user'] = user['email']
            session['user_name'] = user['name']
            session['role'] = user['role']
            session['doctor_id'] = user.get('doctor_id')

            return jsonify({'success': True})

        else:
            return jsonify({'success': False, 'message': 'Invalid email or password'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
@app.route('/logout')
def logout():
    """Handle logout"""
    session.clear()
    return redirect(url_for('index'))


# ------------------
# Authentication helpers
# ------------------

def login_required(view_func):
    """Decorator: Require user to be logged in"""
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('index'))
        return view_func(*args, **kwargs)
    return wrapped_view


def role_required(required_role):
    """Decorator: Require specific role (ADMIN, DOCTOR, STAFF)
    
    Usage:
        @app.route('/admin-only')
        @role_required('ADMIN')
        def admin_page():
            return render_template('admin.html')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('index'))
            
            user_role = session.get('role')
            if user_role != required_role:
                flash(f'Access denied. This page requires {required_role} role.', 'danger')
                return redirect(url_for('dashboard'))
            
            return view_func(*args, **kwargs)
        return wrapped_view
    return decorator


@app.context_processor
def inject_user():
    """Inject user data into all templates"""
    return {
        'current_user': session.get('user_name'),
        'user_role': session.get('role'),
        'user_email': session.get('user'),
        'doctor_id': session.get('doctor_id')
    }


# ------------------
# Database connection
# ------------------
def get_db_connection():
    try:
       return psycopg2.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    port=int(os.getenv("DB_PORT", 3306))
)
    except Error:
        raise


# ------------------
# Helper utilities
# ------------------
def get_user_doctor_id(user_email):
    """Return doctor_id for a given user email or None."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT doctor_id FROM users WHERE email = %s LIMIT 1", (user_email,))
        row = cursor.fetchone()
        return row['doctor_id'] if row and row.get('doctor_id') else None
    except Exception:
        app.logger.exception('Error fetching doctor_id for user %s', user_email)
        return None
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def table_columns(table_name, cursor=None, refresh=False):
    """Return a set of available column names for the given table."""
    cache_key = table_name.lower()
    if not refresh and cache_key in SCHEMA_CACHE:
        return SCHEMA_CACHE[cache_key]

    own_conn = None
    own_cursor = None
    try:
        if cursor is None:
            own_conn = get_db_connection()
            own_cursor = own_conn.cursor(dictionary=True)
            cursor = own_cursor
        cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        cols = {row['Field'] for row in cursor.fetchall()}
        SCHEMA_CACHE[cache_key] = cols
        return cols
    except Exception:
        app.logger.exception('Could not inspect schema for table %s', table_name)
        return SCHEMA_CACHE.get(cache_key, set())
    finally:
        if own_cursor:
            try:
                own_cursor.close()
            except Exception:
                pass
        if own_conn:
            try:
                own_conn.close()
            except Exception:
                pass


def has_column(table_name, column_name, cursor=None):
    return column_name in table_columns(table_name, cursor=cursor)


def refresh_table_columns(table_name, cursor=None):
    return table_columns(table_name, cursor=cursor, refresh=True)


def normalize_status(value, default='ACTIVE'):
    """Normalize status values coming from forms to database enum format."""
    normalized = (value or default).strip().upper()
    return normalized or default


def normalize_invoice_type(source=None):
    """Map any invoice source to the exact invoices.invoice_type enum value."""
    normalized_source = (source or '').strip().lower()
    if normalized_source == 'followup':
        return 'FOLLOWUP'
    return 'APPOINTMENT'


def calculate_age_from_dob(dob_value):
    """Convert an HTML date input into an integer age when possible."""
    if not dob_value:
        return None

    try:
        dob = date.fromisoformat(dob_value)
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return max(age, 0)
    except ValueError:
        return None


def parse_datetime_value(value):
    """Normalize MySQL/Python datetime values into a comparable datetime."""
    if not value:
        return None

    if isinstance(value, datetime.datetime):
        return value

    if isinstance(value, date):
        return datetime.datetime.combine(value, datetime.datetime.min.time())

    if isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            return None

        normalized = raw_value.replace('Z', '+00:00')
        for candidate in (normalized, raw_value):
            try:
                return datetime.datetime.fromisoformat(candidate)
            except ValueError:
                continue

        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d'):
            try:
                return datetime.datetime.strptime(raw_value, fmt)
            except ValueError:
                continue

    return None


def calculate_followup_pending_days(last_contacted=None, created_at=None):
    """Return whole days since last_contacted, falling back to created_at."""
    reference_dt = parse_datetime_value(last_contacted) or parse_datetime_value(created_at)
    if not reference_dt:
        return None

    if reference_dt.tzinfo is not None:
        now_dt = datetime.datetime.now(reference_dt.tzinfo)
    else:
        now_dt = datetime.datetime.now()

    delta = now_dt - reference_dt
    return max(delta.days, 0)


def get_lead_followup_state(last_contacted=None, created_at=None):
    """Return lead follow-up metadata for UI and reporting."""
    pending_days = calculate_followup_pending_days(
        last_contacted=last_contacted,
        created_at=created_at,
    )
    if pending_days is None:
        return {
            'days': None,
            'pending': False,
            'label': None,
            'badge_class': '',
        }

    if pending_days == 0:
        label = 'Just contacted' if parse_datetime_value(last_contacted) else 'Today'
        return {
            'days': 0,
            'pending': False,
            'label': label,
            'badge_class': 'bg-emerald-100 text-emerald-800',
        }

    if pending_days >= 15:
        return {
            'days': pending_days,
            'pending': True,
            'label': '15d follow-up pending',
            'badge_class': 'bg-amber-100 text-amber-800',
        }

    return {
        'days': pending_days,
        'pending': False,
        'label': None,
        'badge_class': '',
    }


def get_session_doctor_id():
    """Return the logged-in doctor's id from session or user mapping."""
    doctor_id = session.get('doctor_id')
    if doctor_id:
        return doctor_id
    return get_user_doctor_id(session.get('user'))


def build_patient_scope_clause(cursor, patient_alias='p'):
    """Return SQL fragments for patient visibility based on the current session."""
    user_role = session.get('role')
    if user_role != 'DOCTOR':
        return '', []

    doctor_id = get_session_doctor_id()
    if not doctor_id:
        return f" AND 1 = 0", []

    patient_cols = table_columns('patients', cursor=cursor)
    if 'doctor_id' in patient_cols:
        return f" AND {patient_alias}.doctor_id = %s", [doctor_id]

    return (
        f" AND EXISTS (SELECT 1 FROM appointments a WHERE a.patient_id = {patient_alias}.patient_id AND a.doctor_id = %s)",
        [doctor_id],
    )


def get_active_patient_filter(cursor, patient_alias='p'):
    """Return the active-patient status filter for the current schema."""
    patient_cols = table_columns('patients', cursor=cursor)
    if 'status' in patient_cols and 'case_status' in patient_cols:
        return f"(UPPER({patient_alias}.status) = 'ACTIVE' OR {patient_alias}.case_status = 'ACTIVE')"
    if 'status' in patient_cols:
        return f"UPPER({patient_alias}.status) = 'ACTIVE'"
    return f"{patient_alias}.case_status = 'ACTIVE'"


def ensure_patients_schema(cursor, conn):
    """Backfill required patient columns without requiring manual migration."""
    patient_cols = refresh_table_columns('patients', cursor)
    altered = False

    if 'doctor_id' not in patient_cols:
        cursor.execute("ALTER TABLE patients ADD COLUMN doctor_id INT NULL")
        altered = True

    if 'status' not in patient_cols:
        cursor.execute("ALTER TABLE patients ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'")
        altered = True

    if altered:
        conn.commit()
        refresh_table_columns('patients', cursor, )


def activate_patient_record(cursor, patient_id, doctor_id=None):
    """Mark an existing patient active and attach the doctor when supported."""
    patient_cols = table_columns('patients', cursor=cursor)
    set_parts = []
    params = []

    if 'case_status' in patient_cols:
        set_parts.append("case_status = %s")
        params.append('ACTIVE')

    if 'status' in patient_cols:
        set_parts.append("status = %s")
        params.append('active')

    if 'doctor_id' in patient_cols and doctor_id:
        set_parts.append("doctor_id = %s")
        params.append(doctor_id)

    if not set_parts:
        return

    params.append(patient_id)
    cursor.execute(
        f"UPDATE patients SET {', '.join(set_parts)} WHERE patient_id = %s",
        tuple(params)
    )


def ensure_patient_for_lead(cursor, lead):
    """Return an active patient id for a lead, creating or updating as needed."""
    patient_row = find_patient_by_contact(
        cursor,
        email=(lead.get('email') or '').strip().lower() or None,
        phone=(lead.get('phone') or '').strip() or None,
    )

    if patient_row and patient_row.get('patient_id'):
        patient_id = patient_row['patient_id']
        activate_patient_record(cursor, patient_id, doctor_id=lead.get('assigned_to'))
        return patient_id

    patient_id = create_patient_from_lead(cursor, lead)
    if patient_id:
        activate_patient_record(cursor, patient_id, doctor_id=lead.get('assigned_to'))
    return patient_id


def ensure_followup_invoice_schema(cursor, conn):
    """Add follow-up invoice columns/indexes when missing, without touching existing invoice behavior."""
    invoice_cols = refresh_table_columns('invoices', cursor)
    altered = False

    if 'followup_id' not in invoice_cols:
        cursor.execute("ALTER TABLE invoices ADD COLUMN followup_id INT NULL AFTER appointment_id")
        altered = True

    if 'invoice_type' not in invoice_cols:
        cursor.execute(
            "ALTER TABLE invoices ADD COLUMN invoice_type ENUM('APPOINTMENT','FOLLOWUP') NOT NULL DEFAULT 'APPOINTMENT' AFTER invoice_number"
        )
        altered = True

    if altered:
        cursor.execute("UPDATE invoices SET invoice_type = 'APPOINTMENT' WHERE invoice_type IS NULL OR invoice_type = ''")
        try:
            cursor.execute("CREATE INDEX idx_invoices_followup_id ON invoices(followup_id)")
        except Exception:
            pass
        try:
            cursor.execute("CREATE INDEX idx_invoices_invoice_type ON invoices(invoice_type)")
        except Exception:
            pass
        try:
            conn.commit()
        except Exception:
            pass
        refresh_table_columns('invoices', cursor)


def ensure_followup_invoice_constraints(cursor, conn):
    """Allow invoices.appointment_id to be nullable/non-unique for separate follow-up billing."""
    cursor.execute(
        """
        SELECT COLUMN_TYPE, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'invoices'
          AND COLUMN_NAME = 'appointment_id'
        """
    )
    column_info = cursor.fetchone() or {}
    column_type = column_info.get('COLUMN_TYPE', 'INT')
    is_nullable = column_info.get('IS_NULLABLE') == 'YES'

    if not is_nullable:
        cursor.execute(f"ALTER TABLE invoices MODIFY COLUMN appointment_id {column_type} NULL")

    cursor.execute("SHOW INDEX FROM invoices WHERE Column_name = 'appointment_id'")
    indexes = cursor.fetchall() or []
    for idx in indexes:
        key_name = idx.get('Key_name')
        non_unique = idx.get('Non_unique', 1)
        if key_name and key_name != 'PRIMARY' and non_unique == 0:
            try:
                cursor.execute(f"ALTER TABLE invoices DROP INDEX {key_name}")
            except Exception:
                pass

    try:
        cursor.execute("CREATE INDEX idx_invoices_appointment_id ON invoices(appointment_id)")
    except Exception:
        pass

    try:
        conn.commit()
    except Exception:
        pass


def to_float(value):
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def serialize_invoice_record(invoice):
    """Normalize invoice payloads for templates, JSON, and PDF generation."""
    if not invoice:
        return invoice

    numeric_fields = ['amount', 'tax', 'total_amount', 'paid_amount', 'balance_amount', 'commission_percentage']
    for field in numeric_fields:
        if field in invoice:
            invoice[field] = to_float(invoice.get(field))

    invoice_type = (invoice.get('invoice_type') or 'APPOINTMENT').upper()
    invoice['invoice_type'] = invoice_type
    invoice['invoice_label'] = 'Treatment Invoice' if invoice_type == 'APPOINTMENT' else 'Follow-up Consultation'
    invoice['invoice_badge_class'] = 'bg-blue-100 text-blue-800' if invoice_type == 'APPOINTMENT' else 'bg-green-100 text-green-800'
    invoice['invoice_card_class'] = 'border-l-4 border-blue-500' if invoice_type == 'APPOINTMENT' else 'border-l-4 border-green-500'
    invoice['invoice_icon_bg_class'] = 'bg-blue-100 text-blue-700' if invoice_type == 'APPOINTMENT' else 'bg-green-100 text-green-700'
    invoice['invoice_pdf_title'] = 'TREATMENT INVOICE' if invoice_type == 'APPOINTMENT' else 'FOLLOW-UP INVOICE'
    invoice['reference_summary'] = 'Based on previous treatment' if invoice_type == 'FOLLOWUP' else ''

    created_at = invoice.get('created_at')
    payment_date = invoice.get('payment_date')
    reference_appointment_date = invoice.get('reference_appointment_date')

    invoice['formatted_created_at'] = format_date_value(created_at, '%d-%m-%Y %H:%M') if created_at else 'N/A'
    invoice['formatted_payment_date'] = format_date_value(payment_date, '%d-%m-%Y %H:%M') if payment_date else 'Unpaid'
    invoice['formatted_reference_appointment_date'] = format_date_value(reference_appointment_date, '%d-%m-%Y') if reference_appointment_date else '—'

    for field in ['created_at', 'payment_date', 'reference_appointment_date']:
        if invoice.get(field):
            invoice[field] = json_default(invoice[field])

    return invoice


def json_default(value):
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def json_dumps_safe(payload):
    return json.dumps(payload, default=json_default)


def format_date_value(value, fmt='%d-%m-%Y'):
    if not value:
        return '—'
    try:
        if isinstance(value, (datetime.datetime, datetime.date)):
            return value.strftime(fmt)
        return str(value)
    except Exception:
        return str(value)


def format_time_value(value):
    if not value:
        return '—'
    try:
        if isinstance(value, datetime.timedelta):
            total_seconds = int(value.total_seconds())
            hours = (total_seconds // 3600) % 24
            minutes = (total_seconds % 3600) // 60
            return f'{hours:02d}:{minutes:02d}'
        if isinstance(value, datetime.time):
            return value.strftime('%H:%M')
        value_str = str(value)
        return value_str[:5] if len(value_str) >= 5 else value_str
    except Exception:
        return str(value)


def get_followups_config(cursor):
    cols = table_columns('followups', cursor=cursor)
    return {
        'has_patient_id': 'patient_id' in cols,
        'has_followup_time': 'follow_up_time' in cols,
        'has_next_followup_date': 'next_follow_up_date' in cols,
        'has_next_followup_time': 'next_follow_up_time' in cols,
        'has_completed_at': 'completed_at' in cols,
    }


def update_patient_case_status(cursor, patient_id):
    """Close the case when no pending follow-up remains; otherwise keep it active."""
    if not patient_id or not has_column('patients', 'case_status', cursor):
        return None

    cursor.execute(
        """
        SELECT COUNT(*) AS pending_count
        FROM followups f
        JOIN appointments a ON f.appointment_id = a.appointment_id
        WHERE a.patient_id = %s AND f.status = 'PENDING'
        """,
        (patient_id,)
    )
    pending_count = (cursor.fetchone() or {}).get('pending_count', 0) or 0
    new_case_status = 'CLOSED' if pending_count == 0 else 'ACTIVE'
    cursor.execute(
        "UPDATE patients SET case_status = %s WHERE patient_id = %s",
        (new_case_status, patient_id)
    )
    return new_case_status


def appointment_exists(appointment_id, cursor):
    """Fetch appointment row by id using provided cursor. Returns dict or None."""
    cursor.execute(
        "SELECT appointment_id, patient_id, lead_id, doctor_id, service, appointment_date, appointment_time, status FROM appointments WHERE appointment_id = %s",
        (appointment_id,)
    )
    return cursor.fetchone()


def invoice_exists(appointment_id, cursor):
    cursor.execute("SELECT invoice_id FROM invoices WHERE appointment_id = %s LIMIT 1", (appointment_id,))
    return bool(cursor.fetchone())


def followup_invoice_exists(followup_id, cursor):
    if has_column('invoices', 'invoice_type', cursor) and has_column('invoices', 'followup_id', cursor):
        cursor.execute(
            "SELECT invoice_id FROM invoices WHERE followup_id = %s AND invoice_type = 'FOLLOWUP' LIMIT 1",
            (followup_id,)
        )
    elif has_column('invoices', 'followup_id', cursor):
        cursor.execute("SELECT invoice_id FROM invoices WHERE followup_id = %s LIMIT 1", (followup_id,))
    else:
        return False
    return bool(cursor.fetchone())


def get_next_invoice_number(cursor):
    current_year = datetime.datetime.now().year
    cursor.execute(
        "SELECT MAX(CAST(SUBSTRING(invoice_number, -4) AS UNSIGNED)) AS max_num FROM invoices WHERE invoice_number LIKE %s",
        (f'INV-{current_year}-%',)
    )
    result = cursor.fetchone()
    max_num = result.get('max_num') if result else 0
    return f'INV-{current_year}-{((max_num or 0) + 1):04d}'


def generate_invoice_pdf(invoice_id):
    """Build a professional invoice PDF, save it to disk, and return the file path."""
    inv = get_invoice_by_id(invoice_id)
    if not inv:
        raise ValueError('Invoice not found')
    inv = serialize_invoice_record(inv)

    invoice_num = inv.get('invoice_number') or f"INV-{inv.get('invoice_id')}"
    invoice_type = (inv.get('invoice_type') or 'APPOINTMENT').upper()
    invoice_title = 'FOLLOW-UP INVOICE' if invoice_type == 'FOLLOWUP' else 'TREATMENT INVOICE'

    font_path = os.path.join(app.root_path, 'DejaVuSans.ttf')
    if 'DejaVu' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('DejaVu', font_path))
    if 'DejaVu-Bold' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('DejaVu-Bold', font_path))

    def format_currency(value):
        return f"₹{float(value or 0):,.2f}"

    invoice_dir = os.path.join(app.root_path, 'generated_invoices')
    os.makedirs(invoice_dir, exist_ok=True)
    safe_invoice_num = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in invoice_num)
    file_path = os.path.join(invoice_dir, f"invoice_{safe_invoice_num}.pdf")

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    brand_style = ParagraphStyle(
        'InvoiceBrand',
        parent=styles['Heading1'],
        fontName='DejaVu-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1f2937'),
    )
    title_style = ParagraphStyle(
        'InvoiceMainTitle',
        parent=styles['Heading1'],
        fontName='DejaVu-Bold',
        fontSize=15,
        leading=19,
        alignment=1,
        textColor=colors.HexColor('#1f2937'),
    )
    meta_style = ParagraphStyle(
        'InvoiceMeta',
        parent=styles['BodyText'],
        fontName='DejaVu',
        fontSize=9.5,
        leading=13,
        alignment=2,
        textColor=colors.HexColor('#334155'),
    )
    card_label_style = ParagraphStyle(
        'InvoiceCardLabel',
        parent=styles['BodyText'],
        fontName='DejaVu-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#374151'),
    )
    card_value_style = ParagraphStyle(
        'InvoiceCardValue',
        parent=styles['BodyText'],
        fontName='DejaVu',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#111827'),
    )
    table_cell_style = ParagraphStyle(
        'InvoiceTableCell',
        parent=styles['BodyText'],
        fontName='DejaVu',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#111827'),
    )
    table_amount_style = ParagraphStyle(
        'InvoiceTableAmount',
        parent=table_cell_style,
        alignment=2,
    )
    followup_style = ParagraphStyle(
        'InvoiceFollowup',
        parent=styles['BodyText'],
        fontName='DejaVu',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#374151'),
    )
    footer_style = ParagraphStyle(
        'InvoiceFooter',
        parent=styles['BodyText'],
        fontName='DejaVu',
        fontSize=10,
        leading=14,
        alignment=1,
        textColor=colors.HexColor('#475569'),
        spaceBefore=12,
    )

    elements = []

    header_table = Table(
        [[
            Paragraph('LeadFlow CRM', brand_style),
            Paragraph(invoice_title, title_style),
            Paragraph(
                f"<b>Invoice #:</b> {invoice_num}<br/><b>Date:</b> {inv.get('formatted_created_at', 'N/A')}",
                meta_style,
            ),
        ]],
        colWidths=[2.15 * inch, 2.55 * inch, 1.55 * inch],
    )
    header_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVu'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.22 * inch))

    patient_details = Table(
        [
            [Paragraph('Patient Name', card_label_style), Paragraph(inv.get('patient_name') or 'N/A', card_value_style)],
            [Paragraph('Doctor Name', card_label_style), Paragraph(inv.get('doctor_name') or 'N/A', card_value_style)],
            [Paragraph('Service', card_label_style), Paragraph(inv.get('service') or 'General Consultation', card_value_style)],
        ],
        colWidths=[1.8 * inch, 4.45 * inch],
    )
    patient_details.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F5F5F5')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
        ('INNERGRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVu'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    elements.append(patient_details)
    elements.append(Spacer(1, 0.2 * inch))

    billing_table = Table(
        [
            [Paragraph('Description', table_cell_style), Paragraph('Amount', table_amount_style)],
            [Paragraph('Service', table_cell_style), Paragraph(format_currency(inv.get('amount')), table_amount_style)],
            [Paragraph('Tax', table_cell_style), Paragraph(format_currency(inv.get('tax')), table_amount_style)],
            [Paragraph('TOTAL', table_cell_style), Paragraph(format_currency(inv.get('total_amount')), table_amount_style)],
        ],
        colWidths=[4.6 * inch, 1.65 * inch],
    )
    billing_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, 2), colors.HexColor('#F3F4F6')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#34495E')),
        ('TEXTCOLOR', (0, 3), (-1, 3), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#9ca3af')),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVu'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(billing_table)
    elements.append(Spacer(1, 0.2 * inch))

    payment_table = Table(
        [
            [Paragraph('Payment Status', card_label_style), Paragraph(inv.get('status') or 'UNPAID', card_value_style)],
            [Paragraph('Paid Amount', card_label_style), Paragraph(format_currency(inv.get('paid_amount')), table_amount_style)],
            [Paragraph('Balance', card_label_style), Paragraph(format_currency(inv.get('balance_amount')), table_amount_style)],
        ],
        colWidths=[2.15 * inch, 4.1 * inch],
    )
    payment_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVu'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(payment_table)

    if invoice_type == 'FOLLOWUP':
        notes_text = inv.get('followup_notes') or 'No follow-up notes'
        elements.append(Spacer(1, 0.2 * inch))
        followup_table = Table(
            [
                [Paragraph('Follow-up consultation for previous treatment', followup_style)],
                [Paragraph(f"Reference Appointment: #{inv.get('reference_appointment_id') or 'N/A'}", followup_style)],
                [Paragraph(f"Reference Invoice: {inv.get('reference_invoice_number') or 'N/A'}", followup_style)],
                [Paragraph(f"Notes: {notes_text}", followup_style)],
            ],
            colWidths=[6.25 * inch],
        )
        followup_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVu'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(followup_table)

    elements.append(Spacer(1, 0.24 * inch))
    elements.append(Paragraph('Thank you for choosing our clinic', footer_style))

    doc.build(elements)
    return file_path

def lead_has_appointment(lead_id, cursor):
    cursor.execute("SELECT appointment_id FROM appointments WHERE lead_id = %s LIMIT 1", (lead_id,))
    return bool(cursor.fetchone())


def find_patient_by_contact(cursor, email=None, phone=None):
    """Find an existing patient by non-empty email or phone."""
    conditions = []
    params = []

    if email:
        conditions.append("email = %s")
        params.append(email)
    if phone:
        conditions.append("phone = %s")
        params.append(phone)

    if not conditions:
        return None

    cursor.execute(
        f"SELECT patient_id FROM patients WHERE {' OR '.join(conditions)} LIMIT 1",
        tuple(params)
    )
    return cursor.fetchone()


def create_patient_from_lead(cursor, lead):
    """Create a patient record for a lead without changing the existing schema."""
    patient_cols = table_columns('patients', cursor=cursor)
    insert_columns = ['name', 'phone', 'email']
    placeholders = ['%s', '%s', '%s']
    phone = (lead.get('phone') or '').strip() or None
    email = (lead.get('email') or '').strip().lower() or None
    insert_values = [lead.get('name'), phone, email]

    if 'case_status' in patient_cols:
        insert_columns.append('case_status')
        placeholders.append('%s')
        insert_values.append('ACTIVE')

    if 'status' in patient_cols:
        insert_columns.append('status')
        placeholders.append('%s')
        insert_values.append('active')

    if 'doctor_id' in patient_cols and lead.get('assigned_to'):
        insert_columns.append('doctor_id')
        placeholders.append('%s')
        insert_values.append(lead.get('assigned_to'))

    insert_columns.append('created_at')
    placeholders.append('NOW()')

    cursor.execute(
        f"INSERT INTO patients ({', '.join(insert_columns)}) VALUES ({', '.join(placeholders)})",
        tuple(insert_values)
    )
    return cursor.lastrowid


# ============= DASHBOARD =============

@app.route('/dashboard')
@login_required
def dashboard():
    """Premium SaaS-style dashboard for LeadFlow CRM."""
    conn = None
    cursor = None

    # Safe defaults
    kpi_data = {
        'total_leads': 0,
        'conversion_rate': 0,
        'todays_appointments': 0,
        'total_revenue': 0,
        'pending_followups_15d': 0,
        'pending_followups_2d': 0,
        'scheduled_appointments': 0,
        'completed_appointments': 0,
        'closed_cases': 0,
        'repeat_patients': 0,
        'scraped_leads': 0,
    }
    lead_source_data = []
    conversion_funnel_data = []
    revenue_trend_data = []
    todays_appointments_table = []
    pending_followups_table = []
    recent_activity = []
    doctor_name = "LeadFlow CRM"

    role = session.get("role")
    user_email = session.get("user")
    doctor_id = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # ROLE-BASED SCOPE
        if role == "DOCTOR":
            doctor_id = get_user_doctor_id(user_email)
            if doctor_id:
                cursor.execute("SELECT name FROM doctors WHERE doctor_id = %s", (doctor_id,))
                doc = cursor.fetchone()
                if doc and doc.get('name'):
                    doctor_name = doc['name']

        is_doctor_view = role == "DOCTOR" and doctor_id is not None
        followup_cfg = get_followups_config(cursor)
        from datetime import datetime as dt_now
        today = date.today()
        now = dt_now.now()

        # ------------------- KPI CARDS -------------------
        # Total Leads
        leads_query = "SELECT COUNT(*) AS total FROM leads WHERE status != 'SCRAPED'"
        leads_params = []
        if is_doctor_view:
            leads_query += " AND assigned_to = %s"
            leads_params.append(doctor_id)
        cursor.execute(leads_query, tuple(leads_params))
        kpi_data['total_leads'] = cursor.fetchone().get('total', 0) or 0

        # Conversion Rate
        converted_query = "SELECT COUNT(*) AS total FROM leads WHERE status = 'CONVERTED'"
        converted_params = []
        if is_doctor_view:
            converted_query += " AND assigned_to = %s"
            converted_params.append(doctor_id)
        cursor.execute(converted_query, tuple(converted_params))
        converted_leads = cursor.fetchone().get('total', 0) or 0
        kpi_data['conversion_rate'] = round((converted_leads / kpi_data['total_leads'] * 100), 1) if kpi_data['total_leads'] > 0 else 0
        kpi_data['converted_cases'] = converted_leads

        # Today's Appointments
        appointments_query = "SELECT COUNT(*) AS total FROM appointments WHERE DATE(appointment_date) = CURDATE()"
        appointments_params = []
        if is_doctor_view:
            appointments_query += " AND doctor_id = %s"
            appointments_params.append(doctor_id)
        cursor.execute(appointments_query, tuple(appointments_params))
        kpi_data['todays_appointments'] = cursor.fetchone().get('total', 0) or 0

        # Total Revenue (paid invoices for current month)
        revenue_query = (
            "SELECT COALESCE(SUM(total_amount), 0) AS revenue "
            "FROM invoices "
            "WHERE status = 'PAID' "
            "AND MONTH(COALESCE(payment_date, created_at)) = MONTH(CURDATE()) "
            "AND YEAR(COALESCE(payment_date, created_at)) = YEAR(CURDATE())"
        )
        revenue_params = []
        if is_doctor_view:
            revenue_query += " AND doctor_id = %s"
            revenue_params.append(doctor_id)
        cursor.execute(revenue_query, tuple(revenue_params))
        kpi_data['total_revenue'] = to_float(cursor.fetchone().get('revenue', 0))

        # Leads pending follow-up (15+ day rule with created_at fallback)
        pending_followups_query = (
            "SELECT COUNT(*) AS count FROM leads "
            "WHERE status IN ('NEW', 'CONTACTED') "
            "AND status != 'SCRAPED' "
            "AND COALESCE(last_contacted, created_at) <= DATE_SUB(NOW(), INTERVAL 15 DAY)"
        )
        pending_followups_params = []
        if is_doctor_view:
            pending_followups_query += " AND assigned_to = %s"
            pending_followups_params.append(doctor_id)
        cursor.execute(pending_followups_query, tuple(pending_followups_params))
        kpi_data['pending_followups_15d'] = cursor.fetchone().get('count', 0) or 0

        # Pending Follow-Ups (next 2 days - reminder)
        upcoming_followups_query = (
            "SELECT COUNT(*) AS count FROM followups "
            "WHERE status = 'PENDING' "
            "AND followup_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 2 DAY)"
        )
        upcoming_followups_params = []
        if is_doctor_view:
            upcoming_followups_query += " AND doctor_id = %s"
            upcoming_followups_params.append(doctor_id)
        cursor.execute(upcoming_followups_query, tuple(upcoming_followups_params))
        kpi_data['pending_followups_2d'] = cursor.fetchone().get('count', 0) or 0

        # Scheduled Appointments (next 7 days)
        scheduled_query = (
            "SELECT COUNT(*) AS count FROM appointments "
            "WHERE appointment_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)"
        )
        scheduled_params = []
        if is_doctor_view:
            scheduled_query += " AND doctor_id = %s"
            scheduled_params.append(doctor_id)
        cursor.execute(scheduled_query, tuple(scheduled_params))
        kpi_data['scheduled_appointments'] = cursor.fetchone().get('count', 0) or 0

        # Completed Appointments
        completed_query = "SELECT COUNT(*) AS count FROM appointments WHERE status = 'COMPLETED'"
        completed_params = []
        if is_doctor_view:
            completed_query += " AND doctor_id = %s"
            completed_params.append(doctor_id)
        cursor.execute(completed_query, tuple(completed_params))
        kpi_data['completed_appointments'] = cursor.fetchone().get('count', 0) or 0

        # Closed Cases
        closed_query = (
            "SELECT COUNT(DISTINCT p.patient_id) AS count "
            "FROM patients p "
            "LEFT JOIN appointments a ON p.patient_id = a.patient_id "
            "WHERE p.case_status = 'CLOSED'"
        )
        closed_params = []
        if is_doctor_view:
            closed_query += " AND a.doctor_id = %s"
            closed_params.append(doctor_id)
        cursor.execute(closed_query, tuple(closed_params))
        kpi_data['closed_cases'] = cursor.fetchone().get('count', 0) or 0

        # Repeat Patients (more than one appointment)
        repeat_query = (
            "SELECT COUNT(*) AS count FROM ("
            "    SELECT patient_id FROM appointments WHERE patient_id IS NOT NULL"
            ") t"
        )
        repeat_params = []
        if is_doctor_view:
            repeat_query = (
                "SELECT COUNT(*) AS count FROM ("
                "    SELECT patient_id FROM appointments WHERE patient_id IS NOT NULL AND doctor_id = %s GROUP BY patient_id HAVING COUNT(*) > 1"
                ") t"
            )
            repeat_params.append(doctor_id)
        else:
            repeat_query = (
                "SELECT COUNT(*) AS count FROM ("
                "    SELECT patient_id FROM appointments WHERE patient_id IS NOT NULL GROUP BY patient_id HAVING COUNT(*) > 1"
                ") t"
            )
        cursor.execute(repeat_query, tuple(repeat_params))
        kpi_data['repeat_patients'] = cursor.fetchone().get('count', 0) or 0

        # Scraped Leads Count
        scraped_query = "SELECT COUNT(*) AS count FROM leads WHERE status = 'SCRAPED'"
        cursor.execute(scraped_query)
        kpi_data['scraped_leads'] = cursor.fetchone().get('count', 0) or 0

        # -------------- CHART: LEAD SOURCE BREAKDOWN --------------
        lead_source_query = "SELECT source, COUNT(*) AS count FROM leads WHERE status != 'SCRAPED'"
        lead_source_params = []
        if is_doctor_view:
            lead_source_query += " AND assigned_to = %s"
            lead_source_params.append(doctor_id)
        lead_source_query += " GROUP BY source ORDER BY count DESC"
        cursor.execute(lead_source_query, tuple(lead_source_params))
        lead_source_data = cursor.fetchall()

        # -------------- CHART: APPOINTMENT TREND --------------
        appointment_trend_query = """
            SELECT DATE_FORMAT(appointment_date, '%Y-%m') AS month, COUNT(*) AS count
            FROM appointments
            WHERE appointment_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
        """
        appointment_trend_params = []
        if is_doctor_view:
            appointment_trend_query += " AND doctor_id = %s"
            appointment_trend_params.append(doctor_id)
        appointment_trend_query += " GROUP BY month ORDER BY month"
        cursor.execute(appointment_trend_query, tuple(appointment_trend_params))
        raw_appointment_trend = {row['month']: row['count'] for row in cursor.fetchall()}

        # -------------- CHART: REVENUE TREND --------------
        # Last 6 months
        revenue_trend_query = """
            SELECT DATE_FORMAT(COALESCE(payment_date, created_at), '%Y-%m') AS month,
                   COALESCE(SUM(total_amount), 0) AS revenue
            FROM invoices
            WHERE status = 'PAID'
              AND COALESCE(payment_date, created_at) >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
        """
        revenue_trend_params = []
        if is_doctor_view:
            revenue_trend_query += " AND doctor_id = %s"
            revenue_trend_params.append(doctor_id)
        revenue_trend_query += " GROUP BY month ORDER BY month"
        cursor.execute(revenue_trend_query, tuple(revenue_trend_params))
        raw_revenue_trend = {row['month']: row['revenue'] for row in cursor.fetchall()}

        # Fill last 6 months
        months = []
        for i in range(5, -1, -1):
            month = (now.replace(day=1) - timedelta(days=30*i)).strftime('%Y-%m')
            months.append(month)
        revenue_trend_data = [{'month': m, 'revenue': to_float(raw_revenue_trend.get(m, 0))} for m in months]
        conversion_funnel_data = [{'month': m, 'count': raw_appointment_trend.get(m, 0)} for m in months]

        # -------------- TABLES: TODAY'S APPOINTMENTS --------------
        todays_apps_query = """
            SELECT a.appointment_time, p.name AS patient, d.name AS doctor, a.service
            FROM appointments a
            JOIN patients p ON a.patient_id = p.patient_id
            JOIN doctors d ON a.doctor_id = d.doctor_id
            WHERE DATE(a.appointment_date) = CURDATE()
        """
        todays_apps_params = []
        if is_doctor_view:
            todays_apps_query += " AND a.doctor_id = %s"
            todays_apps_params.append(doctor_id)
        todays_apps_query += " ORDER BY a.appointment_time"
        cursor.execute(todays_apps_query, tuple(todays_apps_params))
        results = cursor.fetchall()
        print("TODAY:", today)
        todays_appointments_table = results

        # -------------- TABLES: PENDING FOLLOW-UPS --------------
        pending_followups_query = """
            SELECT p.name AS patient_name, a.service, f.followup_date AS last_contacted
            FROM followups f
            JOIN appointments a ON f.appointment_id = a.appointment_id
            JOIN patients p ON a.patient_id = p.patient_id
            WHERE f.status = 'PENDING'
        """
        pending_followups_params = []
        if is_doctor_view:
            pending_followups_query += " AND f.doctor_id = %s"
            pending_followups_params.append(doctor_id)
        pending_followups_query += " ORDER BY f.followup_date"
        cursor.execute(pending_followups_query, tuple(pending_followups_params))
        pending_followups_table = cursor.fetchall()

        # ------------------ RECENT ACTIVITY ------------------
        activity_sql = []
        activity_params = []

        visits_activity = (
            "SELECT 'Visit' AS activity, CONCAT('Visit for ', p.name) AS description, v.visit_date AS created_at "
            "FROM visits v "
            "JOIN patients p ON v.patient_id = p.patient_id "
        )
        if is_doctor_view:
            visits_activity += "WHERE v.doctor_id = %s "
            activity_params.append(doctor_id)
        visits_activity += "ORDER BY v.visit_date DESC LIMIT 5"
        activity_sql.append(visits_activity)

        referrals_activity = (
            "SELECT 'Referral' AS activity, CONCAT('Referral: ', p.name, ' → ', d2.name) AS description, r.referral_date AS created_at "
            "FROM referrals r "
            "JOIN visits v ON r.visit_id = v.visit_id "
            "JOIN patients p ON v.patient_id = p.patient_id "
            "JOIN doctors d2 ON r.to_doctor_id = d2.doctor_id "
        )
        if is_doctor_view:
            referrals_activity += "WHERE (r.from_doctor_id = %s OR r.to_doctor_id = %s) "
            activity_params.extend([doctor_id, doctor_id])
        referrals_activity += "ORDER BY r.referral_date DESC LIMIT 5"
        activity_sql.append(referrals_activity)

        followups_activity = (
            "SELECT 'Followup' AS activity, CONCAT('Followup for ', p.name) AS description, f.created_at AS created_at "
            "FROM followups f "
            "JOIN appointments a ON f.appointment_id = a.appointment_id "
            "JOIN patients p ON a.patient_id = p.patient_id "
        )
        if is_doctor_view:
            followups_activity += "WHERE f.doctor_id = %s "
            activity_params.append(doctor_id)
        followups_activity += "ORDER BY f.created_at DESC LIMIT 5"
        activity_sql.append(followups_activity)

        leads_activity = (
            "SELECT 'Lead' AS activity, CONCAT('New lead: ', l.name, ' (', l.source, ')') AS description, l.created_at AS created_at "
            "FROM leads l WHERE l.status != 'SCRAPED'"
        )
        if is_doctor_view:
            leads_activity += " AND l.assigned_to = %s"
            activity_params.append(doctor_id)
        leads_activity += " ORDER BY l.created_at DESC LIMIT 5"
        activity_sql.append(leads_activity)

        union_query = " UNION ALL ".join([f"({q})" for q in activity_sql])
        union_query += " ORDER BY created_at DESC LIMIT 10"
        cursor.execute(union_query, tuple(activity_params))
        recent_activity = cursor.fetchall()

    except Error as e:
        app.logger.error(f'Database error in dashboard: {e}')
        flash('Error loading dashboard. Please try again.', 'danger')

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # JSON serialization with safe handling for dates and decimals
    lead_source_json = json_dumps_safe(lead_source_data)
    conversion_funnel_json = json_dumps_safe(conversion_funnel_data)
    revenue_trend_json = json_dumps_safe(revenue_trend_data)

    return render_template(
        'dashboard.html',
        kpi_data=kpi_data,
        lead_source_json=lead_source_json,
        conversion_funnel_json=conversion_funnel_json,
        revenue_trend_json=revenue_trend_json,
        todays_appointments_table=todays_appointments_table,
        pending_followups_table=pending_followups_table,
        recent_activity=recent_activity,
        doctor_name=doctor_name,
        role=role,
        last_updated=now.strftime('%b %d, %Y %I:%M %p'),
    )


# ============= ANALYTICS PAGES =============
# The following analytics modules have been removed to keep LeadFlow focused
# on the core clinic workflow (Lead Management, Follow-Ups, Appointments and Finance).
# Any remaining charts and analytics are available on the main Dashboard.


@app.route('/follow-ups')
@login_required
def follow_up_analytics():
    """Follow-up analytics and timeline."""
    conn = None
    cursor = None

    stats = {
        'pending': 0,
        'overdue': 0,
        'completed': 0,
        'total': 0,
        'completion_rate': 0,
    }
    timeline = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS cnt FROM followups")
        stats['total'] = cursor.fetchone().get('cnt', 0) or 0

        cursor.execute("SELECT COUNT(*) AS cnt FROM followups WHERE status = 'PENDING'")
        stats['pending'] = cursor.fetchone().get('cnt', 0) or 0

        cursor.execute("SELECT COUNT(*) AS cnt FROM followups WHERE status = 'DONE'")
        stats['completed'] = cursor.fetchone().get('cnt', 0) or 0

        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM followups "
            "WHERE status = 'PENDING' AND followup_date <= DATE_SUB(CURDATE(), INTERVAL 15 DAY)"
        )
        stats['overdue'] = cursor.fetchone().get('cnt', 0) or 0

        stats['completion_rate'] = round((stats['completed'] / stats['total'] * 100), 1) if stats['total'] else 0

        cursor.execute(
            "SELECT f.followup_id, f.followup_date, f.status, f.notes, p.name AS patient_name, d.name AS doctor_name "
            "FROM followups f "
            "LEFT JOIN patients p ON f.patient_id = p.patient_id "
            "LEFT JOIN doctors d ON f.doctor_id = d.doctor_id "
            "ORDER BY f.created_at DESC LIMIT 20"
        )
        timeline = cursor.fetchall() or []

    except Exception as e:
        app.logger.exception('Error loading follow-up analytics: %s', e)
        flash('Error loading follow-up analytics.', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template(
        'followups-analytics.html',
        stats=stats,
        timeline=timeline,
    )


@app.route('/test-db')
def test_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        conn.close()
        return {"status": "success", "tables": tables}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ============= LEADS MANAGEMENT =============

@app.route('/leads')
@login_required
def leads():
    """
    Leads management page with role-based access control.
    
    DOCTOR: Shows only their assigned leads (excluding SCRAPED)
    ADMIN: Shows all leads (excluding SCRAPED)
    """
    conn = None
    cursor = None

    # Filters for the leads view (kept even if DB errors)
    search_query = request.args.get('q', '').strip()
    service_filter = request.args.get('service', '').strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_patients_schema(cursor, conn)
        
        # Get user role from session
        user_role = session.get('role', 'STAFF')
        user_email = session.get('user')

        # Filters for the leads view
        search_query = request.args.get('q', '').strip()
        service_filter = request.args.get('service', '').strip()

        # Base query - Active leads (New + Contacted + Converted) for lead conversion flow
        base_query = """
            SELECT 
                l.lead_id,
                l.name,
                l.phone,
                l.email,
                l.service,
                l.source,
                l.status,
                l.created_at,
                l.last_contacted,
                l.assigned_to,
                d.name AS doctor_name,
                (SELECT COUNT(*) FROM appointments a WHERE a.lead_id = l.lead_id) AS appointment_count
            FROM leads l
            LEFT JOIN doctors d
                ON l.assigned_to = d.doctor_id
            WHERE l.status IN ('NEW','CONTACTED','CONVERTED')
        """

        query_params = []

        if service_filter:
            base_query += " AND l.service LIKE %s"
            query_params.append(f"%{service_filter}%")

        if search_query:
            base_query += " AND (l.name LIKE %s OR l.phone LIKE %s OR l.service LIKE %s OR l.source LIKE %s)"
            q_like = f"%{search_query}%"
            query_params.extend([q_like, q_like, q_like, q_like])

        # Role-based filtering
        if user_role == 'DOCTOR':
            doctor_id = get_session_doctor_id()
            if doctor_id:
                base_query += " AND l.assigned_to = %s"
                query_params.append(doctor_id)
                query = base_query + " ORDER BY l.lead_id DESC"
                cursor.execute(query, tuple(query_params))
            else:
                flash('Doctor ID not found. Please contact administrator.', 'warning')
                leads = []
                return render_template('leads.html', leads=leads, search_query=search_query, service_filter=service_filter)

        elif user_role in ['ADMIN', 'STAFF']:
            query = base_query + " ORDER BY l.lead_id DESC"
            cursor.execute(query, tuple(query_params))

        else:
            flash('Invalid user role. Access denied.', 'danger')
            leads = []
            return render_template('leads.html', leads=leads, search_query=search_query, service_filter=service_filter)

        leads = cursor.fetchall()
        for lead in leads:
            followup_state = get_lead_followup_state(
                last_contacted=lead.get('last_contacted'),
                created_at=lead.get('created_at'),
            )
            lead['followup_pending_days'] = followup_state['days']
            lead['followup_pending'] = 1 if followup_state['pending'] else 0
            lead['followup_label'] = followup_state['label']
            lead['followup_badge_class'] = followup_state['badge_class']
        
    except Error as e:
        app.logger.error(f"Database error in leads route: {e}")
        flash('An error occurred while fetching leads. Please try again.', 'danger')
        leads = []
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    
    return render_template('leads.html', leads=leads, search_query=search_query, service_filter=service_filter)

@app.route('/add-lead', methods=['GET', 'POST'])
@login_required
def add_lead():
    """
    Add new lead with secure role-based assignment.
    
    DOCTOR role: Auto-assign to self, ignore form input
    ADMIN role: Allow assigning to any doctor via dropdown
    """
    # Allowed ENUM values from DB schema
    ALLOWED_SOURCES = {'FACEBOOK', 'GOOGLE', 'INSTAGRAM', 'WEBSITE', 'REFERRAL', 'REFFERAL'}
    ALLOWED_STATUS = {'NEW', 'CONTACTED', 'CONVERTED', 'SCRAPED', 'CLOSED'}
    
    user_role = session.get('role')
    user_email = session.get('user')

    if request.method == 'GET':
        doctors = []
        
        # Only load doctor list for ADMIN users
        if user_role == 'ADMIN':
            conn = None
            cursor = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT doctor_id, name FROM doctors ORDER BY name")
                doctors = cursor.fetchall()
            except Exception as e:
                app.logger.error('Error loading doctors: {}'.format(e))
                flash('Could not load doctors list.', 'danger')
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

        return render_template('add_lead.html', doctors=doctors)

    else:  # POST: collect and validate form data
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip() or None
        email = request.form.get('email', '').strip() or None
        service = request.form.get('service', '').strip() or None
        source = (request.form.get('source') or '').strip().upper()
        status = (request.form.get('status') or '').strip().upper()
        assigned_to = request.form.get('assigned_to', '').strip()
        notes = request.form.get('notes') or None

        # Normalize and protect against ENUM mismatches
        if source not in ALLOWED_SOURCES:
            source = None
        if status not in ALLOWED_STATUS:
            status = 'NEW'

        # Basic required field check
        if not name:
            flash('Name is required.', 'warning')
            return redirect(url_for('add_lead'))

        conn = None
        cursor = None
        assigned_to_val = None

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # ===== SECURE ROLE-BASED ASSIGNMENT LOGIC =====
            if user_role == 'DOCTOR':
                # DOCTOR: Fetch their own doctor_id from users table, ignore form input
                cursor.execute(
                    "SELECT doctor_id FROM users WHERE email = %s AND role = 'DOCTOR'",
                    (user_email,)
                )
                doctor = cursor.fetchone()
                
                if doctor and doctor['doctor_id']:
                    assigned_to_val = doctor['doctor_id']
                else:
                    # Fallback: Doctor account without doctor_id mapping
                    app.logger.warning('Doctor {} has no doctor_id mapping'.format(user_email))
                    flash('Error: Your doctor profile is not properly configured.', 'danger')
                    return redirect(url_for('add_lead'))
            
            elif user_role == 'ADMIN':
                # ADMIN: Use form input with validation
                if assigned_to:
                    try:
                        assigned_to_val = int(assigned_to)
                    except (ValueError, TypeError):
                        assigned_to_val = None
            
            # Insert lead with secure assignment
            query = (
                "INSERT INTO leads (name, phone, email, source, status, service, assigned_to, notes) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            )

            cursor.execute(
                query,
                (name, phone, email, source, status, service, assigned_to_val, notes)
            )
            conn.commit()
            flash('Lead added successfully.', 'success')

            return redirect(url_for('leads'))

        except Error as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            app.logger.error('Database error in add_lead: {}'.format(e))
            flash('Error saving lead to database.', 'danger')
            return redirect(url_for('add_lead'))
        
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            app.logger.error('Unexpected error in add_lead: {}'.format(e))
            flash('An unexpected error occurred.', 'danger')
            return redirect(url_for('add_lead'))

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

@app.route('/scrape-lead/<int:lead_id>', methods=['POST'])
@login_required
def scrape_lead(lead_id):
    """
    Mark a lead as SCRAPED and unassign it from doctor.
    
    Security:
    - DOCTOR: Can only scrape their own assigned leads
    - ADMIN: Can scrape any lead
    """
    user_role = session.get('role')
    user_email = session.get('user')
    
    # Only DOCTOR and ADMIN can scrape leads
    if user_role not in ['DOCTOR', 'ADMIN']:
        flash('Access denied. Only doctors and admins can scrape leads.', 'danger')
        return redirect(url_for('leads'))
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch current lead details
        cursor.execute("SELECT lead_id, assigned_to FROM leads WHERE lead_id = %s", (lead_id,))
        lead = cursor.fetchone()
        
        if not lead:
            flash('Lead not found.', 'danger')
            return redirect(url_for('leads'))
        
        # Security check: DOCTOR can only scrape their own leads
        if user_role == 'DOCTOR':
            cursor.execute("SELECT doctor_id FROM users WHERE email = %s", (user_email,))
            doctor_data = cursor.fetchone()
            
            if not doctor_data or doctor_data['doctor_id'] != lead['assigned_to']:
                flash('Access denied. You can only scrape your own leads.', 'danger')
                return redirect(url_for('leads'))
        
        # Update lead: Set status to SCRAPED and assigned_to to NULL
        update_query = (
            "UPDATE leads "
            "SET status = %s, assigned_to = NULL "
            "WHERE lead_id = %s"
        )
        
        cursor.execute(update_query, ('SCRAPED', lead_id))
        conn.commit()
        
        flash('Lead marked as scraped successfully.', 'success')
        return redirect(url_for('leads'))
    
    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.error(f"Database error in scrape_lead: {e}")
        flash('Error updating lead. Please try again.', 'danger')
        return redirect(url_for('leads'))
    
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


@app.route('/mark-contacted/<int:lead_id>', methods=['POST'])
@login_required
def mark_contacted(lead_id):
    """Mark a lead as CONTACTED and update the last_contacted timestamp."""
    user_role = session.get('role')
    user_email = session.get('user')

    if user_role not in ['DOCTOR', 'ADMIN']:
        flash('Access denied. Only doctors and admins can update lead status.', 'danger')
        return redirect(url_for('leads'))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_patients_schema(cursor, conn)

        cursor.execute("SELECT lead_id, assigned_to FROM leads WHERE lead_id = %s", (lead_id,))
        lead = cursor.fetchone()

        if not lead:
            flash('Lead not found.', 'danger')
            return redirect(url_for('leads'))

        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != lead.get('assigned_to'):
                flash('Access denied. You can only update your own leads.', 'danger')
                return redirect(url_for('leads'))

        cursor.execute(
            "UPDATE leads SET status = %s, last_contacted = NOW() WHERE lead_id = %s",
            ('CONTACTED', lead_id)
        )
        conn.commit()
        flash('Lead marked as contacted.', 'success')

    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.error(f"Database error in mark_contacted: {e}")
        flash('Error updating lead status. Please try again.', 'danger')

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

    return redirect(url_for('leads'))


@app.route('/mark-converted/<int:lead_id>', methods=['POST'])
@login_required
def mark_converted(lead_id):
    """Mark a lead as CONVERTED and update the last_contacted timestamp."""
    user_role = session.get('role')
    user_email = session.get('user')

    if user_role not in ['DOCTOR', 'ADMIN']:
        flash('Access denied. Only doctors and admins can update lead status.', 'danger')
        return redirect(url_for('leads'))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT lead_id, assigned_to FROM leads WHERE lead_id = %s", (lead_id,))
        lead = cursor.fetchone()

        if not lead:
            flash('Lead not found.', 'danger')
            return redirect(url_for('leads'))

        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != lead.get('assigned_to'):
                flash('Access denied. You can only update your own leads.', 'danger')
                return redirect(url_for('leads'))

        # Prevent duplicate conversion/appointment creation
        if lead.get('status') == 'CONVERTED':
            if lead_has_appointment(lead_id, cursor):
                flash('Lead is already converted and appointment was created.', 'info')
                return redirect(url_for('leads'))
            else:
                flash('Lead is already converted. Complete appointment details below.', 'info')
                return redirect(url_for('convert_to_appointment', lead_id=lead_id))

        # Set conversion status and chain to appointment creation form
        cursor.execute(
            "SELECT lead_id, name, phone, email, service, assigned_to, status FROM leads WHERE lead_id = %s",
            (lead_id,)
        )
        lead = cursor.fetchone()
        patient_id = ensure_patient_for_lead(cursor, lead)
        if not patient_id:
            conn.rollback()
            flash('Failed to create patient record for this lead.', 'danger')
            return redirect(url_for('leads'))

        cursor.execute(
            "UPDATE leads SET status = %s, last_contacted = NOW() WHERE lead_id = %s",
            ('CONVERTED', lead_id)
        )
        conn.commit()
        flash('Lead marked as converted. Please schedule appointment now.', 'success')
        return redirect(url_for('convert_to_appointment', lead_id=lead_id))

    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.error(f"Database error in mark_converted: {e}")
        flash('Error updating lead status. Please try again.', 'danger')

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

    return redirect(url_for('leads'))


@app.route('/update-last-contacted/<int:lead_id>', methods=['POST'])
@login_required
def update_last_contacted(lead_id):
    """Update the last_contacted timestamp for a lead."""
    user_role = session.get('role')
    user_email = session.get('user')

    if user_role not in ['DOCTOR', 'ADMIN']:
        flash('Access denied. Only doctors and admins can update leads.', 'danger')
        return redirect(url_for('leads'))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT lead_id, assigned_to FROM leads WHERE lead_id = %s", (lead_id,))
        lead = cursor.fetchone()

        if not lead:
            flash('Lead not found.', 'danger')
            return redirect(url_for('leads'))

        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != lead.get('assigned_to'):
                flash('Access denied. You can only update your own leads.', 'danger')
                return redirect(url_for('leads'))

        cursor.execute(
            "UPDATE leads SET last_contacted = NOW() WHERE lead_id = %s",
            (lead_id,)
        )
        conn.commit()
        flash('Last contacted date updated.', 'success')

    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.error(f"Database error in update_last_contacted: {e}")
        flash('Error updating lead date. Please try again.', 'danger')

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

    return redirect(url_for('leads'))


@app.route('/reactivate-lead/<int:lead_id>', methods=['POST'])
@login_required
def reactivate_lead(lead_id):
    """Re-activate a scraped lead and move it back into active leads."""
    user_role = session.get('role')
    user_email = session.get('user')

    if user_role not in ['DOCTOR', 'ADMIN']:
        flash('Access denied. Only doctors and admins can update leads.', 'danger')
        return redirect(url_for('leads'))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT lead_id, assigned_to FROM leads WHERE lead_id = %s", (lead_id,))
        lead = cursor.fetchone()

        if not lead:
            flash('Lead not found.', 'danger')
            return redirect(url_for('leads'))

        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id:
                flash('Doctor profile is not configured.', 'danger')
                return redirect(url_for('leads'))
            assigned_to = doctor_id
        else:
            assigned_to = lead.get('assigned_to')

        cursor.execute(
            "UPDATE leads SET status = %s, assigned_to = %s, last_contacted = NOW() WHERE lead_id = %s",
            ('NEW', assigned_to, lead_id)
        )
        conn.commit()
        flash('Lead reactivated and moved back into active leads.', 'success')

    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.error(f"Database error in reactivate_lead: {e}")
        flash('Error reactivating lead. Please try again.', 'danger')

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

    return redirect(url_for('scraped_leads'))


@app.route('/scraped-leads')
@login_required
def scraped_leads():
    """
    Scraped leads page with role-based access.
    
    ADMIN: Show all scraped leads
    DOCTOR: Show all scraped leads (accessible to any doctor for reference)
    """
    user_role = session.get('role')
    user_email = session.get('user')
    
    # Only ADMIN and DOCTOR can view scraped leads
    if user_role not in ['ADMIN', 'DOCTOR']:
        flash('Access denied. Only doctors and admins can view scraped leads.', 'danger')
        return redirect(url_for('leads'))
    
    conn = None
    cursor = None
    service_filter = request.args.get('service', '').strip()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query for scraped leads
        query = (
            "SELECT "
            "  lead_id, name, phone, email, service, source, created_at "
            "FROM leads "
            "WHERE status = 'SCRAPED'"
        )
        
        params = []
        
        # Optional service filter
        if service_filter:
            query += " AND service LIKE %s"
            params.append(f"%{service_filter}%")
        
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, params)
        leads = cursor.fetchall()
        
    except Error as e:
        app.logger.error(f"Database error in scraped_leads: {e}")
        flash('An error occurred while fetching scraped leads.', 'danger')
        leads = []
    
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
    
    return render_template('scraped-leads.html', leads=leads, service_filter=service_filter)



@app.route('/generate-leads', methods=['GET', 'POST'])
@login_required
def generate_leads():
    """Generate 20 random leads and insert into the `leads` table.

    Uses only these columns: name, phone, email, source, status, assigned_to, service
    Doctor ids are fetched from the `doctors` table and assigned randomly.
    All DB operations use parameterized queries and proper error handling.
    Returns JSON with success status.
    """
    ALLOWED_SOURCES = ["FACEBOOK", "GOOGLE", "INSTAGRAM", "WEBSITE", "REFFERAL"]
    ALLOWED_STATUS = ["NEW", "CONTACTED", "CONVERTED", "CLOSED"]
    SAMPLE_SERVICES = [
        'Acne Treatment', 'Hair Fall Control', 'Anti-Aging', 'Eczema Treatment', 'Psoriasis Care',
        'Skin Whitening', 'Body Contouring', 'Laser Hair Removal'
    ]
    FIRST_NAMES = ['Alex', 'Sam', 'Priya', 'Aisha', 'Carlos', 'Lina', 'Noah', 'Maya', 'Arjun', 'Sofia']
    LAST_NAMES = ['Khan', 'Sharma', 'Patel', 'Garcia', 'Lee', 'Singh', 'Brown', 'Davis', 'Mehta', 'Roy']

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch doctor ids for assignment
        cursor.execute("SELECT doctor_id FROM doctors")
        rows = cursor.fetchall()
        doctor_ids = [r[0] for r in rows] if rows else []

        leads_to_insert = []
        for _ in range(20):
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            # simple email and phone generation
            email = (name.replace(' ', '').lower() + str(random.randint(10,999)) + '@example.com')
            phone = ''.join(str(random.randint(0, 9)) for _ in range(10))
            source = random.choice(ALLOWED_SOURCES)
            status = random.choice(ALLOWED_STATUS)
            service = random.choice(SAMPLE_SERVICES)
            assigned = random.choice(doctor_ids) if doctor_ids else None

            leads_to_insert.append((name, phone, email, source, status, assigned, service))

        insert_query = (
            "INSERT INTO leads (name, phone, email, source, status, assigned_to, service)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )

        cursor.executemany(insert_query, leads_to_insert)
        conn.commit()

        return jsonify({"success": True, "message": "20 leads generated"})

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"success": False, "error": str(e)})

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

# ============= PATIENTS MANAGEMENT =============

@app.route('/patients')
@login_required
def patients():
    """Patients management page - Shows only ACTIVE patients."""
    conn = None
    cursor = None
    patients_list = []
    doctors_list = []
    user_role = session.get('role')
    stats = {
        'total_patients': 0,
        'recent_patients': 0,
        'closed_patients': 0
    }
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_patients_schema(cursor, conn)
        active_filter = get_active_patient_filter(cursor, patient_alias='p')

        # Base query for active patients. Keep the page sourced from patients,
        # not appointments, so newly converted leads appear immediately.
        query = f"""
            SELECT
                p.patient_id,
                p.name,
                p.phone,
                p.email,
                p.problem_description AS medical_history,
                p.case_status,
                p.created_at
            FROM patients p
            WHERE {active_filter}
        """
        params = []
        scope_clause, scope_params = build_patient_scope_clause(cursor, patient_alias='p')
        query += scope_clause
        params.extend(scope_params)

        query += " ORDER BY p.name ASC"

        cursor.execute(query, params)
        patients_list = cursor.fetchall()
        stats['total_patients'] = len(patients_list)

        # Count recent patients (added in last 30 days)
        recent_query = f"""
            SELECT COUNT(*) as count FROM patients p
            WHERE {active_filter}
              AND p.created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        """
        recent_params = []
        recent_scope_clause, recent_scope_params = build_patient_scope_clause(cursor, patient_alias='p')
        recent_query += recent_scope_clause
        recent_params.extend(recent_scope_params)

        cursor.execute(recent_query, recent_params)
        result = cursor.fetchone()
        stats['recent_patients'] = result['count'] if result else 0

        # Count closed cases
        closed_query = """
            SELECT COUNT(*) as count FROM patients p
            WHERE p.case_status = 'CLOSED'
        """
        closed_params = []
        closed_scope_clause, closed_scope_params = build_patient_scope_clause(cursor, patient_alias='p')
        closed_query += closed_scope_clause
        closed_params.extend(closed_scope_params)

        cursor.execute(closed_query, closed_params)
        result = cursor.fetchone()
        stats['closed_patients'] = result['count'] if result else 0

        # Fetch doctors for assignment dropdown
        if user_role == 'ADMIN':
            cursor.execute("SELECT doctor_id, name FROM doctors ORDER BY name")
            doctors_list = cursor.fetchall()

    except Error as e:
        app.logger.error(f'Database error in patients route: {e}')
        flash('Error loading patients', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template('patients.html', patients=patients_list, doctors=doctors_list, **stats)

@app.route('/add-patient', methods=['GET', 'POST'])
@login_required
def add_patient():
    """Add new patient to database"""
    user_role = session.get('role')
    session_doctor_id = get_session_doctor_id() if user_role == 'DOCTOR' else None

    if request.method == 'GET':
        conn = None
        cursor = None
        doctors_list = []

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            ensure_patients_schema(cursor, conn)
            if user_role == 'ADMIN':
                cursor.execute("SELECT doctor_id, name FROM doctors WHERE status = 'ACTIVE' ORDER BY name")
                doctors_list = cursor.fetchall()
        except Error as e:
            app.logger.error(f'Database error fetching doctors: {e}')
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return render_template('add-patient.html', doctors=doctors_list)
    else:
        # POST: Insert new patient
        print("[DEBUG] Route hit: /add-patient [POST]")
        print(f"[DEBUG] Incoming form data: {request.form.to_dict()}")
        app.logger.info('Route hit: /add-patient [POST]')
        app.logger.info('Incoming form data for add_patient: %s', request.form.to_dict())

        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip() or None
        email = request.form.get('email', '').strip().lower() or None
        problem_description = request.form.get('problem', '').strip() or None
        form_doctor_id = (request.form.get('doctor_id') or request.form.get('doctor') or '').strip() or None
        selected_doctor_id = session_doctor_id if user_role == 'DOCTOR' else form_doctor_id
        dob = request.form.get('dob', '').strip()
        age = calculate_age_from_dob(dob)

        if not name or not email or not phone or not selected_doctor_id:
            flash('Name, email, phone, and assigned doctor are required.', 'warning')
            return redirect(url_for('add_patient'))

        if dob and age is None:
            flash('Invalid date of birth.', 'warning')
            return redirect(url_for('add_patient'))

        conn = None
        cursor = None

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            ensure_patients_schema(cursor, conn)
            print('[DEBUG] add_patient: database connection established')
            app.logger.info('add_patient: database connection established')

            cursor.execute(
                "SELECT doctor_id, status FROM doctors WHERE doctor_id = %s LIMIT 1",
                (selected_doctor_id,)
            )
            doctor = cursor.fetchone()
            if not doctor:
                flash('Selected doctor does not exist.', 'danger')
                return redirect(url_for('add_patient'))
            if normalize_status(doctor.get('status')) != 'ACTIVE':
                flash('Selected doctor is inactive.', 'danger')
                return redirect(url_for('add_patient'))

            if email:
                cursor.execute("SELECT patient_id FROM patients WHERE email = %s LIMIT 1", (email,))
                if cursor.fetchone():
                    flash('A patient with this email already exists.', 'danger')
                    return redirect(url_for('add_patient'))

            patient_cols = table_columns('patients', cursor=cursor)
            insert_columns = ['name', 'age', 'phone', 'email', 'problem_description']
            insert_placeholders = ['%s', '%s', '%s', '%s', '%s']
            insert_values = [name, age, phone, email, problem_description]

            if 'case_status' in patient_cols:
                insert_columns.append('case_status')
                insert_placeholders.append('%s')
                insert_values.append('ACTIVE')

            if 'status' in patient_cols:
                insert_columns.append('status')
                insert_placeholders.append('%s')
                insert_values.append('ACTIVE')

            if 'doctor_id' in patient_cols:
                insert_columns.append('doctor_id')
                insert_placeholders.append('%s')
                insert_values.append(selected_doctor_id)

            insert_columns.append('created_at')
            insert_placeholders.append('NOW()')

            insert_query = (
                f"INSERT INTO patients ({', '.join(insert_columns)}) "
                f"VALUES ({', '.join(insert_placeholders)})"
            )

            print(f"[DEBUG] Executing patient insert: {insert_query} | values={insert_values}")
            app.logger.info('Executing patient insert for email=%s', email)
            cursor.execute(insert_query, tuple(insert_values))
            conn.commit()
            print(f"[DEBUG] add_patient: insert committed successfully, patient_id={cursor.lastrowid}")
            app.logger.info('add_patient: insert committed successfully, patient_id=%s', cursor.lastrowid)

            app.logger.info(f'New patient {name} added by user {session.get("user")}')
            flash('Patient added successfully!', 'success')
            return redirect(url_for('patients'))

        except IntegrityError as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"[ERROR] add_patient integrity error: {e}")
            app.logger.exception('Integrity error in add_patient: %s', e)
            if getattr(e, 'errno', None) == 1062:
                flash('A patient with this email already exists.', 'danger')
            else:
                flash('Could not add patient because of a database constraint.', 'danger')
            return redirect(url_for('add_patient'))

        except Error as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"[ERROR] add_patient database error: {e}")
            app.logger.exception(f'Database error in add_patient: {e}')
            flash('Error adding patient. Please try again.', 'danger')
            return redirect(url_for('add_patient'))

        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"[ERROR] add_patient unexpected error: {e}")
            app.logger.exception('Unexpected error in add_patient: %s', e)
            flash('Unexpected error adding patient. Please try again.', 'danger')
            return redirect(url_for('add_patient'))

        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

@app.route('/toggle-case/<int:patient_id>', methods=['POST'])
@login_required
def toggle_case(patient_id):
    """Toggle patient case status between ACTIVE and CLOSED.
    
    Logic:
    - ACTIVE → CLOSED
    - CLOSED → ACTIVE
    - Data is never deleted, only status is updated
    """
    user_role = session.get('role')
    user_email = session.get('user')
    
    if user_role not in ['DOCTOR', 'ADMIN', 'STAFF']:
        flash('Access denied.', 'danger')
        return redirect(url_for('patients'))
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch current case status
        query = "SELECT patient_id, case_status, name FROM patients WHERE patient_id = %s"
        params = [patient_id]
        scope_clause, scope_params = build_patient_scope_clause(cursor, patient_alias='patients')
        query += scope_clause
        params.extend(scope_params)
        cursor.execute(query, tuple(params))
        patient = cursor.fetchone()
        
        if not patient:
            flash('Patient not found.', 'danger')
            return redirect(url_for('patients'))
        
        current_status = patient.get('case_status', 'ACTIVE')
        patient_name = patient.get('name', 'Unknown')
        
        # Toggle status
        if current_status == 'ACTIVE':
            new_status = 'CLOSED'
            action_text = 'closed'
        elif current_status == 'CLOSED':
            new_status = 'ACTIVE'
            action_text = 'reopened'
        else:
            flash('Invalid case status.', 'danger')
            return redirect(url_for('patients'))
        
        # Update case status
        update_query = "UPDATE patients SET case_status = %s WHERE patient_id = %s"
        cursor.execute(update_query, (new_status, patient_id))
        conn.commit()
        
        app.logger.info('Patient %s (ID: %s) case %s by user %s', patient_name, patient_id, action_text, user_email)
        flash(f'Patient case {action_text} successfully!', 'success')
        
        # Redirect to appropriate page
        if new_status == 'CLOSED':
            return redirect(url_for('closed_cases'))
        else:
            return redirect(url_for('patients'))
    
    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.exception('Database error in toggle_case: %s', e)
        flash('Error updating case status. Please try again.', 'danger')
        return redirect(url_for('patients'))
    
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

# ============= DOCTORS MANAGEMENT =============

@app.route('/doctors')
@login_required
def doctors():
    """Doctors management page with role-based visibility and search.
    
    ADMIN: See all ACTIVE doctors
    DOCTOR: See only own doctor record (matched by email)
    STAFF: See all ACTIVE doctors
    
    Backend:
    - Fetches: doctor_id, name, specialization, experience, phone, email, availability, status
    - Filters by status = 'ACTIVE'
    - Search by name or specialization
    - Orders by name ASC
    """
    user_role = session.get('role')
    user_email = session.get('user')
    
    # Get search query from request args
    search_query = request.args.get('search', '').strip()
    
    conn = None
    cursor = None
    doctors_list = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Base query - select all required fields and filter by ACTIVE status
        base_query = """
            SELECT 
                doctor_id,
                name,
                specialization,
                experience,
                phone,
                email,
                availability,
                status
            FROM doctors
            WHERE status = 'ACTIVE'
        """
        
        params = []
        
        if user_role == 'ADMIN' or user_role == 'STAFF':
            # Show all ACTIVE doctors for ADMIN and STAFF
            query = base_query
            
            # Apply search filter if provided
            if search_query:
                query += " AND (name LIKE %s OR specialization LIKE %s)"
                params.append(f"%{search_query}%")
                params.append(f"%{search_query}%")
            
            query += " ORDER BY name ASC"
            cursor.execute(query, params)
            doctors_list = cursor.fetchall()
        
        elif user_role == 'DOCTOR':
            # Show only the doctor record for this logged-in doctor
            # Match by email through users table
            query = """
                SELECT 
                    d.doctor_id,
                    d.name,
                    d.specialization,
                    d.experience,
                    d.phone,
                    d.email,
                    d.availability,
                    d.status
                FROM doctors d
                WHERE d.status = 'ACTIVE' 
                  AND d.email = %s
            """
            cursor.execute(query, (user_email,))
            doctors_list = cursor.fetchall()
        
        else:
            flash('Invalid user role.', 'danger')
            doctors_list = []
    
    except Error as e:
        app.logger.error(f'Database error in doctors route: {e}')
        flash('Error loading doctors', 'danger')
        doctors_list = []
    
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    
    return render_template('doctors.html', doctors=doctors_list, search_query=search_query, user_role=user_role)

@app.route('/add-doctor', methods=['GET', 'POST'])
@role_required('ADMIN')
def add_doctor():
    """Add new doctor - ADMIN ONLY
    
    If non-ADMIN tries to access, the @role_required decorator will
    redirect them to dashboard with an error message.
    """
    if request.method == 'POST':
        print("[DEBUG] Route hit: /add-doctor [POST]")
        print(f"[DEBUG] Incoming form data: {request.form.to_dict()}")
        app.logger.info('Route hit: /add-doctor [POST]')
        app.logger.info('Incoming form data for add_doctor: %s', request.form.to_dict())

        name = request.form.get('name', '').strip()
        specialization = request.form.get('specialty', '').strip() or None
        experience_raw = request.form.get('experience', '').strip()
        phone = request.form.get('phone', '').strip() or None
        email = request.form.get('email', '').strip().lower() or None
        availability = request.form.get('availability', '').strip() or None
        doctor_status = normalize_status(request.form.get('status'), default='ACTIVE')
        user_status = doctor_status if doctor_status in ['ACTIVE', 'INACTIVE'] else 'ACTIVE'

        if not name or not specialization or not experience_raw or not phone or not email:
            flash('Name, specialty, experience, phone, and email are required.', 'warning')
            return redirect(url_for('add_doctor'))

        try:
            experience = int(experience_raw)
            if experience < 0:
                raise ValueError
        except ValueError:
            flash('Experience must be a valid non-negative number.', 'warning')
            return redirect(url_for('add_doctor'))

        conn = None
        cursor = None

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            print('[DEBUG] add_doctor: database transaction started')
            app.logger.info('add_doctor: database transaction started')

            cursor.execute("SELECT doctor_id FROM doctors WHERE email = %s LIMIT 1", (email,))
            if cursor.fetchone():
                conn.rollback()
                flash('A doctor with this email already exists.', 'danger')
                return redirect(url_for('add_doctor'))

            cursor.execute("SELECT user_id FROM users WHERE email = %s LIMIT 1", (email,))
            if cursor.fetchone():
                conn.rollback()
                flash('A user with this email already exists.', 'danger')
                return redirect(url_for('add_doctor'))

            doctor_query = (
                "INSERT INTO doctors (name, specialization, experience, phone, email, availability, status, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())"
            )
            doctor_values = (name, specialization, experience, phone, email, availability, doctor_status)
            print(f"[DEBUG] Executing doctor insert: {doctor_query} | values={doctor_values}")
            app.logger.info('Executing doctor insert for email=%s', email)
            cursor.execute(doctor_query, doctor_values)
            doctor_id = cursor.lastrowid

            temporary_password = f"Temp@{doctor_id}{phone[-4:] if phone else 'Doc'}"
            user_query = (
                "INSERT INTO users (name, email, password, role, status, doctor_id, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, NOW())"
            )
            user_values = (name, email, temporary_password, 'DOCTOR', user_status, doctor_id)
            print(f"[DEBUG] Executing user insert: {user_query} | values={(name, email, '***', 'DOCTOR', user_status, doctor_id)}")
            app.logger.info('Executing linked user insert for doctor_id=%s', doctor_id)
            cursor.execute(user_query, user_values)

            conn.commit()
            print(f"[DEBUG] add_doctor: inserts committed successfully, doctor_id={doctor_id}")
            app.logger.info('add_doctor: inserts committed successfully, doctor_id=%s', doctor_id)

            # Display credentials in a confirmation page
            credentials = {
                'name': name,
                'email': email,
                'password': temporary_password,
                'specialization': specialization,
                'phone': phone
            }
            return render_template('doctor_credentials.html', credentials=credentials)

        except IntegrityError as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"[ERROR] add_doctor integrity error: {e}")
            app.logger.exception('Integrity error in add_doctor: %s', e)
            if getattr(e, 'errno', None) == 1062:
                flash('A doctor or user with this email already exists.', 'danger')
            else:
                flash('Could not add doctor because of a database constraint.', 'danger')
            return redirect(url_for('add_doctor'))

        except Error as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"[ERROR] add_doctor database error: {e}")
            app.logger.exception('Database error in add_doctor: %s', e)
            flash('Error adding doctor. Please try again.', 'danger')
            return redirect(url_for('add_doctor'))

        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"[ERROR] add_doctor unexpected error: {e}")
            app.logger.exception('Unexpected error in add_doctor: %s', e)
            flash('Unexpected error adding doctor. Please try again.', 'danger')
            return redirect(url_for('add_doctor'))

        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    return render_template('add-doctor.html')

# ============= APPOINTMENTS =============

@app.route('/create-appointment/<int:lead_id>', methods=['GET', 'POST'])
@login_required
def convert_to_appointment(lead_id):
    """
    Create an appointment from a lead using a clean transaction lifecycle.

    Rules:
    - Uses a fresh DB connection per request path
    - Uses patient_id, never patient_name, in appointments
    - Uses doctor_id from the current session
    - Commits on success, rolls back on failure
    """
    user_role = session.get('role')
    session_doctor_id = get_session_doctor_id()

    if request.method == 'GET':
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            ensure_patients_schema(cursor, conn)

            cursor.execute(
                "SELECT lead_id, name, phone, email, service, assigned_to, status FROM leads WHERE lead_id = %s",
                (lead_id,)
            )
            lead = cursor.fetchone()
            if not lead:
                flash('Lead not found.', 'danger')
                return redirect(url_for('leads'))

            # Security check for DOCTOR role
            if user_role == 'DOCTOR':
                if not session_doctor_id or session_doctor_id != lead.get('assigned_to'):
                    flash('Access denied. You can only create appointments for your own leads.', 'danger')
                    return redirect(url_for('leads'))

            # Check doctor assignment exists
            if not lead.get('assigned_to'):
                flash('Lead is not assigned to any doctor. Please assign doctor before converting.', 'warning')
                return redirect(url_for('leads'))

            cursor.execute("SELECT doctor_id, name FROM doctors WHERE doctor_id = %s", (lead['assigned_to'],))
            doctor = cursor.fetchone()
            if not doctor:
                flash('Assigned doctor not found. Please contact admin.', 'danger')
                return redirect(url_for('leads'))

            # Prevent duplicate appointment creation from same lead
            if lead_has_appointment(lead_id, cursor):
                flash('Appointment already exists for this lead.', 'info')
                return redirect(url_for('leads'))

            return render_template('create-appointment.html', lead=lead, doctor=doctor)
        except Error as e:
            print("MySQL error in create appointment GET:", e)
            app.logger.exception('Database error in convert_to_appointment GET for lead %s: %s', lead_id, e)
            flash(f'Error loading appointment form: {e}', 'danger')
            return redirect(url_for('leads'))
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    patient_name = request.form.get('patient_name', '').strip() or None
    patient_phone = request.form.get('patient_phone', '').strip() or None
    service = request.form.get('service', '').strip() or None
    appointment_date = request.form.get('appointment_date', '').strip()
    appointment_time = request.form.get('appointment_time', '').strip()
    notes = request.form.get('notes', '').strip() or None

    if not session_doctor_id:
        flash('Doctor session not found. Please log in again.', 'danger')
        return redirect(url_for('leads'))

    if not appointment_date or not appointment_time:
        flash('Appointment date and time are required.', 'warning')
        return redirect(url_for('convert_to_appointment', lead_id=lead_id))

    try:
        datetime.date.fromisoformat(appointment_date)
    except ValueError:
        flash('Appointment date must be a valid date.', 'warning')
        return redirect(url_for('convert_to_appointment', lead_id=lead_id))

    try:
        datetime.time.fromisoformat(appointment_time)
    except ValueError:
        flash('Appointment time must be a valid time.', 'warning')
        return redirect(url_for('convert_to_appointment', lead_id=lead_id))

    conn = None
    cursor = None
    patient_id = None
    doctor_id = session_doctor_id

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_patients_schema(cursor, conn)

        cursor.execute(
            "SELECT lead_id, name, phone, email, service, assigned_to, status FROM leads WHERE lead_id = %s",
            (lead_id,)
        )
        lead = cursor.fetchone()
        if not lead:
            raise ValueError('Lead not found.')

        if user_role == 'DOCTOR' and doctor_id != lead.get('assigned_to'):
            raise ValueError('Access denied. You can only create appointments for your own leads.')

        cursor.execute("SELECT doctor_id FROM doctors WHERE doctor_id = %s", (doctor_id,))
        if not cursor.fetchone():
            raise ValueError('Doctor does not exist. Please log in again.')

        if lead_has_appointment(lead_id, cursor):
            flash('An appointment already exists for this lead. No duplicate created.', 'info')
            return redirect(url_for('appointments'))

        patient_name = patient_name or (lead.get('name') or '').strip() or None
        patient_phone = patient_phone or (lead.get('phone') or '').strip() or None
        service = service or (lead.get('service') or '').strip() or None
        patient_lookup_email = (lead.get('email') or '').strip().lower() or None

        if not service:
            raise ValueError('Service is required before creating an appointment for this lead.')

        patient_row = find_patient_by_contact(
            cursor,
            email=patient_lookup_email,
            phone=patient_phone,
        )

        if not patient_row and patient_name:
            cursor.execute(
                "SELECT patient_id FROM patients WHERE name = %s ORDER BY patient_id DESC LIMIT 1",
                (patient_name,)
            )
            patient_row = cursor.fetchone()

        if patient_row and patient_row.get('patient_id'):
            patient_id = patient_row['patient_id']
            activate_patient_record(cursor, patient_id, doctor_id=doctor_id)
        else:
            # Use the same transaction for lead -> patient -> appointment.
            lead_for_patient = dict(lead)
            lead_for_patient['assigned_to'] = doctor_id
            patient_id = ensure_patient_for_lead(cursor, lead_for_patient)

        if not patient_id:
            raise ValueError('Patient record could not be created.')

        cursor.execute("SELECT patient_id FROM patients WHERE patient_id = %s", (patient_id,))
        if not cursor.fetchone():
            raise ValueError(f'Patient ID {patient_id} does not exist in patients table.')

        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'appointments'
            """
        )
        appointment_columns = {row['COLUMN_NAME'] for row in cursor.fetchall()}
        required_columns = {
            'patient_id',
            'doctor_id',
            'service',
            'appointment_date',
            'appointment_time',
            'status',
        }
        missing_columns = sorted(required_columns - appointment_columns)
        if missing_columns:
            raise ValueError(
                f"Appointments table is missing required columns: {', '.join(missing_columns)}"
            )

        debug_payload = {
            'lead_id': lead_id,
            'patient_id': patient_id,
            'doctor_id': doctor_id,
            'service': service,
            'appointment_date': appointment_date,
            'appointment_time': appointment_time,
        }
        print("APPOINTMENT INSERT VALUES:", debug_payload)
        app.logger.info('Creating appointment with values: %s', debug_payload)

        cursor.execute(
            """
            INSERT INTO appointments
                (lead_id, patient_id, doctor_id, service, appointment_date, appointment_time, status, notes)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (lead_id, patient_id, doctor_id, service, appointment_date, appointment_time, 'SCHEDULED', notes)
        )

        cursor.execute(
            "UPDATE leads SET status = %s, assigned_to = %s, last_contacted = NOW() WHERE lead_id = %s",
            ('CONVERTED', doctor_id, lead_id)
        )

        conn.commit()
        app.logger.info('Appointment created for lead %s with patient %s by doctor %s', lead_id, patient_id, doctor_id)
        flash('Appointment created and lead converted successfully.', 'success')
        return redirect(url_for('appointments'))

    except Error as db_e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        error_context = {
            'lead_id': lead_id,
            'patient_name': patient_name,
            'patient_phone': patient_phone,
            'service': service,
            'appointment_date': appointment_date,
            'appointment_time': appointment_time,
            'doctor_id': doctor_id,
            'patient_id': patient_id,
        }
        print(f"MySQL error while creating appointment: {db_e}")
        print("APPOINTMENT INSERT CONTEXT:", error_context)
        app.logger.exception('MySQL error creating appointment for lead %s: %s', lead_id, db_e)
        flash(f'Appointment creation failed: {db_e}', 'danger')
        return redirect(url_for('convert_to_appointment', lead_id=lead_id))
    except Exception as ex:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        error_context = {
            'lead_id': lead_id,
            'patient_name': patient_name,
            'patient_phone': patient_phone,
            'service': service,
            'appointment_date': appointment_date,
            'appointment_time': appointment_time,
            'doctor_id': doctor_id,
            'patient_id': patient_id,
        }
        print(f"Unexpected error while creating appointment: {ex}")
        print("APPOINTMENT INSERT CONTEXT:", error_context)
        app.logger.exception('Unexpected error creating appointment for lead %s: %s', lead_id, ex)
        flash(f'Error creating appointment: {ex}', 'danger')
        return redirect(url_for('convert_to_appointment', lead_id=lead_id))
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/appointments')
@login_required
def appointments():
    """
    Appointments management page with role-based access.

    DOCTOR: Show only their own appointments
    ADMIN/STAFF: Show all appointments
    
    Fixed:
    - Uses LEFT JOINs to include appointments even without linked patient/doctor
    - Uses correct column names matching template (appointment_date, appointment_time)
    - Includes notes and invoice check
    - Handles null values gracefully
    """
    user_role = session.get('role')
    user_email = session.get('user')

    conn = None
    cursor = None
    appointments_list = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_patients_schema(cursor, conn)
        
        # Use LEFT JOINs to include ALL appointments even if patient/doctor not yet linked
        base_query = """
            SELECT
                a.appointment_id,
                p.name AS patient_name,
                d.name AS doctor_name,
                a.service,
                a.appointment_date,
                a.appointment_time,
                a.status,
                a.notes,
                CASE WHEN i.invoice_id IS NOT NULL THEN 1 ELSE 0 END AS invoice_exists
            FROM appointments a
            LEFT JOIN patients p ON a.patient_id = p.patient_id
            LEFT JOIN doctors d ON a.doctor_id = d.doctor_id
            LEFT JOIN invoices i ON a.appointment_id = i.appointment_id
        """

        if user_role == 'DOCTOR':
            doctor_id = get_session_doctor_id()
            if not doctor_id:
                app.logger.warning('Doctor %s has no doctor_id mapping', user_email)
                flash('Doctor profile not properly configured.', 'danger')
                return render_template('appointments.html', appointments=[])

            query = base_query + " WHERE a.doctor_id = %s ORDER BY a.appointment_date DESC"
            cursor.execute(query, (doctor_id,))
            app.logger.info('Fetching appointments for doctor %s', doctor_id)

        elif user_role in ['ADMIN', 'STAFF']:
            query = base_query + " ORDER BY a.appointment_date DESC"
            cursor.execute(query)
            app.logger.info('Fetching all appointments for %s user', user_role)

        else:
            flash('Invalid user role. Access denied.', 'danger')
            return render_template('appointments.html', appointments=[])

        appointments_list = cursor.fetchall()
        app.logger.info('Appointments loaded: %d records', len(appointments_list) if appointments_list else 0)

    except Error as e:
        app.logger.exception('Database error in appointments route: %s', e)
        flash('Error loading appointments.', 'danger')
        appointments_list = []

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    return render_template('appointments.html', appointments=appointments_list)


@app.route('/update-appointment-status/<int:appointment_id>/<string:new_status>', methods=['POST'])
@login_required
def update_appointment_status(appointment_id, new_status):
    """
    Update appointment status (COMPLETED or CANCELLED).
    
    Security:
    - DOCTOR: Can only update their own appointments
    - ADMIN: Can update any appointment
    - Only allow COMPLETED or CANCELLED
    
    Hook: When status becomes COMPLETED, invoice creation logic can be triggered here.
    """
    # Validate status
    if new_status not in ['COMPLETED', 'CANCELLED']:
        flash('Invalid appointment status.', 'danger')
        return redirect(url_for('appointments'))
    
    user_role = session.get('role')
    user_email = session.get('user')
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch appointment details
        cursor.execute(
            "SELECT appointment_id, doctor_id FROM appointments WHERE appointment_id = %s",
            (appointment_id,)
        )
        appointment = cursor.fetchone()
        
        if not appointment:
            flash('Appointment not found.', 'danger')
            return redirect(url_for('appointments'))
        
        # Security check for DOCTOR role
        if user_role == 'DOCTOR':
            cursor.execute("SELECT doctor_id FROM users WHERE email = %s", (user_email,))
            doctor_data = cursor.fetchone()
            
            if not doctor_data or doctor_data['doctor_id'] != appointment['doctor_id']:
                flash('Access denied. You can only update your own appointments.', 'danger')
                return redirect(url_for('appointments'))
        
        # Update appointment status
        update_query = (
            "UPDATE appointments SET status = %s, updated_at = NOW() WHERE appointment_id = %s"
        )
        
        cursor.execute(update_query, (new_status, appointment_id))
        conn.commit()
        
        # ===== HOOK FOR FUTURE INVOICE CREATION =====
        # When status becomes COMPLETED, prepare for invoice generation
        if new_status == 'COMPLETED':
            # TODO: Trigger invoice creation logic here
            # This could be:
            # 1. Direct call to invoice creation
            # 2. Queue a background job
            # 3. Set a flag for batch processing
            app.logger.info(f"Appointment {appointment_id} marked COMPLETED - ready for invoice generation")
        
        flash(f'Appointment marked as {new_status}.', 'success')
        return redirect(url_for('appointments'))
    
    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.error(f"Database error in update_appointment_status: {e}")
        flash('Error updating appointment.', 'danger')
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


# ============= GENERATE INVOICE FROM APPOINTMENT =============

@app.route('/generate-invoice/<int:appointment_id>', methods=['POST'])
@login_required
def generate_invoice(appointment_id):
    """
    Generate invoice from a completed appointment with professional SaaS features.
    
    Features:
    - Auto-generates unique invoice_number (INV-2026-XXXX format)
    - Sets paid_amount = 0, balance_amount = total_amount initially
    - Supports payment_method tracking
    - Commission-based doctor earnings calculation
    
    POST route - creates invoice for COMPLETED appointments.
    
    Validations:
    - Appointment must exist
    - Appointment status must be COMPLETED
    - No invoice should already exist for this appointment
    - DOCTOR role: restricted to own appointments
    - ADMIN role: unrestricted
    
    Calculations:
    - amount = 2000.00
    - tax = amount * 0.18
    - total_amount = amount + tax
    - paid_amount = 0
    - balance_amount = total_amount
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        invoice_has_type = has_column('invoices', 'invoice_type', cursor)
        invoice_has_followup_id = has_column('invoices', 'followup_id', cursor)

        # Fetch appointment and lock row
        cursor.execute(
            "SELECT appointment_id, patient_id, doctor_id, service, status FROM appointments WHERE appointment_id = %s FOR UPDATE",
            (appointment_id,)
        )
        appointment = cursor.fetchone()
        if not appointment:
            conn.rollback()
            flash(f'Appointment #{appointment_id} not found.', 'danger')
            return redirect(url_for('appointments'))

        # Must be COMPLETED
        if appointment.get('status') != 'COMPLETED':
            conn.rollback()
            flash(f'Cannot generate invoice. Appointment status is {appointment.get("status")}.', 'warning')
            return redirect(url_for('appointments'))

        # Invoice must not already exist
        if invoice_exists(appointment_id, cursor):
            conn.rollback()
            flash(f'Invoice already exists for appointment #{appointment_id}.', 'info')
            return redirect(url_for('invoices'))

        # RBAC: DOCTOR only for own appointments
        user_role = session.get('role')
        if user_role == 'DOCTOR':
            user_email = session.get('user')
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != appointment.get('doctor_id'):
                conn.rollback()
                flash('Access denied. You can only generate invoices for your own appointments.', 'danger')
                return redirect(url_for('appointments'))
        elif user_role not in ['ADMIN', 'STAFF']:
            conn.rollback()
            flash('Access denied. Invalid user role for this action.', 'danger')
            return redirect(url_for('appointments'))

        # patient_id must be present
        if not appointment.get('patient_id'):
            conn.rollback()
            app.logger.error('Appointment %s has NULL patient_id - cannot generate invoice', appointment_id)
            flash('Cannot generate invoice: appointment has no linked patient. Please create patient and retry.', 'danger')
            return redirect(url_for('appointments'))

        # Calculate amounts
        amount = 2000.00
        tax = round(amount * 0.18, 2)
        total_amount = round(amount + tax, 2)
        paid_amount = 0.00
        balance_amount = total_amount

        # Auto-generate invoice number (INV-YYYY-XXXX format)
        current_year = datetime.datetime.now().year
        cursor.execute(
            "SELECT MAX(CAST(SUBSTRING(invoice_number, -4) AS UNSIGNED)) AS max_num FROM invoices WHERE invoice_number LIKE %s",
            (f'INV-{current_year}-%',)
        )
        result = cursor.fetchone()
        max_num = result.get('max_num') if result else 0
        next_num = (max_num or 0) + 1
        invoice_number = f'INV-{current_year}-{next_num:04d}'

        insert_columns = [
            'appointment_id', 'patient_id', 'doctor_id', 'service', 'amount', 'tax',
            'total_amount', 'paid_amount', 'balance_amount', 'status', 'invoice_number', 'created_at'
        ]
        insert_placeholders = ['%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', 'NOW()']
        insert_values = [
            appointment_id,
            appointment.get('patient_id'),
            appointment.get('doctor_id'),
            appointment.get('service') or 'General Consultation',
            amount,
            tax,
            total_amount,
            paid_amount,
            balance_amount,
            'UNPAID',
            invoice_number,
        ]
        if invoice_has_followup_id:
            insert_columns.insert(1, 'followup_id')
            insert_placeholders.insert(1, '%s')
            insert_values.insert(1, None)
        if invoice_has_type:
            invoice_type_value = normalize_invoice_type('appointment')
            created_at_index = insert_columns.index('created_at')
            insert_columns.insert(created_at_index, 'invoice_type')
            insert_placeholders.insert(created_at_index, '%s')
            insert_values.append(invoice_type_value)
            print("Saving invoice_type:", invoice_type_value)
        else:
            invoice_type_value = normalize_invoice_type('appointment')

        app.logger.info(
            'Generating appointment invoice for appointment_id=%s with invoice_type=%s',
            appointment_id,
            invoice_type_value if invoice_has_type else 'N/A'
        )

        cursor.execute(
            f"INSERT INTO invoices ({', '.join(insert_columns)}) VALUES ({', '.join(insert_placeholders)})",
            tuple(insert_values)
        )

        conn.commit()
        app.logger.info('Invoice %s created for appointment %s by user %s', invoice_number, appointment_id, session.get('user'))
        flash(f'✓ Invoice {invoice_number} generated successfully! Amount: ₹{total_amount:,.2f}', 'success')
        return redirect(url_for('invoices'))

    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.exception('Database error while generating invoice for %s: %s', appointment_id, e)
        error_msg = str(e)
        if 'Duplicate entry' in error_msg or 'UNIQUE constraint failed' in error_msg:
            flash(f'Invoice already exists for appointment #{appointment_id}.', 'warning')
        elif 'foreign key' in error_msg.lower():
            flash('Error: Invalid patient or doctor reference. Contact administrator.', 'danger')
        else:
            flash(f'Database error: {error_msg}', 'danger')
        return redirect(url_for('appointments'))

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.exception('Unexpected error in invoice generation for %s: %s', appointment_id, e)
        flash('Unexpected error while generating invoice. Contact administrator.', 'danger')
        return redirect(url_for('appointments'))

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ============= VISITS =============

@app.route('/visits')
@login_required
def visits():
    """Visits management page with role-based access.
    ADMIN/STAFF: see all visits
    DOCTOR: see only their visits (matched by doctors.email)
    """
    user_role = session.get('role')
    user_email = session.get('user')

    conn = None
    cursor = None
    visits_list = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = (
            "SELECT v.visit_id, p.name AS patient_name, d.name AS doctor_name, "
            "v.visit_date, v.diagnosis, v.status, v.follow_up_date "
            "FROM visits v "
            "JOIN patients p ON v.patient_id = p.patient_id "
            "JOIN doctors d ON v.doctor_id = d.doctor_id"
        )
        params = []

        if user_role == 'DOCTOR':
            query += " WHERE d.email = %s"
            params.append(user_email)

        query += " ORDER BY v.visit_date DESC"
        cursor.execute(query, params)
        visits_list = cursor.fetchall()

    except Error as e:
        app.logger.error(f"Database error in visits route: {e}")
        flash('Error loading visits.', 'danger')
        visits_list = []

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template('visits.html', visits=visits_list)


@app.route('/add-visit', methods=['GET', 'POST'])
@login_required
def add_visit():
    """Add a new visit record."""
    user_role = session.get('role')
    session_doctor_id = get_session_doctor_id() if user_role == 'DOCTOR' else None

    if request.method == 'GET':
        patients = []
        doctors = []
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            ensure_patients_schema(cursor, conn)
            active_filter = get_active_patient_filter(cursor, patient_alias='patients')
            patient_query = f"SELECT patient_id, name FROM patients WHERE {active_filter}"
            patient_params = []
            patient_scope_clause, patient_scope_params = build_patient_scope_clause(cursor, patient_alias='patients')
            patient_query += patient_scope_clause + " ORDER BY name"
            patient_params.extend(patient_scope_params)
            cursor.execute(patient_query, tuple(patient_params))
            patients = cursor.fetchall()

            if user_role == 'DOCTOR' and session_doctor_id:
                cursor.execute(
                    "SELECT doctor_id, name FROM doctors WHERE status = 'ACTIVE' AND doctor_id = %s ORDER BY name",
                    (session_doctor_id,)
                )
            else:
                cursor.execute("SELECT doctor_id, name FROM doctors WHERE status = 'ACTIVE' ORDER BY name")
            doctors = cursor.fetchall()
        except Error as e:
            app.logger.error(f"Database error loading visit form: {e}")
            flash('Error loading form data.', 'danger')
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        return render_template('add-visit.html', patients=patients, doctors=doctors)

    # POST
    patient_id = request.form.get('patient_id')
    doctor_id = session_doctor_id if user_role == 'DOCTOR' else request.form.get('doctor_id')
    visit_date = request.form.get('visit_date')
    diagnosis = request.form.get('diagnosis') or None
    status = request.form.get('status') or 'OPEN'
    follow_up_date = request.form.get('follow_up_date') or None

    if not patient_id or not doctor_id or not visit_date:
        flash('Patient, doctor and visit date are required.', 'warning')
        return redirect(url_for('add_visit'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_patients_schema(cursor, conn)

        patient_query = "SELECT patient_id FROM patients WHERE patient_id = %s"
        patient_params = [patient_id]
        patient_scope_clause, patient_scope_params = build_patient_scope_clause(cursor, patient_alias='patients')
        patient_query += patient_scope_clause
        patient_params.extend(patient_scope_params)
        cursor.execute(patient_query, tuple(patient_params))
        if not cursor.fetchone():
            flash('Access denied for the selected patient.', 'danger')
            return redirect(url_for('add_visit'))

        insert_q = (
            "INSERT INTO visits (patient_id, doctor_id, visit_date, diagnosis, status, follow_up_date) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
        )
        cursor.execute(insert_q, (patient_id, doctor_id, visit_date, diagnosis, status, follow_up_date))
        conn.commit()
        flash('Visit added successfully.', 'success')
        return redirect(url_for('visits'))
    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.error(f"Database error adding visit: {e}")
        flash('Error adding visit.', 'danger')
        return redirect(url_for('add_visit'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route('/update-visit-status/<int:visit_id>/<string:new_status>', methods=['POST'])
@login_required
def update_visit_status(visit_id, new_status):
    """Change status of a visit with RBAC and valid transitions."""
    # only allow RESOLVED or REFERRED
    if new_status not in ['RESOLVED', 'REFERRED']:
        flash('Invalid visit status.', 'danger')
        return redirect(url_for('visits'))

    user_role = session.get('role')
    user_email = session.get('user')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT v.visit_id, v.status, d.email AS doctor_email "
            "FROM visits v JOIN doctors d ON v.doctor_id = d.doctor_id "
            "WHERE v.visit_id = %s",
            (visit_id,)
        )
        row = cursor.fetchone()
        if not row:
            flash('Visit not found.', 'danger')
            return redirect(url_for('visits'))
        if row.get('status') != 'OPEN':
            flash('Only OPEN visits can be updated.', 'warning')
            return redirect(url_for('visits'))
        if user_role == 'DOCTOR' and row.get('doctor_email') != user_email:
            flash('Access denied.', 'danger')
            return redirect(url_for('visits'))
        cursor.execute("UPDATE visits SET status = %s WHERE visit_id = %s", (new_status, visit_id))
        conn.commit()
        flash('Visit status updated.', 'success')
    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.error(f"Database error updating visit status: {e}")
        flash('Error updating visit status.', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('visits'))


# ============= FOLLOW-UPS =============

@app.route('/followups')
@login_required
def followups():
    """Follow-ups management page with role-based access, filtering, and overdue tracking."""
    # Initialize variables
    followups_list = []
    stats = {
        'total_followups': 0,
        'pending': 0,
        'completed': 0,
        'missed': 0
    }
    
    user_role = session.get('role', 'STAFF')
    user_email = session.get('user', '')
    status_filter = request.args.get('status', '').strip()
    date_filter = request.args.get('date', '').strip()
    show_overdue = request.args.get('overdue', '').strip()
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        followup_cfg = get_followups_config(cursor)
        doctor_id = get_user_doctor_id(user_email) if user_role == 'DOCTOR' else None
        
        # ===== AUTO-MARK OVERDUE AS MISSED (BACKEND LOGIC) =====
        # Safety-first: Update any PENDING followups with date < today to MISSED
        # Commented out to prevent follow-ups from disappearing
        # auto_missed_query = """
        # UPDATE followups 
        # SET status = 'MISSED' 
        # WHERE status = 'PENDING' AND followup_date < CURDATE()
        # """
        # cursor.execute(auto_missed_query)
        # conn.commit()
        
        # ===== STATISTICS QUERY =====
        stats_query = """
        SELECT 
            COUNT(*) AS total,
            COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending,
            COUNT(CASE WHEN status = 'DONE' THEN 1 END) AS completed,
            COUNT(CASE WHEN status = 'MISSED' THEN 1 END) AS missed
        FROM followups
        """
        stats_params = []
        if doctor_id:
            stats_query += " WHERE doctor_id = %s"
            stats_params.append(doctor_id)

        cursor.execute(stats_query, tuple(stats_params))
        stats_result = cursor.fetchone()
        if stats_result:
            stats = {
                'total_followups': int(stats_result.get('total', 0)),
                'pending': int(stats_result.get('pending', 0)),
                'completed': int(stats_result.get('completed', 0)),
                'missed': int(stats_result.get('missed', 0))
            }
        
        # ===== FOLLOWUPS QUERY WITH LEFT JOINS =====
        # Backward-compatible query - works before and after migration
        time_select = "f.follow_up_time," if followup_cfg['has_followup_time'] else "NULL AS follow_up_time,"
        next_date_select = "f.next_follow_up_date," if followup_cfg['has_next_followup_date'] else "NULL AS next_follow_up_date,"
        next_time_select = "f.next_follow_up_time," if followup_cfg['has_next_followup_time'] else "NULL AS next_follow_up_time,"
        completed_select = "f.completed_at," if followup_cfg['has_completed_at'] else "NULL AS completed_at,"

        followup_invoice_join = (
            "LEFT JOIN invoices i ON f.followup_id = i.followup_id AND i.invoice_type = 'FOLLOWUP'"
            if has_column('invoices', 'invoice_type', cursor) and has_column('invoices', 'followup_id', cursor)
            else (
                "LEFT JOIN invoices i ON f.followup_id = i.followup_id"
                if has_column('invoices', 'followup_id', cursor)
                else "LEFT JOIN invoices i ON 1=0"
            )
        )

        query = f"""
        SELECT 
            f.followup_id,
            f.appointment_id,
            f.doctor_id,
            f.followup_date,
            {time_select}
            f.notes,
            f.status,
            f.created_at,
            {completed_select}
            {next_date_select}
            {next_time_select}
            p.name AS patient_name,
            d.name AS doctor_name,
            a.patient_id,
            a.appointment_date,
            a.service,
            a.status AS appointment_status,
            CASE WHEN i.invoice_id IS NOT NULL THEN 1 ELSE 0 END AS has_invoice,
            i.invoice_id AS followup_invoice_id
        FROM followups f
        LEFT JOIN appointments a ON f.appointment_id = a.appointment_id
        LEFT JOIN patients p ON a.patient_id = p.patient_id
        LEFT JOIN doctors d ON f.doctor_id = d.doctor_id
        {followup_invoice_join}
        WHERE 1=1
        """
        
        params = []
        
        # RBAC: DOCTOR sees only their follow-ups
        if doctor_id:
            query += " AND f.doctor_id = %s"
            params.append(doctor_id)
        
        # Optional status filter
        if status_filter and status_filter in ['PENDING', 'DONE', 'MISSED']:
            query += " AND f.status = %s"
            params.append(status_filter)
        
        # Optional date filter (show follow-ups from this date onwards)
        if date_filter:
            try:
                query += " AND f.followup_date >= %s"
                params.append(date_filter)
            except Exception as e:
                app.logger.warning('Invalid date filter: %s', e)
        
        # Show only missed follow-ups
        if show_overdue == 'on':
            query += " AND f.status = 'MISSED'"
        
        # Order by followup_date ascending (upcoming first)
        query += " ORDER BY f.followup_date ASC"
        
        cursor.execute(query, params)
        followups_result = cursor.fetchall()
        
        # ===== FORMAT DATETIME FIELDS =====
        for followup in followups_result:
            followup['formatted_followup_date'] = format_date_value(followup.get('followup_date'))
            followup['formatted_followup_time'] = format_time_value(followup.get('follow_up_time'))
            followup['formatted_next_followup_date'] = format_date_value(followup.get('next_follow_up_date'))
            followup['formatted_next_followup_time'] = format_time_value(followup.get('next_follow_up_time'))

            # Format created_at
            if followup.get('created_at'):
                try:
                    if isinstance(followup['created_at'], datetime.datetime):
                        followup['formatted_created_at'] = followup['created_at'].strftime('%d-%m-%Y')
                    else:
                        followup['formatted_created_at'] = str(followup['created_at'])
                except Exception as e:
                    app.logger.warning('Error formatting created_at: %s', e)
                    followup['formatted_created_at'] = str(followup.get('created_at', 'N/A'))
            else:
                followup['formatted_created_at'] = 'N/A'
            
            # Format completed_at
            if followup.get('completed_at'):
                try:
                    if isinstance(followup['completed_at'], datetime.datetime):
                        followup['formatted_completed_at'] = followup['completed_at'].strftime('%d-%m-%Y')
                    else:
                        followup['formatted_completed_at'] = str(followup['completed_at'])
                except Exception as e:
                    app.logger.warning('Error formatting completed_at: %s', e)
                    followup['formatted_completed_at'] = str(followup.get('completed_at', '—'))
            else:
                followup['formatted_completed_at'] = '—'
        
        followups_list = followups_result
        
    except Error as e:
        app.logger.exception('Database error in followups route: %s', e)
        flash('Error loading follow-ups.', 'danger')
        followups_list = []
    
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    
    return render_template('followups.html', 
                         followups=followups_list, 
                         stats=stats,
                         status_filter=status_filter,
                         date_filter=date_filter,
                         show_overdue=show_overdue)


@app.route('/add-followup/<int:appointment_id>', methods=['GET', 'POST'])
@login_required
def add_followup(appointment_id):
    """Add a new follow-up for an appointment with time and patient tracking.
    
    Features:
    - Captures follow-up date AND time
    - Automatically links patient_id from appointment
    - DOCTOR/ADMIN can schedule follow-ups
    - RBAC: DOCTOR only for their own appointments
    """
    user_role = session.get('role')
    user_email = session.get('user')
    
    if user_role not in ['DOCTOR', 'ADMIN', 'STAFF']:
        flash('Access denied.', 'danger')
        return redirect(url_for('appointments'))
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        followup_cfg = get_followups_config(cursor)
        
        # Fetch appointment details with patient info
        cursor.execute(
            "SELECT a.appointment_id, a.doctor_id, a.patient_id, a.appointment_date, a.service, a.status, p.name AS patient_name, d.name AS doctor_name FROM appointments a LEFT JOIN patients p ON a.patient_id = p.patient_id LEFT JOIN doctors d ON a.doctor_id = d.doctor_id WHERE a.appointment_id = %s",
            (appointment_id,)
        )
        appointment = cursor.fetchone()
        
        if not appointment:
            flash('Appointment not found.', 'danger')
            return redirect(url_for('appointments'))
        
        # RBAC: DOCTOR can only add follow-ups for their own appointments
        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != appointment.get('doctor_id'):
                flash('Access denied. You can only add follow-ups for your own appointments.', 'danger')
                return redirect(url_for('appointments'))

        if appointment.get('status') != 'COMPLETED':
            flash('Follow-ups can only be scheduled after a completed appointment.', 'warning')
            return redirect(url_for('appointments'))

        if request.method == 'GET':
            tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            return render_template('add-followup.html', appointment=appointment, tomorrow=tomorrow)
        
        # POST: Create follow-up with optional time support (time becomes required after migration)
        followup_date = request.form.get('followup_date', '').strip()
        followup_time = request.form.get('followup_time', '').strip() or None
        notes = request.form.get('notes', '').strip() or None
        
        if not followup_date:
            flash('Follow-up date is required.', 'warning')
            return redirect(url_for('add_followup', appointment_id=appointment_id))
        
        # Validate date format (YYYY-MM-DD)
        try:
            datetime.datetime.strptime(followup_date, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD.', 'warning')
            return redirect(url_for('add_followup', appointment_id=appointment_id))
        
        # Validate time format if provided (HH:MM)
        if followup_time:
            try:
                datetime.datetime.strptime(followup_time, '%H:%M')
            except ValueError:
                flash('Invalid time format. Use HH:MM.', 'warning')
                return redirect(url_for('add_followup', appointment_id=appointment_id))
        
        insert_columns = ['appointment_id', 'doctor_id']
        insert_values = [appointment_id, appointment.get('doctor_id')]
        placeholders = ['%s', '%s']

        if followup_cfg['has_patient_id']:
            insert_columns.append('patient_id')
            insert_values.append(appointment.get('patient_id'))
            placeholders.append('%s')

        insert_columns.append('followup_date')
        insert_values.append(followup_date)
        placeholders.append('%s')

        if followup_cfg['has_followup_time']:
            insert_columns.append('follow_up_time')
            insert_values.append(followup_time)
            placeholders.append('%s')

        insert_columns.extend(['notes', 'status', 'created_at'])
        insert_values.extend([notes, 'PENDING'])
        placeholders.extend(['%s', '%s', 'NOW()'])

        insert_query = (
            f"INSERT INTO followups ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(placeholders)})"
        )
        cursor.execute(insert_query, tuple(insert_values))
        update_patient_case_status(cursor, appointment.get('patient_id'))
        conn.commit()
        
        app.logger.info('Follow-up created for appointment %s by user %s', appointment_id, user_email)
        flash('Follow-up scheduled successfully!', 'success')
        return redirect(url_for('followups'))
    
    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.exception('Database error in add_followup: %s', e)
        flash('Error creating follow-up. Please try again.', 'danger')
        return redirect(url_for('appointments'))
    
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/complete-followup/<int:followup_id>', methods=['POST'])
@login_required
def complete_followup(followup_id):
    """Mark a follow-up as DONE (DOCTOR/ADMIN only)."""
    user_role = session.get('role')
    user_email = session.get('user')
    
    if user_role not in ['DOCTOR', 'ADMIN', 'STAFF']:
        flash('Access denied.', 'danger')
        return redirect(url_for('followups'))
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        followup_cfg = get_followups_config(cursor)
        
        # Fetch follow-up and verify ownership
        cursor.execute("SELECT followup_id, doctor_id, status FROM followups WHERE followup_id = %s", (followup_id,))
        followup = cursor.fetchone()
        
        if not followup:
            flash('Follow-up not found.', 'danger')
            return redirect(url_for('followups'))
        
        # RBAC: DOCTOR can only complete their own follow-ups
        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != followup.get('doctor_id'):
                flash('Access denied. You can only complete your own follow-ups.', 'danger')
                return redirect(url_for('followups'))
        
        completed_sql = ", completed_at = NOW()" if followup_cfg['has_completed_at'] else ""
        cursor.execute(
            f"UPDATE followups SET status = 'DONE'{completed_sql} WHERE followup_id = %s",
            (followup_id,)
        )
        cursor.execute(
            "SELECT patient_id FROM appointments WHERE appointment_id = (SELECT appointment_id FROM followups WHERE followup_id = %s)",
            (followup_id,)
        )
        appt = cursor.fetchone()
        update_patient_case_status(cursor, appt.get('patient_id') if appt else None)
        conn.commit()
        
        app.logger.info('Follow-up %s marked as done by user %s', followup_id, user_email)
        flash('Follow-up marked as completed!', 'success')
        return redirect(url_for('followups'))
    
    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.exception('Database error in complete_followup: %s', e)
        flash('Error updating follow-up. Please try again.', 'danger')
        return redirect(url_for('followups'))
    
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/toggle-followup/<int:followup_id>', methods=['POST'])
@login_required
def toggle_followup(followup_id):
    """Toggle follow-up status and update the corresponding patient case.

    Rules:
      * if all follow-ups for a patient are DONE → case_status = 'CLOSED'
      * if any follow-up remains PENDING → case_status = 'ACTIVE'

    Access restricted to DOCTOR/ADMIN/STAFF. MISSED entries are not editable.
    """
    user_role = session.get('role')
    user_email = session.get('user')

    if user_role not in ['DOCTOR', 'ADMIN', 'STAFF']:
        flash('Access denied.', 'danger')
        return redirect(url_for('followups'))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        followup_cfg = get_followups_config(cursor)

        cursor.execute(
            "SELECT followup_id, doctor_id, status, appointment_id "
            "FROM followups WHERE followup_id = %s",
            (followup_id,)
        )
        followup = cursor.fetchone()
        if not followup:
            flash('Follow-up not found.', 'danger')
            return redirect(url_for('followups'))

        current_status = followup.get('status')
        if current_status == 'MISSED':
            flash('Cannot toggle MISSED follow-ups.', 'warning')
            return redirect(url_for('followups'))

        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != followup.get('doctor_id'):
                flash('Access denied. You can only toggle your own follow-ups.', 'danger')
                return redirect(url_for('followups'))

        if current_status == 'PENDING':
            new_status = 'DONE'
            completed_at_sql = ', completed_at = NOW()' if followup_cfg['has_completed_at'] else ''
        else:
            new_status = 'PENDING'
            completed_at_sql = ', completed_at = NULL' if followup_cfg['has_completed_at'] else ''

        cursor.execute(
            f"""
            UPDATE followups
            SET status = %s {completed_at_sql}
            WHERE followup_id = %s
            """,
            (new_status, followup_id)
        )

        cursor.execute(
            "SELECT patient_id FROM appointments WHERE appointment_id = %s",
            (followup.get('appointment_id'),)
        )
        appt = cursor.fetchone()
        patient_id = appt['patient_id'] if appt else None

        new_case = update_patient_case_status(cursor, patient_id)
        pending_count = 0 if new_case == 'CLOSED' else 1

        conn.commit()
        app.logger.info(
            'Follow-up %s toggled from %s to %s by %s; patient %s case %s',
            followup_id, current_status, new_status, user_email,
            patient_id or 'unknown', ('closed' if pending_count == 0 else 'active')
        )
        flash(f'Follow-up toggled to {new_status}!', 'success')
        return redirect(url_for('followups'))

    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.exception('Database error in toggle_followup: %s', e)
        flash('Error updating follow-up. Please try again.', 'danger')
        return redirect(url_for('followups'))

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ============= NEXT FOLLOW-UP SCHEDULING =============

@app.route('/add-next-followup/<int:followup_id>', methods=['GET', 'POST'])
@login_required
def add_next_followup(followup_id):
    """Schedule the next follow-up after completing a current follow-up.
    
    Features:
    - Creates a new follow-up record linked to same patient, doctor, and appointment
    - Does not overwrite the original follow-up
    - Maintains follow-up history (multiple follow-ups over time)
    - Requires current follow-up to be DONE
    """
    user_role = session.get('role')
    user_email = session.get('user')
    
    if user_role not in ['DOCTOR', 'ADMIN', 'STAFF']:
        flash('Access denied.', 'danger')
        return redirect(url_for('followups'))
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        followup_cfg = get_followups_config(cursor)
        
        # Fetch current follow-up details
        patient_join = (
            "LEFT JOIN patients p ON f.patient_id = p.patient_id "
            if followup_cfg['has_patient_id']
            else "LEFT JOIN patients p ON a.patient_id = p.patient_id "
        )
        current_followup_query = (
            f"SELECT f.followup_id, f.appointment_id, f.doctor_id, "
            f"{'f.patient_id' if followup_cfg['has_patient_id'] else 'a.patient_id AS patient_id'}, "
            f"f.status, a.service, p.name AS patient_name, d.name AS doctor_name "
            f"FROM followups f "
            f"LEFT JOIN appointments a ON f.appointment_id = a.appointment_id "
            f"{patient_join}"
            f"LEFT JOIN doctors d ON f.doctor_id = d.doctor_id "
            f"WHERE f.followup_id = %s"
        )
        cursor.execute(current_followup_query, (followup_id,))
        current_followup = cursor.fetchone()
        
        if not current_followup:
            flash('Follow-up not found.', 'danger')
            return redirect(url_for('followups'))
        
        # RBAC: DOCTOR can only schedule next follow-up for their own
        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != current_followup.get('doctor_id'):
                flash('Access denied. You can only schedule follow-ups for your own patients.', 'danger')
                return redirect(url_for('followups'))

        if current_followup.get('status') != 'DONE':
            flash('Complete the current follow-up before scheduling the next one.', 'warning')
            return redirect(url_for('followups'))
        
        if request.method == 'GET':
            tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            return render_template('add-next-followup.html', current_followup=current_followup, tomorrow=tomorrow, form_mode='next')
        
        # POST: Create next follow-up
        next_followup_date = request.form.get('next_followup_date', '').strip()
        next_followup_time = request.form.get('next_followup_time', '').strip()
        notes = request.form.get('notes', '').strip() or None
        
        if not next_followup_date or not next_followup_time:
            flash('Next follow-up date and time are required.', 'warning')
            return redirect(url_for('add_next_followup', followup_id=followup_id))
        
        # Validate date format
        try:
            datetime.datetime.strptime(next_followup_date, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD.', 'warning')
            return redirect(url_for('add_next_followup', followup_id=followup_id))
        
        # Validate time format
        try:
            datetime.datetime.strptime(next_followup_time, '%H:%M')
        except ValueError:
            flash('Invalid time format. Use HH:MM.', 'warning')
            return redirect(url_for('add_next_followup', followup_id=followup_id))
        
        if followup_cfg['has_next_followup_date'] or followup_cfg['has_next_followup_time']:
            update_parts = []
            update_params = []
            if followup_cfg['has_next_followup_date']:
                update_parts.append("next_follow_up_date = %s")
                update_params.append(next_followup_date)
            if followup_cfg['has_next_followup_time']:
                update_parts.append("next_follow_up_time = %s")
                update_params.append(next_followup_time)
            update_params.append(followup_id)
            cursor.execute(
                f"UPDATE followups SET {', '.join(update_parts)} WHERE followup_id = %s",
                tuple(update_params)
            )
        
        insert_columns = ['appointment_id', 'doctor_id']
        insert_values = [current_followup.get('appointment_id'), current_followup.get('doctor_id')]
        placeholders = ['%s', '%s']
        if followup_cfg['has_patient_id']:
            insert_columns.append('patient_id')
            insert_values.append(current_followup.get('patient_id'))
            placeholders.append('%s')
        insert_columns.append('followup_date')
        insert_values.append(next_followup_date)
        placeholders.append('%s')
        if followup_cfg['has_followup_time']:
            insert_columns.append('follow_up_time')
            insert_values.append(next_followup_time)
            placeholders.append('%s')
        insert_columns.extend(['notes', 'status', 'created_at'])
        insert_values.extend([notes, 'PENDING'])
        placeholders.extend(['%s', '%s', 'NOW()'])
        cursor.execute(
            f"INSERT INTO followups ({', '.join(insert_columns)}) VALUES ({', '.join(placeholders)})",
            tuple(insert_values)
        )
        update_patient_case_status(cursor, current_followup.get('patient_id'))
        
        conn.commit()
        
        app.logger.info('Next follow-up created from followup %s for patient %s by user %s', followup_id, current_followup.get('patient_id'), user_email)
        flash('Next follow-up scheduled successfully. A new follow-up record has been created.', 'success')
        return redirect(url_for('followups'))
    
    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.exception('Database error in add_next_followup: %s', e)
        flash('Error scheduling next follow-up. Please try again.', 'danger')
        return redirect(url_for('followups'))
    
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/reschedule-followup/<int:followup_id>', methods=['GET', 'POST'])
@login_required
def reschedule_followup(followup_id):
    """Reschedule a pending follow-up without creating a new history record."""
    user_role = session.get('role')
    user_email = session.get('user')

    if user_role not in ['DOCTOR', 'ADMIN', 'STAFF']:
        flash('Access denied.', 'danger')
        return redirect(url_for('followups'))

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        followup_cfg = get_followups_config(cursor)

        patient_join = (
            "LEFT JOIN patients p ON f.patient_id = p.patient_id "
            if followup_cfg['has_patient_id']
            else "LEFT JOIN patients p ON a.patient_id = p.patient_id "
        )
        query = (
            f"SELECT f.followup_id, f.appointment_id, f.doctor_id, "
            f"{'f.patient_id' if followup_cfg['has_patient_id'] else 'a.patient_id AS patient_id'}, "
            f"f.status, f.followup_date, "
            f"{'f.follow_up_time' if followup_cfg['has_followup_time'] else 'NULL AS follow_up_time'}, "
            f"f.notes, a.service, p.name AS patient_name, d.name AS doctor_name "
            f"FROM followups f "
            f"LEFT JOIN appointments a ON f.appointment_id = a.appointment_id "
            f"{patient_join}"
            f"LEFT JOIN doctors d ON f.doctor_id = d.doctor_id "
            f"WHERE f.followup_id = %s"
        )
        cursor.execute(query, (followup_id,))
        followup = cursor.fetchone()
        if not followup:
            flash('Follow-up not found.', 'danger')
            return redirect(url_for('followups'))

        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != followup.get('doctor_id'):
                flash('Access denied. You can only reschedule your own follow-ups.', 'danger')
                return redirect(url_for('followups'))

        if followup.get('status') != 'PENDING':
            flash('Only pending follow-ups can be rescheduled.', 'warning')
            return redirect(url_for('followups'))

        if request.method == 'GET':
            tomorrow = datetime.date.today().isoformat()
            return render_template('add-next-followup.html', current_followup=followup, tomorrow=tomorrow, form_mode='reschedule')

        next_followup_date = request.form.get('next_followup_date', '').strip()
        next_followup_time = request.form.get('next_followup_time', '').strip() or None
        notes = request.form.get('notes', '').strip() or None

        if not next_followup_date:
            flash('Rescheduled follow-up date is required.', 'warning')
            return redirect(url_for('reschedule_followup', followup_id=followup_id))

        try:
            datetime.datetime.strptime(next_followup_date, '%Y-%m-%d')
            if next_followup_time:
                datetime.datetime.strptime(next_followup_time, '%H:%M')
        except ValueError:
            flash('Invalid date or time format.', 'warning')
            return redirect(url_for('reschedule_followup', followup_id=followup_id))

        update_parts = ["followup_date = %s", "notes = %s"]
        update_values = [next_followup_date, notes]
        if followup_cfg['has_followup_time']:
            update_parts.append("follow_up_time = %s")
            update_values.append(next_followup_time)
        update_values.append(followup_id)
        cursor.execute(
            f"UPDATE followups SET {', '.join(update_parts)} WHERE followup_id = %s",
            tuple(update_values)
        )
        conn.commit()
        flash('Follow-up rescheduled successfully.', 'success')
        return redirect(url_for('followups'))

    except Error as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.exception('Database error in reschedule_followup: %s', e)
        flash('Error rescheduling follow-up. Please try again.', 'danger')
        return redirect(url_for('followups'))

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/generate-followup-invoice/<int:followup_id>', methods=['POST'])
@app.route('/generate-invoice-from-followup/<int:followup_id>', methods=['POST'])
@login_required
def generate_followup_invoice(followup_id):
    """Generate a dedicated FOLLOWUP invoice without touching appointment invoices."""
    user_role = session.get('role')
    user_email = session.get('user')
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        print(f"[DEBUG] Route hit: /generate-followup-invoice/{followup_id}")
        app.logger.info('Route hit: /generate-followup-invoice/%s', followup_id)
        followup_cfg = get_followups_config(cursor)
        ensure_followup_invoice_schema(cursor, conn)
        ensure_followup_invoice_constraints(cursor, conn)
        invoice_cols = refresh_table_columns('invoices', cursor)
        
        # Fetch follow-up and its linked appointment/patient data
        patient_select = "f.patient_id" if followup_cfg['has_patient_id'] else "a.patient_id AS patient_id"
        cursor.execute(
            f"SELECT f.followup_id, f.appointment_id, f.doctor_id, {patient_select}, "
            f"f.notes AS followup_notes, a.service, a.status AS appointment_status "
            f"FROM followups f "
            f"LEFT JOIN appointments a ON f.appointment_id = a.appointment_id "
            f"WHERE f.followup_id = %s FOR UPDATE",
            (followup_id,)
        )
        followup = cursor.fetchone()
        
        if not followup:
            flash('Follow-up not found.', 'danger')
            return redirect(url_for('followups'))
        
        # RBAC: DOCTOR can only generate invoices for their own follow-ups
        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != followup.get('doctor_id'):
                flash('Access denied. You can only generate invoices for your own follow-ups.', 'danger')
                return redirect(url_for('followups'))
        
        if not followup.get('appointment_id'):
            flash('Appointment for this follow-up not found.', 'danger')
            conn.rollback()
            return redirect(url_for('followups'))
        
        # Check if appointment is COMPLETED
        if followup.get('appointment_status') != 'COMPLETED':
            flash(f'Cannot generate invoice. Related appointment status is {followup.get("appointment_status")}. Only COMPLETED appointments can have invoices.', 'warning')
            conn.rollback()
            return redirect(url_for('followups'))
        
        # Check if dedicated follow-up invoice already exists
        if followup_invoice_exists(followup_id, cursor):
            conn.rollback()
            flash('Follow-up invoice already exists for this follow-up.', 'info')
            return redirect(url_for('invoices'))

        patient_id = followup.get('patient_id')
        if not patient_id:
            conn.rollback()
            flash('Cannot generate follow-up invoice because patient data is missing.', 'danger')
            return redirect(url_for('followups'))

        service_name = (request.form.get('service') or followup.get('service') or 'Follow-up Consultation').strip()
        amount = to_float(request.form.get('amount') or 1000.00)
        tax = round(amount * 0.18, 2)
        total_amount = round(amount + tax, 2)
        invoice_number = get_next_invoice_number(cursor) if 'invoice_number' in invoice_cols else None

        insert_columns = []
        insert_values = []
        placeholders = []

        def add_value(column_name, value):
            if column_name in invoice_cols:
                insert_columns.append(column_name)
                insert_values.append(value)
                placeholders.append('%s')

        # Keep follow-up invoices independent from appointment invoices.
        # Some deployments have a UNIQUE constraint on invoices.appointment_id,
        # so we must not reuse the appointment_id for follow-up billing rows.
        add_value('appointment_id', None)
        add_value('followup_id', followup_id)
        add_value('patient_id', patient_id)
        add_value('doctor_id', followup.get('doctor_id'))
        add_value('service', service_name)
        add_value('amount', amount)
        add_value('tax', tax)
        add_value('total_amount', total_amount)
        add_value('paid_amount', 0)
        add_value('balance_amount', total_amount)
        add_value('status', 'UNPAID')
        add_value('invoice_number', invoice_number)
        followup_invoice_type = normalize_invoice_type('followup')
        add_value('invoice_type', followup_invoice_type)
        print("Saving invoice_type:", followup_invoice_type)

        if 'created_at' in invoice_cols:
            insert_columns.append('created_at')
            placeholders.append('NOW()')

        insert_sql = f"INSERT INTO invoices ({', '.join(insert_columns)}) VALUES ({', '.join(placeholders)})"
        print("Creating follow-up invoice with data:", {
            'followup_id': followup_id,
            'patient_id': patient_id,
            'doctor_id': followup.get('doctor_id'),
            'service': service_name,
            'amount': amount,
            'invoice_type': followup_invoice_type,
            'invoice_number': invoice_number,
            'columns': insert_columns,
        })
        app.logger.info(
            'Executing follow-up invoice insert for followup_id=%s appointment_id=%s invoice_number=%s',
            followup_id,
            followup.get('appointment_id'),
            invoice_number
        )
        cursor.execute(insert_sql, tuple(insert_values))

        conn.commit()
        print("Follow-up invoice created:", followup_id)
        flash(f'Follow-up invoice {invoice_number} generated successfully.', 'success')
        return redirect(url_for('invoices'))
    
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.exception('Database error in generate_followup_invoice: %s', e)
        print("Follow-up invoice error:", str(e))
        flash(f'Error generating invoice: {str(e)}', 'danger')
        return redirect(url_for('followups'))
    
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ============= INVOICES =============

@app.route('/invoices')
@login_required
def invoices():
    """
    Invoices management page with robust filtering and revenue summary.
    
    Always loads invoices with optional filters for search and status.
    Uses LEFT JOIN with patients and doctors for complete data display.
    Revenue summary includes total, paid, and pending amounts.
    """
    # Initialize ALL variables at function start - prevents UnboundLocalError
    invoices_list = []
    revenue_data = {}
    search_query = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    invoice_type_filter = request.args.get('type', '').strip().upper()
    user_role = session.get('role', 'STAFF')
    user_email = session.get('user', '')
    doctor_filter = request.args.get('doctor', '').strip()
    doctors = []
    invoice_type_links = {}
    
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_followup_invoice_schema(cursor, conn)
        invoice_type_select = "i.invoice_type," if has_column('invoices', 'invoice_type', cursor) else "'APPOINTMENT' AS invoice_type,"
        followup_id_select = "i.followup_id," if has_column('invoices', 'followup_id', cursor) else "NULL AS followup_id,"
        appointment_id_select = "i.appointment_id," if has_column('invoices', 'appointment_id', cursor) else "NULL AS appointment_id,"

        if user_role in ['ADMIN', 'STAFF']:
            cursor.execute("SELECT doctor_id, name FROM doctors ORDER BY name")
            doctors = cursor.fetchall() or []
        
        # ===== REVENUE SUMMARY QUERY =====
        # Calculate total revenue, paid revenue, pending revenue
        revenue_query = """
        SELECT 
            COALESCE(SUM(total_amount), 0) AS total_revenue,
            COALESCE(SUM(CASE WHEN status = 'PAID' THEN total_amount ELSE 0 END), 0) AS paid_revenue,
            COALESCE(SUM(CASE WHEN status = 'UNPAID' THEN total_amount ELSE 0 END), 0) AS pending_revenue,
            COALESCE(SUM(CASE WHEN status = 'PAID' AND MONTH(COALESCE(payment_date, created_at)) = MONTH(CURDATE()) AND YEAR(COALESCE(payment_date, created_at)) = YEAR(CURDATE()) THEN total_amount ELSE 0 END), 0) AS this_month_revenue,
            COUNT(*) AS total_invoices,
            COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
            COUNT(CASE WHEN status = 'UNPAID' THEN 1 END) AS unpaid_count
        FROM invoices
        """
        revenue_params = []
        
        # RBAC: Filter revenue for doctors
        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if doctor_id:
                revenue_query += " WHERE doctor_id = %s"
                revenue_params.append(doctor_id)
        elif doctor_filter:
            revenue_query += " WHERE doctor_id = %s"
            revenue_params.append(doctor_filter)

        if invoice_type_filter in ['APPOINTMENT', 'FOLLOWUP']:
            revenue_query += " AND invoice_type = %s" if revenue_params else " WHERE invoice_type = %s"
            revenue_params.append(invoice_type_filter)

        cursor.execute(revenue_query, revenue_params)
        revenue_result = cursor.fetchone()
        
        if revenue_result:
            revenue_data = {
                'total_revenue': float(revenue_result.get('total_revenue', 0)),
                'paid_revenue': float(revenue_result.get('paid_revenue', 0)),
                'pending_revenue': float(revenue_result.get('pending_revenue', 0)),
                'this_month_revenue': float(revenue_result.get('this_month_revenue', 0)),
                'total_invoices': int(revenue_result.get('total_invoices', 0)),
                'paid_count': int(revenue_result.get('paid_count', 0)),
                'unpaid_count': int(revenue_result.get('unpaid_count', 0))
            }
        
        # ===== INVOICES QUERY WITH OPTIONAL FILTERS =====
        # Base query with LEFT JOINs - always executes regardless of filters
        query = """
        SELECT 
            i.invoice_id,
            i.invoice_number,
        """ + invoice_type_select + """
        """ + followup_id_select + """
        """ + appointment_id_select + """
            p.name AS patient_name,
            d.name AS doctor_name,
            i.service,
            i.amount,
            i.tax,
            i.total_amount,
            i.paid_amount,
            i.balance_amount,
            i.status,
            i.created_at,
            i.payment_date,
            f.notes AS followup_notes,
            ref_appointment.appointment_id AS reference_appointment_id,
            ref_appointment.appointment_date AS reference_appointment_date,
            ref_invoice.invoice_number AS reference_invoice_number
        FROM invoices i
        LEFT JOIN patients p ON i.patient_id = p.patient_id
        LEFT JOIN doctors d ON i.doctor_id = d.doctor_id
        LEFT JOIN followups f ON i.followup_id = f.followup_id
        LEFT JOIN appointments ref_appointment ON COALESCE(i.appointment_id, f.appointment_id) = ref_appointment.appointment_id
        LEFT JOIN invoices ref_invoice ON ref_invoice.appointment_id = ref_appointment.appointment_id
            AND ref_invoice.invoice_type = 'APPOINTMENT'
            AND ref_invoice.invoice_id <> i.invoice_id
        WHERE 1=1
        """
        
        params = []
        
        # Optional search filter - safe parameterization
        if search_query:
            query += """ AND (
                i.invoice_number LIKE %s 
                OR p.name LIKE %s 
                OR d.name LIKE %s 
                OR i.service LIKE %s
            )"""
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
        
        # Optional status filter - enum validation
        if status_filter and status_filter in ['PAID', 'UNPAID']:
            query += " AND i.status = %s"
            params.append(status_filter)

        if invoice_type_filter in ['APPOINTMENT', 'FOLLOWUP']:
            query += " AND i.invoice_type = %s"
            params.append(invoice_type_filter)

        if user_role in ['ADMIN', 'STAFF'] and doctor_filter:
            query += " AND i.doctor_id = %s"
            params.append(doctor_filter)
        
        # RBAC: DOCTOR role sees only their invoices
        if user_role == 'DOCTOR':
            doctor_id = get_user_doctor_id(user_email)
            if doctor_id:
                query += " AND i.doctor_id = %s"
                params.append(doctor_id)
        
        # Order by creation date, most recent first
        query += " ORDER BY i.created_at DESC"
        
        # Execute query - this ALWAYS runs
        cursor.execute(query, params)
        invoices_list = cursor.fetchall()
        invoices_list = [serialize_invoice_record(invoice) for invoice in invoices_list]

    except Error as e:
        app.logger.exception('Database error in invoices route: %s', e)
        flash('Error loading invoices.', 'danger')
        
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    base_filters = {}
    if search_query:
        base_filters['search'] = search_query
    if status_filter:
        base_filters['status'] = status_filter
    if doctor_filter:
        base_filters['doctor'] = doctor_filter

    invoice_type_links = {
        'all': url_for('invoices', **base_filters),
        'appointment': url_for('invoices', **dict(base_filters, type='APPOINTMENT')),
        'followup': url_for('invoices', **dict(base_filters, type='FOLLOWUP')),
    }
    
    return render_template('invoices.html',
                         invoices=invoices_list,
                         revenue_summary=revenue_data,
                         search_query=search_query,
                         status_filter=status_filter,
                         invoice_type_filter=invoice_type_filter,
                         invoice_type_links=invoice_type_links,
                         doctors=doctors,
                         user_role=user_role)


@app.route('/toggle-payment/<int:invoice_id>', methods=['POST'])
@login_required
def toggle_payment_route(invoice_id):
    """Toggle invoice payment status safely with RBAC and transaction handling."""
    user_role = session.get('role')
    user_email = session.get('user')
    try:
        result = svc_toggle_payment(invoice_id, user_role, user_email)
        if result.get('success'):
            flash('Payment status updated.', 'success')
        else:
            flash(result.get('message', 'Could not update payment status.'), 'danger')
    except Exception as e:
        app.logger.exception('Error toggling payment for invoice %s: %s', invoice_id, e)
        flash('Error updating payment. Please try again.', 'danger')
    return redirect(url_for('invoices'))


@app.route('/finance-dashboard')
@login_required
def finance_dashboard():
    """Return structured finance dashboard data for template rendering."""
    try:
        data = get_finance_dashboard()
        # Template expects 'data' with keys:
        # total_revenue, pending_revenue, total_invoices, paid_count, monthly, per_doctor
        return render_template('finance-dashboard.html', data=data)
    except Exception as e:
        app.logger.exception('Error loading finance dashboard: %s', e)
        flash('Error loading finance data.', 'danger')
        return render_template('finance-dashboard.html', data={})


@app.route('/doctor-earnings')
@login_required
def doctor_earnings():
    """Show per-doctor earnings with commission percentage from doctors table."""
    try:
        user_role = session.get('role')
        user_email = session.get('user')
        
        from services.invoice_service import get_doctor_invoice_earnings
        rows = get_doctor_invoice_earnings(user_role=user_role, user_email=user_email)
        return render_template('doctor-earnings.html', earnings=rows)
    except Exception as e:
        app.logger.exception('Error loading doctor earnings: %s', e)
        flash('Error loading doctor earnings.', 'danger')
        return render_template('doctor-earnings.html', earnings=[])


@app.route('/analytics')
@login_required
def analytics():
    """Return JSON analytics: monthly revenue, top doctors, conversion rate, appointment distribution."""
    try:
        data = get_analytics()
        return jsonify(data)
    except Exception as e:
        app.logger.exception('Error loading analytics: %s', e)
        return jsonify({'error': 'Unable to load analytics'}), 500


@app.route('/invoice/<int:invoice_id>/pdf')
@app.route('/invoice/<int:invoice_id>/download')
@login_required
def invoice_pdf(invoice_id):
    """Generate and return a downloadable invoice PDF."""
    try:
        inv = get_invoice_by_id(invoice_id)
        if not inv:
            flash('Invoice not found.', 'danger')
            return redirect(url_for('invoices'))
        if session.get('role') == 'DOCTOR':
            doctor_id = get_user_doctor_id(session.get('user'))
            if not doctor_id or doctor_id != inv.get('doctor_id'):
                flash('Access denied. You can only download your own invoices.', 'danger')
                return redirect(url_for('invoices'))

        pdf_path = generate_invoice_pdf(invoice_id)
        return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path), mimetype='application/pdf')
    except Exception as e:
        app.logger.exception('Error generating PDF for invoice %s: %s', invoice_id, e)
        flash(f'Error generating invoice PDF: {e}', 'danger')
        return redirect(url_for('invoices'))


@app.route('/download-invoice/<int:invoice_id>')
@login_required
def download_invoice(invoice_id):
    """Alternative download endpoint for invoice PDF."""
    return invoice_pdf(invoice_id)

# ============= CAMPAIGNS =============

@app.route('/campaigns', methods=['GET'])
@login_required
def campaigns():
    """Campaigns management page."""
    conn = None
    cursor = None
    campaigns = []

    try:
        print("Campaign route hit")
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT c.*, COUNT(cl.log_id) AS total_sent, "
            "SUM(cl.status = 'SENT') AS sent_success, "
            "SUM(cl.status = 'FAILED') AS sent_failed "
            "FROM campaigns c "
            "LEFT JOIN campaign_logs cl ON c.campaign_id = cl.campaign_id "
            "WHERE c.is_active = TRUE "
            "GROUP BY c.campaign_id "
            "ORDER BY c.created_at DESC"
        )
        campaigns = cursor.fetchall() or []

    except Error as e:
        app.logger.error(f"Database error in campaigns route: {e}")
        flash('Error loading campaigns.', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template('campaigns.html', campaigns=campaigns)


@app.route('/campaigns/create', methods=['POST'])
@role_required('ADMIN')
def create_campaign():
    name = request.form.get('name', '').strip()
    service_filter = request.form.get('service_filter', '').strip()
    message = request.form.get('message', '').strip()

    if not name or not message:
        flash('Campaign name and message are required.', 'warning')
        return redirect(url_for('campaigns'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO campaigns (name, service_filter, message, status, created_by, created_at) "
            "VALUES (%s, %s, %s, 'DRAFT', (SELECT user_id FROM users WHERE email = %s), NOW())",
            (name, service_filter or None, message, session.get('user'))
        )
        conn.commit()
        flash('Campaign created successfully.', 'success')
    except Error as e:
        if conn:
            conn.rollback()
        app.logger.error(f"Error creating campaign: {e}")
        flash('Error creating campaign.', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(url_for('campaigns'))


@app.route('/campaigns/run/<int:campaign_id>', methods=['POST'])
@role_required('ADMIN')
def run_campaign(campaign_id):
    """Run campaign against scraped leads with matching service."""
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT campaign_id, service_filter, message FROM campaigns WHERE campaign_id = %s AND is_active = TRUE", (campaign_id,))
        campaign = cursor.fetchone()
        if not campaign:
            flash('Campaign not found.', 'danger')
            return redirect(url_for('campaigns'))

        select_query = "SELECT lead_id, name, phone, email FROM leads WHERE status = 'SCRAPED'"
        params = []
        if campaign.get('service_filter'):
            select_query += " AND service LIKE %s"
            params.append(f"%{campaign.get('service_filter')}%")

        cursor.execute(select_query, tuple(params))
        leads = cursor.fetchall() or []

        if not leads:
            flash('No scraped leads found for this campaign filter.', 'warning')
            return redirect(url_for('campaigns'))

        # Log as sent during this run
        success_count = 0
        for lead in leads:
            # simulate message send (could integrate WhatsApp API)
            cursor.execute(
                "INSERT INTO campaign_logs (campaign_id, lead_id, sent_at, status, response) VALUES (%s, %s, NOW(), %s, %s)",
                (campaign_id, lead['lead_id'], 'SENT', 'Simulated send')
            )
            success_count += 1

        cursor.execute("UPDATE campaigns SET status = 'SENT', sent_at = NOW() WHERE campaign_id = %s", (campaign_id,))
        conn.commit()

        flash(f'Campaign sent to {success_count} leads.', 'success')
        return redirect(url_for('campaigns'))

    except Error as e:
        if conn:
            conn.rollback()
        app.logger.error(f"Error running campaign: {e}")
        flash('Error running campaign. Please try again.', 'danger')
        return redirect(url_for('campaigns'))

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()




# ============= CLOSED CASES =============

@app.route('/closed-cases')
@login_required
def closed_cases():
    """Closed cases page - Shows only CLOSED patients."""
    conn = None
    cursor = None
    cases_list = []
    user_role = session.get('role')
    user_email = session.get('user')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_patients_schema(cursor, conn)
        
        # Base query for closed patients
        query = """
            SELECT
                p.patient_id,
                p.name,
                p.phone,
                p.email,
                p.problem_description,
                p.case_status,
                p.created_at
            FROM patients p
            WHERE p.case_status = 'CLOSED'
        """
        params = []
        
        scope_clause, scope_params = build_patient_scope_clause(cursor, patient_alias='p')
        query += scope_clause
        params.extend(scope_params)
        
        query += " ORDER BY p.name ASC"
        
        cursor.execute(query, params)
        cases_list = cursor.fetchall()
        
    except Error as e:
        app.logger.error(f'Database error in closed_cases route: {e}')
        flash('Error loading closed cases', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    
    return render_template('closed-cases.html', cases=cases_list)


# ============= API ENDPOINTS =============

@app.route('/api/leads', methods=['GET'])
@login_required
def get_leads():
    """API endpoint to get leads"""
    user_role = session.get('role')
    user_email = session.get('user')

    conn = None
    cursor = None
    query = "SELECT l.*, d.name AS doctor_name FROM leads l LEFT JOIN doctors d ON l.assigned_to = d.doctor_id"
    params = []

    if user_role == 'DOCTOR':
        doctor_id = get_session_doctor_id()
        if doctor_id:
            query += " WHERE l.assigned_to = %s"
            params.append(doctor_id)
    query += " ORDER BY l.created_at DESC"

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_patients_schema(cursor, conn)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall() or []
        for lead in rows:
            followup_state = get_lead_followup_state(
                last_contacted=lead.get('last_contacted'),
                created_at=lead.get('created_at'),
            )
            lead['followup_pending_days'] = followup_state['days']
            lead['followup_pending'] = bool(followup_state['pending'])
            lead['followup_label'] = followup_state['label']
            lead['followup_badge_class'] = followup_state['badge_class']
        return jsonify(rows)
    except Exception as e:
        app.logger.error(f"API leads error: {e}")
        return jsonify({'error': 'Unable to fetch leads'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route('/api/patients', methods=['GET'])
@login_required
def get_patients():
    """API endpoint to get patients"""
    user_role = session.get('role')
    user_email = session.get('user')
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_patients_schema(cursor, conn)
        query = "SELECT p.* FROM patients p WHERE 1 = 1"
        params = []
        scope_clause, scope_params = build_patient_scope_clause(cursor, patient_alias='p')
        query += scope_clause
        params.extend(scope_params)
        query += " ORDER BY p.created_at DESC"
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall() or []
        return jsonify(rows)
    except Exception as e:
        app.logger.error(f"API patients error: {e}")
        return jsonify({'error': 'Unable to fetch patients'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route('/api/doctors', methods=['GET'])
@login_required
def get_doctors():
    """API endpoint to get doctors"""
    user_role = session.get('role')
    user_email = session.get('user')

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if user_role == 'DOCTOR':
            doctor_id = get_session_doctor_id()
            if doctor_id:
                cursor.execute("SELECT * FROM doctors WHERE doctor_id = %s", (doctor_id,))
            else:
                return jsonify([])
        else:
            cursor.execute("SELECT * FROM doctors WHERE status = 'ACTIVE' ORDER BY name ASC")

        rows = cursor.fetchall() or []
        return jsonify(rows)
    except Exception as e:
        app.logger.error(f"API doctors error: {e}")
        return jsonify({'error': 'Unable to fetch doctors'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route('/api/appointments', methods=['GET'])
@login_required
def get_appointments():
    """API endpoint to get appointments"""
    user_role = session.get('role')
    user_email = session.get('user')

    conn = None
    cursor = None

    q = """
        SELECT a.*, p.name AS patient_name, d.name AS doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
    """
    params = []

    if user_role == 'DOCTOR':
        doctor_id = get_session_doctor_id()
        if doctor_id:
            q += " WHERE a.doctor_id = %s"
            params.append(doctor_id)

    q += " ORDER BY a.appointment_date DESC, a.appointment_time DESC"

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_patients_schema(cursor, conn)
        cursor.execute(q, tuple(params))
        rows = cursor.fetchall() or []
        return jsonify(rows)
    except Exception as e:
        app.logger.error(f"API appointments error: {e}")
        return jsonify({'error': 'Unable to fetch appointments'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
