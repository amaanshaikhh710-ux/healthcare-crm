# Quick Reference: Invoice Generation from Appointments

## What's New? 🎉
You can now generate invoices directly from completed appointments with one click!

---

## How to Use

### Step 1: Complete an Appointment
- Go to **Appointments** page
- Click **"✓ Done"** button to mark appointment as COMPLETE
- Status changes from SCHEDULED → COMPLETED ✅

### Step 2: Generate Invoice
- Look for **"💰 Invoice"** button in the Actions column
- Button appears only if:
  - ✓ Appointment status is COMPLETED
  - ✓ No invoice has been generated yet
- Click the button to generate invoice automatically

### Step 3: Confirmation
- You'll see success message: 
  ```
  "Invoice generated successfully! Amount: ₹2,360.00 (₹2,000.00 + 18% tax ₹360.00)"
  ```
- You'll be redirected to **Invoices** page
- New invoice appears with status: **UNPAID**

---

## Invoice Details

When you generate an invoice, the following details are recorded:

| Field | Value | Notes |
|-------|-------|-------|
| Patient Name | From Appointment | Automated |
| Doctor Name | From Appointment | Automated |
| Service | From Appointment | Automated |
| Amount | ₹2,000.00 | Base service charge |
| Tax (18%) | ₹360.00 | GST/Tax calculation |
| Total Amount | ₹2,360.00 | Amount + Tax |
| Status | UNPAID | Default status |
| Date Created | Today | Auto-generated |

---

## What if Invoice Already Exists?

If an invoice has already been generated for an appointment:
- The button changes to **"✓ Invoice"** (gray badge)
- Clicking it shows: *"Invoice already generated for this appointment"*
- You'll be taken to Invoices page
- Only ONE invoice can exist per appointment

---

## Role Permissions

### 👨‍⚕️ DOCTOR Role
- ✓ Can generate invoices for own appointments
- ✗ Cannot generate for other doctors' appointments
- Permission check is automatic

### 👤 ADMIN/STAFF Role
- ✓ Can generate invoices for ANY appointment
- ✓ Full access to all appointments
- No restrictions

---

## Important Notes ⚠️

1. **Appointment Must Be COMPLETED**
   - Status must be changed to COMPLETED first
   - Cannot generate for SCHEDULED or CANCELLED appointments

2. **One Invoice Per Appointment**
   - Duplicate invoices are prevented automatically
   - Unique constraint on appointment_id in invoices table

3. **Default Amount**
   - All invoices created with ₹2,000 base amount
   - Contact ADMIN if different amount needed
   - Tax is always 18% of base amount

4. **No Manual Editing (Optional)**
   - After generation, invoice status is UNPAID
   - To mark as PAID, contact ADMIN
   - Amount cannot be changed after creation

5. **Automatic Calculations**
   - Tax calculated automatically: amount × 0.18
   - Total calculated: amount + tax
   - No decimal rounding errors

---

## Workflow Example

**Scenario: Dr. Smith completes an appointment for patient John Doe**

```
1. Dr. Smith logs in → Appointments page
2. Sees appointment: John Doe | SCHEDULED | Dr. Smith | General Checkup
3. Clicks "✓ Done" → Status changes to COMPLETED
4. "💰 Invoice" button appears for this appointment
5. Clicks "💰 Invoice"
6. System immediately:
   - Calculates: Amount = ₹2,000 + Tax = ₹360 = Total ₹2,360
   - Creates invoice record in database
   - Links invoice to appointment
   - Logs the action for audit trail
7. Success message shows → Redirected to Invoices
8. New invoice visible: Invoice#XXX | John Doe | Dr. Smith | ₹2,360 | UNPAID
```

---

## Troubleshooting

### Q: I don't see the "💰 Invoice" button
**A:** Check:
- Is appointment status COMPLETED? (Click "✓ Done" first)
- Did you refresh the page after marking as complete?
- Does invoice already exist? (Check gray "✓ Invoice" badge)

### Q: I got "Access denied" error
**A:** 
- You're DOCTOR → Can only generate for own appointments
- Contact ADMIN if you need invoice for different doctor's appointment

### Q: Button shows but clicking gives error
**A:**
- Database connection issue
- Contact system administrator
- Check error message in flash notification

### Q: Invoice shows UNPAID status
**A:** Normal! All invoices start as UNPAID
- Contact ADMIN to mark as PAID
- Or set payment status in invoices page

### Q: Can I change the amount?
**A:** Currently NO (default = ₹2,000)
- Contact ADMIN for custom amount
- Feature may be added in future versions

---

## Tips & Best Practices

✅ **DO:**
- Complete appointment before generating invoice
- Check invoice was created successfully
- Review invoice details in Invoices page
- Contact ADMIN if issues occur

❌ **DON'T:**
- Try to generate invoice for SCHEDULED appointment
- Try to generate multiple invoices for same appointment
- Manually edit invoice SQL (always use application)
- Bypass role-based access controls

---

## Technical Details (For Developers)

**Route:** `GET /generate-invoice/<appointment_id>`  
**Method:** GET (clicking link)  
**Auth Required:** Yes (login_required)  
**RBAC:** Yes (role-based)  
**Database:** MySQL with invoices table  
**Security:** Parameterized queries, SQL injection prevention  
**HTTP Response:** 302 Redirect on success/error  

**Tables Involved:**
- `appointments` → Source data
- `leads` → Patient information
- `doctors` → Doctor information  
- `invoices` → Destination table
- `users` → Authentication & role checking

---

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Review INVOICE_GENERATION_GUIDE.md (detailed documentation)
3. Contact System Administrator
4. Check application logs for detailed error messages

---

**Last Updated:** February 24, 2026  
**Version:** 1.0  
**Status:** Production Ready ✅
