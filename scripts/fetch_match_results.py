"""
Fetch real 2026 FIFA World Cup match results from ESPN API.
Includes goal scorers for accurate prediction scoring.

Usage:
    py -3 scripts/fetch_match_results.py
"""

import json
import os
import sys
import time
import ssl
from datetime import datetime, timezone
import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
    sys.exit(1)

# ── Global SSL workaround for Supabase certificate hostname mismatch ──
_original_context = ssl.create_default_context

def _relaxed_ssl_context() -> ssl.SSLContext:
    ctx = _original_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx

ssl._create_default_https_context = _relaxed_ssl_context

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ESPN API endpoints for 2026 FIFA World Cup
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.worldcup"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def fetch_espn_scoreboard(date: str = "") -> dict:
    """Fetch scoreboard data from ESPN API for a specific date or all.
    
    Args:
        date: Optional date string in YYYYMMDD format
    
    Returns:
        JSON response from ESPN API
    """
    url = f"{ESPN_BASE}/scoreboard"
    params = {}
    if date:
        params["dates"] = date
    params["limit"] = 200
    
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    
    try:
        resp = httpx.get(url, params=params, timeout=30, headers=headers)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        print(f"  HTTP error {e.response.status_code} for date {date}")
        return {}
    except Exception as e:
        print(f"  Error fetching ESPN data for date {date}: {e}")
        return {}


def extract_scorers_from_competitions(event: dict) -> tuple[list[str], list[str]]:
    """Extract goal scorers from ESPN API event data.
    
    ESPN structures scoring summaries differently based on match state.
    Returns (home_scorers, away_scorers) as lists of player names.
    """
    home_scorers = []
    away_scorers = []
    
    competitions = event.get("competitions", [])
    if not competitions:
        return home_scorers, away_scorers
    
    competition = competitions[0]
    
    # Try to get scorers from the 'scoring' summary (most detailed)
    # Format: list of {"type": {"text": "goal"}, "participant": {...}, "clock": {...}, "scoreValue": 1, "scoringPlayId": ...}
    scoring_summaries = competition.get("scoringSummaries", [])
    
    for summary in scoring_summaries:
        if not isinstance(summary, list):
            continue
        for play in summary:
            scoring_type = play.get("type", {}).get("text", "").lower()
            if "goal" not in scoring_type:
                continue
            
            # Get the player/participant who scored
            participants = play.get("participants", [])
            for participant in participants:
                athlete = participant.get("athlete", {})
                player_name = athlete.get("displayName") or athlete.get("shortName") or ""
                if not player_name:
                    continue
                
                # Determine which team this player is on
                team_side = participant.get("side", {}).get("text", "").lower()
                if team_side in ("home", "team1"):
                    home_scorers.append(player_name)
                elif team_side in ("away", "team2"):
                    away_scorers.append(player_name)
    
    # If no scorers found via scoringSummaries, try the 'leaders' or 'scoring' fields
    if not home_scorers and not away_scorers:
        # Try the "scoring" field from each competitor
        competitors = competition.get("competitors", [])
        for comp in competitors:
            team_type = comp.get("homeAway", "")
            scorers_data = comp.get("scoring", [])
            for scorer_entry in scorers_data:
                if isinstance(scorer_entry, dict):
                    # Try different field names ESPN uses
                    player_name = (
                        scorer_entry.get("athlete", {}).get("displayName") or
                        scorer_entry.get("name") or
                        scorer_entry.get("displayName") or
                        ""
                    )
                    if player_name:
                        if team_type == "home":
                            home_scorers.append(player_name)
                        else:
                            away_scorers.append(player_name)
    
    # Clean up: Remove "(P)" or "(OG)" suffixes and trim
    def clean_name(name: str) -> str:
        name = name.replace("(P)", "").replace("(OG)", "").replace("(pen)", "").strip()
        return name
    
    home_scorers = [clean_name(s) for s in home_scorers if clean_name(s)]
    away_scorers = [clean_name(s) for s in away_scorers if clean_name(s)]
    
    return home_scorers, away_scorers


def extract_match_from_espn(event: dict) -> dict | None:
    """Convert an ESPN API event to our match result format."""
    competitions = event.get("competitions", [])
    if not competitions:
        return None
    
    competition = competitions[0]
    competitors = competition.get("competitors", [])
    
    if len(competitors) < 2:
        return None
    
    # Find home and away teams
    home_team_data = None
    away_team_data = None
    for comp in competitors:
        if comp.get("homeAway") == "home":
            home_team_data = comp
        else:
            away_team_data = comp
    
    if not home_team_data or not away_team_data:
        return None
    
    home_team_name = home_team_data.get("team", {}).get("displayName") or home_team_data.get("team", {}).get("name", "")
    away_team_name = away_team_data.get("team", {}).get("displayName") or away_team_data.get("team", {}).get("name", "")
    
    home_score = home_team_data.get("score", "")
    away_score = away_team_data.get("score", "")
    
    # Check if match has started / has scores
    if not home_score and not away_score:
        return None  # Not played yet
    
    try:
        home_score = int(home_score) if home_score else 0
        away_score = int(away_score) if away_score else 0
    except (ValueError, TypeError):
        return None
    
    # Get match status
    status_type = competition.get("status", {}).get("type", {}).get("name", "")
    is_finished = status_type in ("STATUS_FINAL", "STATUS_FINAL_PEN", "STATUS_FINAL_ET")
    is_in_progress = status_type in ("STATUS_IN_PROGRESS", "STATUS_HALFTIME")
    
    if not is_finished and not is_in_progress:
        return None  # Not started or postponed
    
    # Get match date
    match_date = competition.get("date", "")
    
    # Extract goal scorers
    home_scorers, away_scorers = extract_scorers_from_competitions(event)
    
    # Get stage/round info
    # ESPN tournament groups structure
    group_info = competition.get("group", {})
    round_info = event.get("round", {})
    
    stage = "Group Stage"
    group_letter = ""
    
    # Determine stage from ESPN data
    round_number = round_info.get("number", 0)
    round_name = round_info.get("name", "")
    round_slug = round_info.get("slug", "")
    
    if round_number == 1:
        stage = "Group Stage"
        # Try to get group letter
        group_letter = group_info.get("name", "").replace("Group ", "") if group_info.get("name") else ""
    elif "round_of_32" in round_slug or round_number == 2:
        stage = "Round of 32"
    elif "round_of_16" in round_slug or round_number == 3:
        stage = "Round of 16"
    elif "quarter" in round_slug or round_number == 4:
        stage = "Quarter-finals"
    elif "semi" in round_slug or round_number == 5:
        stage = "Semi-finals"
    elif "third" in round_slug or round_number == 6:
        stage = "Third place"
    elif "final" in round_slug or round_number == 7:
        stage = "Final"
    elif round_name:
        stage = round_name
    
    return {
        "home_team": home_team_name,
        "away_team": away_team_name,
        "home_score": home_score,
        "away_score": away_score,
        "home_scorers": home_scorers,
        "away_scorers": away_scorers,
        "match_date": match_date,
        "stage": stage,
        "group_letter": group_letter,
        "is_finished": is_finished,
        "espn_id": event.get("id", ""),
    }


def name_similarity(a: str, b: str) -> float:
    """Simple name similarity check (case-insensitive contains)."""
    a_lower = a.lower().strip()
    b_lower = b.lower().strip()
    
    # Direct match
    if a_lower == b_lower:
        return 1.0
    
    # One contains the other
    if a_lower in b_lower or b_lower in a_lower:
        return 0.8
    
    # Check each word
    a_words = set(a_lower.split())
    b_words = set(b_lower.split())
    if not a_words or not b_words:
        return 0.0
    
    intersection = a_words & b_words
    union = a_words | b_words
    
    # Skip common filler words
    fillers = {"fc", "afc", "ac", "sc", "the", "de", "city", "united"}
    intersection -= fillers
    union -= fillers
    
    if not union:
        return 0.0
    
    return len(intersection) / len(union)


def find_matching_team(sb_client, team_name: str) -> int | None:
    """Find a team ID in the DB matching an ESPN team name."""
    # Try exact match first
    resp = sb_client.table("teams").select("id, name").eq("name", team_name).execute()
    if resp.data:
        return resp.data[0]["id"]
    
    # Try case-insensitive
    all_teams = sb_client.table("teams").select("id, name").execute()
    if not all_teams.data:
        return None
    
    # Find best match
    best_score = 0
    best_id = None
    
    for team in all_teams.data:
        score = name_similarity(team_name, team["name"])
        if score > best_score:
            best_score = score
            best_id = team["id"]
    
    if best_score >= 0.5:
        return best_id
    
    return None


def fetch_all_espn_matches() -> list[dict]:
    """Fetch all completed and in-progress matches from ESPN."""
    all_matches = []
    
    # Try fetching without date filter first (gets current window)
    print("Fetching ESPN scoreboard data...")
    data = fetch_espn_scoreboard()
    
    events = data.get("events", [])
    
    # If no events, try fetching specific date ranges for the tournament
    if not events:
        # 2026 World Cup dates: June 11 - July 19, 2026
        date_ranges = []
        for month in [6, 7]:
            for day in range(1, 32):
                if month == 6 and (day < 11 or day > 30):
                    continue
                if month == 7 and day > 19:
                    break
                date_str = f"2026{month:02d}{day:02d}"
                date_ranges.append(date_str)
        
        print(f"Fetching data for {len(date_ranges)} days...")
        for i, date_str in enumerate(date_ranges):
            print(f"  [{i+1}/{len(date_ranges)}] Fetching {date_str}...")
            day_data = fetch_espn_scoreboard(date_str)
            day_events = day_data.get("events", [])
            events.extend(day_events)
            time.sleep(0.5)  # Be nice to the API
    
    # Deduplicate by event ID
    seen_ids = set()
    unique_events = []
    for event in events:
        event_id = event.get("id", "")
        if event_id and event_id not in seen_ids:
            seen_ids.add(event_id)
            unique_events.append(event)
    
    print(f"Found {len(unique_events)} events from ESPN API")
    
    for event in unique_events:
        match = extract_match_from_espn(event)
        if match:
            all_matches.append(match)
    
    print(f"  → {len(all_matches)} completed/in-progress matches with scores")
    return all_matches


def save_espn_results_to_json(espn_matches: list[dict]):
    """Save ESPN results to a JSON file for backup/debugging."""
    with open("scripts/espn_results.json", "w", encoding="utf-8") as f:
        json.dump(espn_matches, f, indent=2, ensure_ascii=False)
    print("Saved ESPN results to scripts/espn_results.json")


def ensure_scorer_columns_exist(sb_client):
    """Check if scorer columns exist in match_results table and add if needed."""
    try:
        # Test if the column exists by doing a simple select
        sb_client.table("match_results").select("home_scorers").limit(0).execute()
        sb_client.table("match_results").select("away_scorers").limit(0).execute()
        print("  ✓ Scorer columns already exist in match_results table")
        return True
    except Exception:
        try:
            print("  ⚠ Scorer columns missing. Adding them via direct SQL...")
            # Try to add columns using raw SQL via RPC or direct execution
            # Supabase REST API doesn't support ALTER TABLE directly,
            # but we'll skip scorers if columns don't exist
            print("  ⚠ Cannot add columns via REST API. Will skip scorers.")
            return False
        except Exception:
            return False


def update_match_results_in_db(sb_client, espn_matches: list[dict]) -> tuple[int, int]:
    """Update Supabase match_results table with ESPN data.
    
    Returns:
        (matches_updated, match_errors) counts
    """
    updated = 0
    errors = 0
    
    # Detect what columns exist in match_results table by trying a select
    has_scorers = False
    has_updated_at = True
    try:
        sb_client.table("match_results").select("home_scorers").limit(0).execute()
        has_scorers = True
    except Exception:
        pass
    try:
        sb_client.table("match_results").select("updated_at").limit(0).execute()
    except Exception:
        has_updated_at = False
    
    print(f"  → Table columns detected: scorers={'yes' if has_scorers else 'no'}, updated_at={'yes' if has_updated_at else 'no'}")
    
    for match in espn_matches:
        home_team_name = match["home_team"]
        away_team_name = match["away_team"]
        
        home_team_id = find_matching_team(sb_client, home_team_name)
        away_team_id = find_matching_team(sb_client, away_team_name)
        
        if not home_team_id or not away_team_id:
            print(f"  ⚠ Could not find teams: {home_team_name} vs {away_team_name}")
            errors += 1
            continue
        
        # Find the match in the DB
        match_resp = sb_client.table("matches").select(
            "id, status"
        ).eq("home_team_id", home_team_id).eq("away_team_id", away_team_id).execute()
        
        if not match_resp.data:
            print(f"  ⚠ Match not in DB: {home_team_name} vs {away_team_name}")
            errors += 1
            continue
        
        db_match = match_resp.data[0]
        match_db_id = db_match["id"]
        
        # Update match status to finished
        new_status = "finished" if match["is_finished"] else "live"
        sb_client.table("matches").update({
            "status": new_status,
        }).eq("id", match_db_id).execute()
        
        # Upsert match_results - only use columns that exist
        result_data = {
            "match_id": match_db_id,
            "home_score": match["home_score"],
            "away_score": match["away_score"],
        }
        
        if has_scorers:
            result_data["home_scorers"] = match["home_scorers"]
            result_data["away_scorers"] = match["away_scorers"]
        
        if has_updated_at:
            result_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        try:
            existing = sb_client.table("match_results").select("id").eq("match_id", match_db_id).execute()
            if existing.data:
                sb_client.table("match_results").update(result_data).eq("match_id", match_db_id).execute()
            else:
                sb_client.table("match_results").insert(result_data).execute()
            
            updated += 1
            home_scorers_str = ", ".join(match["home_scorers"]) if match["home_scorers"] else "none"
            away_scorers_str = ", ".join(match["away_scorers"]) if match["away_scorers"] else "none"
            print(f"  ✓ {home_team_name} {match['home_score']}-{match['away_score']} {away_team_name} [{match['stage']}]")
            if has_scorers:
                print(f"    Scorers: {home_team_name}: {home_scorers_str} | {away_team_name}: {away_scorers_str}")
            
        except Exception as e:
            print(f"  ✗ Error saving result for {home_team_name} vs {away_team_name}: {e}")
            errors += 1
    
    return updated, errors


def main():
    print("=" * 60)
    print("Fetching 2026 FIFA World Cup Results from ESPN API")
    print("=" * 60)
    
    # 1. Fetch all ESPN matches
    espn_matches = fetch_all_espn_matches()
    
    if not espn_matches:
        print("\nNo matches found from ESPN API.")
        print("Trying alternative: ESPN may use 'fifa.worldcup' slug...")
        
        # Try with common alternative endpoint
        alt_urls = [
            "https://site.api.espn.com/apis/site/v2/sports/soccer/concacaf.worldcup/scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.worldcup/_/scoreboard",
        ]
        
        for alt_url in alt_urls:
            print(f"Trying {alt_url}...")
            try:
                resp = httpx.get(alt_url, params={"limit": 200, "dates": "2026"}, 
                                 timeout=30, headers={"User-Agent": USER_AGENT})
                if resp.status_code == 200:
                    data = resp.json()
                    events = data.get("events", [])
                    print(f"  Found {len(events)} events")
                    for event in events:
                        match = extract_match_from_espn(event)
                        if match:
                            espn_matches.append(match)
            except Exception:
                pass
    
    if not espn_matches:
        print("\n⚠ Could not fetch data from ESPN API. The 2026 World Cup may not be available yet,")
        print("  or ESPN uses a different slug/ID for this tournament.")
        print("\nFalling back to scraping data from scripts/matches.json (Wikipedia data)...")
        
        # Load from our existing matches.json
        try:
            with open("scripts/matches.json", encoding="utf-8") as f:
                matches_data = json.load(f)
            
            # Filter to only results (completed matches) - detect by presence of scores
            for match in matches_data:
                if "home_score" in match and "away_score" in match:
                    espn_matches.append({
                        "home_team": match["home_team"],
                        "away_team": match["away_team"],
                        "home_score": match["home_score"],
                        "away_score": match["away_score"],
                        "home_scorers": match.get("home_scorers", []),
                        "away_scorers": match.get("away_scorers", []),
                        "match_date": match.get("date", ""),
                        "stage": match.get("stage", "Group Stage"),
                        "group_letter": match.get("group", ""),
                        "is_finished": True,
                        "espn_id": "",
                    })
            
            print(f"Using {len(espn_matches)} matches from scripts/matches.json")
            print("NOTE: These results may not include goal scorers (scraped from Wikipedia)")
            print("      For accurate scorer-based scoring, a source with detailed data is needed.")
        except FileNotFoundError:
            print("ERROR: scripts/matches.json not found. Run scrape_data.py first.")
            sys.exit(1)
    
    # 2. Save to JSON for backup
    save_espn_results_to_json(espn_matches)
    
    # 3. Update Supabase
    print("\n" + "=" * 60)
    print("Updating Supabase with match results...")
    print("=" * 60)
    
    updated, errors = update_match_results_in_db(sb, espn_matches)
    
    print("\n" + "=" * 60)
    print(f"Summary: {updated} results updated, {errors} errors")
    print("=" * 60)
    
    # 4. Now calculate and save user scores
    print("\n" + "=" * 60)
    print("Calculating user prediction scores...")
    print("=" * 60)
    
    calculate_and_save_scores(sb)
    
    print("\nDone!")


def calculate_and_save_scores(sb_client):
    """Calculate scores for each user based on predictions vs actual results."""
    
    # Fetch all match_results
    results_resp = sb_client.table("match_results").select("*").execute()
    results = results_resp.data or []
    
    if not results:
        print("⚠ No match results found in database. Run fetch first.")
        return
    
    # Fetch all predictions
    predictions_resp = sb_client.table("predictions").select("*").execute()
    predictions = predictions_resp.data or []
    
    if not predictions:
        print("⚠ No predictions found in database.")
        return
    
    print(f"Found {len(results)} results, {len(predictions)} predictions")
    
    # Group predictions by user
    user_predictions: dict[str, list] = {}
    for pred in predictions:
        uid = pred["user_id"]
        if uid not in user_predictions:
            user_predictions[uid] = []
        user_predictions[uid].append(pred)
    
    print(f"Found {len(user_predictions)} users who made predictions")
    
    # Calculate points for each user
    user_points: dict[str, int] = {}
    user_details: dict[str, dict] = {}
    
    for userId, user_preds in user_predictions.items():
        total_points = 0
        points_detail = []
        
        for pred in user_preds:
            match_id = pred["match_id"]
            
            # Find matching result
            result = None
            for r in results:
                if r["match_id"] == match_id:
                    result = r
                    break
            
            if not result:
                continue  # Match hasn't been played yet
            
            actual_home = result["home_score"]
            actual_away = result["away_score"]
            actual_home_scorers = set(result.get("home_scorers") or [])
            actual_away_scorers = set(result.get("away_scorers") or [])
            
            points = 0
            breakdown = []
            
            # 1. Correct winner (1 point)
            if actual_home > actual_away:
                actual_winner = "home"
            elif actual_home == actual_away:
                actual_winner = "draw"
            else:
                actual_winner = "away"
            
            if pred["chosen_winner"] == actual_winner:
                points += 1
                breakdown.append("winner(+1)")
            
            # 2. Exact score (3 points)
            if pred["home_score"] == actual_home and pred["away_score"] == actual_away:
                points += 3
                breakdown.append("exact_score(+3)")
            
            # 3. Each correct scorer (1 point each)
            for scorer in (pred.get("home_scorers") or []):
                if scorer in actual_home_scorers:
                    points += 1
                    breakdown.append(f"scorer:{scorer}(+1)")
            for scorer in (pred.get("away_scorers") or []):
                if scorer in actual_away_scorers:
                    points += 1
                    breakdown.append(f"scorer:{scorer}(+1)")
            
            total_points += points
            if points > 0:
                points_detail.append({
                    "match_id": match_id,
                    "points": points,
                    "breakdown": breakdown,
                })
        
        user_points[userId] = total_points
        user_details[userId] = {
            "total_points": total_points,
            "details": points_detail,
        }
    
    # Save scores to user_scores table
    print("\nSaving scores to user_scores table...")
    
    scores_updated = 0
    scores_inserted = 0
    
    for uid, total in user_points.items():
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            existing = sb_client.table("user_scores").select("id").eq("user_id", uid).execute()
            if existing.data:
                sb_client.table("user_scores").update({
                    "total_points": total,
                    "updated_at": now,
                }).eq("user_id", uid).execute()
                scores_updated += 1
            else:
                sb_client.table("user_scores").insert({
                    "user_id": uid,
                    "total_points": total,
                    "updated_at": now,
                }).execute()
                scores_inserted += 1
        except Exception as e:
            print(f"  ✗ Error saving score for user {uid[:8]}...: {e}")
    
    print(f"  Updated {scores_updated} existing scores, inserted {scores_inserted} new scores")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SCORING SUMMARY")
    print("=" * 60)
    
    # Sort by points descending
    sorted_users = sorted(user_points.items(), key=lambda x: x[1], reverse=True)
    
    for rank, (uid, total) in enumerate(sorted_users, 1):
        # Try to get user email
        try:
            user_resp = sb_client.auth.admin.get_user_by_id(uid)
            email = user_resp.user.email if user_resp and user_resp.user else uid[:8]
        except Exception:
            email = uid[:8] + "..."
        
        details = user_details[uid]["details"]
        total_match_count = len(details)
        print(f"  {rank}. {email}: {total} pts ({total_match_count} matches scoring)")
    
    print("=" * 60)


if __name__ == "__main__":
    main()