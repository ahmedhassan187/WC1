"""Verify database state after fetch_match_results."""
import os
import ssl
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# ── Global SSL workaround for Supabase certificate hostname mismatch ──
_original_context = ssl.create_default_context

def _relaxed_ssl_context() -> ssl.SSLContext:
    ctx = _original_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx

ssl._create_default_https_context = _relaxed_ssl_context

sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

# Count tables
for table in ["teams", "matches", "match_results", "predictions", "user_scores", "players"]:
    r = sb.table(table).select("*", count="exact").execute()
    print(f"{table}: {len(r.data or [])} rows")

# Check match statuses
r = sb.table("matches").select("status", count="exact").execute()
if r.data:
    statuses = {}
    for m in r.data:
        s = m["status"]
        statuses[s] = statuses.get(s, 0) + 1
    print(f"Match statuses: {statuses}")

# Check some match_results
r = sb.table("match_results").select("match_id, home_score, away_score").limit(5).execute()
if r.data:
    for m in r.data:
        print(f"  Match {m['match_id']}: {m['home_score']}-{m['away_score']}")
    
# Check all matches with results
r = sb.table("matches").select("id, home_team:teams!matches_home_team_id_fkey(name), away_team:teams!matches_away_team_id_fkey(name), status, stage").order("id", desc=False).execute()
if r.data:
    finished = [m for m in r.data if m["status"] == "finished"]
    scheduled = [m for m in r.data if m["status"] == "scheduled"]
    print(f"\nFinished matches: {len(finished)}")
    print(f"Scheduled matches: {len(scheduled)}")
    for m in finished[:3]:
        home = m.get("home_team", {}).get("name", "?")
        away = m.get("away_team", {}).get("name", "?")
        print(f"  {home} vs {away} [{m['stage']}]")