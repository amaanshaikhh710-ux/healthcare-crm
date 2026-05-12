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
# get_finance_dashboard
# ---------------------------------------------------------------------------

def get_finance_dashboard():
    """
    Return structured finance KPIs and monthly/doctor breakdowns.
    Fully PostgreSQL-compatible:
      - EXTRACT instead of MONTH()/YEAR()
      - TO_CHAR instead of DATE_FORMAT()
      - CURRENT_DATE / CURRENT_TIMESTAMP instead of CURDATE() / NOW()
      - INTERVAL syntax instead of DATE_SUB/DATE_ADD
      - COALESCE instead of IFNULL
      - || instead of CONCAT (where needed)
    """
    conn = None
    cursor = None
    try:
        conn = _get_conn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ── Overall KPIs ────────────────────────────────────────────────────
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(total_amount), 0)                                         AS total_revenue,
                COALESCE(SUM(CASE WHEN status = 'PAID'   THEN total_amount ELSE 0 END), 0) AS paid_revenue,
                COALESCE(SUM(CASE WHEN status = 'UNPAID' THEN total_amount ELSE 0 END), 0) AS pending_revenue,
                COALESCE(SUM(
                    CASE WHEN status = 'PAID'
                         AND EXTRACT(MONTH FROM COALESCE(payment_date, created_at))
                             = EXTRACT(MONTH FROM CURRENT_DATE)
                         AND EXTRACT(YEAR  FROM COALESCE(payment_date, created_at))
                             = EXTRACT(YEAR  FROM CURRENT_DATE)
                    THEN total_amount ELSE 0 END
                ), 0)                                                                   AS this_month_revenue,
                COUNT(*)                                                                AS total_invoices,
                COUNT(CASE WHEN status = 'PAID'   THEN 1 END)                          AS paid_count,
                COUNT(CASE WHEN status = 'UNPAID' THEN 1 END)                          AS unpaid_count
            FROM invoices
            """
        )
        kpi = cursor.fetchone() or {}

        # ── Monthly revenue trend (last 12 months) ──────────────────────────
        cursor.execute(
            """
            SELECT
                TO_CHAR(COALESCE(payment_date, created_at), 'YYYY-MM') AS month,
                COALESCE(SUM(total_amount), 0)                          AS revenue,
                COUNT(*)                                                AS invoice_count
            FROM invoices
            WHERE status = 'PAID'
              AND COALESCE(payment_date, created_at) >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY month
            ORDER BY month ASC
            """
        )
        monthly_raw = cursor.fetchall() or []
        monthly = [
            {
                "month":         r["month"],
                "revenue":       _to_float(r["revenue"]),
                "invoice_count": int(r["invoice_count"] or 0),
            }
            for r in monthly_raw
        ]

        # ── Per-doctor revenue ───────────────────────────────────────────────
        cursor.execute(
            """
            SELECT
                d.doctor_id,
                d.name                                                    AS doctor_name,
                d.specialization,
                COALESCE(d.commission_percentage, 0)                      AS commission_percentage,
                COUNT(i.invoice_id)                                       AS total_invoices,
                COALESCE(SUM(i.total_amount), 0)                          AS total_billed,
                COALESCE(SUM(CASE WHEN i.status = 'PAID'
                                  THEN i.total_amount ELSE 0 END), 0)     AS paid_revenue,
                COALESCE(SUM(CASE WHEN i.status = 'UNPAID'
                                  THEN i.total_amount ELSE 0 END), 0)     AS pending_revenue,
                COALESCE(
                    SUM(CASE WHEN i.status = 'PAID' THEN i.total_amount ELSE 0 END)
                    * COALESCE(d.commission_percentage, 0) / 100
                , 0)                                                       AS commission_earned,
                COALESCE(SUM(
                    CASE WHEN i.status = 'PAID'
                         AND EXTRACT(MONTH FROM COALESCE(i.payment_date, i.created_at))
                             = EXTRACT(MONTH FROM CURRENT_DATE)
                         AND EXTRACT(YEAR  FROM COALESCE(i.payment_date, i.created_at))
                             = EXTRACT(YEAR  FROM CURRENT_DATE)
                    THEN i.total_amount ELSE 0 END
                ), 0)                                                      AS this_month_revenue
            FROM doctors d
            LEFT JOIN invoices i ON d.doctor_id = i.doctor_id
            GROUP BY d.doctor_id, d.name, d.specialization, d.commission_percentage
            ORDER BY total_billed DESC
            """
        )
        per_doctor_raw = cursor.fetchall() or []
        per_doctor = [
            {
                "doctor_id":           r["doctor_id"],
                "doctor_name":         r["doctor_name"],
                "specialization":      r["specialization"],
                "commission_percentage": _to_float(r["commission_percentage"]),
                "total_invoices":      int(r["total_invoices"] or 0),
                "total_billed":        _to_float(r["total_billed"]),
                "paid_revenue":        _to_float(r["paid_revenue"]),
                "pending_revenue":     _to_float(r["pending_revenue"]),
                "commission_earned":   _to_float(r["commission_earned"]),
                "this_month_revenue":  _to_float(r["this_month_revenue"]),
            }
            for r in per_doctor_raw
        ]

        return {
            "total_revenue":      _to_float(kpi.get("total_revenue", 0)),
            "paid_revenue":       _to_float(kpi.get("paid_revenue", 0)),
            "pending_revenue":    _to_float(kpi.get("pending_revenue", 0)),
            "this_month_revenue": _to_float(kpi.get("this_month_revenue", 0)),
            "total_invoices":     int(kpi.get("total_invoices", 0) or 0),
            "paid_count":         int(kpi.get("paid_count", 0) or 0),
            "unpaid_count":       int(kpi.get("unpaid_count", 0) or 0),
            "monthly":            monthly,
            "per_doctor":         per_doctor,
        }

    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return {
            "total_revenue": 0, "paid_revenue": 0, "pending_revenue": 0,
            "this_month_revenue": 0, "total_invoices": 0,
            "paid_count": 0, "unpaid_count": 0,
            "monthly": [], "per_doctor": [],
        }
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
# get_doctor_earnings  (alias used by some routes)
# ---------------------------------------------------------------------------

def get_doctor_earnings(user_role=None, user_email=None):
    """Thin wrapper — returns per_doctor list from finance dashboard."""
    data = get_finance_dashboard()
    return data.get("per_doctor", [])


# ---------------------------------------------------------------------------
# get_analytics
# ---------------------------------------------------------------------------

def get_analytics():
    """
    Return JSON-ready analytics payload.
    PostgreSQL-compatible: TO_CHAR, EXTRACT, INTERVAL, COALESCE, no MySQL funcs.
    """
    conn = None
    cursor = None
    try:
        conn = _get_conn()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ── Monthly revenue (last 12 months) ────────────────────────────────
        cursor.execute(
            """
            SELECT
                TO_CHAR(COALESCE(payment_date, created_at), 'YYYY-MM') AS month,
                COALESCE(SUM(total_amount), 0)                          AS revenue
            FROM invoices
            WHERE status = 'PAID'
              AND COALESCE(payment_date, created_at) >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY month
            ORDER BY month ASC
            """
        )
        monthly_revenue = [
            {"month": r["month"], "revenue": _to_float(r["revenue"])}
            for r in (cursor.fetchall() or [])
        ]

        # ── Top 5 doctors by revenue ─────────────────────────────────────────
        cursor.execute(
            """
            SELECT
                d.name                                                AS doctor_name,
                COALESCE(SUM(CASE WHEN i.status = 'PAID'
                                  THEN i.total_amount ELSE 0 END), 0) AS total_revenue,
                COUNT(i.invoice_id)                                   AS invoice_count
            FROM doctors d
            LEFT JOIN invoices i ON d.doctor_id = i.doctor_id
            GROUP BY d.doctor_id, d.name
            ORDER BY total_revenue DESC
            LIMIT 5
            """
        )
        top_doctors = [
            {
                "doctor_name":   r["doctor_name"],
                "total_revenue": _to_float(r["total_revenue"]),
                "invoice_count": int(r["invoice_count"] or 0),
            }
            for r in (cursor.fetchall() or [])
        ]

        # ── Conversion rate ──────────────────────────────────────────────────
        cursor.execute("SELECT COUNT(*) AS total FROM leads WHERE status != 'SCRAPED'")
        total_leads = int((cursor.fetchone() or {}).get("total", 0) or 0)

        cursor.execute("SELECT COUNT(*) AS total FROM leads WHERE status = 'CONVERTED'")
        converted = int((cursor.fetchone() or {}).get("total", 0) or 0)

        conversion_rate = round(converted / total_leads * 100, 1) if total_leads else 0

        # ── Appointment status distribution ──────────────────────────────────
        cursor.execute(
            """
            SELECT
                status,
                COUNT(*) AS count
            FROM appointments
            GROUP BY status
            ORDER BY count DESC
            """
        )
        appt_distribution = [
            {"status": r["status"], "count": int(r["count"] or 0)}
            for r in (cursor.fetchall() or [])
        ]

        # ── Lead source breakdown ────────────────────────────────────────────
        cursor.execute(
            """
            SELECT
                COALESCE(source, 'Unknown') AS source,
                COUNT(*)                    AS count
            FROM leads
            WHERE status != 'SCRAPED'
            GROUP BY source
            ORDER BY count DESC
            """
        )
        lead_sources = [
            {"source": r["source"], "count": int(r["count"] or 0)}
            for r in (cursor.fetchall() or [])
        ]

        # ── Follow-up completion rate ────────────────────────────────────────
        cursor.execute(
            """
            SELECT
                COUNT(*)                                          AS total,
                COUNT(CASE WHEN status = 'DONE'    THEN 1 END)   AS done,
                COUNT(CASE WHEN status = 'PENDING' THEN 1 END)   AS pending,
                COUNT(CASE WHEN status = 'MISSED'  THEN 1 END)   AS missed
            FROM followups
            """
        )
        fu = cursor.fetchone() or {}
        fu_total   = int(fu.get("total",   0) or 0)
        fu_done    = int(fu.get("done",    0) or 0)
        fu_pending = int(fu.get("pending", 0) or 0)
        fu_missed  = int(fu.get("missed",  0) or 0)
        fu_rate    = round(fu_done / fu_total * 100, 1) if fu_total else 0

        return {
            "monthly_revenue":      monthly_revenue,
            "top_doctors":          top_doctors,
            "conversion_rate":      conversion_rate,
            "total_leads":          total_leads,
            "converted_leads":      converted,
            "appointment_distribution": appt_distribution,
            "lead_sources":         lead_sources,
            "followup_stats": {
                "total":           fu_total,
                "done":            fu_done,
                "pending":         fu_pending,
                "missed":          fu_missed,
                "completion_rate": fu_rate,
            },
        }

    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return {}
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
