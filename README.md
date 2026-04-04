# 🏠 Metusa Deal Analyzer

**AI-Powered Property Investment Analysis Tool**

Professional deal analysis for property investors, sourcers, and landlords. Get comprehensive PDF reports with investment verdicts in 60 seconds.

---

## ✨ Features

- 🔗 **URL Analysis** - Paste Rightmove/Zoopla/OnTheMarket links - AI extracts all details
- 🤖 **Fully AI-Powered** - Smart analysis with investment insights and recommendations  
- ⚡ **Instant Analysis** - Get results in under 60 seconds
- 📊 **AI Deal Score** - Smart 0-100 scoring based on multiple factors
- 📈 **5-Year Projection** - Long-term cashflow and equity forecasts
- 📄 **Professional PDF Reports** - Investor-grade analysis documents
- 🎯 **Smart Verdicts** - PROCEED/REVIEW/AVOID recommendations
- 💰 **Accurate Calculations** - Up-to-date Stamp Duty (5% surcharge), yields, cashflow, ROI
- 🔒 **Enterprise Security** - Rate limiting, input validation, XSS protection

### Two Input Modes:
1. **🔗 Property URL** - Paste a link from Rightmove, Zoopla, or OnTheMarket - AI auto-extracts details
2. **📝 Manual Entry** - Enter property details manually for analysis

---

## 🚀 Quick Start

### Option 1: One-Command Setup (Recommended)

```bash
./run.sh
```

This will:
- Create a virtual environment
- Install dependencies
- Start the server
- Open at http://localhost:5000

### Option 2: Manual Setup

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

### Option 3: Docker (Coming Soon)

```bash
docker build -t metusa-deal-analyzer .
docker run -p 5000:5000 metusa-deal-analyzer
```

---

## 📋 Prerequisites

### Required
- Python 3.8 or higher
- pip (Python package manager)

### Optional (for PDF generation)
- wkhtmltopdf
  - **Mac**: `brew install --cask wkhtmltopdf`
  - **Linux**: `sudo apt-get install wkhtmltopdf`
  - **Windows**: Download from [wkhtmltopdf.org](https://wkhtmltopdf.org/)

---

## 🎨 Usage

### 1. Open the App
Navigate to `http://localhost:5000` in your browser.

### 2. Enter Property Details
- **Address** - Full property address
- **Postcode** - For area analysis
- **Deal Type** - BTL, BRR, HMO, or Flip

### 3. Input Financials
- **Purchase Price** - Property asking price
- **Monthly Rent** - Expected rental income
- **Deposit %** - Usually 25% for BTL
- **Interest Rate** - Current mortgage rate (default: 4.0%)

### 4. Get Your Analysis
Click "Analyze This Deal" and receive:
- Investment verdict (PROCEED/REVIEW/AVOID)
- Key metrics (Yield, Cashflow, ROI)
- Professional PDF report
- Risk assessment
- Next steps recommendations

---

## 💰 Pricing Tiers

| Plan | Price | Reports | Features |
|------|-------|---------|----------|
| **Free** | £0 | 1/month | Basic analysis |
| **Pay-Per-Deal** | £15 | Per report | Full PDF report |
| **Starter** | £29/mo | 5/month | All features |
| **Pro** | £79/mo | 20/month | API access |
| **Unlimited** | £199/mo | Unlimited | White-label |

---

## 🛠️ Technology Stack

### Frontend
- HTML5, CSS3, JavaScript
- Responsive design (mobile-first)
- Modern CSS Grid & Flexbox

### Backend
- **Framework**: Flask (Python)
- **PDF Generation**: pdfkit + wkhtmltopdf
- **Templates**: Jinja2
- **CORS**: Flask-CORS

### AI Integration
- OpenClaw AI for analysis text generation
- Professional calculation methodology
- Risk assessment algorithms

---

## 📁 Project Structure

```
metusa-deal-analyzer/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── run.sh                # Setup & run script
├── README.md             # This file
├── templates/
│   └── index.html        # Frontend UI
├── static/
│   ├── css/             # Stylesheets
│   └── js/              # JavaScript files
└── output/              # Generated PDFs
```

---

## 🔧 Configuration

### Environment Variables

Create a `.env` file:

```env
FLASK_ENV=production
FLASK_SECRET_KEY=your-secret-key-here
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
```

### Customization

Edit these files to customize:
- `templates/index.html` - UI design, colors, branding
- `app.py` - Calculation formulas, logic
- PDF template in `generate_pdf_report()` - Report layout

---

## 🧪 Testing

### Run Tests
```bash
python -m pytest tests/
```

### Test Data
Example deal to test:
- **Address**: 42 Oakfield Avenue, Manchester M14 6LT
- **Type**: BTL
- **Price**: £185,000
- **Rent**: £950/month
- **Deposit**: 25%
- **Interest**: 4.0%

**Expected Result**: PROCEED (6.16% yield, positive cashflow)

---

## 🚀 Deployment

### Local Development
```bash
python app.py
```

### Production Deployment

#### Option 1: Heroku
```bash
# Install Heroku CLI
heroku create metusa-deal-analyzer
git push heroku main
```

#### Option 2: DigitalOcean / VPS
```bash
# Use Gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

#### Option 3: Docker
```bash
docker build -t metusa-deal-analyzer .
docker run -d -p 5000:5000 --name deal-analyzer metusa-deal-analyzer
```

---

## 📝 API Documentation

### POST /extract-url
Extract property details from a listing URL (Rightmove, Zoopla, OnTheMarket).

**Request:**
```json
{
  "url": "https://www.rightmove.co.uk/properties/12345678"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "address": "42 Oakfield Avenue, Manchester",
    "postcode": "M14 6LT",
    "price": 185000,
    "property_type": "Semi-Detached",
    "bedrooms": 3
  }
}
```

### POST /ai-analyze
Full AI-powered deal analysis with insights.

**Request:**
```json
{
  "address": "42 Oakfield Avenue, Manchester",
  "postcode": "M14 6LT",
  "dealType": "BTL",
  "purchasePrice": "185000",
  "monthlyRent": "950",
  "deposit": "25",
  "interestRate": "4.0"
}
```

**Response:**
```json
{
  "success": true,
  "results": {
    "verdict": "PROCEED",
    "gross_yield": "6.16",
    "monthly_cashflow": 226,
    "cash_on_cash": "8.42",
    "deal_score": 75,
    "ai_verdict": "This property represents a strong investment...",
    "ai_strengths": "• Strong gross yield...<br>• Positive cashflow...",
    "ai_risks": "• Market conditions...<br>• Void periods...",
    "ai_area": "M14 shows good rental demand...",
    "ai_next_steps": "1. Verify comparables<br>2. Arrange viewing..."
  }
}
```

### POST /download-pdf
Generate and download PDF report.

**Request:** Same as /ai-analyze

**Response:** PDF file download

---

## 🐛 Troubleshooting

### Issue: PDF generation fails
**Solution**: Install wkhtmltopdf
```bash
# Mac
brew install --cask wkhtmltopdf

# Linux
sudo apt-get install wkhtmltopdf
```

### Issue: Port 5000 already in use
**Solution**: Change port in app.py
```python
app.run(debug=True, port=5001)  # Use different port
```

### Issue: Dependencies fail to install
**Solution**: Update pip and setuptools
```bash
pip install --upgrade pip setuptools
pip install -r requirements.txt
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT License - see LICENSE file for details

---

## 👨‍💻 Author

**Metusa Property** - Professional Deal Sourcing & Analysis

- Website: [metusaproperty.co.uk](https://metusaproperty.co.uk)
- Email: uche@metusaproperty.co.uk

---

## 🙏 Acknowledgments

- Property investment formulas based on industry standards
- Stamp duty calculations per UK government guidelines
- UI design inspired by modern fintech applications

---

## 📊 Metalyzi Benchmark Database

The platform includes a proprietary benchmark database covering UK postcode districts, built from government open data sources (all Open Government Licence).

### Data Sources

| Source | Data | Update Frequency |
|--------|------|-----------------|
| **Land Registry PPD** | Median/avg sold prices, transaction counts per district | Monthly |
| **VOA PRMS** | Median/quartile rents by local authority + bedrooms | Annual |
| **ONS HPI** | 5-year compound price growth rates | Monthly |

### Database Schema

Two Supabase tables:
- `postcode_benchmarks` — district-level price, rent, yield, void rate, and growth data
- `benchmark_update_log` — pipeline run history with error tracking

### Running the Pipeline

```bash
# Set environment variables
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_SERVICE_KEY=your-service-role-key

# Seed initial data for priority districts (first run)
python scripts/update_benchmarks.py --seed

# Monthly update (all sources)
python scripts/update_benchmarks.py

# Update specific source only
python scripts/update_benchmarks.py --source land-registry
python scripts/update_benchmarks.py --source voa
```

### Automated Monthly Updates

The pipeline can be triggered via the `/api/benchmarks/update` endpoint (protected by `BENCHMARK_CRON_SECRET` header). Set up an external cron service (e.g., cron-job.org) to call:

```
POST https://metusa-deal-analyzer.onrender.com/api/benchmarks/update
Headers: X-Cron-Secret: <your-secret>
```

Schedule: `0 9 15 * *` (9am on 15th of each month)

### How Benchmarks Power Deal Analysis

When a deal is analysed:
1. `get_benchmark_for_postcode()` queries the database with a 4-level fallback (exact match → district+type → district-only → nearest prefix)
2. Benchmark data is injected into the Claude AI prompt as structured context
3. The frontend displays a "Benchmark Comparison" panel showing the deal vs district medians
4. The existing `compare_to_regional_benchmark()` function also runs using the hardcoded REGIONAL_BENCHMARKS dictionary for backwards compatibility

### Priority Seed Districts

LS1, LS2, LS6, LS11, M1, M14, M40, B1, B29, L1, L8, S1, S2, NG1, NG7, E1, E3, N17, SE15, SW9, W12, BL1, BL9, WN1, SK1, SK16, BS1, BS3, GL1, OX1, CB1, MK1, NE1, NE6, SR1, TS1, HU1, G1, G42, EH1, EH6, CF1, CF24

---

## 📞 Support

For support, email uche@metusaproperty.co.uk or open an issue on GitHub.

---

**Ready to analyze your first deal?** Run `./run.sh` and open http://localhost:5000 🚀

