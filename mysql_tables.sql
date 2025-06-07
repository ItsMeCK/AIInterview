CREATE DATABASE IF NOT EXISTS ai_interview_portal_db;
USE ai_interview_portal_db;

-- For storing company information (if you plan multi-tenancy)
CREATE TABLE IF NOT EXISTS companies (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    -- Add other company-specific fields
);

-- For storing admin user information
CREATE TABLE IF NOT EXISTS admin_users (
    id VARCHAR(255) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL, -- Store hashed passwords!
    company_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(255) PRIMARY KEY,
    company_id VARCHAR(255), -- Link to a company if multi-tenant
    title VARCHAR(255) NOT NULL,
    department VARCHAR(255),
    description TEXT,
    status VARCHAR(50) DEFAULT 'Open', -- e.g., Open, Closed, Draft
    applications_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by VARCHAR(255), -- Link to an admin_user id
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (created_by) REFERENCES admin_users(id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS candidates (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255) UNIQUE,
    resume_text TEXT, -- Or path to a resume file
    resume_filename VARCHAR(255), -- If storing file path
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interviews (
    id VARCHAR(255) PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL,
    candidate_id VARCHAR(255),
    company_id VARCHAR(255), -- Denormalized for easier querying or from job_id->company_id
    interview_date TIMESTAMP NULL,
    status VARCHAR(50) DEFAULT 'Invited', -- e.g., Invited, Scheduled, Resume Submitted, In Progress, Completed, Pending Review, Reviewed
    score INT, -- e.g., 0-100
    ai_summary TEXT,
    admin_feedback TEXT,
    transcript_json JSON, -- Store structured transcript: [{"actor": "ai", "text": "...", "timestamp": "..."}, ...]
    ai_questions_json JSON, -- Store questions and answers: [{"q": "...", "a": "..."}]
    screenshot_paths_json JSON, -- Store list of paths/URLs to screenshots: ["/uploads/img1.jpg", "/uploads/img2.jpg"]
    invitation_link VARCHAR(255) UNIQUE, -- Secure link for candidate
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE SET NULL ON UPDATE CASCADE
);

-- Example: Insert dummy company and admin user if you want to test FKs immediately
-- Make sure these IDs match placeholders in backend or are handled by auth later.
-- INSERT INTO companies (id, name) VALUES ('company_innovatech', 'Innovatech Solutions');
-- INSERT INTO admin_users (id, email, password_hash, company_id) VALUES ('admin_user_123', 'admin@example.com', 'your_bcrypt_hash_here', 'company_innovatech');

-- Note on JSON fields:
-- MySQL 5.7.8+ supports the JSON data type.
-- If using an older version, you might need to store these as TEXT and handle JSON parsing/stringifying entirely in the application.
-- The provided backend code attempts to parse these fields if they are strings.

-- Make sure 'job_example_123' exists in your 'jobs' table
-- Make sure 'company_innovatech' exists in your 'companies' table
INSERT INTO interviews (id, job_id, company_id, invitation_link, status, created_at, updated_at)
VALUES
('int_cand_test01', 'job_ce48a27f-202b-43ed-a8b8-dcb41afec7af', 'company_innovatech', 'your-unique-guid-for-link-12345', 'Invited', NOW(), NOW());
-- Replace 'job_example_123' with an actual job_id from your jobs table
-- Replace 'your-unique-guid-for-link-12345' with a unique GUID you create

ALTER TABLE jobs
ADD COLUMN number_of_questions INT DEFAULT 5,
ADD COLUMN must_ask_topics TEXT NULL;


ALTER TABLE interviews
ADD COLUMN detailed_scorecard_json JSON NULL COMMENT 'Stores detailed scores for different categories' AFTER score;

