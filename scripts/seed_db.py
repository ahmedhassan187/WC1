"""
Seed Supabase with scraped data.

Seeds:
  - teams table from teams.json
  - matches table from matches.json (both fixtures and results)
  - match_results table for completed matches with scores

Requires:
    - Supabase project with tables created via seed.sql
    - scripts/teams.json and scripts/matches.json from scrape_data.py
    - .env file with SUPABASE_URL and SUPABASE_SERVICE_KEY

Usage:
    py -3 scripts/seed_db.py
"""

import json
import os
import re
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

# Clean existing data (order matters due to foreign keys)
print("Cleaning existing data...")
for table in ["user_scores", "predictions", "match_results", "matches", "players", "teams"]:
    try:
        sb.table(table).delete().neq("id", 0).execute()
    except Exception:
        pass

# Load scraped data
try:
    with open("scripts/teams.json", encoding="utf-8") as f:
        teams_data = json.load(f)
    with open("scripts/matches.json", encoding="utf-8") as f:
        matches_data = json.load(f)
except FileNotFoundError:
    print("ERROR: Run scrape_data.py first to generate teams.json and matches.json")
    sys.exit(1)


def parse_match_datetime(date_str: str, time_str: str) -> str:
    """
    Parse a date string like "11 June 2026" or "June 11" and time like "1:00 p.m."
    Returns ISO datetime string in UTC.
    """
    # Handle year-less dates (add the year)
    if "2026" not in date_str:
        date_str = f"{date_str} 2026"

    # Handle "June 11 2026" → "11 June 2026"
    month_match = re.match(r"(June|July|August)\s+(\d+)\s+(\d{4})", date_str)
    if month_match:
        month_name = month_match.group(1)
        day = month_match.group(2)
        year = month_match.group(3)
        date_str = f"{day} {month_name} {year}"

    # Parse time (handle a.m./p.m. format)
    time_str = time_str.strip() if time_str else ""
    hour = 0
    minute = 0
    if time_str:
        time_match = re.match(r"(\d+):(\d+)\s*(a\.m\.|p\.m\.)", time_str, re.I)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            ampm = time_match.group(3).lower()
            if "p" in ampm and hour != 12:
                hour += 12
            elif "a" in ampm and hour == 12:
                hour = 0
        else:
            # Try HH:MM format
            time_match = re.match(r"(\d+):(\d+)", time_str)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))

    # Build full datetime string
    dt_str = f"{date_str} {hour:02d}:{minute:02d}"

    try:
        dt = datetime.strptime(dt_str, "%d %B %Y %H:%M")
    except ValueError:
        try:
            dt = datetime.strptime(dt_str, "%d %b %Y %H:%M")
        except ValueError:
            print(f"  Warning: Could not parse date '{dt_str}', using default")
            # Default to noon if we can't parse
            dt = datetime.strptime(f"{date_str} 12:00", "%d %B %Y %H:%M")

    # Add timezone info - assume Wikipedia times are local (Eastern Time for US 2026 WC)
    # The 2026 World Cup is in USA/Canada/Mexico - EDT is UTC-4
    dt_utc = dt.replace(tzinfo=timezone.utc) - timedelta(hours=4)
    return dt_utc.isoformat()


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
        "flag_emoji": team.get("flag_emoji", ""),
        "group_letter": team.get("group", ""),
    }).execute()
    if result.data:
        team_id_map[team["name"]] = result.data[0]["id"]

print(f"Seeded {len(team_id_map)} teams")

# ── Seed Matches ──
print(f"\nSeeding {len(matches_data)} matches...")

match_count = 0
result_count = 0

for i, match in enumerate(matches_data):
    home_id = team_id_map.get(match["home_team"])
    away_id = team_id_map.get(match["away_team"])

    if not home_id or not away_id:
        print(f"  Skipping: {match['home_team']} vs {match['away_team']} (team not found)")
        continue

    # Check if match already exists
    try:
        existing = sb.table("matches").select("id").eq("home_team_id", home_id).eq("away_team_id", away_id).execute()
        if existing.data:
            continue
    except Exception:
        pass

    try:
        dt_utc = parse_match_datetime(match.get("date", ""), match.get("time", ""))

        # Determine status
        match_type = match.get("match_type", "result")
        is_result = match_type == "result" and "home_score" in match and "away_score" in match

        if is_result:
            status = "finished"
        else:
            status = "scheduled"

        match_data = {
            "home_team_id": home_id,
            "away_team_id": away_id,
            "match_datetime": dt_utc,
            "stage": match.get("stage", "Group Stage"),
            "group_letter": match.get("group", ""),
            "venue": "",
            "status": status,
        }

        insert_resp = sb.table("matches").insert(match_data).execute()
        match_count += 1

        # Also insert into match_results if it's a completed result
        if is_result and insert_resp.data:
            match_db_id = insert_resp.data[0]["id"]
            try:
                sb.table("match_results").insert({
                    "match_id": match_db_id,
                    "home_score": match["home_score"],
                    "away_score": match["away_score"],
                    "home_scorers": [],
                    "away_scorers": [],
                }).execute()
                result_count += 1
            except Exception as e:
                print(f"  Warning: Could not insert result for {match['home_team']} vs {match['away_team']}: {e}")

    except Exception as e:
        print(f"  Error inserting {match['home_team']} vs {match['away_team']}: {e}")

print(f"Seeded {match_count} matches ({result_count} with results)")
print("\nDone!")