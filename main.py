"""
99x Workforce Compliance API
FastAPI backend — handles all business logic, Anthropic calls and data storage
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os, json, httpx
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from compliance_engine import parse_timesheet, parse_staff, parse_leave, parse_holidays, build_report

app = FastAPI(title="99x Compliance API", version="1.0.0")

# CORS — allow the frontend (any origin for now, lock down in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# CONFIGURE: Anthropic API key — set this as an environment variable in Railway
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


# ── Models ────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    month: str
    region: str = "SL"


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "99x Compliance API", "version": "1.0.0"}


# ── Generate report ───────────────────────────────────────────────────────────

@app.post("/api/generate")
async def generate_report(
    timesheet: UploadFile = File(...),
    staff:     UploadFile = File(...),
    leave:     UploadFile = File(...),
    holiday:   UploadFile = File(...),
    month:     str = Form(...),
    region:    str = Form("SL"),
):
    try:
        # Read uploaded files into memory
        ts_bytes  = await timesheet.read()
        sp_bytes  = await staff.read()
        lv_bytes  = await leave.read()
        hol_bytes = await holiday.read()

        # Parse each file
        ts_map, ts_name_map         = parse_timesheet(ts_bytes)
        staff_map                   = parse_staff(sp_bytes)
        leave_map                   = parse_leave(lv_bytes, month)
        working_days, holidays      = parse_holidays(hol_bytes, month, region)

        # Run compliance calculations
        records = build_report(
            ts_map, ts_name_map, staff_map,
            leave_map, working_days, holidays, month
        )

        result = {
            "month":        month,
            "region":       region,
            "working_days": working_days,
            "holidays":     holidays,
            "generated_at": datetime.now().isoformat(),
            "records":      records,
        }

        # Save to JSON store for history
        filename = DATA_DIR / f"{month.lower()}_{region.lower()}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Chat with Aria ────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured on server.")

    # Load report data for context
    filename = DATA_DIR / f"{req.month.lower()}_{req.region.lower()}.json"
    if not filename.exists():
        raise HTTPException(status_code=404, detail=f"No report found for {req.month}. Please generate it first.")

    with open(filename, encoding="utf-8") as f:
        data = json.load(f)

    system_prompt = _build_context(data)

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 800,
                "system":     system_prompt,
                "messages":   [m.dict() for m in req.messages[-10:]],
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data_resp = response.json()
    reply = data_resp["content"][0]["text"] if data_resp.get("content") else "Sorry, I could not process that."
    return {"reply": reply}


# ── History ───────────────────────────────────────────────────────────────────

@app.get("/api/history")
def get_history(last_n: int = 6):
    files = sorted(DATA_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:last_n]
    history = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            d = json.load(fp)
            n = len(d["records"])
            green = sum(1 for r in d["records"] if r["compliance"] >= 80)
            amber = sum(1 for r in d["records"] if 50 <= r["compliance"] < 80)
            red   = sum(1 for r in d["records"] if r["compliance"] < 50)
            avg   = round(sum(r["compliance"] for r in d["records"]) / n) if n else 0
            history.append({
                "month":        d["month"],
                "region":       d.get("region", "SL"),
                "working_days": d["working_days"],
                "total":        n,
                "compliant":    green,
                "at_risk":      amber,
                "non_compliant":red,
                "avg_compliance": avg,
                "generated_at": d.get("generated_at", ""),
            })
    return history


@app.get("/api/report/{month}")
def get_report(month: str, region: str = "SL"):
    filename = DATA_DIR / f"{month.lower()}_{region.lower()}.json"
    if not filename.exists():
        raise HTTPException(status_code=404, detail=f"No report found for {month}/{region}")
    with open(filename, encoding="utf-8") as f:
        return json.load(f)


# ── Context builder for Aria ──────────────────────────────────────────────────

def _build_context(data: dict) -> str:
    records = data["records"]
    n       = len(records)
    green   = [r for r in records if r["compliance"] >= 80]
    amber   = [r for r in records if 50 <= r["compliance"] < 80]
    red     = [r for r in records if r["compliance"] < 50]
    avg     = round(sum(r["compliance"] for r in records) / n) if n else 0

    acct_map = {}
    for r in records:
        for a in (r.get("accounts") or []):
            if a not in acct_map:
                acct_map[a] = {"count": 0, "total": 0}
            acct_map[a]["count"] += 1
            acct_map[a]["total"] += r["compliance"]
    acct_summary = ", ".join(
        f"{a}({v['count']} staff, avg {round(v['total']/v['count'])}%)"
        for a, v in sorted(acct_map.items())
    )

    red_list = "\n".join(
        f"- {r['name']} ({r['empId']}) | {r['compliance']}% | "
        f"{r['contractualHours']}h/{r['requiredHours']}h | {', '.join(r.get('accounts') or [])}"
        for r in sorted(red, key=lambda x: x["compliance"])
    )
    amber_list = "\n".join(
        f"- {r['name']} | {r['compliance']}% | {', '.join(r.get('accounts') or [])}"
        for r in sorted(amber, key=lambda x: x["compliance"])[:20]
    )
    zero_bill = ", ".join(
        r["name"] for r in records if r.get("billableHours", 0) == 0 and r.get("totalHours", 0) > 0
    ) or "None"
    all_emp = "\n".join(
        f"{r['name']}|{r['empId']}|{r['compliance']}%|"
        f"{r.get('contractualHours',0)}h|{r.get('billableHours',0)}bh|"
        f"{r.get('totalLeaveApplied',0)}ld|{', '.join(r.get('accounts') or [])}"
        for r in records
    )

    return (
        f"You are Aria, a concise and helpful HR Intelligence Assistant for 99x.\n\n"
        f"REPORT: {data['month']} | Region: {data.get('region','SL')} | "
        f"Working days: {data['working_days']} | Required: {data['working_days']*8}h\n"
        f"Total: {n} | Compliant(>=80%): {len(green)} | "
        f"At risk(50-79%): {len(amber)} | Non-compliant(<50%): {len(red)} | Avg: {avg}%\n\n"
        f"NON-COMPLIANT:\n{red_list or 'None'}\n\n"
        f"AT RISK:\n{amber_list or 'None'}\n\n"
        f"BY ACCOUNT: {acct_summary}\n\n"
        f"ZERO BILLABLE: {zero_bill}\n\n"
        f"ALL EMPLOYEES:\n{all_emp}"
    )
