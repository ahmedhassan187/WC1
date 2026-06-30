-- Migration: Add missing columns to match_results and user_scores tables
-- Run this in Supabase SQL Editor to enable scorer tracking and timestamps

-- Add scorer columns to match_results
ALTER TABLE IF EXISTS match_results 
  ADD COLUMN IF NOT EXISTS home_scorers TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS away_scorers TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Add updated_at to user_scores if missing
ALTER TABLE IF EXISTS user_scores 
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Add stage column to matches if missing (for knockout stage tracking)
ALTER TABLE IF EXISTS matches 
  ADD COLUMN IF NOT EXISTS stage TEXT DEFAULT 'Group Stage';

-- Verify the columns
SELECT table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_name IN ('match_results', 'user_scores', 'matches')
