"""
⚠️  DOCUMENTATION FILE - NOT EXECUTABLE
=====================================

This file is a REFERENCE/DOCUMENTATION of the leads route implementation.
It is NOT meant to be run directly.

The actual implementation is in app.py

This file shows the structure and logic for reference purposes only.
Copy/paste relevant parts into app.py if needed.

For production use, see: app.py - /leads route
"""
def leads():
    """
    Display leads with role-based filtering.
    
    Access Control Logic:
    - ADMIN: See all leads
    - DOCTOR: See only assigned leads
    - STAFF: See all leads
    
    Returns:
        Rendered leads.html template with filtered leads data
    """
    
    # Step 1: Check if user is authenticated
    if 'user_id' not in session:
        flash('Please log in first', 'warning')
        return redirect(url_for('login'))
    
    cursor = None
    conn = None
    
    try:
        # Step 2: Establish database connection
        conn = mysql.connector.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            database=app.config['MYSQL_DB']
        )
        
        # Step 3: Create cursor with dictionary=True for named results
        cursor = conn.cursor(dictionary=True)
        
        # Step 4: Get user role from session
        user_role = session.get('role', 'STAFF')  # Default to STAFF if not set
        user_id = session.get('user_id')
        doctor_id = session.get('doctor_id')  # Only populated for DOCTOR role
        
        # Step 5: Build and execute query based on role
        leads_data = []
        
        if user_role == 'DOCTOR':
            # DOCTOR: Show only leads assigned to them
            if doctor_id is None:
                flash('Doctor ID not found in session', 'danger')
                return redirect(url_for('dashboard'))
            
            query = """
                SELECT 
                    l.lead_id,
                    l.lead_name,
                    l.email,
                    l.phone,
                    l.status,
                    l.assigned_to,
                    l.created_at,
                    l.updated_at,
                    d.doctor_name
                FROM leads l
                LEFT JOIN doctors d ON l.assigned_to = d.doctor_id
                WHERE l.assigned_to = %s
                ORDER BY l.created_at DESC
            """
            cursor.execute(query, (doctor_id,))
        
        elif user_role == 'ADMIN':
            # ADMIN: Show all leads with doctor assignment info
            query = """
                SELECT 
                    l.lead_id,
                    l.lead_name,
                    l.email,
                    l.phone,
                    l.status,
                    l.assigned_to,
                    l.created_at,
                    l.updated_at,
                    d.doctor_name
                FROM leads l
                LEFT JOIN doctors d ON l.assigned_to = d.doctor_id
                ORDER BY l.created_at DESC
            """
            cursor.execute(query)
        
        elif user_role == 'STAFF':
            # STAFF: Show all leads with doctor assignment info
            query = """
                SELECT 
                    l.lead_id,
                    l.lead_name,
                    l.email,
                    l.phone,
                    l.status,
                    l.assigned_to,
                    l.created_at,
                    l.updated_at,
                    d.doctor_name
                FROM leads l
                LEFT JOIN doctors d ON l.assigned_to = d.doctor_id
                ORDER BY l.created_at DESC
            """
            cursor.execute(query)
        
        else:
            # Unknown role - default to empty (security first)
            flash('Invalid user role. Access denied.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Step 6: Fetch results
        leads_data = cursor.fetchall()
        
        # Log access for security audit
        app.logger.info(f'User {user_id} (Role: {user_role}) accessed leads page. Records: {len(leads_data)}')
        
        # Step 7: Close cursor
        cursor.close()
        
        # Step 8: Render template with leads
        return render_template(
            'leads.html',
            leads=leads_data,
            user_role=user_role,
            user_id=user_id,
            doctor_id=doctor_id or '',
            total_leads=len(leads_data)
        )
    
    except MySQLError as db_err:
        # Database-specific errors
        app.logger.error(f'Database error in leads route: {db_err}')
        flash(f'Database error occurred. Please try again later.', 'danger')
        return redirect(url_for('dashboard'))
    
    except KeyError as key_err:
        # Missing session data
        app.logger.error(f'Session key error in leads route: {key_err}')
        flash('Session error. Please log in again.', 'danger')
        return redirect(url_for('login'))
    
    except Exception as err:
        # Catch-all for other errors
        app.logger.error(f'Unexpected error in leads route: {err}')
        flash('An unexpected error occurred. Please try again later.', 'danger')
        return redirect(url_for('dashboard'))
    
    finally:
        # Step 9: Always close cursor and connection (cleanup)
        if cursor is not None:
            try:
                cursor.close()
            except MySQLError as err:
                app.logger.warning(f'Error closing cursor: {err}')
        
        if conn is not None:
            try:
                conn.close()
            except MySQLError as err:
                app.logger.warning(f'Error closing connection: {err}')


# ============================================
# OPTIONAL: ADD THIS TO YOUR JINJA TEMPLATE
# ============================================

"""
In your leads.html template, you can check the user role:

{% extends "base.html" %}

{% block content %}
<div class="container">
    <div class="leads-header">
        <h1>Leads Management</h1>
        {% if user_role == 'DOCTOR' %}
            <p class="text-muted">Showing your assigned leads</p>
        {% elif user_role == 'ADMIN' %}
            <p class="text-muted">Showing all leads (Admin view)</p>
        {% elif user_role == 'STAFF' %}
            <p class="text-muted">Showing all leads (Staff view)</p>
        {% endif %}
    </div>
    
    <div class="leads-count">
        Total Leads: {{ total_leads }}
    </div>
    
    {% if leads %}
        <table class="table table-striped">
            <thead>
                <tr>
                    <th>Lead Name</th>
                    <th>Email</th>
                    <th>Phone</th>
                    <th>Status</th>
                    {% if user_role != 'DOCTOR' %}
                        <th>Assigned To</th>
                    {% endif %}
                    <th>Created</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for lead in leads %}
                <tr>
                    <td>{{ lead.lead_name }}</td>
                    <td>{{ lead.email }}</td>
                    <td>{{ lead.phone }}</td>
                    <td>
                        <span class="badge badge-{{ 'success' if lead.status == 'converted' else 'warning' if lead.status == 'pending' else 'secondary' }}">
                            {{ lead.status }}
                        </span>
                    </td>
                    {% if user_role != 'DOCTOR' %}
                        <td>{{ lead.doctor_name or 'Unassigned' }}</td>
                    {% endif %}
                    <td>{{ lead.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
                    <td>
                        <a href="{{ url_for('view_lead', lead_id=lead.lead_id) }}" class="btn btn-sm btn-info">View</a>
                        {% if user_role in ['ADMIN', 'STAFF'] %}
                            <a href="{{ url_for('edit_lead', lead_id=lead.lead_id) }}" class="btn btn-sm btn-warning">Edit</a>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <div class="alert alert-info">
            {% if user_role == 'DOCTOR' %}
                No leads assigned to you yet.
            {% else %}
                No leads found in the system.
            {% endif %}
        </div>
    {% endif %}
</div>
{% endblock %}
"""
