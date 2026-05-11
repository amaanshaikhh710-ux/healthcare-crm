-- ============================================================================
-- Follow-Up Module Enhancement - Database Migration
-- LeadFlow CRM
-- Task: Add support for patient_id, time fields, next follow-up tracking
-- ============================================================================

-- Step 1: Add missing columns to followups table
-- These columns enable richer follow-up tracking and patient linking

ALTER TABLE followups 
ADD COLUMN IF NOT EXISTS patient_id INT DEFAULT NULL AFTER doctor_id,
ADD COLUMN IF NOT EXISTS follow_up_time TIME DEFAULT NULL AFTER followup_date,
ADD COLUMN IF NOT EXISTS next_follow_up_date DATE DEFAULT NULL AFTER completed_at,
ADD COLUMN IF NOT EXISTS next_follow_up_time TIME DEFAULT NULL AFTER next_follow_up_date;

-- Step 2: Add foreign key constraint for patient_id (if not already exists)
-- This ensures referential integrity with the patients table
ALTER TABLE followups 
ADD CONSTRAINT IF NOT EXISTS fk_followup_patient 
FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE;

-- Step 3: Create indexes for the new columns to optimize queries
CREATE INDEX IF NOT EXISTS idx_followup_patient ON followups(patient_id);
CREATE INDEX IF NOT EXISTS idx_next_followup_date ON followups(next_follow_up_date, doctor_id);
CREATE INDEX IF NOT EXISTS idx_followup_full ON followups(patient_id, doctor_id, status, followup_date);

-- Step 4: Populate patient_id from appointments for existing follow-ups without patient_id
-- This ensures backward compatibility with existing data
UPDATE followups f
LEFT JOIN appointments a ON f.appointment_id = a.appointment_id
SET f.patient_id = a.patient_id
WHERE f.patient_id IS NULL AND a.patient_id IS NOT NULL;

-- Step 5: Verify the migration
-- Check the updated table structure
-- DESCRIBE followups;

-- Select sample data to verify changes
-- SELECT f.followup_id, f.patient_id, f.doctor_id, f.followup_date, f.follow_up_time, 
--        f.next_follow_up_date, f.next_follow_up_time, f.status
-- FROM followups f
-- LIMIT 5;
