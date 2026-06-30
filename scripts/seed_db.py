"""
Seed Supabase with scraped data.

Requires:
    - Supabase project with tables created via seed.sql
    - scripts/teams.json and scripts/matches.json from scrape_data.py
    - .env file with SUPABASE_URL and SUPABASE_SERVICE_KEY

Usage:
    py -3.14 scripts/seed_db.py
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Load scraped data
try:
    with open("scripts/teams.json", encoding="utf-8") as f:
        teams_data = json.load(f)
    with open("scripts/matches.json", encoding="utf-8") as f:
        matches_data = json.load(f)
except FileNotFoundError:
    print("ERROR: Run scrape_data.py first to generate teams.json and matches.json")
    sys.exit(1)

# ── Seed Teams ──
print(f"\nSeeding {len(teams_data)} teams...")
team_id_map = {}

for team in teams_data:
    existing = sb.table("teams").select("id").eq("name", team["name"]).execute()
    if existing.data:
        team_id_map[team["name"]] = existing.data[0]["id"]
        continue

    result = sb.table("teams").insert({
        "name": team["name"],
        "group_letter": team["group"],
        "flag_emoji": "",
    }).execute()
    if result.data:
        team_id_map[team["name"]] = result.data[0]["id"]

print(f"Seeded {len(team_id_map)} teams")

# ── Seed Matches ──
print(f"\nSeeding {len(matches_data)} matches...")

BASE_YEAR = 2026
BASE_MONTH = 6
BASE_DAY = 11
TIMEZONE_OFFSET = timedelta(hours=-4)  # EDT (UTC-4), adjust as needed

match_count = 0
for i, match in enumerate(matches_data):
    home_id = team_id_map.get(match["home_team"])
    away_id = team_id_map.get(match["away_team"])

    if not home_id or not away_id:
        print(f"  Skipping: {match['home_team']} vs {match['away_team']} (team not found)")
        continue

    try:
        existing = sb.table("matches").select("id").eq("home_team_id", home_id).eq("away_team_id", away_id).execute()
        if existing.data:
            continue
    except Exception:
        pass

    try:
        time_str = match.get("time", "00:00")
        date_str = match.get("date", "")

        dt_str = f"{date_str} {time_str}"
        dt = datetime.strptime(dt_str, "%d %B %Y %H:%M")
        dt_utc = dt.replace(tzinfo=timezone.utc) - TIMEZONE_OFFSET

        sb.table("matches").insert({
            "home_team_id": home_id,
            "away_team_id": away_id,
            "match_datetime": dt_utc.isoformat(),
            "stage": match.get("stage", "Group Stage"),
            "group_letter": match.get("group", ""),
            "venue": "",
            "status": "scheduled",
        }).execute()
        match_count += 1
    except Exception as e:
        print(f"  Error inserting {match['home_team']} vs {match['away_team']}: {e}")

print(f"Seeded {match_count} matches")
print("\nDone!")
