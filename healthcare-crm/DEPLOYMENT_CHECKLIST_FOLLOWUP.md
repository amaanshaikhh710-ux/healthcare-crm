# Deployment Checklist - Follow-Up Module Enhancement

## Pre-Deployment Verification

### ✅ Code Review Checklist
- [ ] All Python code uses proper error handling
- [ ] All database queries reviewed for SQL injection prevention
- [ ] All RBAC checks implemented correctly
- [ ] No hardcoded sensitive data in code
- [ ] Logging implemented for audit trail
- [ ] No circular imports or dependency issues
- [ ] All imports at top of files

### ✅ Database Checklist
- [ ] Backup current database created
- [ ] FOLLOWUP_ENHANCEMENT.sql reviewed
- [ ] Migration tested on staging database
- [ ] No syntax errors in SQL
- [ ] Foreign key constraints verified
- [ ] Indexes created successfully
- [ ] Data integrity maintained after migration

### ✅ Testing Checklist
- [ ] Appointments display correctly (all newly created show)
- [ ] Follow-up creation with time works
- [ ] Next follow-up scheduling works (no data overwrite)
- [ ] Invoice generation from follow-up works
- [ ] RBAC restrictions enforced for all users
- [ ] Doctor sees only own data
- [ ] Admin sees all data
- [ ] Error handling for invalid inputs
- [ ] Database commit verified
- [ ] No template rendering errors

### ✅ File Verification
- [ ] app.py updated correctly
- [ ] templates/appointments.html updated
- [ ] templates/add-followup.html updated (time field added)
- [ ] templates/followups.html updated (new columns, buttons)
- [ ] templates/add-next-followup.html created
- [ ] FOLLOWUP_ENHANCEMENT.sql created
- [ ] Documentation files created
- [ ] No syntax errors in any file

## Deployment Steps (In Order)

### Step 1: Pre-Deployment Backup
```bash
# Backup current database
mysqldump -u root -p healthcare_crm > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup current app files
cp -r /path/to/app /path/to/app_backup_$(date +%Y%m%d_%H%M%S)
```
**Verify**: Backup files exist and are readable
- [ ] Database backup created
- [ ] Code backup created

### Step 2: Apply Database Migration
```bash
# Execute SQL migration
mysql -u root -p healthcare_crm < FOLLOWUP_ENHANCEMENT.sql

# Verify migration success
mysql -u root -p healthcare_crm -e "DESCRIBE followups;"
mysql -u root -p healthcare_crm -e "SELECT COUNT(*) FROM followups;"
```
**Verify**: New columns present without errors
- [ ] No SQL errors
- [ ] New columns visible (follow_up_time, next_follow_up_date, etc.)
- [ ] Existing data preserved
- [ ] Indexes created

### Step 3: Deploy Code
```bash
# Stop application (if running as service)
sudo systemctl stop leadflow-crm    # or equivalent

# Deploy new app.py
cp app.py /production/path/app.py

# Deploy updated templates
cp templates/*.html /production/path/templates/

# Copy new template
cp templates/add-next-followup.html /production/path/templates/

# Verify file permissions
ls -la /production/path/app.py      # Should have correct permissions
ls -la /production/path/templates/  # Should be readable
```
**Verify**: Files copied without errors
- [ ] app.py deployed
- [ ] All templates deployed
- [ ] add-next-followup.html deployed
- [ ] File permissions correct (readable by app)

### Step 4: Start Application
```bash
# Start application
sudo systemctl start leadflow-crm    # or equivalent

# Check application status
sudo systemctl status leadflow-crm

# Verify application listening
netstat -tlnp | grep 5000            # or appropriate port

# Check logs for errors
tail -f /var/log/leadflow-crm/app.log
```
**Verify**: Application started without errors
- [ ] Service running
- [ ] No startup errors in logs
- [ ] Application responsive
- [ ] Database connection working

### Step 5: Functional Testing
```
Test 1: Appointment Display
- Navigate to /appointments
- Verify newly created appointment appears
- Check date and time display correctly

Test 2: Follow-Up with Time
- Create new follow-up for completed appointment
- Verify time field required and accepted
- Check time displays in followups list

Test 3: Next Follow-Up
- Mark follow-up as DONE
- Click Next button
- Schedule next follow-up
- Verify both follow-ups exist

Test 4: Invoice from Follow-Up
- Mark appointment as COMPLETED
- Create and mark follow-up as DONE
- Click Invoice button
- Verify invoice created

Test 5: RBAC for Doctor
- Login as doctor
- Verify only own appointments visible
- Try to access other doctor's follow-up (should deny)
```

**Verify**: All tests pass
- [ ] Appointment display works
- [ ] Follow-up time works
- [ ] Next follow-up works
- [ ] Invoice button works
- [ ] RBAC enforced

## Post-Deployment Verification

### ✅ Application Health Checks
```bash
# Check application logs for errors
tail -f /var/log/leadflow-crm/app.log

# Check database connectivity
mysql -u root -p -e "SELECT COUNT(*) FROM followups;"

# Verify all routes accessible
curl -s http://localhost:5000/appointments | head -20
curl -s http://localhost:5000/followups | head -20
```

### ✅ Performance Checks
- [ ] Application response time normal (< 1 second per page)
- [ ] Database queries still fast
- [ ] No memory leaks visible
- [ ] No obvious slow operations

### ✅ Data Integrity Checks
```sql
-- Check patient_id populated in follow-ups
SELECT COUNT(*) as total, 
       COUNT(patient_id) as with_patient_id
FROM followups;

-- Should show both counts equal or most have patient_id

-- Check no follow-ups created without proper links
SELECT f.followup_id
FROM followups f
WHERE f.patient_id IS NULL AND f.appointment_id IS NOT NULL
LIMIT 10;

-- Should return minimal results (old data before migration)
```

### ✅ User Acceptance Testing
- [ ] Admin user can see all appointments
- [ ] Doctor user can see only own appointments
- [ ] Follow-ups page shows new time column
- [ ] Follow-up creation accepts time
- [ ] Next follow-up feature works
- [ ] Invoice button works from follow-up page
- [ ] No error messages on main pages
- [ ] No 404 errors on routes

## Rollback Plan (If Issues Found)

### Immediate Rollback
```bash
# Stop application
sudo systemctl stop leadflow-crm

# Restore previous code
rm -rf /production/path/*
cp -r /production/path_backup_[timestamp]/* /production/path/

# Start application
sudo systemctl start leadflow-crm
```

### Database Rollback
```bash
# If data corruption, restore from backup
mysql -u root -p healthcare_crm < backup_[timestamp].sql

# Verify restoration
SELECT COUNT(*) FROM followups;
SELECT COUNT(*) FROM appointments;
SELECT COUNT(*) FROM invoices;
```

### Verification After Rollback
- [ ] Application running
- [ ] Database restored
- [ ] Data integrity verified
- [ ] Previous functionality working
- [ ] Logs checked for errors

## Known Issues & Mitigations

### Issue 1: New Columns Appear NULL
**Cause**: Migration not run properly
**Fix**:
- Verify migration executed without errors
- Check followups table structure: `DESCRIBE followups;`
- Re-run migration if needed

### Issue 2: Follow-Up Time Not Saving
**Cause**: Form not submitting time, or database column issue
**Fix**:
- Verify form includes follow_up_time field
- Check database column type is TIME
- Review browser console for JavaScript errors
- Check application logs

### Issue 3: Appointments Showing Old Errors
**Cause**: Template caching or old query still running
**Fix**:
- Clear browser cache
- Restart Flask application
- Verify app.py has LEFT JOINs (not INNER JOINs)

### Issue 4: RBAC Access Denied
**Cause**: Doctor ID not mapping correctly
**Fix**:
- Verify users.doctor_id is populated: `SELECT * FROM users WHERE role='DOCTOR';`
- Check doctor record exists: `SELECT * FROM doctors WHERE doctor_id = X;`
- Review RBAC check in route logs

## Monitoring After Deployment

### Daily Tasks (First Week)
- [ ] Check application logs for errors
- [ ] Verify no outstanding issues reported
- [ ] Check database backup ran successfully
- [ ] Monitor application performance

### Weekly Tasks (First Month)
- [ ] Review error logs
- [ ] Check performance metrics
- [ ] Verify data integrity
- [ ] Get user feedback

### Long-term Monitoring
- [ ] Continue regular database backups
- [ ] Monitor application logs
- [ ] Track performance metrics
- [ ] Plan for scaling if needed

## Success Criteria

✅ Deployment successful when:
1. Application starts without errors
2. Database migration completed without errors
3. All RBAC checks working correctly
4. Appointments display immediately after creation
5. Follow-up time field working
6. Next follow-up feature creating records without overwrites
7. Invoice generation from follow-up working
8. No new error messages in logs
9. All existing features still working
10. Performance acceptable (response time normal)

## Emergency Contacts

In case of issues:
- Database Administrator: [contact info if applicable]
- Application Support: [contact info if applicable]
- Backup Location: [document backup location]
- Rollback Authorization: [who can authorize]

## Sign-Off

- [ ] Code reviewed and approved
- [ ] Database backup confirmed
- [ ] Pre-deployment tests passed
- [ ] Deployment executed successfully
- [ ] Post-deployment tests passed
- [ ] No critical issues found
- [ ] Stakeholders notified of completion

**Deployment Date**: _______________
**Deployed By**: _______________
**Reviewed By**: _______________
**Sign-Off Date**: _______________

---

## Quick Reference: Command Summary

```bash
# Quick deployment script (after review)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cd /production/path

# Backup
mysqldump -u root -pPASSWORD healthcare_crm > backup_$TIMESTAMP.sql
cp -r . ../app_backup_$TIMESTAMP

# Migrate database
mysql -u root -pPASSWORD healthcare_crm < FOLLOWUP_ENHANCEMENT.sql

# Update code
cp app.py app.py.old
cp /source/app.py .
cp /source/templates/*.html templates/

# Restart
sudo systemctl restart leadflow-crm

# Verify
sleep 5
curl -s http://localhost:5000/appointments | grep -q "Appointments" && echo "✓ Deployment successful" || echo "✗ Deployment failed"
```

Use this script only after full testing and approval.
