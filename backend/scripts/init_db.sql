-- Initial database setup script
-- Runs once when the PostgreSQL container first starts

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- For fuzzy text search
CREATE EXTENSION IF NOT EXISTS "btree_gin";    -- For combined indexes
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements"; -- For query monitoring

-- Create application schema
CREATE SCHEMA IF NOT EXISTS dex;

-- Set default search path
ALTER DATABASE dextrader SET search_path TO dex, public;
