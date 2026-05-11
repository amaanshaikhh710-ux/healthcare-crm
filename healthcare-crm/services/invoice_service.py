from db import get_db_connection
from mysql.connector import Error
import datetime


def _table_columns(table_name, cursor):
    cursor.execute(f"SHOW COLUMNS FROM {table_name}")
    return {row['Field'] for row in cursor.fetchall()}


def _get_user_doctor_id(user_email):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT doctor_id FROM users WHERE email = %s LIMIT 1", (user_email,))
        row = cursor.fetchone()
        return row['doctor_id'] if row and row.get('doctor_id') else None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_invoices(user_role, user_email, limit=None, offset=None, doctor_filter=None, search=None, status_filter=None):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        invoice_cols = _table_columns('invoices', cursor)
        invoice_type_select = "i.invoice_type," if 'invoice_type' in invoice_cols else "'APPOINTMENT' AS invoice_type,"
        followup_id_select = "i.followup_id," if 'followup_id' in invoice_cols else "NULL AS followup_id,"

        base_query = (
            f"SELECT i.invoice_id, i.invoice_number, {invoice_type_select} {followup_id_select} p.name AS patient_name, d.name AS doctor_name, i.service, "
            "i.amount, i.tax, i.total_amount, i.paid_amount, i.balance_amount, i.status, i.payment_date, i.payment_method, "
            "i.created_at, i.doctor_id, d.commission_percentage "
            "FROM invoices i "
            "LEFT JOIN patients p ON i.patient_id = p.patient_id "
            "LEFT JOIN doctors d ON i.doctor_id = d.doctor_id "
        )

        where_clauses = []
        params = []

        if user_role == 'DOCTOR':
            doctor_id = _get_user_doctor_id(user_email)
            if not doctor_id:
                return []
            where_clauses.append("i.doctor_id = %s")
            params.append(doctor_id)

        if doctor_filter:
            where_clauses.append("i.doctor_id = %s")
            params.append(doctor_filter)

        if status_filter:
            where_clauses.append("i.status = %s")
            params.append(status_filter)

        if search:
            where_clauses.append("(p.name LIKE %s OR d.name LIKE %s OR i.service LIKE %s OR i.invoice_number LIKE %s)")
            s = f"%{search}%"
            params.extend([s, s, s, s])

        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)

        base_query += " ORDER BY i.created_at DESC"

        if limit is not None:
            base_query += " LIMIT %s"
            params.append(limit)
            if offset is not None:
                base_query += " OFFSET %s"
                params.append(offset)

        cursor.execute(base_query, tuple(params))
        rows = cursor.fetchall()
        return rows

    except Error:
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def toggle_payment(invoice_id, user_role, user_email):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        conn.start_transaction()

        # Lock invoice
        cursor.execute("SELECT invoice_id, status, doctor_id, total_amount FROM invoices WHERE invoice_id = %s FOR UPDATE", (invoice_id,))
        inv = cursor.fetchone()
        if not inv:
            conn.rollback()
            return {'success': False, 'message': 'Invoice not found'}

        # RBAC: DOCTOR only own invoices
        if user_role == 'DOCTOR':
            doctor_id = _get_user_doctor_id(user_email)
            if not doctor_id or doctor_id != inv.get('doctor_id'):
                conn.rollback()
                return {'success': False, 'message': 'Access denied'}

        new_status = 'PAID' if inv.get('status') == 'UNPAID' else 'UNPAID'
        
        if new_status == 'PAID':
            # Mark as PAID: paid_amount = total_amount, balance_amount = 0
            cursor.execute(
                "UPDATE invoices SET status = %s, paid_amount = %s, balance_amount = %s, payment_date = NOW(), updated_at = NOW() WHERE invoice_id = %s",
                (new_status, inv.get('total_amount'), 0, invoice_id)
            )
        else:
            # Mark as UNPAID: paid_amount = 0, balance_amount = total_amount
            cursor.execute(
                "UPDATE invoices SET status = %s, paid_amount = %s, balance_amount = %s, payment_date = NULL, updated_at = NOW() WHERE invoice_id = %s",
                (new_status, 0, inv.get('total_amount'), invoice_id)
            )

        conn.commit()
        return {'success': True, 'invoice_id': invoice_id, 'new_status': new_status}

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_invoice_by_id(invoice_id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        invoice_cols = _table_columns('invoices', cursor)
        doctor_cols = _table_columns('doctors', cursor)
        invoice_type_select = "i.invoice_type," if 'invoice_type' in invoice_cols else "'APPOINTMENT' AS invoice_type,"
        followup_id_select = "i.followup_id," if 'followup_id' in invoice_cols else "NULL AS followup_id,"
        appointment_id_select = "i.appointment_id," if 'appointment_id' in invoice_cols else "NULL AS appointment_id,"
        commission_select = "d.commission_percentage" if 'commission_percentage' in doctor_cols else "NULL AS commission_percentage"
        cursor.execute(
            f"SELECT i.invoice_id, i.invoice_number, {invoice_type_select} {followup_id_select} {appointment_id_select} "
            "i.doctor_id, i.amount, i.tax, i.total_amount, i.paid_amount, i.balance_amount, "
            "i.status, i.created_at, i.payment_date, i.payment_method, p.name AS patient_name, "
            f"d.name AS doctor_name, i.service, {commission_select}, f.notes AS followup_notes, "
            "ref_appointment.appointment_id AS reference_appointment_id, "
            "ref_appointment.appointment_date AS reference_appointment_date, "
            "ref_invoice.invoice_number AS reference_invoice_number "
            "FROM invoices i "
            "LEFT JOIN patients p ON i.patient_id = p.patient_id "
            "LEFT JOIN doctors d ON i.doctor_id = d.doctor_id "
            "LEFT JOIN followups f ON i.followup_id = f.followup_id "
            "LEFT JOIN appointments ref_appointment ON COALESCE(i.appointment_id, f.appointment_id) = ref_appointment.appointment_id "
            "LEFT JOIN invoices ref_invoice ON ref_invoice.appointment_id = ref_appointment.appointment_id "
            "AND ref_invoice.invoice_type = 'APPOINTMENT' "
            "AND ref_invoice.invoice_id <> i.invoice_id "
            "WHERE i.invoice_id = %s",
            (invoice_id,)
        )
        return cursor.fetchone()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_revenue_summary():
    """Get comprehensive revenue summary for dashboard."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Total Revenue (from PAID invoices)
        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) AS total FROM invoices WHERE status = 'PAID'")
        total_revenue = cursor.fetchone()['total']

        # Paid Revenue (already paid)
        cursor.execute("SELECT COALESCE(SUM(paid_amount), 0) AS total FROM invoices WHERE status = 'PAID'")
        paid_revenue = cursor.fetchone()['total']

        # Pending Revenue (unpaid balance)
        cursor.execute("SELECT COALESCE(SUM(balance_amount), 0) AS total FROM invoices WHERE status = 'UNPAID'")
        pending_revenue = cursor.fetchone()['total']

        # This Month Revenue
        cursor.execute(
            "SELECT COALESCE(SUM(total_amount), 0) AS total FROM invoices WHERE status = 'PAID' AND MONTH(payment_date) = MONTH(CURDATE()) AND YEAR(payment_date) = YEAR(CURDATE())"
        )
        this_month_revenue = cursor.fetchone()['total']

        # Total invoices count
        cursor.execute("SELECT COUNT(*) AS total FROM invoices")
        total_invoices = cursor.fetchone()['total']

        return {
            'total_revenue': float(total_revenue or 0),
            'paid_revenue': float(paid_revenue or 0),
            'pending_revenue': float(pending_revenue or 0),
            'this_month_revenue': float(this_month_revenue or 0),
            'total_invoices': int(total_invoices or 0),
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_doctor_invoice_earnings(doctor_id=None, user_role=None, user_email=None):
    """Get doctor earnings with commission calculation based on commission_percentage field."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # If checking specific doctor (for DOCTOR role)
        if user_role == 'DOCTOR':
            doctor_id = _get_user_doctor_id(user_email)

        if doctor_id:
            # Single doctor earnings
            cursor.execute(
                "SELECT d.doctor_id, d.name AS doctor_name, COALESCE(d.commission_percentage, 40) AS commission_percentage, "
                "COUNT(i.invoice_id) AS total_cases, COALESCE(SUM(i.total_amount), 0) AS total_revenue, "
                "COALESCE(SUM(i.paid_amount), 0) AS paid_revenue "
                "FROM doctors d LEFT JOIN invoices i ON d.doctor_id = i.doctor_id AND i.status = 'PAID' "
                "WHERE d.doctor_id = %s GROUP BY d.doctor_id, d.name, d.commission_percentage",
                (doctor_id,)
            )
        else:
            # All doctors earnings
            cursor.execute(
                "SELECT d.doctor_id, d.name AS doctor_name, COALESCE(d.commission_percentage, 40) AS commission_percentage, "
                "COUNT(i.invoice_id) AS total_cases, COALESCE(SUM(i.total_amount), 0) AS total_revenue, "
                "COALESCE(SUM(i.paid_amount), 0) AS paid_revenue "
                "FROM doctors d LEFT JOIN invoices i ON d.doctor_id = i.doctor_id AND i.status = 'PAID' "
                "GROUP BY d.doctor_id, d.name, d.commission_percentage ORDER BY total_revenue DESC"
            )

        rows = cursor.fetchall()

        result = []
        for r in rows:
            total_revenue = float(r.get('total_revenue') or 0)
            commission_pct = float(r.get('commission_percentage') or 40)
            earning = round(total_revenue * commission_pct / 100, 2)

            result.append({
                'doctor_id': r.get('doctor_id'),
                'doctor_name': r.get('doctor_name'),
                'commission_percentage': commission_pct,
                'total_cases': int(r.get('total_cases') or 0),
                'total_revenue': total_revenue,
                'paid_revenue': float(r.get('paid_revenue') or 0),
                'earning': earning,
            })

        return result

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
