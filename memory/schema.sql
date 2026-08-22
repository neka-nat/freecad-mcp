CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS freecad_mcp;

CREATE TABLE IF NOT EXISTS freecad_mcp.sessions (
    id text PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    user_name text NOT NULL DEFAULT 'AXIO',
    summary text NOT NULL DEFAULT '',
    tags text[] NOT NULL DEFAULT ARRAY[]::text[]
);

CREATE TABLE IF NOT EXISTS freecad_mcp.events (
    id text PRIMARY KEY,
    session_id text NOT NULL REFERENCES freecad_mcp.sessions(id) ON DELETE CASCADE,
    ts timestamptz NOT NULL DEFAULT now(),
    kind text NOT NULL CHECK (kind IN ('prompt', 'tool_call', 'tool_result', 'error', 'fix', 'verify', 'export')),
    payload jsonb NOT NULL,
    embedding vector(768)
);

CREATE TABLE IF NOT EXISTS freecad_mcp.lessons (
    id text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    title text NOT NULL,
    body text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('INFO', 'WARN', 'CRIT')),
    source_session text REFERENCES freecad_mcp.sessions(id) ON DELETE SET NULL,
    embedding vector(768)
);

CREATE TABLE IF NOT EXISTS freecad_mcp.parts (
    id text PRIMARY KEY,
    name text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'unknown',
    last_session text REFERENCES freecad_mcp.sessions(id) ON DELETE SET NULL,
    fcstd_path text,
    stl_path text,
    notes text NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_freecad_events_session_ts
    ON freecad_mcp.events (session_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_freecad_events_kind_ts
    ON freecad_mcp.events (kind, ts DESC);

CREATE INDEX IF NOT EXISTS idx_freecad_lessons_severity_created
    ON freecad_mcp.lessons (severity, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_freecad_lessons_embedding
    ON freecad_mcp.lessons USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_freecad_parts_name
    ON freecad_mcp.parts (name);

