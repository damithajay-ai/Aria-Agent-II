[README.txt](https://github.com/user-attachments/files/26624908/README.txt)
╔══════════════════════════════════════════════════════════════╗
║    99x Workforce Compliance — Proper Full-Stack Setup       ║
╚══════════════════════════════════════════════════════════════╝

ARCHITECTURE
────────────
frontend/index.html   → UI only (Netlify or any static host)
backend/              → All logic, API calls, data (Railway)

The API key and all business logic live on the backend.
The browser never sees the API key or raw data.


════════════════════════════════════════════════════════════════
STEP 1 — Deploy the backend to Railway
════════════════════════════════════════════════════════════════

1. Go to https://railway.app → Sign up free (use GitHub)

2. Click "New Project" → "Deploy from GitHub repo"

3. Upload the backend/ folder to a GitHub repo first:
   - Go to github.com → New repository → name: 99x-compliance-backend
   - Upload these files:
       main.py
       compliance_engine.py
       requirements.txt
       railway.toml

4. Connect Railway to that GitHub repo

5. Railway auto-detects Python and deploys automatically

6. Once deployed, go to Settings → Variables and add:
       ANTHROPIC_API_KEY = sk-ant-your-key-here

7. Copy your Railway URL — it looks like:
       https://99x-compliance-backend.railway.app


════════════════════════════════════════════════════════════════
STEP 2 — Configure the frontend
════════════════════════════════════════════════════════════════

1. Open frontend/index.html in Notepad

2. Find this line near the top of the script:
       var API_BASE = 'https://YOUR-RAILWAY-APP.railway.app';

3. Replace with your actual Railway URL:
       var API_BASE = 'https://99x-compliance-backend.railway.app';

4. Save the file


════════════════════════════════════════════════════════════════
STEP 3 — Deploy the frontend to Netlify
════════════════════════════════════════════════════════════════

1. Go to netlify.com → Add new project → Deploy manually
2. Drag the frontend/index.html file (rename to index.html first)
3. Done — share the Netlify link with your team


════════════════════════════════════════════════════════════════
WHAT'S DIFFERENT FROM BEFORE
════════════════════════════════════════════════════════════════

BEFORE (broken):                    NOW (correct):
──────────────────────────────────────────────────────────────
API key in HTML file          →     API key in Railway env var
Calculations in browser       →     Calculations on server
CORS proxy hacks              →     Direct server-to-server call
No history storage            →     JSON files saved per month
Everything in one HTML file   →     Clean separation of concerns


════════════════════════════════════════════════════════════════
API ENDPOINTS
════════════════════════════════════════════════════════════════

POST /api/generate   Upload 4 files → returns compliance data
POST /api/chat       Send message → returns Aria reply
GET  /api/history    Returns last 6 months of summaries
GET  /api/report/:month  Returns full data for a specific month
GET  /               Health check


════════════════════════════════════════════════════════════════
TROUBLESHOOTING
════════════════════════════════════════════════════════════════

Backend not responding
→ Check Railway dashboard → Deployments → view logs

ANTHROPIC_API_KEY error
→ Go to Railway → Variables → make sure key is set correctly

CORS error
→ The backend already has CORS enabled for all origins
→ If still failing, check Railway logs for the actual error

Files uploading but wrong results
→ Check that file names match the expected patterns
→ Verify month selection matches the timesheet filename
