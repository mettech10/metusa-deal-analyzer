# DEAL ANALYZER WEB APP - COMPLETE PROMPT

## 🎯 App Overview

**Name:** Metusa Deal Analyzer  
**Purpose:** AI-powered property investment analysis tool for deal sourcers and investors  
**Target Users:** Property investors, deal sourcers, landlords, first-time buyers  
**Output:** Professional PDF deal analysis reports with investment verdict

---

## 📱 Core Features

### 1. PROPERTY INPUT FORM
**Fields Required:**
- **Property Address** (full address with postcode)
- **Deal Type** (dropdown: BTL, BRR, HMO, FLIP)
- **Purchase Price** (£ input)
- **Monthly Rent** (£ input, or ARV for flips)
- **Deposit %** (default: 25%, range: 20-40%)
- **Interest Rate** (default: 4.0%, current market rates)
- **Refurbishment Costs** (if BRR/Flip)
- **After Repair Value** (if BRR/Flip)
- **User Email** (for report delivery)
- **User Name** (personalization)

**Optional Fields:**
- Property photos (upload or URLs)
- Specific fees (legal, valuation, arrangement)
- Room count (for HMO)
- Room rates (for HMO)

---

### 2. AI ANALYSIS ENGINE

**When user submits form:**

1. **Extract Property Data**
   - Parse all form inputs
   - Validate required fields
   - Calculate derived values

2. **Perform Calculations**
   - Stamp duty (3% surcharge for 2nd properties)
   - Total purchase costs
   - Deposit amount
   - Loan amount
   - Monthly mortgage (interest-only)
   - Annual rent
   - Operating expenses:
     * Management (10%)
     * Void periods (2 weeks)
     * Maintenance reserve (8%)
     * Insurance (£480/year)
   - Net annual income
   - Monthly cashflow
   - Gross yield %
   - Net yield %
   - Cash-on-cash return %

3. **Generate Investment Verdict**
   - **PROCEED**: All metrics exceed targets, low risk
   - **REVIEW**: Borderline metrics, medium risk  
   - **AVOID**: Below targets or high risk

4. **Area Research** (if address provided)
   - Postcode analysis
   - Rental demand indicators
   - Transport links
   - Crime statistics (via Police UK API)
   - Market trends

5. **Risk Assessment**
   - Market risk (location quality)
   - Tenant demand risk
   - Refurbishment risk (if applicable)
   - Finance risk
   - Overall risk rating

6. **Write Analysis Text**
   - Executive summary
   - Strengths of the deal
   - Weaknesses/concerns
   - Specific recommendations
   - Next steps checklist

---

### 3. PDF REPORT GENERATION

**Report Structure:**

**Page 1 - Executive Summary**
- Header with Metusa Property branding
- Property address and deal type
- 4 key metric cards (Yield, Cashflow, CoC, Risk)
- Investment verdict (PROCEED/REVIEW/AVOID)

**Page 2 - Financial Analysis**
- Purchase costs breakdown table
- Financing structure table
- Income & expenses table
- Key metrics summary

**Page 3 - Area Analysis**
- Location profile
- Rental demand assessment
- Transport links
- Crime statistics
- Market indicators

**Page 4 - Risk Assessment & Recommendation**
- Risk matrix (4 categories)
- Overall risk rating
- Strengths (bullet points)
- Weaknesses (bullet points)
- Next steps checklist
- Investment verdict box

**Styling:**
- Navy (#1B1F3B) and Gold (#D4AF37) brand colors
- Professional fonts (Arial/Helvetica)
- Clean tables and charts
- Photo placeholders (if uploaded)
- Footer with contact info and date

---

### 4. EMAIL DELIVERY

**Automated email sent to user:**
- Subject: "Your Deal Analysis Report - [Property Address]"
- Body: Brief summary + PDF attachment
- Professional formatting
- Call-to-action (contact for more deals)

---

## 🎨 UI/UX Design

### Landing Page
```
┌─────────────────────────────────────────┐
│  METUSA DEAL ANALYZER                   │
│  "Professional property investment       │
│   analysis in 60 seconds"                │
│                                         │
│  [Photo 1] [Photo 2] [Photo 3]          │
│                                         │
│  [Start Analysis - Button]              │
│                                         │
│  ⚡ Instant  📈 PDF  🎯 Expert          │
│                                         │
└─────────────────────────────────────────┘
```

### Form Page
- Clean, step-by-step form
- Progress indicator (Step 1 of 3)
- Help tooltips for each field
- Real-time validation
- Auto-save draft

### Results Page
- Loading animation while analyzing
- Summary cards with key metrics
- Download PDF button
- Email report button
- Share results option

---

## 💰 Pricing Tiers

### FREE TIER
- 1 free analysis per month
- Basic PDF report
- Email delivery

### PAY-PER-DEAL - £15/report
- Full professional report
- Area analysis included
- Email delivery
- No subscription

### STARTER - £29/month
- 5 reports per month
- Full features
- Priority support
- Historical reports

### PRO - £79/month  
- 20 reports per month
- Full features
- API access
- White-label options
- Phone support

### UNLIMITED - £199/month
- Unlimited reports
- All features
- Custom branding
- Dedicated support
- Team access (5 users)

---

## 🔧 Technical Requirements

### Frontend
- **Framework:** React or Vue.js
- **Styling:** Tailwind CSS or similar
- **Responsive:** Mobile-first design
- **Form Library:** React Hook Form or Formik
- **Validation:** Yup or Zod

### Backend
- **Framework:** Node.js (Express) or Python (Flask/FastAPI)
- **PDF Generation:** Puppeteer (HTML to PDF) or ReportLab
- **Email:** SendGrid or AWS SES
- **Database:** PostgreSQL (user data, reports)
- **File Storage:** AWS S3 or similar

### AI Integration
- **Analysis Engine:** OpenClaw AI integration
- **Calculations:** Server-side formulas
- **PDF Generation:** Automated HTML template filling
- **Email:** Automated delivery

### APIs Needed
- **Land Registry API:** Sold prices (free)
- **Police UK API:** Crime data (free)
- **PropertyData API:** Rental valuations (£49/mo)
- **Postcodes.io:** Postcode lookup (free)

---

## 📊 Success Metrics

### User Metrics
- Sign-up rate
- Free to paid conversion
- Monthly active users
- Reports generated
- Retention rate

### Business Metrics
- Monthly recurring revenue (MRR)
- Average revenue per user (ARPU)
- Customer lifetime value (LTV)
- Churn rate
- Customer acquisition cost (CAC)

### Quality Metrics
- Report accuracy (validate against manual calculations)
- User satisfaction (NPS score)
- Support ticket volume
- Feature usage breakdown

---

## 🚀 Launch Strategy

### Phase 1: MVP (Week 1-2)
- Basic form
- BTL calculations only
- PDF generation
- Email delivery

### Phase 2: Core Features (Week 3-4)
- All deal types (BTL, BRR, HMO, Flip)
- Area analysis
- Risk assessment
- Payment integration

### Phase 3: Advanced (Month 2)
- User accounts & history
- Subscription management
- API access
- Team features

### Phase 4: Scale (Month 3+)
- Mobile app
- Integrations (CRM, accounting)
- White-label for agents
- International expansion

---

## 📝 Copy & Messaging

### Headlines
- "Analyze Property Deals in 60 Seconds"
- "Professional Deal Analysis, Instantly"
- "Know If It's a Good Deal Before You Buy"
- "The Deal Analyzer Trusted by 1000+ Investors"

### Value Propositions
- Save hours of manual calculations
- Professional reports for investors
- Make data-driven decisions
- Avoid bad deals before you commit

### Call-to-Actions
- "Analyze Your First Deal Free"
- "Get Your Deal Report"
- "Start Free Trial"
- "See Sample Report"

---

## 🔒 Security & Compliance

### Data Protection
- GDPR compliant (UK/EU users)
- Data encryption at rest and in transit
- Secure payment processing (Stripe)
- Regular security audits

### User Data
- Property addresses encrypted
- No sharing with third parties
- Users can delete their data
- Retention policy (2 years)

---

## 📞 Support & Documentation

### Help Center
- FAQ section
- Video tutorials
- Calculation methodology
- Glossary of terms

### Support Channels
- Email support (all tiers)
- Live chat (Pro+)
- Phone support (Unlimited)
- Community forum

### Documentation
- API documentation
- Integration guides
- White-label setup
- Developer resources

---

## 🎯 Future Enhancements

### V2 Features
- **Image Analysis:** Upload property photos, AI estimates refurb costs
- **Comparables:** Automatic similar property search
- **Portfolio Tracking:** Manage multiple properties
- **Market Alerts:** Get notified of new deals
- **Investor Matching:** Connect sourcers with investors

### AI Enhancements
- **Price Prediction:** AI estimates fair market value
- **Rent Estimation:** Suggests achievable rent
- **Refurb Cost Estimator:** Based on photos/description
- **Investment Strategy:** Recommends best strategy for property

---

## ✅ Checklist for Development

### Frontend
- [ ] Landing page design
- [ ] Form components
- [ ] Results display
- [ ] PDF viewer
- [ ] Payment integration
- [ ] User dashboard

### Backend
- [ ] API endpoints
- [ ] Calculation engine
- [ ] PDF generation
- [ ] Email service
- [ ] Database schema
- [ ] Authentication

### AI Integration
- [ ] Calculation logic
- [ ] Analysis text generation
- [ ] Risk assessment
- [ ] PDF template

### Testing
- [ ] Unit tests (calculations)
- [ ] Integration tests
- [ ] User testing
- [ ] Performance testing

### Launch
- [ ] Domain setup
- [ ] SSL certificate
- [ ] Analytics tracking
- [ ] Support system
- [ ] Marketing materials

---

**Ready to build the Metusa Deal Analyzer! 🚀🏠**
