-- ============================================================================
-- SaaS Financial Module - Database Migration Script
-- LeadFlow CRM - Professional Invoice System Upgrade
-- ============================================================================
-- 
-- This script adds the necessary fields to the invoices table to support
-- the new SaaS-level financial management features.
--
-- IMPORTANT: Back up your database before running this script!
-- ============================================================================

-- Add new columns to invoices table
ALTER TABLE invoices ADD COLUMN (
    payment_date DATETIME NULL COMMENT 'Date when invoice was marked as paid',
    payment_method ENUM('CASH','UPI','CARD','BANK') NULL COMMENT 'Payment method used',
    paid_amount DECIMAL(10,2) DEFAULT 0 COMMENT 'Amount already paid',
    balance_amount DECIMAL(10,2) DEFAULT 0 COMMENT 'Amount remaining to pay',
    is_active BOOLEAN DEFAULT TRUE COMMENT 'Flag for soft deletes if needed',
    invoice_number VARCHAR(50) UNIQUE NOT NULL DEFAULT 'INV-2026-0000' COMMENT 'Unique invoice identifier'
);

-- ============================================================================
-- Back-fill existing invoices with calculated values
-- ============================================================================

-- For PAID invoices: Set paid_amount = total_amount, balance_amount = 0
UPDATE invoices 
SET 
    paid_amount = total_amount,
    balance_amount = 0,
    invoice_number = CONCAT('INV-2026-', LPAD(invoice_id, 4, '0'))
WHERE status = 'PAID';

-- For UNPAID invoices: Set paid_amount = 0, balance_amount = total_amount
UPDATE invoices 
SET 
    paid_amount = 0,
    balance_amount = total_amount,
    invoice_number = CONCAT('INV-2026-', LPAD(invoice_id, 4, '0'))
WHERE status = 'UNPAID';

-- ============================================================================
-- Ensure doctors table has commission_percentage field (if not already present)
-- ============================================================================

-- Check if column exists and add if missing
ALTER TABLE doctors ADD COLUMN commission_percentage DECIMAL(5,2) DEFAULT 40 
COMMENT 'Commission percentage for this doctor (e.g., 40 for 40%)';

-- ============================================================================
-- Create indexes for improved query performance
-- ============================================================================

-- Index for invoice number search
CREATE INDEX idx_invoice_number ON invoices(invoice_number);

-- Index for payment status filtering
CREATE INDEX idx_invoice_status ON invoices(status);

-- Index for date range queries
CREATE INDEX idx_invoice_created_at ON invoices(created_at);

-- Index for doctor-specific queries
CREATE INDEX idx_invoice_doctor_id ON invoices(doctor_id);

-- Index for payment date queries
CREATE INDEX idx_invoice_payment_date ON invoices(payment_date);

-- ============================================================================
-- Add CHECK constraint to ensure balance calculation is correct
-- (Optional - uncomment if your MySQL version supports it)
-- ============================================================================

-- ALTER TABLE invoices ADD CONSTRAINT chk_balance_amount 
-- CHECK (balance_amount = total_amount - paid_amount);

-- ============================================================================
-- Verification Query
-- ============================================================================

-- Run this query to verify the upgrade was successful
SELECT 
    COUNT(*) as total_invoices,
    SUM(CASE WHEN status = 'PAID' THEN total_amount ELSE 0 END) as total_revenue,
    SUM(CASE WHEN status = 'UNPAID' THEN balance_amount ELSE 0 END) as pending_amount,
    SUM(paid_amount) as total_collected
FROM invoices;

-- ============================================================================
-- Schema Verification (check column existence)
-- ============================================================================

DESCRIBE invoices;

-- ============================================================================
-- Campaigns and Re-engagement Module Setup
-- ============================================================================

-- Create campaigns table
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    service_filter VARCHAR(255) NULL,
    message TEXT NOT NULL,
    status ENUM('DRAFT','SENT','FAILED') NOT NULL DEFAULT 'DRAFT',
    created_by INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME NULL,
    is_active BOOLEAN DEFAULT TRUE,
    INDEX idx_campaign_service_filter (service_filter),
    INDEX idx_campaign_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create campaign_logs table
CREATE TABLE IF NOT EXISTS campaign_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    campaign_id INT NOT NULL,
    lead_id INT NOT NULL,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status ENUM('SENT','FAILED') DEFAULT 'SENT',
    response TEXT NULL,
    INDEX idx_log_campaign (campaign_id),
    INDEX idx_log_lead (lead_id),
    CONSTRAINT fk_campaign_logs_campaign FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    CONSTRAINT fk_campaign_logs_lead FOREIGN KEY (lead_id) REFERENCES leads(lead_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS users (
    doctor_id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
);

-- ============================================================================
-- END OF MIGRATION SCRIPT
-- ============================================================================
-- 
-- If you encounter any errors:
-- 1. Ensure the invoices table exists
-- 2. Ensure the doctors table exists  
-- 3. Verify your MySQL user has ALTER TABLE permissions
-- 4. Check that invoice_number values are truly unique after update
--
-- For support or issues, refer to SAAS_UPGRADE_SUMMARY.md
-- ============================================================================
