# ============================================================================
# LeadFlow CRM - Flask Application
# Production-Ready SaaS Architecture
# ============================================================================

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from functools import wraps
from datetime import datetime
import os

# ============================================================================
# INITIALIZE FLASK APP
# ============================================================================

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'your-secret-key-here-change-this-in-production'

# ============================================================================
# AUTHENTICATION DATA
# ============================================================================

USERS = {
    'admin@leadflow.com': {'password': 'admin123', 'name': 'Admin User'},
}

# ============================================================================
# SAMPLE DATA MODELS
# ============================================================================

DASHBOARD_DATA = {
    'stats': [
        {'title': 'Total Leads', 'value': '1,234', 'trend': '+12% this month'},
        {'title': 'Conversion Rate', 'value': '32.5%', 'trend': '+2.3% from last month'},
        {'title': 'Pending Follow-ups', 'value': '12', 'trend': '3 completed today'},
        {'title': 'Appointments', 'value': '24', 'trend': '5 new bookings'},
    ],
    'recent_activity': [
        {'date': 'Today 2:30 PM', 'action': 'Lead Created', 'description': 'New lead: Sarah Johnson'},
        {'date': 'Today 11:45 AM', 'action': 'Follow-up Completed', 'description': 'Called Priya Patel'},
        {'date': 'Yesterday 4:15 PM', 'action': 'Invoice Generated', 'description': 'INV-001234 for $750'},
        {'date': 'Yesterday 1:20 PM', 'action': 'Case Closed', 'description': 'Completed treatment'},
    ]
}

LEADS_DATA = [
    {'id': 1, 'name': 'Sarah Johnson', 'service': 'Acne Treatment', 'source': 'Facebook', 'doctor': 'Dr. Smith', 'status': 'New', 'last_contacted': '2 hours ago'},
    {'id': 2, 'name': 'Priya Patel', 'service': 'Hair Fall Control', 'source': 'Google', 'doctor': 'Dr. Sharma', 'status': 'Contacted', 'last_contacted': '1 day ago'},
    {'id': 3, 'name': 'Michael Brown', 'service': 'Anti-Aging', 'source': 'Referral', 'doctor': 'Dr. Johnson', 'status': 'Lost', 'last_contacted': '5 days ago'},
    {'id': 4, 'name': 'Emma Davis', 'service': 'Eczema Treatment', 'source': 'Instagram', 'doctor': 'Dr. Lee', 'status': 'New', 'last_contacted': '3 days ago'},
    {'id': 5, 'name': 'Robert Wilson', 'service': 'Psoriasis', 'source': 'Website', 'doctor': 'Dr. Garcia', 'status': 'Contacted', 'last_contacted': '1 week ago'},
]

PATIENTS_DATA = [
    {'id': 1, 'name': 'Sarah Johnson', 'status': 'Active', 'phone': '(555) 123-4567', 'email': 'sarah@example.com', 'joined': '2024-01-15', 'problem': 'Acne treatment'},
    {'id': 2, 'name': 'Priya Patel', 'status': 'Active', 'phone': '(555) 234-5678', 'email': 'priya@example.com', 'joined': '2024-02-20', 'problem': 'Hair fall control'},
    {'id': 3, 'name': 'Emma Davis', 'status': 'Inactive', 'phone': '(555) 345-6789', 'email': 'emma@example.com', 'joined': '2023-12-10', 'problem': 'Eczema treatment'},
    {'id': 4, 'name': 'Michael Brown', 'status': 'Active', 'phone': '(555) 456-7890', 'email': 'michael@example.com', 'joined': '2024-01-28', 'problem': 'Anti-aging'},
]

DOCTORS_DATA = [
    {'id': 1, 'name': 'Dr. Rajesh Smith', 'specialty': 'Dermatology', 'experience': '15 years', 'phone': '(555) 111-2222', 'email': 'dr.smith@leadflow.com'},
    {'id': 2, 'name': 'Dr. Priya Sharma', 'specialty': 'Cosmetology', 'experience': '10 years', 'phone': '(555) 222-3333', 'email': 'dr.sharma@leadflow.com'},
    {'id': 3, 'name': 'Dr. John Johnson', 'specialty': 'Dermatology', 'experience': '12 years', 'phone': '(555) 333-4444', 'email': 'dr.johnson@leadflow.com'},
]

APPOINTMENTS_DATA = [
    {'id': 1, 'patient': 'Sarah Johnson', 'doctor': 'Dr. Smith', 'datetime': '2024-02-20 10:00 AM', 'status': 'Scheduled', 'service': 'Acne Treatment'},
    {'id': 2, 'patient': 'Priya Patel', 'doctor': 'Dr. Sharma', 'datetime': '2024-02-20 11:30 AM', 'status': 'Scheduled', 'service': 'Hair Treatment'},
    {'id': 3, 'patient': 'Emma Davis', 'doctor': 'Dr. Lee', 'datetime': '2024-02-19 2:00 PM', 'status': 'Completed', 'service': 'Eczema Treatment'},
]

VISITS_DATA = [
    {'id': 1, 'patient': 'Sarah Johnson', 'doctor': 'Dr. Smith', 'date': '2024-02-15', 'notes': 'Acne improvement noted', 'status': 'Completed'},
    {'id': 2, 'patient': 'Emma Davis', 'doctor': 'Dr. Lee', 'date': '2024-02-19', 'notes': 'Treatment ongoing', 'status': 'Completed'},
]

INVOICES_DATA = [
    {'id': 'INV-001234', 'patient': 'Sarah Johnson', 'doctor': 'Dr. Smith', 'amount': 750, 'date': '2024-02-10', 'status': 'Paid'},
    {'id': 'INV-001232', 'patient': 'Priya Patel', 'doctor': 'Dr. Sharma', 'amount': 980, 'date': '2024-02-08', 'status': 'Pending'},
    {'id': 'INV-001230', 'patient': 'Michael Brown', 'doctor': 'Dr. Johnson', 'amount': 1200, 'date': '2024-02-05', 'status': 'Paid'},
]

CAMPAIGNS_DATA = [
    {'id': 1, 'name': 'Facebook Spring Campaign', 'status': 'Active', 'leads': 245, 'conversions': 52},
    {'id': 2, 'name': 'Google Ads - Acne Treatment', 'status': 'Active', 'leads': 189, 'conversions': 38},
    {'id': 3, 'name': 'Instagram Hair Care', 'status': 'Paused', 'leads': 156, 'conversions': 22},
]

CLOSED_CASES_DATA = [
    {'id': 1, 'patient': 'John Smith', 'status': 'Completed', 'treatment': 'Acne Treatment', 'doctor': 'Dr. Smith', 'date_closed': '2024-02-10'},
    {'id': 2, 'patient': 'Jane Wilson', 'status': 'Completed', 'treatment': 'Hair Restoration', 'doctor': 'Dr. Sharma', 'date_closed': '2024-02-08'},
]

# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/')
def index():
    """Login page"""
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    """Handle login"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if email in USERS and USERS[email]['password'] == password:
        session['user'] = email
        session['user_name'] = USERS[email]['name']
        return jsonify({'success': True, 'message': 'Login successful'})
    
    return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

@app.route('/logout')
def logout():
    """Handle logout"""
    session.clear()
    return redirect(url_for('index'))

# ============================================================================
# DASHBOARD ROUTES
# ============================================================================

@app.route('/dashboard')
def dashboard():
    """Main dashboard"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('dashboard.html', 
                         stats=DASHBOARD_DATA['stats'], 
                         activity=DASHBOARD_DATA['recent_activity'])

# ============================================================================
# LEADS MANAGEMENT ROUTES
# ============================================================================

@app.route('/leads')
def leads():
    """Leads list page"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('leads.html', leads=LEADS_DATA, doctors=DOCTORS_DATA)

@app.route('/add-lead', methods=['GET', 'POST'])
def add_lead():
    """Add new lead"""
    if 'user' not in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        return jsonify({'success': True, 'message': 'Lead added successfully'})
    return render_template('add-lead.html', doctors=DOCTORS_DATA)

@app.route('/scraped-leads')
def scraped_leads():
    """Scraped leads page"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('scraped-leads.html', leads=LEADS_DATA)

# ============================================================================
# PATIENTS MANAGEMENT ROUTES
# ============================================================================

@app.route('/patients')
def patients():
    """Patients list page"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('patients.html', patients=PATIENTS_DATA, doctors=DOCTORS_DATA)

@app.route('/add-patient', methods=['GET', 'POST'])
def add_patient():
    """Add new patient"""
    if 'user' not in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        return jsonify({'success': True, 'message': 'Patient added successfully'})
    return render_template('add-patient.html', doctors=DOCTORS_DATA)

# ============================================================================
# DOCTORS MANAGEMENT ROUTES
# ============================================================================

@app.route('/doctors')
def doctors():
    """Doctors list page"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('doctors.html', doctors=DOCTORS_DATA)

@app.route('/add-doctor', methods=['GET', 'POST'])
def add_doctor():
    """Add new doctor"""
    if 'user' not in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        return jsonify({'success': True, 'message': 'Doctor added successfully'})
    return render_template('add-doctor.html')

# ============================================================================
# APPOINTMENTS ROUTES
# ============================================================================

@app.route('/appointments')
def appointments():
    """Appointments list page"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('appointments.html', appointments=APPOINTMENTS_DATA)

# ============================================================================
# VISITS ROUTES
# ============================================================================

@app.route('/visits')
def visits():
    """Visits list page"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('visits.html', visits=VISITS_DATA)

# ============================================================================
# FOLLOW-UPS ROUTES
# ============================================================================

@app.route('/followups')
def followups():
    """Follow-ups list page"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('followups.html')

# ============================================================================
# INVOICES ROUTES
# ============================================================================

@app.route('/invoices')
def invoices():
    """Invoices list page"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('invoices.html', invoices=INVOICES_DATA)

# ============================================================================
# CAMPAIGNS ROUTES
# ============================================================================

@app.route('/campaigns')
def campaigns():
    """Campaigns list page"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('campaigns.html', campaigns=CAMPAIGNS_DATA)

# ============================================================================
# CLOSED CASES ROUTES
# ============================================================================

@app.route('/closed-cases')
def closed_cases():
    """Closed cases list page"""
    if 'user' not in session:
        return redirect(url_for('index'))
    return render_template('closed-cases.html', cases=CLOSED_CASES_DATA)

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/leads', methods=['GET'])
def api_leads():
    """API: Get all leads"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(LEADS_DATA)

@app.route('/api/patients', methods=['GET'])
def api_patients():
    """API: Get all patients"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(PATIENTS_DATA)

@app.route('/api/doctors', methods=['GET'])
def api_doctors():
    """API: Get all doctors"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(DOCTORS_DATA)

@app.route('/api/appointments', methods=['GET'])
def api_appointments():
    """API: Get all appointments"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify(APPOINTMENTS_DATA)

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    if 'user' in session:
        return render_template('dashboard.html'), 404
    return redirect(url_for('index'))

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors"""
    return jsonify({'error': 'Internal server error'}), 500

# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == '__main__':
    print("=" * 70)
    print("LeadFlow CRM - Flask Application")
    print("=" * 70)
    print("Starting Flask Development Server...")
    print("URL: http://localhost:5000")
    print("Login: admin@leadflow.com / admin123")
    print("=" * 70)
    app.run(debug=True, host='localhost', port=5000, use_reloader=False)
