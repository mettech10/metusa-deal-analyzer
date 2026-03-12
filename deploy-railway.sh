#!/bin/bash
# Quick deploy script for Railway

echo "🚀 Metusa Deal Analyzer - Railway Deployment"
echo "=============================================="

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "📦 Installing Railway CLI..."
    npm install -g @railway/cli
fi

echo "✅ Railway CLI found"

# Check if logged in
if ! railway whoami &> /dev/null; then
    echo "🔑 Please login to Railway..."
    railway login
fi

echo "✅ Logged in to Railway"

# Initialize project if not already
if [ ! -f ".railway/config.json" ]; then
    echo "🆕 Creating new Railway project..."
    railway init
else
    echo "✅ Railway project already initialized"
fi

# Deploy
echo ""
echo "🚀 Deploying to Railway..."
railway up

# Get domain
echo ""
echo "🌐 Getting your live URL..."
railway domain

echo ""
echo "✅ Deployment complete!"
echo "📊 Your app should be live in 2-3 minutes"
echo ""
echo "Next steps:"
echo "1. Test the live URL"
echo "2. Add custom domain: analyzer.metusaproperty.co.uk"
echo "3. Set environment variables in Railway dashboard"
