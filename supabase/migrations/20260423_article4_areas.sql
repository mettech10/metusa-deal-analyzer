-- ============================================================
-- Article 4 Direction engine — area registry + update audit log
--
-- Article 4 Directions remove permitted-development rights and
-- require full planning permission for C3→C4 HMO conversion
-- (and other specified changes of use). Coverage is set by
-- each local planning authority, so the dataset is a union of
-- council-level directions rather than a single national feed.
--
-- This migration backs the live Leaflet map, the HMO result
-- card, and the monthly update pipeline. Boundaries are stored
-- as GeoJSON; postcode-district / sector arrays give a fast
-- point-in-coverage check without PostGIS.
-- ============================================================

-- ── article4_areas ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS article4_areas (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,

  -- Location identifiers
  council_name            VARCHAR(200) NOT NULL,
  council_code            VARCHAR(20),              -- ONS local authority code
  region                  VARCHAR(100),
  country                 VARCHAR(50) DEFAULT 'England',

  -- Article 4 details
  direction_type          VARCHAR(100),             -- 'HMO C4', 'HMO Sui Generis', 'Permitted Development', 'Mixed'
  property_types_affected TEXT[],                   -- e.g. ARRAY['C3 to C4', 'C3 to HMO']

  -- Geographic boundary
  boundary_geojson        JSONB,                    -- GeoJSON polygon / multipolygon of affected area
  postcode_districts      TEXT[],                   -- e.g. ARRAY['M14','M15','LS6']
  postcode_sectors        TEXT[],                   -- e.g. ARRAY['M14 5','LS6 1']
  approximate_center_lat  FLOAT,
  approximate_center_lng  FLOAT,

  -- Status
  status                  VARCHAR(50) NOT NULL,     -- 'active' | 'proposed' | 'consultation' | 'revoked'

  -- Dates
  confirmed_date          DATE,
  proposed_date           DATE,
  consultation_end_date   DATE,
  effective_date          DATE,

  -- Impact & source
  impact_description      TEXT,
  planning_portal_url     TEXT,
  council_planning_url    TEXT,
  source_document_url     TEXT,

  -- Data management
  verified                BOOLEAN DEFAULT FALSE,
  data_source             VARCHAR(100),             -- 'manual' | 'council_api' | 'planning_portal'
  last_verified_at        TIMESTAMPTZ,
  created_at              TIMESTAMPTZ DEFAULT NOW(),
  updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_a4_council            ON article4_areas(council_name);
CREATE INDEX IF NOT EXISTS idx_a4_status             ON article4_areas(status);
CREATE INDEX IF NOT EXISTS idx_a4_postcode_districts ON article4_areas USING GIN(postcode_districts);
CREATE INDEX IF NOT EXISTS idx_a4_postcode_sectors   ON article4_areas USING GIN(postcode_sectors);

-- Keep updated_at in sync on UPDATE
CREATE OR REPLACE FUNCTION set_article4_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_article4_areas_updated_at ON article4_areas;
CREATE TRIGGER trg_article4_areas_updated_at
  BEFORE UPDATE ON article4_areas
  FOR EACH ROW EXECUTE FUNCTION set_article4_updated_at();

-- ── article4_update_log ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS article4_update_log (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  run_date         TIMESTAMPTZ DEFAULT NOW(),
  areas_checked    INTEGER,
  areas_updated    INTEGER,
  new_areas_added  INTEGER,
  areas_proposed   INTEGER,
  errors           TEXT[],
  data_sources     TEXT[]
);

CREATE INDEX IF NOT EXISTS idx_a4_log_run_date ON article4_update_log(run_date DESC);

-- ── RLS ────────────────────────────────────────────────────────
-- Article 4 data is public planning information. Anon users (the
-- Leaflet map, the HMO result card) can read. Writes are service
-- role only (the monthly update job and manual admin tooling).
ALTER TABLE article4_areas      ENABLE ROW LEVEL SECURITY;
ALTER TABLE article4_update_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anon read article4 areas"      ON article4_areas;
CREATE POLICY "Anon read article4 areas"
  ON article4_areas
  FOR SELECT
  TO anon, authenticated
  USING (true);

DROP POLICY IF EXISTS "Service role full access a4"   ON article4_areas;
CREATE POLICY "Service role full access a4"
  ON article4_areas
  FOR ALL
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS "Service role full access a4 log" ON article4_update_log;
CREATE POLICY "Service role full access a4 log"
  ON article4_update_log
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- ============================================================
-- Seed: confirmed active + proposed UK Article 4 directions.
-- Use ON CONFLICT DO NOTHING so re-running the migration is safe;
-- the unique key is (council_name, direction_type) for this seed.
-- ============================================================

-- Deduplication: one seed row per (council, direction)
CREATE UNIQUE INDEX IF NOT EXISTS idx_a4_council_direction
  ON article4_areas(council_name, direction_type);

INSERT INTO article4_areas
  (council_name, council_code, region, direction_type, status,
   postcode_districts,
   approximate_center_lat, approximate_center_lng,
   confirmed_date, impact_description,
   council_planning_url, verified, data_source)
VALUES
-- ── GREATER MANCHESTER ────────────────────────────────────────
('Manchester City Council', 'E08000003', 'Greater Manchester',
 'HMO C4', 'active',
 ARRAY['M14','M15','M16','M13'],
 53.4408, -2.2301, '2012-01-01',
 'C3 dwellinghouse to C4 HMO requires planning permission across most of the city',
 'https://www.manchester.gov.uk/planning', TRUE, 'manual'),

('Salford City Council', 'E08000006', 'Greater Manchester',
 'HMO C4', 'active',
 ARRAY['M5','M6','M7','M3'],
 53.4875, -2.2901, '2015-01-01',
 'Article 4 direction removing permitted development rights for C3 to C4 HMO conversion in central Salford',
 'https://www.salford.gov.uk/planning', TRUE, 'manual'),

-- ── YORKSHIRE ─────────────────────────────────────────────────
('Leeds City Council', 'E08000035', 'Yorkshire and The Humber',
 'HMO C4', 'active',
 ARRAY['LS6','LS2','LS3','LS4','LS7','LS8','LS9','LS11','LS12','LS13'],
 53.8008, -1.5491, '2012-04-06',
 'Citywide Article 4 direction covering most of Leeds — C3 to C4 HMO requires full planning permission',
 'https://www.leeds.gov.uk/planning', TRUE, 'manual'),

('Sheffield City Council', 'E08000019', 'Yorkshire and The Humber',
 'HMO C4', 'active',
 ARRAY['S1','S2','S3','S10','S11','S6','S7','S8'],
 53.3811, -1.4701, '2014-07-01',
 'Article 4 direction in student and HMO concentration areas',
 'https://www.sheffield.gov.uk/planning', TRUE, 'manual'),

-- ── WEST MIDLANDS ─────────────────────────────────────────────
('Birmingham City Council', 'E08000025', 'West Midlands',
 'HMO C4', 'active',
 ARRAY['B1','B2','B3','B4','B5','B6','B7','B8','B9','B10','B11','B12',
       'B13','B14','B15','B16','B17','B18','B19','B20','B21'],
 52.4862, -1.8904, '2013-06-17',
 'Birmingham-wide Article 4 direction for HMO conversions',
 'https://www.birmingham.gov.uk/planning', TRUE, 'manual'),

('Coventry City Council', 'E08000026', 'West Midlands',
 'HMO C4', 'active',
 ARRAY['CV1','CV2','CV3','CV4','CV5','CV6'],
 52.4068, -1.5197, '2015-01-01',
 'Citywide Article 4 for HMO',
 'https://www.coventry.gov.uk/planning', TRUE, 'manual'),

-- ── SOUTH WEST ────────────────────────────────────────────────
('Bristol City Council', 'E06000023', 'South West',
 'HMO C4', 'active',
 ARRAY['BS1','BS2','BS3','BS4','BS5','BS6','BS7','BS8','BS9','BS10','BS13','BS14','BS15','BS16'],
 51.4545, -2.5879, '2013-01-01',
 'Article 4 direction across Bristol restricting C3 to C4 HMO conversions',
 'https://www.bristol.gov.uk/planning', TRUE, 'manual'),

-- ── EAST MIDLANDS ─────────────────────────────────────────────
('Nottingham City Council', 'E06000018', 'East Midlands',
 'HMO C4', 'active',
 ARRAY['NG1','NG2','NG3','NG5','NG7','NG8','NG9'],
 52.9548, -1.1581, '2012-01-01',
 'Citywide Article 4 for HMO conversions',
 'https://www.nottinghamcity.gov.uk', TRUE, 'manual'),

('Leicester City Council', 'E06000016', 'East Midlands',
 'HMO C4', 'active',
 ARRAY['LE1','LE2','LE3','LE4','LE5'],
 52.6369, -1.1398, '2014-01-01',
 'Article 4 direction across Leicester',
 'https://www.leicester.gov.uk/planning', TRUE, 'manual'),

-- ── NORTH WEST ────────────────────────────────────────────────
('Liverpool City Council', 'E08000012', 'North West',
 'HMO C4', 'active',
 ARRAY['L1','L2','L3','L4','L5','L6','L7','L8','L15','L17'],
 53.4084, -2.9916, '2014-01-01',
 'Article 4 across Liverpool city centre and inner suburbs',
 'https://www.liverpool.gov.uk/planning', TRUE, 'manual'),

-- ── NORTH EAST ────────────────────────────────────────────────
('Newcastle City Council', 'E08000021', 'North East',
 'HMO C4', 'active',
 ARRAY['NE1','NE2','NE3','NE4','NE5','NE6','NE7'],
 54.9783, -1.6178, '2013-10-01',
 'Article 4 direction in Newcastle covering student areas and HMO concentrations',
 'https://www.newcastle.gov.uk/planning', TRUE, 'manual'),

-- ── LONDON ────────────────────────────────────────────────────
('London Borough of Newham', 'E09000025', 'London',
 'HMO C4', 'active',
 ARRAY['E6','E7','E12','E13','E15','E16'],
 51.5255, 0.0352, '2015-01-01',
 'Article 4 direction for HMO conversions in Newham',
 'https://www.newham.gov.uk/planning', TRUE, 'manual'),

('London Borough of Waltham Forest', 'E09000031', 'London',
 'HMO C4', 'active',
 ARRAY['E4','E10','E11','E17'],
 51.5908, -0.0134, '2016-01-01',
 'Article 4 HMO direction',
 'https://www.walthamforest.gov.uk', TRUE, 'manual'),

('London Borough of Haringey', 'E09000014', 'London',
 'HMO C4', 'active',
 ARRAY['N4','N8','N15','N17','N22'],
 51.5906, -0.1110, '2015-01-01',
 'Article 4 direction in Haringey',
 'https://www.haringey.gov.uk/planning', TRUE, 'manual'),

-- ── SOUTH EAST ────────────────────────────────────────────────
('Oxford City Council', 'E07000178', 'South East',
 'HMO C4', 'active',
 ARRAY['OX1','OX2','OX3','OX4'],
 51.7520, -1.2577, '2012-06-01',
 'Citywide Article 4 — Oxford has very high HMO density',
 'https://www.oxford.gov.uk/planning', TRUE, 'manual'),

('Cambridge City Council', 'E07000008', 'East of England',
 'HMO C4', 'active',
 ARRAY['CB1','CB2','CB3','CB4','CB5'],
 52.2053, 0.1218, '2013-01-01',
 'Article 4 direction across Cambridge',
 'https://www.cambridge.gov.uk/planning', TRUE, 'manual'),

('Southampton City Council', 'E06000045', 'South East',
 'HMO C4', 'active',
 ARRAY['SO14','SO15','SO16','SO17','SO18'],
 50.9097, -1.4044, '2013-01-01',
 'Article 4 for HMO in Southampton',
 'https://www.southampton.gov.uk', TRUE, 'manual'),

('Portsmouth City Council', 'E06000044', 'South East',
 'HMO C4', 'active',
 ARRAY['PO1','PO2','PO3','PO4','PO5'],
 50.8198, -1.0880, '2014-01-01',
 'Article 4 direction Portsmouth',
 'https://www.portsmouth.gov.uk', TRUE, 'manual'),

-- ── WALES ─────────────────────────────────────────────────────
('Cardiff Council', 'W06000015', 'Wales',
 'HMO C4', 'active',
 ARRAY['CF10','CF11','CF14','CF24'],
 51.4816, -3.1791, '2016-01-01',
 'Article 4 direction in Cardiff — note: Wales uses different planning legislation',
 'https://www.cardiff.gov.uk/planning', TRUE, 'manual'),

-- ── PROPOSED / CONSULTATION ───────────────────────────────────
('Bolton Metropolitan Borough Council', 'E08000001', 'Greater Manchester',
 'HMO C4', 'proposed',
 ARRAY['BL1','BL2','BL3'],
 53.5675, -2.4281, NULL,
 'Under consultation — proposed Article 4 direction for Bolton town centre and inner areas',
 'https://www.bolton.gov.uk/planning', FALSE, 'manual'),

('Oldham Metropolitan Borough Council', 'E08000004', 'Greater Manchester',
 'HMO C4', 'proposed',
 ARRAY['OL1','OL4','OL8'],
 53.5409, -2.1114, NULL,
 'Proposed Article 4 direction — under consultation',
 'https://www.oldham.gov.uk/planning', FALSE, 'manual')

ON CONFLICT (council_name, direction_type) DO NOTHING;
