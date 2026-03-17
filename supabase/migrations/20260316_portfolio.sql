-- Portfolio Properties Table
CREATE TABLE IF NOT EXISTS portfolio_properties (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  
  -- Property Details
  address TEXT NOT NULL,
  postcode TEXT,
  property_type TEXT DEFAULT 'residential',
  bedrooms INTEGER,
  
  -- Financials
  purchase_price DECIMAL(12,2) NOT NULL,
  purchase_date DATE,
  current_value DECIMAL(12,2) NOT NULL,
  monthly_rent DECIMAL(10,2) NOT NULL,
  mortgage_balance DECIMAL(12,2) DEFAULT 0,
  
  -- Calculated Fields
  gross_yield DECIMAL(5,2),
  equity DECIMAL(12,2),
  equity_gain DECIMAL(12,2),
  equity_gain_percent DECIMAL(5,2),
  
  -- Status & Notes
  status TEXT DEFAULT 'active',
  notes TEXT,
  
  -- Metadata
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_portfolio_user_id ON portfolio_properties(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_status ON portfolio_properties(status);

-- Enable RLS
ALTER TABLE portfolio_properties ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view own properties" 
  ON portfolio_properties FOR SELECT 
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own properties" 
  ON portfolio_properties FOR INSERT 
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own properties" 
  ON portfolio_properties FOR UPDATE 
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own properties" 
  ON portfolio_properties FOR DELETE 
  USING (auth.uid() = user_id);

-- Saved Comparisons Table
CREATE TABLE IF NOT EXISTS saved_comparisons (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  
  name TEXT NOT NULL,
  deals JSONB NOT NULL, -- Array of deal data
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comparisons_user_id ON saved_comparisons(user_id);

ALTER TABLE saved_comparisons ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own comparisons" 
  ON saved_comparisons FOR SELECT 
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own comparisons" 
  ON saved_comparisons FOR INSERT 
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own comparisons" 
  ON saved_comparisons FOR DELETE 
  USING (auth.uid() = user_id);