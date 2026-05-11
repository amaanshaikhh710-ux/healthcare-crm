from db import get_db_connection
from mysql.connector import Error


def get_finance_dashboard():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Total Revenue (PAID)
        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) AS total_revenue FROM invoices WHERE status = 'PAID'")
        total_revenue = cursor.fetchone()['total_revenue']

        # Pending Revenue (UNPAID balance)
        cursor.execute("SELECT COALESCE(SUM(balance_amount), 0) AS pending_revenue FROM invoices WHERE status = 'UNPAID'")
        pending_revenue = cursor.fetchone()['pending_revenue']

        # This Month Revenue
        cursor.execute(
            "SELECT COALESCE(SUM(total_amount), 0) AS this_month FROM invoices WHERE status = 'PAID' AND MONTH(payment_date) = MONTH(CURDATE()) AND YEAR(payment_date) = YEAR(CURDATE())"
        )
        this_month_revenue = cursor.fetchone()['this_month']

        # Total invoices and paid count
        cursor.execute("SELECT COUNT(*) AS total_invoices FROM invoices")
        total_invoices = cursor.fetchone()['total_invoices']

        cursor.execute("SELECT COUNT(*) AS paid_count FROM invoices WHERE status = 'PAID'")
        paid_count = cursor.fetchone()['paid_count']

        # Monthly revenue (year, month)
        cursor.execute(
            "SELECT YEAR(payment_date) AS yr, MONTH(payment_date) AS mth, COALESCE(SUM(total_amount), 0) AS revenue "
            "FROM invoices WHERE status = 'PAID' GROUP BY yr, mth ORDER BY yr DESC, mth DESC"
        )
        monthly = cursor.fetchall()

        # Revenue per doctor with commission
        cursor.execute(
            "SELECT d.doctor_id, d.name AS doctor_name, COALESCE(d.commission_percentage, 40) AS commission_percentage, "
            "COALESCE(SUM(i.total_amount), 0) AS revenue "
            "FROM doctors d LEFT JOIN invoices i ON d.doctor_id = i.doctor_id AND i.status = 'PAID' "
            "GROUP BY d.doctor_id, d.name, d.commission_percentage ORDER BY revenue DESC"
        )
        per_doctor = cursor.fetchall()

        return {
            'total_revenue': float(total_revenue or 0),
            'pending_revenue': float(pending_revenue or 0),
            'this_month_revenue': float(this_month_revenue or 0),
            'total_invoices': int(total_invoices or 0),
            'paid_count': int(paid_count or 0),
            'monthly': monthly,
            'per_doctor': per_doctor,
        }

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_doctor_earnings():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT d.doctor_id, d.name AS doctor_name, COALESCE(d.commission_percentage, 40) AS commission_percentage, "
            "COUNT(i.invoice_id) AS total_cases, COALESCE(SUM(i.total_amount), 0) AS total_revenue "
            "FROM doctors d LEFT JOIN invoices i ON d.doctor_id = i.doctor_id AND i.status = 'PAID' "
            "GROUP BY d.doctor_id, d.name, d.commission_percentage ORDER BY total_revenue DESC"
        )
        rows = cursor.fetchall()

        # Calculate earnings based on commission percentage
        result = []
        for r in rows:
            total_revenue = float(r.get('total_revenue') or 0)
            commission_pct = float(r.get('commission_percentage') or 40)
            earning = round(total_revenue * commission_pct / 100, 2)
            result.append({
                'doctor_id': r.get('doctor_id'),
                'doctor_name': r.get('doctor_name'),
                'total_cases': int(r.get('total_cases') or 0),
                'total_revenue': total_revenue,
                'commission_percentage': commission_pct,
                'earning': earning,
            })

        return result

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_analytics():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Monthly revenue for last 12 months
        cursor.execute(
            "SELECT YEAR(created_at) AS yr, MONTH(created_at) AS mth, COALESCE(SUM(total_amount),0) AS revenue "
            "FROM invoices WHERE status = 'PAID' GROUP BY yr, mth ORDER BY yr DESC, mth DESC LIMIT 12"
        )
        monthly = cursor.fetchall()

        # Top 5 doctors by revenue
        cursor.execute(
            "SELECT d.name AS doctor_name, COALESCE(SUM(i.total_amount),0) AS revenue "
            "FROM invoices i LEFT JOIN doctors d ON i.doctor_id = d.doctor_id WHERE i.status = 'PAID' GROUP BY d.doctor_id, d.name ORDER BY revenue DESC LIMIT 5"
        )
        top_doctors = cursor.fetchall()

        # Conversion rate: leads -> appointments
        cursor.execute("SELECT COUNT(*) AS total_leads FROM leads WHERE status != 'SCRAPED'")
        total_leads = cursor.fetchone()['total_leads'] or 0

        cursor.execute("SELECT COUNT(DISTINCT lead_id) AS total_converted FROM appointments WHERE lead_id IS NOT NULL")
        total_converted = cursor.fetchone()['total_converted'] or 0

        conversion_rate = round((total_converted / total_leads * 100), 2) if total_leads > 0 else 0

        # Appointment status distribution
        cursor.execute("SELECT status, COUNT(*) AS count FROM appointments GROUP BY status")
        appt_dist = cursor.fetchall()

        return {
            'monthly': monthly,
            'top_doctors': top_doctors,
            'conversion_rate': conversion_rate,
            'appointment_distribution': appt_dist,
        }

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
