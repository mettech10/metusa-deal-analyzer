-- Metalyzi Benchmark Database
-- Postcode-district-level investment return benchmarks from UK government open data

CREATE TABLE IF NOT EXISTS postcode_benchmarks (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  postcode_district VARCHAR(10) NOT NULL,
  property_type VARCHAR(50) NOT NULL DEFAULT 'all',
  bedrooms INTEGER,

  -- Sold price data (Land Registry PPD)
  median_sold_price DECIMAL(12,2),
  avg_sold_price DECIMAL(12,2),
  transaction_count_12m INTEGER,
  price_growth_5yr_pct DECIMAL(5,2),

  -- Rental data (VOA Private Rental Market Statistics)
  median_monthly_rent DECIMAL(8,2),
  lower_quartile_rent DECIMAL(8,2),
  upper_quartile_rent DECIMAL(8,2),

  -- Yield benchmarks (calculated from price + rent)
  gross_yield_median DECIMAL(5,2),
  gross_yield_lower DECIMAL(5,2),
  gross_yield_upper DECIMAL(5,2),

  -- Void rate proxy (MHCLG vacancy data)
  void_rate_pct DECIMAL(5,2),
  avg_days_to_let INTEGER,

  -- Transaction activity (HMRC)
  btl_transaction_share_pct DECIMAL(5,2),

  -- Metadata
  data_source VARCHAR(100),
  last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  data_month VARCHAR(7),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  UNIQUE(postcode_district, property_type, bedrooms)
);

CREATE INDEX IF NOT EXISTS idx_benchmarks_district
  ON postcode_benchmarks (postcode_district, property_type, bedrooms);

CREATE INDEX IF NOT EXISTS idx_benchmarks_updated
  ON postcode_benchmarks (last_updated);

-- Update log table
CREATE TABLE IF NOT EXISTS benchmark_update_log (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  run_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  districts_updated INTEGER DEFAULT 0,
  districts_added INTEGER DEFAULT 0,
  records_upserted INTEGER DEFAULT 0,
  errors TEXT,
  duration_ms INTEGER,
  data_month VARCHAR(7),
  source VARCHAR(50),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- RLS: benchmarks are public read, service role write
ALTER TABLE postcode_benchmarks ENABLE ROW LEVEL SECURITY;
ALTER TABLE benchmark_update_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Benchmarks are publicly readable"
  ON postcode_benchmarks FOR SELECT
  USING (true);

CREATE POLICY "Only service role can write benchmarks"
  ON postcode_benchmarks FOR ALL
  USING (auth.role() = 'service_role');

CREATE POLICY "Only service role can read update log"
  ON benchmark_update_log FOR ALL
  USING (auth.role() = 'service_role');
