import os
import psycopg2
import psycopg2.extras
from psycopg2 import Error
from decimal import Decimal


# ---------------------------------------------------------------------------
# DB connection (mirrors app.py)
# ---------------------------------------------------------------------------

def _get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 5432)),
    )


def _to_float(value):
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# get_invoice_by_id
# ---------------------------------------------------------------------------

def get_invoice_by_id(invoice_id):
    """Return a single invoice row as a dict, or None."""
    conn = None
    cursor = None
    try:
        conn = _get_conn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            SELECT
                i.*,
                p.name  AS patient_name,
                d.name  AS doctor_name,
                f.notes AS followup_notes,
                ref_appt.appointment_id   AS reference_appointment_id,
                ref_appt.appointment_date AS reference_appointment_date,
                ref_inv.invoice_number    AS reference_invoice_number
            FROM invoices i
            LEFT JOIN patients     p        ON i.patient_id  = p.patient_id
            LEFT JOIN doctors      d        ON i.doctor_id   = d.doctor_id
            LEFT JOIN followups    f        ON i.followup_id = f.followup_id
            LEFT JOIN appointments ref_appt ON COALESCE(i.appointment_id, f.appointment_id)
                                               = ref_appt.appointment_id
            LEFT JOIN invoices     ref_inv  ON ref_inv.appointment_id = ref_appt.appointment_id
                                           AND ref_inv.invoice_type   = 'APPOINTMENT'
                                           AND ref_inv.invoice_id    <> i.invoice_id
            WHERE i.invoice_id = %s
            LIMIT 1
            """,
            (invoice_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
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


# ---------------------------------------------------------------------------
# toggle_payment
# ---------------------------------------------------------------------------

def toggle_payment(invoice_id, user_role, user_email):
    """
    Toggle invoice between PAID and UNPAID.
    Returns {'success': True/False, 'message': str}.
    PostgreSQL-compatible: uses CURRENT_TIMESTAMP, RETURNING, COALESCE.
    """
    conn = None
    cursor = None
    try:
        conn = _get_conn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Lock the row
        cursor.execute(
            "SELECT invoice_id, status, doctor_id, total_amount FROM invoices WHERE invoice_id = %s FOR UPDATE",
            (invoice_id,),
        )
        inv = cursor.fetchone()
        if not inv:
            conn.rollback()
            return {"success": False, "message": "Invoice not found."}

        # RBAC: DOCTOR may only toggle their own invoices
        if user_role == "DOCTOR":
            cursor.execute(
                "SELECT doctor_id FROM users WHERE email = %s LIMIT 1", (user_email,)
            )
            u = cursor.fetchone()
            if not u or u.get("doctor_id") != inv.get("doctor_id"):
                conn.rollback()
                return {"success": False, "message": "Access denied."}

        current_status = inv.get("status", "UNPAID")
        total_amount = _to_float(inv.get("total_amount", 0))

        if current_status == "UNPAID":
            new_status   = "PAID"
            paid_amount   = total_amount
            balance_amount = 0.0
            # PostgreSQL: CURRENT_TIMESTAMP
            cursor.execute(
                """
                UPDATE invoices
                SET status         = %s,
                    paid_amount    = %s,
                    balance_amount = %s,
                    payment_date   = CURRENT_TIMESTAMP
                WHERE invoice_id = %s
                """,
                (new_status, paid_amount, balance_amount, invoice_id),
            )
        else:
            new_status    = "UNPAID"
            paid_amount   = 0.0
            balance_amount = total_amount
            cursor.execute(
                """
                UPDATE invoices
                SET status         = %s,
                    paid_amount    = %s,
                    balance_amount = %s,
                    payment_date   = NULL
                WHERE invoice_id = %s
                """,
                (new_status, paid_amount, balance_amount, invoice_id),
            )

        conn.commit()
        return {"success": True, "message": f"Invoice marked as {new_status}."}

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return {"success": False, "message": str(e)}
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


# ---------------------------------------------------------------------------
# get_doctor_invoice_earnings
# ---------------------------------------------------------------------------

def get_doctor_invoice_earnings(user_role=None, user_email=None):
    """
    Return per-doctor earnings aggregated from invoices.
    PostgreSQL-compatible: EXTRACT, COALESCE, no IFNULL/MySQL functions.
    """
    conn = None
    cursor = None
    try:
        conn = _get_conn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = """
            SELECT
                d.doctor_id,
                d.name                                          AS doctor_name,
                d.specialization,
                COALESCE(d.commission_percentage, 0)           AS commission_percentage,
                COUNT(i.invoice_id)                            AS total_invoices,
                COALESCE(SUM(i.total_amount), 0)               AS total_billed,
                COALESCE(SUM(CASE WHEN i.status = 'PAID'
                                  THEN i.total_amount ELSE 0 END), 0) AS total_paid,
                COALESCE(SUM(CASE WHEN i.status = 'UNPAID'
                                  THEN i.total_amount ELSE 0 END), 0) AS total_pending,
                COALESCE(SUM(CASE WHEN i.status = 'PAID'
                                  THEN i.total_amount ELSE 0 END)
                         * COALESCE(d.commission_percentage, 0) / 100, 0) AS commission_earned,
                COALESCE(SUM(
                    CASE WHEN i.status = 'PAID'
                         AND EXTRACT(MONTH FROM COALESCE(i.payment_date, i.created_at))
                             = EXTRACT(MONTH FROM CURRENT_DATE)
                         AND EXTRACT(YEAR  FROM COALESCE(i.payment_date, i.created_at))
                             = EXTRACT(YEAR  FROM CURRENT_DATE)
                    THEN i.total_amount ELSE 0 END
                ), 0)                                          AS this_month_revenue
            FROM doctors d
            LEFT JOIN invoices i ON d.doctor_id = i.doctor_id
        """
        params = []

        if user_role == "DOCTOR":
            cursor.execute(
                "SELECT doctor_id FROM users WHERE email = %s LIMIT 1", (user_email,)
            )
            u = cursor.fetchone()
            doctor_id = u.get("doctor_id") if u else None
            if doctor_id:
                query += " WHERE d.doctor_id = %s"
                params.append(doctor_id)
            else:
                return []

        query += " GROUP BY d.doctor_id, d.name, d.specialization, d.commission_percentage"
        query += " ORDER BY total_billed DESC"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]

    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return []
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
