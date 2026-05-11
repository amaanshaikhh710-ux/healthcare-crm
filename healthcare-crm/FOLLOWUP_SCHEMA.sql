-- ============================================================================
-- Follow-Up Management System - Database Schema
-- LeadFlow CRM
-- ============================================================================

-- Create followups table for clinical follow-up tracking
CREATE TABLE IF NOT EXISTS followups (
    followup_id INT AUTO_INCREMENT PRIMARY KEY,
    appointment_id INT NOT NULL,
    doctor_id INT NOT NULL,
    followup_date DATE NOT NULL,
    notes TEXT DEFAULT NULL,
    status ENUM('PENDING', 'DONE', 'MISSED') DEFAULT 'PENDING',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME DEFAULT NULL,
    
    -- Indexes for performance
    INDEX idx_appointment (appointment_id),
    INDEX idx_doctor (doctor_id),
    INDEX idx_followup_date (followup_date),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    
    -- Foreign key constraints
    CONSTRAINT fk_followup_appointment FOREIGN KEY (appointment_id) 
        REFERENCES appointments(appointment_id) ON DELETE CASCADE,
    CONSTRAINT fk_followup_doctor FOREIGN KEY (doctor_id) 
        REFERENCES doctors(doctor_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Indexes for common queries
-- ============================================================================

-- Index for finding pending follow-ups
CREATE INDEX IF NOT EXISTS idx_pending_followups 
ON followups(status, followup_date) WHERE status = 'PENDING';

-- Index for doctor-specific follow-ups
CREATE INDEX IF NOT EXISTS idx_doctor_followups 
ON followups(doctor_id, status, followup_date);

-- Index for overdue follow-ups
CREATE INDEX IF NOT EXISTS idx_overdue_followups 
ON followups(followup_date, status) WHERE status = 'PENDING';

-- ============================================================================
-- Verification
-- ============================================================================

-- Check table structure
DESCRIBE followups;

-- Show sample query for overdue follow-ups
-- SELECT DISTINCT f.*, 
--        CASE WHEN f.followup_date < CURDATE() AND f.status = 'PENDING' THEN 1 ELSE 0 END AS is_overdue
-- FROM followups f
-- WHERE f.followup_date < CURDATE() AND f.status = 'PENDING'
-- ORDER BY f.followup_date ASC;
