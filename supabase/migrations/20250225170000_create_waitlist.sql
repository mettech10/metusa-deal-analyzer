-- Create waitlist table for email collection
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS waitlist (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  source TEXT DEFAULT 'website',
  converted BOOLEAN DEFAULT FALSE
);

-- Enable Row Level Security
ALTER TABLE waitlist ENABLE ROW LEVEL SECURITY;

-- Allow inserts from public (for the waitlist form)
CREATE POLICY "Allow public inserts" ON waitlist
  FOR INSERT TO public WITH CHECK (true);

-- Allow service role to read all
CREATE POLICY "Allow service role full access" ON waitlist
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS waitlist_email_idx ON waitlist(email);
