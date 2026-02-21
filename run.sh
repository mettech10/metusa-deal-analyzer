#!/bin/bash
# Setup and run script for Metusa Deal Analyzer

echo "🏠 Metusa Deal Analyzer - Setup Script"
echo "========================================"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python 3 found"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip."
    exit 1
fi

echo "✅ pip3 found"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🚀 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if wkhtmltopdf is installed (needed for PDF generation)
if ! command -v wkhtmltopdf &> /dev/null; then
    echo "⚠️  Warning: wkhtmltopdf is not installed."
    echo "PDF generation may not work. Install it with:"
    echo "  Mac: brew install --cask wkhtmltopdf"
    echo "  Linux: sudo apt-get install wkhtmltopdf"
    echo "  Windows: Download from https://wkhtmltopdf.org/"
fi

# Run the application
echo ""
echo "🎯 Starting Metusa Deal Analyzer..."
echo "Open your browser and go to: http://localhost:5000"
echo ""
python app.py
