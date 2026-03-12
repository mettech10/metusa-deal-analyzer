# Metusa Deal Analyzer - Deployment Guide

## 🚀 Quick Deploy to Railway (Recommended)

Railway offers a generous free tier and is the easiest option.

### 1. Sign Up
- Go to https://railway.app
- Sign up with GitHub

### 2. Deploy
Option A: One-Click Deploy (if you put code on GitHub)
```
1. Push this code to a GitHub repo
2. In Railway: New Project → Deploy from GitHub repo
3. Railway auto-detects Python and deploys
```

Option B: CLI Deploy
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
cd metusa-deal-analyzer
railway init

# Deploy
railway up

# Get your URL
railway domain
```

### 3. Your app will be live at:
`https://metusa-deal-analyzer.up.railway.app`

---

## 🚀 Alternative: Render (Free Forever)

### 1. Sign Up
- https://render.com
- Connect GitHub

### 2. Create Web Service
- New → Web Service
- Connect your GitHub repo
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`

### 3. Your app will be live at:
`https://metusa-deal-analyzer.onrender.com`

---

## 🚀 Alternative: PythonAnywhere (Free)

### 1. Sign Up
- https://www.pythonanywhere.com

### 2. Upload Files
- Go to Files tab
- Upload all files from metusa-deal-analyzer folder

### 3. Create Web App
- Go to Web tab
- Add a new web app
- Select Flask
- Python 3.11
- Path: `/home/yourusername/metusa-deal-analyzer/app.py`

### 4. Install Requirements
- Open Bash console
- `pip install -r requirements.txt`

### 5. Reload Web App

---

## 🌐 Step 2: Configure Custom Domain

Once deployed, you need to:

### 1. Get Your Live URL
Example: `https://metusa-deal-analyzer.up.railway.app`

### 2. Add Custom Domain in Hosting Platform
- Railway: Settings → Domains → Add Custom Domain
- Render: Settings → Custom Domains → Add Domain
- Enter: `analyzer.metusaproperty.co.uk`

### 3. Configure DNS (Where you bought your domain)

Login to your domain registrar (where you bought metusaproperty.co.uk):

**Add CNAME Record:**
```
Type: CNAME
Name: analyzer
Value: [your-app-url] (e.g., metusa-deal-analyzer.up.railway.app)
TTL: 3600
```

**Example DNS Settings:**
| Type | Name | Value | TTL |
|------|------|-------|-----|
| CNAME | analyzer | metusa-deal-analyzer.up.railway.app | 3600 |

### 4. Wait for DNS (5-48 hours)
- Usually takes 5-30 minutes
- Check: https://dnschecker.org

---

## ✅ Verification

Once set up, these URLs should work:
- ✅ https://analyzer.metusaproperty.co.uk
- ✅ https://metusa-deal-analyzer.up.railway.app (original)

---

## 🔒 SSL/HTTPS

Railway and Render provide **free SSL certificates** automatically.
Your subdomain will be secure (https://).

---

## 📋 Summary Checklist

- [ ] Deploy app to Railway/Render/PythonAnywhere
- [ ] Get live URL
- [ ] Add custom domain in hosting settings
- [ ] Add CNAME record in domain DNS
- [ ] Wait for DNS propagation
- [ ] Test: https://analyzer.metusaproperty.co.uk

---

## 🆘 Need Help?

**If you get stuck:**
1. Tell me which hosting platform you're using
2. Share the error message
3. I'll guide you through it

**Questions to answer:**
- Do you have a GitHub account?
- Where did you buy metusaproperty.co.uk? (GoDaddy, Namecheap, etc.)
- Do you want me to walk you through deployment step-by-step?
