"""
⚠️  DOCUMENTATION FILE - NOT EXECUTABLE
=====================================

This file is a REFERENCE/DOCUMENTATION of RBAC implementation patterns and code examples.
It is NOT meant to be run directly - it's missing Flask app context and imports.

The actual implementation is in app.py

This file shows:
1. @role_required() decorator implementation
2. Role-based dashboard route
3. Role-based leads route
4. Admin-only route protection examples
5. Updated context processor
6. Jinja template examples
7. Testing procedures
8. Common patterns and copy-paste templates

For production use, see: app.py
For step-by-step guide, see: RBAC_IMPLEMENTATION_GUIDE.md
"""

def role_required(required_role):
    """
    Decorator to require specific role for route access.
    
    Args:
        required_role (str): Required role ('ADMIN', 'DOCTOR', 'STAFF')
    
    Usage:
        @app.route('/admin-only')
        @role_required('ADMIN')
        def admin_page():
            return render_template('admin.html')
    
    Behavior:
        - If user not logged in: Redirect to login
        - If user has wrong role: Redirect to dashboard with error message
        - If user has correct role: Execute route normally
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            # Check if user is logged in
            if 'user' not in session:
                return redirect(url_for('index'))
            
            # Check if user has required role
            user_role = session.get('role')
            if user_role != required_role:
                flash(f'Access denied. This page requires {required_role} role.', 'danger')
                return redirect(url_for('dashboard'))
            
            # User has correct role, execute route
            return view_func(*args, **kwargs)
        return wrapped_view
    return decorator


# ============================================================================
# 2. ROLE-BASED DASHBOARD ROUTE
# ============================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    """
    Main dashboard with role-based metrics from MySQL.
    
    - ADMIN/STAFF: See stats for ALL leads
    - DOCTOR: See stats for only their assigned leads
    """
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        user_role = session.get('role', 'STAFF')
        stats = []
        
        if user_role == 'DOCTOR':
            # DOCTOR: Show only their leads
            doctor_id = session.get('doctor_id')
            if doctor_id:
                # Total leads assigned to this doctor
                cursor.execute(
                    "SELECT COUNT(*) as total FROM leads WHERE assigned_to = %s",
                    (doctor_id,)
                )
                total_leads = cursor.fetchone()['total'] or 0
                
                # Converted leads for this doctor
                cursor.execute(
                    "SELECT COUNT(*) as converted FROM leads WHERE assigned_to = %s AND status = 'CONVERTED'",
                    (doctor_id,)
                )
                converted_leads = cursor.fetchone()['converted'] or 0
                
                # Pending follow-ups for this doctor
                cursor.execute(
                    "SELECT COUNT(*) as pending FROM leads WHERE assigned_to = %s AND status = 'CONTACTED'",
                    (doctor_id,)
                )
                pending_followups = cursor.fetchone()['pending'] or 0
            else:
                total_leads = converted_leads = pending_followups = 0
                flash('Doctor ID not found. Please contact administrator.', 'warning')
        
        else:  # ADMIN or STAFF
            # Show ALL leads across clinic
            cursor.execute("SELECT COUNT(*) as total FROM leads")
            total_leads = cursor.fetchone()['total'] or 0
            
            cursor.execute("SELECT COUNT(*) as converted FROM leads WHERE status = 'CONVERTED'")
            converted_leads = cursor.fetchone()['converted'] or 0
            
            cursor.execute("SELECT COUNT(*) as pending FROM leads WHERE status = 'CONTACTED'")
            pending_followups = cursor.fetchone()['pending'] or 0
        
        # Calculate conversion rate
        conversion_rate = round((converted_leads / total_leads * 100), 1) if total_leads > 0 else 0
        
        # Build stats array
        stats = [
            {
                'title': 'Total Leads',
                'value': str(total_leads),
                'trend': 'All leads',
                'icon': '👥',
                'color': 'blue'
            },
            {
                'title': 'Conversion Rate',
                'value': f'{conversion_rate}%',
                'trend': f'{converted_leads} converted',
                'icon': '📈',
                'color': 'amber'
            },
            {
                'title': 'Pending Follow-ups',
                'value': str(pending_followups),
                'trend': 'Awaiting contact',
                'icon': '📞',
                'color': 'yellow'
            },
            {
                'title': 'Converted',
                'value': str(converted_leads),
                'trend': 'Closed deals',
                'icon': '✅',
                'color': 'green'
            }
        ]
        
    except Error as e:
        app.logger.error(f'Database error in dashboard: {e}')
        flash('Error loading dashboard. Please try again.', 'danger')
        stats = []
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    
    return render_template('dashboard.html', stats=stats)


# ============================================================================
# 3. ROLE-BASED LEADS ROUTE
# ============================================================================

@app.route('/leads')
@login_required
def leads():
    """
    Leads management page with role-based access control.
    
    - ADMIN/STAFF: See ALL leads
    - DOCTOR: See only leads assigned to them
    """
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get user role from session
        user_role = session.get('role', 'STAFF')
        user_email = session.get('user')
        
        # Base query with LEFT JOIN to get doctor names
        base_query = """
            SELECT 
                l.lead_id,
                l.name,
                l.service,
                l.source,
                l.status,
                l.last_contacted,
                l.assigned_to,
                d.name AS doctor_name
            FROM leads l
            LEFT JOIN doctors d
                ON l.assigned_to = d.doctor_id
        """
        
        # Role-based filtering
        if user_role == 'DOCTOR':
            # DOCTOR role: Fetch doctor_id from users table using email
            cursor.execute("SELECT doctor_id FROM users WHERE email = %s", (user_email,))
            user_data = cursor.fetchone()
            
            if user_data and user_data['doctor_id']:
                doctor_id = user_data['doctor_id']
                # Filter leads assigned to this doctor only
                query = base_query + " WHERE l.assigned_to = %s ORDER BY l.lead_id DESC"
                cursor.execute(query, (doctor_id,))
            else:
                # No doctor_id found for this doctor user
                flash('Doctor ID not found. Please contact administrator.', 'warning')
                leads = []
                return render_template('leads.html', leads=leads)
        
        elif user_role in ['ADMIN', 'STAFF']:
            # ADMIN and STAFF: Show all leads
            query = base_query + " ORDER BY l.lead_id DESC"
            cursor.execute(query)
        
        else:
            # Unknown role - deny access
            flash('Invalid user role. Access denied.', 'danger')
            leads = []
            return render_template('leads.html', leads=leads)
        
        # Fetch all results
        leads = cursor.fetchall()
        
        # Log access for audit trail
        app.logger.info(f'User {user_email} (Role: {user_role}) accessed leads. Records: {len(leads)}')
        
    except Error as e:
        app.logger.error(f'Database error in leads route: {e}')
        flash('An error occurred while fetching leads. Please try again.', 'danger')
        leads = []
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    
    return render_template('leads.html', leads=leads)


# ============================================================================
# 4. ADMIN-ONLY ROUTES EXAMPLES
# ============================================================================

@app.route('/add-doctor', methods=['GET', 'POST'])
@role_required('ADMIN')
def add_doctor():
    """
    Add new doctor - ADMIN ONLY.
    
    If non-ADMIN user tries to access:
    - Redirects to /dashboard
    - Shows: "Access denied. This page requires ADMIN role."
    """
    if request.method == 'POST':
        # Handle form submission
        return jsonify({'success': True, 'message': 'Doctor added'})
    return render_template('add-doctor.html')


@app.route('/scraped-leads')
@role_required('ADMIN')
def scraped_leads():
    """
    Scraped leads page - ADMIN ONLY.
    Shows leads from external sources (web scraping, imports, etc).
    """
    # TODO: Implement MySQL query for scraped leads
    leads = []
    return render_template('scraped-leads.html', leads=leads)


@app.route('/campaigns')
@role_required('ADMIN')
def campaigns():
    """
    Campaigns management page - ADMIN ONLY.
    Manages marketing campaigns and lead sources.
    """
    # TODO: Implement MySQL query for campaigns
    campaigns = []
    return render_template('campaigns.html', campaigns=campaigns)


# ============================================================================
# 5. UPDATED CONTEXT PROCESSOR
# ============================================================================

@app.context_processor
def inject_user():
    """
    Inject user data into all templates.
    
    Available in all templates:
    - current_user: User's name
    - user_role: User's role (ADMIN, DOCTOR, STAFF)
    - user_email: User's email address
    - doctor_id: Doctor's ID (if user is a doctor, else None)
    """
    return {
        'current_user': session.get('user_name'),
        'user_role': session.get('role'),
        'user_email': session.get('user'),
        'doctor_id': session.get('doctor_id')
    }


# ============================================================================
# 6. JINJA TEMPLATE EXAMPLES
# ============================================================================

"""
BASE.HTML - SIDEBAR WITH CONDITIONAL ADMIN ITEMS

<!-- Sales & Marketing Section -->
<div class="pt-4">
    <p class="px-4 py-2 text-xs font-bold text-slate-500 uppercase">Sales & Marketing</p>
    
    <!-- Always visible -->
    <a href="{{ url_for('leads') }}" class="sidebar-link ...">
        <span class="text-lg">🎯</span>
        <span>Leads</span>
    </a>
    
    <!-- ADMIN ONLY -->
    {% if user_role == 'ADMIN' %}
    <a href="{{ url_for('scraped_leads') }}" class="sidebar-link ...">
        <span class="text-lg">🔄</span>
        <span>Scraped Leads</span>
    </a>
    
    <a href="{{ url_for('campaigns') }}" class="sidebar-link ...">
        <span class="text-lg">📢</span>
        <span>Campaigns</span>
    </a>
    {% endif %}
</div>

<!-- Clinic Management Section -->
<div class="pt-4">
    <p class="px-4 py-2 text-xs font-bold text-slate-500 uppercase">Clinic Management</p>
    
    <!-- Always visible -->
    <a href="{{ url_for('doctors') }}" class="sidebar-link ...">
        <span class="text-lg">👨‍⚕️</span>
        <span>Doctors</span>
    </a>
    
    <!-- ADMIN ONLY -->
    {% if user_role == 'ADMIN' %}
    <a href="{{ url_for('add_doctor') }}" class="sidebar-link ...">
        <span class="text-lg">➕</span>
        <span>Add Doctor</span>
    </a>
    {% endif %}
</div>
"""

"""
DASHBOARD.HTML - SHOW ROLE-SPECIFIC MESSAGE

<div class="mb-6">
    <h1 class="text-3xl font-bold text-slate-900">Dashboard</h1>
    
    {% if user_role == 'DOCTOR' %}
        <p class="text-slate-600">Your assigned leads and metrics</p>
    {% elif user_role == 'ADMIN' %}
        <p class="text-slate-600">Complete clinic overview</p>
    {% else %}
        <p class="text-slate-600">Staff dashboard</p>
    {% endif %}
</div>
"""

"""
LEADS.HTML - ROLE-SPECIFIC TABLE ACTIONS

<table>
    <thead>
        <tr>
            <th>Lead Name</th>
            <th>Service</th>
            <th>Status</th>
            {% if user_role != 'DOCTOR' %}
                <th>Assigned To</th>
            {% endif %}
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        {% for lead in leads %}
        <tr>
            <td>{{ lead.name }}</td>
            <td>{{ lead.service }}</td>
            <td>{{ lead.status }}</td>
            {% if user_role != 'DOCTOR' %}
                <td>{{ lead.doctor_name or 'Unassigned' }}</td>
            {% endif %}
            <td>
                <a href="#" class="text-blue-600">View</a>
                {% if user_role in ['ADMIN', 'STAFF'] %}
                    <a href="#" class="text-blue-600">Edit</a>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
"""


# ============================================================================
# 7. TESTING THE RBAC SYSTEM
# ============================================================================

"""
HOW TO TEST RBAC

1. Test Doctor Access:
   - Login as doctor@example.com
   - Visit /dashboard → Should see only their leads stats
   - Visit /leads → Should see only their assigned leads
   - Try to visit /add-doctor → Should see error and redirect to dashboard
   - Check sidebar → "Scraped Leads", "Campaigns", "Add Doctor" should be hidden

2. Test Admin Access:
   - Login as admin@example.com
   - Visit /dashboard → Should see all clinic leads stats
   - Visit /leads → Should see ALL leads
   - Visit /add-doctor → Should work without error
   - Check sidebar → All items including admin-only should be visible

3. Test Staff Access:
   - Login as staff@example.com
   - Visit /dashboard → Should see all clinic leads stats (like admin)
   - Visit /leads → Should see ALL leads (like admin)
   - Try to visit /add-doctor → Should see error and redirect to dashboard

4. Test Security:
   - Try SQL injection in search → Should be protected (parameterized queries)
   - Try accessing admin route without auth → Should redirect to login
   - Try accessing admin route as doctor → Should redirect to dashboard
"""


# ============================================================================
# 8. COMMON PATTERNS - COPY & PASTE
# ============================================================================

"""
PATTERN: Doctor-Only View of Resource
--------------------------------------
@app.route('/my-patients')
@login_required
def my_patients():
    doctor_id = session.get('doctor_id')
    if not doctor_id:
        flash('Doctor ID not found', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get only this doctor's patients
    cursor.execute("SELECT * FROM patients WHERE assigned_doctor = %s", (doctor_id,))
    patients = cursor.fetchall()
    return render_template('my_patients.html', patients=patients)


PATTERN: Admin-Only Action
---------------------------
@app.route('/delete-campaign/<int:campaign_id>', methods=['POST'])
@role_required('ADMIN')
def delete_campaign(campaign_id):
    # Only admins can reach here
    cursor.execute("DELETE FROM campaigns WHERE id = %s", (campaign_id,))
    conn.commit()
    flash('Campaign deleted', 'success')
    return redirect(url_for('campaigns'))


PATTERN: Role-Based View of Same Resource
------------------------------------------
@app.route('/reports')
@login_required
def reports():
    if session.get('role') == 'DOCTOR':
        # Only their reports
        cursor.execute(
            "SELECT * FROM reports WHERE doctor_id = %s",
            (session.get('doctor_id'),)
        )
    else:
        # All reports
        cursor.execute("SELECT * FROM reports")
    
    reports = cursor.fetchall()
    return render_template('reports.html', reports=reports)
"""
