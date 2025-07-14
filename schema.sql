-- Create Users table
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    osu_id INTEGER UNIQUE NOT NULL,
    username TEXT NOT NULL,
    avatar_url TEXT,
    rank INTEGER,
    pp REAL,
    playcount INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create Analysis Results table
CREATE TABLE IF NOT EXISTS analysis_results (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recent_skill REAL DEFAULT 0,
    peak_skill REAL DEFAULT 0,
    skill_match REAL DEFAULT 0,
    confidence REAL DEFAULT 0,
    verdict TEXT DEFAULT 'unknown',
    insights TEXT,
    confidence_factors TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create API Cache table
CREATE TABLE IF NOT EXISTS api_cache (
    id BIGSERIAL PRIMARY KEY,
    cache_key TEXT UNIQUE NOT NULL,
    cache_data TEXT,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create Leaderboard table
CREATE TABLE IF NOT EXISTS leaderboard (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recent_skill REAL DEFAULT 0,
    peak_skill REAL DEFAULT 0,
    skill_match REAL DEFAULT 0,
    confidence REAL DEFAULT 0,
    verdict TEXT DEFAULT 'unknown',
    skill_score REAL DEFAULT 0,
    rank_position INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_leaderboard_skill_score ON leaderboard (skill_score DESC);
CREATE INDEX IF NOT EXISTS idx_leaderboard_user_id ON leaderboard (user_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users USING GIN (username gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_users_osu_id ON users (osu_id);
CREATE INDEX IF NOT EXISTS idx_analysis_user_id ON analysis_results (user_id);
CREATE INDEX IF NOT EXISTS idx_analysis_created_at ON analysis_results (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_cache_key ON api_cache (cache_key);
CREATE INDEX IF NOT EXISTS idx_api_cache_expires ON api_cache (expires_at);

-- Enable Row Level Security (RLS)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE leaderboard ENABLE ROW LEVEL SECURITY;

-- Create RLS policies (allowing all operations for now - adjust as needed)
CREATE POLICY "Enable all operations for users" ON users FOR ALL USING (true);
CREATE POLICY "Enable all operations for analysis_results" ON analysis_results FOR ALL USING (true);
CREATE POLICY "Enable all operations for api_cache" ON api_cache FOR ALL USING (true);
CREATE POLICY "Enable all operations for leaderboard" ON leaderboard FOR ALL USING (true);

-- Create function to update leaderboard ranks
CREATE OR REPLACE FUNCTION update_leaderboard_ranks()
RETURNS void AS $$
BEGIN
    UPDATE leaderboard 
    SET rank_position = ranked.rank
    FROM (
        SELECT id, 
               ROW_NUMBER() OVER (ORDER BY skill_score DESC) as rank
        FROM leaderboard
    ) ranked
    WHERE leaderboard.id = ranked.id;
END;
$$ LANGUAGE plpgsql;

-- Create function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for automatic updated_at updates
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_leaderboard_updated_at 
    BEFORE UPDATE ON leaderboard 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Enable pg_trgm extension for better text search (if not already enabled)
CREATE EXTENSION IF NOT EXISTS pg_trgm;