# DIVA Studio — Production Deployment Guide

This document provides step-by-step instructions to deploy **DIVA Studio** using **Option 1: Vercel (Frontend) + Railway (Backend)**.

---

## 🏗️ Architecture Overview

- **Frontend (`apps/web`)**: Next.js 16 deployed on **Vercel**
- **Backend (`apps/api`)**: FastAPI + Gunicorn deployed on **Railway**
- **Database**: PostgreSQL hosted on **Supabase** (or Railway Postgres)
- **AI Engine**: fal.ai (Flux Kontext Model)
- **File Storage**: Local persistent volume on Railway `/app/storage` (or Cloudflare R2 / S3)

---

## 🔒 Step 1: Environment Variables Setup

### 1. Backend (`apps/api`) Environment Variables (Railway)
Set the following environment variables in your Railway project settings:

```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_HOST.supabase.co:5432/postgres
JWT_SECRET_KEY=YOUR_SECURE_RANDOM_64_CHAR_SECRET_KEY
ALLOWED_ORIGIN=https://your-diva-web.vercel.app
PUBLIC_BASE_URL=https://your-diva-api.up.railway.app
FLUX_API_KEY=your_fal_ai_api_key
PORT=8000
```

> ⚠️ **SECURITY NOTICE**:
> Generate a strong JWT secret key before deploying using Python:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

---

### 2. Frontend (`apps/web`) Environment Variables (Vercel)
Set the following environment variable in Vercel project settings:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-diva-api.up.railway.app
```

---

## 🚀 Step 2: Backend Deployment (Railway)

1. **Log in to Railway** at [railway.app](https://railway.app).
2. Click **New Project** → **Deploy from GitHub repo**.
3. Select your repository (`Diva`).
4. Set the **Root Directory** to `apps/api`.
5. Railway will automatically detect the `Dockerfile` and `railway.toml` config.
6. Under **Variables**, add all the backend environment variables listed above.
7. Under **Settings** -> **Networking**, click **Generate Domain** to get your public API URL (e.g. `https://diva-api.up.railway.app`).
8. Deploy! The `/health` endpoint will be checked automatically.

---

## 🌐 Step 3: Frontend Deployment (Vercel)

1. **Log in to Vercel** at [vercel.com](https://vercel.com).
2. Click **Add New** → **Project**.
3. Import your GitHub repository (`Diva`).
4. Set the **Framework Preset** to **Next.js**.
5. Set the **Root Directory** to `apps/web`.
6. Expand **Environment Variables** and add:
   - `NEXT_PUBLIC_API_BASE_URL` = `https://your-diva-api.up.railway.app`
7. Click **Deploy**.

---

## 🗄️ Step 4: Database Seeding & Verification

Once the backend is live on Railway, run the database seed script to populate the reference styles catalog if using a fresh database:

```bash
# Connect via local CLI pointing to production DB or run inside Railway terminal:
python -m app.seed
```

---

## ⚙️ Post-Deployment Health Verification

1. **API Health Check**:
   Navigate to `https://your-diva-api.up.railway.app/health`. Expected response:
   ```json
   { "status": "ok" }
   ```

2. **Full User Flow Verification**:
   - Go to `https://your-diva-web.vercel.app`
   - Sign up / Create an account
   - Select a reference preset style
   - Upload a test selfie (face detection will validate)
   - Click **Generate My Image**
   - Verify render completes and can be downloaded from the dashboard
