-- WC Predictions - Database Schema for Supabase
-- Run this in the Supabase SQL Editor

-- Teams
CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    flag_emoji TEXT DEFAULT '',
    group_letter TEXT DEFAULT ''
);

-- Players
CREATE TABLE IF NOT EXISTS players (
    id SERIAL PRIMARY KEY,
    team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position TEXT DEFAULT ''
);

-- Matches
CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    home_team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    away_team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    match_datetime TIMESTAMPTZ NOT NULL,
    stage TEXT DEFAULT 'Group Stage',
    group_letter TEXT DEFAULT '',
    venue TEXT DEFAULT '',
    status TEXT DEFAULT 'scheduled'
);

-- Predictions
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    chosen_winner TEXT NOT NULL CHECK (chosen_winner IN ('home', 'draw', 'away')),
    home_score INTEGER NOT NULL CHECK (home_score >= 0),
    away_score INTEGER NOT NULL CHECK (away_score >= 0),
    home_scorers TEXT[] DEFAULT '{}',
    away_scorers TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, match_id)
);

-- Match Results (admin/scraped)
CREATE TABLE IF NOT EXISTS match_results (
    id SERIAL PRIMARY KEY,
    match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE UNIQUE,
    home_score INTEGER NOT NULL,
    away_score INTEGER NOT NULL,
    home_scorers TEXT[] DEFAULT '{}',
    away_scorers TEXT[] DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- User scores (cached for leaderboard)
CREATE TABLE IF NOT EXISTS user_scores (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE,
    total_points INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_matches_datetime ON matches(match_datetime);
CREATE INDEX IF NOT EXISTS idx_predictions_user ON predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_predictions_match ON predictions(match_id);
CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id);
