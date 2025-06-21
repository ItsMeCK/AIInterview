-- Migration script to add buffered_question_json field to interviews table
-- Run this if you have an existing database without this field

USE ai_interview_portal_db;

-- Add the missing buffered_question_json field
ALTER TABLE interviews 
ADD COLUMN buffered_question_json JSON NULL 
COMMENT 'Stores the next question to be asked' 
AFTER transcript_json; 