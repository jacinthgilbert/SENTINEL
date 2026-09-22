-- The Sentinel — schema (plan §3.4)
CREATE EXTENSION IF NOT EXISTS postgis;

-- ── precomputed layers (loaded in Step 2) ────────────────────────────────
CREATE TABLE zones (
  h3            TEXT PRIMARY KEY,              -- H3 res-9 hex (~174 m edge)
  geom          GEOMETRY(Polygon, 4326) NOT NULL,
  population    INTEGER      NOT NULL DEFAULT 0,
  elderly_frac  REAL         NOT NULL DEFAULT 0,
  hand_min_m    REAL
);
CREATE INDEX zones_geom_idx ON zones USING GIST (geom);

CREATE TABLE facilities (
  id       SERIAL PRIMARY KEY,
  kind     TEXT NOT NULL CHECK (kind IN ('hospital','school','shelter')),
  name     TEXT,
  capacity INTEGER,                            -- shelters only
  geom     GEOMETRY(Point, 4326) NOT NULL
);
CREATE INDEX facilities_geom_idx ON facilities USING GIST (geom);
CREATE INDEX facilities_kind_idx ON facilities (kind);

CREATE TABLE road_segments (
  id         BIGINT PRIMARY KEY,               -- OSM way id, matches graphml edge
  geom       GEOMETRY(LineString, 4326) NOT NULL,
  hand_m     REAL,
  is_blocked BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX road_segments_geom_idx ON road_segments USING GIST (geom);
CREATE INDEX road_segments_blocked_idx ON road_segments (is_blocked) WHERE is_blocked;

-- ── runtime tables ───────────────────────────────────────────────────────
CREATE TABLE reports (
  id         SERIAL PRIMARY KEY,
  reporter   TEXT,
  geom       GEOMETRY(Point, 4326) NOT NULL,
  depth_cm   INTEGER,
  photo_path TEXT,
  cv_conf    REAL,                             -- CV "is this flooded" 0..1
  trust      REAL,                             -- trust.py output 0..1
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX reports_geom_idx ON reports USING GIST (geom);
CREATE INDEX reports_created_idx ON reports (created_at DESC);

CREATE TABLE sensor_readings (
  id        SERIAL PRIMARY KEY,
  sensor_id TEXT NOT NULL,
  level_cm  REAL NOT NULL,
  ts        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX sensor_readings_lookup_idx ON sensor_readings (sensor_id, ts DESC);

CREATE TABLE alerts (
  id         SERIAL PRIMARY KEY,
  zone_h3    TEXT REFERENCES zones(h3),
  severity   TEXT NOT NULL CHECK (severity IN ('advisory','watch','warning')),
  confidence REAL,
  reason     JSONB,                            -- SHAP contributions
  cap_xml    TEXT,
  sent_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX alerts_sent_idx ON alerts (sent_at DESC);
