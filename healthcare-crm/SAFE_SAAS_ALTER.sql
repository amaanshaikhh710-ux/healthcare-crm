-- LeadFlow CRM safe SaaS upgrade
-- Run these ALTER statements on the existing database.
-- They extend the schema without dropping current tables or data.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS doctor_id INT NULL;

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS last_contacted DATETIME NULL,
    ADD COLUMN IF NOT EXISTS notes TEXT NULL;

ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS lead_id INT NULL,
    ADD COLUMN IF NOT EXISTS notes TEXT NULL,
    ADD COLUMN IF NOT EXISTS updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

ALTER TABLE patients
    ADD COLUMN IF NOT EXISTS case_status ENUM('ACTIVE', 'CLOSED') NOT NULL DEFAULT 'ACTIVE';

ALTER TABLE followups
    ADD COLUMN IF NOT EXISTS patient_id INT NULL AFTER doctor_id,
    ADD COLUMN IF NOT EXISTS follow_up_time TIME NULL AFTER followup_date,
    ADD COLUMN IF NOT EXISTS next_follow_up_date DATE NULL AFTER status,
    ADD COLUMN IF NOT EXISTS next_follow_up_time TIME NULL AFTER next_follow_up_date,
    ADD COLUMN IF NOT EXISTS completed_at DATETIME NULL AFTER created_at;

ALTER TABLE followups
    ADD INDEX IF NOT EXISTS idx_followups_patient_id (patient_id),
    ADD INDEX IF NOT EXISTS idx_followups_next_date (next_follow_up_date),
    ADD INDEX IF NOT EXISTS idx_followups_doctor_status_date (doctor_id, status, followup_date);

ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS followup_id INT NULL AFTER appointment_id,
    ADD COLUMN IF NOT EXISTS payment_date DATETIME NULL,
    ADD COLUMN IF NOT EXISTS payment_method ENUM('CASH','UPI','CARD','BANK') NULL,
    ADD COLUMN IF NOT EXISTS paid_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS balance_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(50) NULL,
    ADD COLUMN IF NOT EXISTS invoice_type ENUM('APPOINTMENT','FOLLOWUP') NOT NULL DEFAULT 'APPOINTMENT' AFTER invoice_number,
    ADD COLUMN IF NOT EXISTS updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

ALTER TABLE invoices
    MODIFY COLUMN appointment_id INT NULL;

DROP INDEX appointment_id ON invoices;
CREATE INDEX idx_invoices_appointment_id ON invoices(appointment_id);

ALTER TABLE doctors
    ADD COLUMN IF NOT EXISTS commission_percentage DECIMAL(5,2) NOT NULL DEFAULT 40.00;

UPDATE invoices
SET
    invoice_number = COALESCE(NULLIF(invoice_number, ''), CONCAT('INV-', YEAR(COALESCE(created_at, NOW())), '-', LPAD(invoice_id, 4, '0'))),
    invoice_type = COALESCE(invoice_type, 'APPOINTMENT'),
    paid_amount = CASE WHEN status = 'PAID' THEN total_amount ELSE COALESCE(paid_amount, 0) END,
    balance_amount = CASE WHEN status = 'PAID' THEN 0 ELSE total_amount - COALESCE(paid_amount, 0) END
WHERE 1 = 1;

ALTER TABLE followups
    ADD CONSTRAINT fk_followups_patient
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
    ON DELETE SET NULL;

ALTER TABLE invoices
    ADD CONSTRAINT fk_invoices_followup
    FOREIGN KEY (followup_id) REFERENCES followups(followup_id)
    ON DELETE SET NULL;

ALTER TABLE users
    ADD CONSTRAINT fk_users_doctor
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id)
    ON DELETE SET NULL;
