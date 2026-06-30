"""
Scrape 2026 FIFA World Cup data from Wikipedia.

Scrapes both completed results (for scoring) and upcoming fixtures (for predictions).
Saves to teams.json and matches.json with a 'match_type' field:
  - "result": completed match with scores (for leaderboard)
  - "fixture": upcoming match without scores (for predictions)

Usage:
    cd WC_Predictions
    py -3 scripts/scrape_data.py
"""

import json
import re
import httpx
from bs4 import BeautifulSoup

WIKI_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup"
GROUPS = "ABCDEFGHIJKL"


def parse_time(time_str: str) -> tuple[str, str]:
    """Convert '1:00 p.m.' → ('13:00', '') or empty → ('', '')"""
    if not time_str:
        return "", ""
    time_str = time_str.strip()
    match = re.match(r"(\d+):(\d+)\s*(a\.m\.|p\.m\.)", time_str, re.I)
    if match:
        hour = int(match.group(1))
        minute = match.group(2)
        ampm = match.group(3).lower()
        if "p" in ampm and hour != 12:
            hour += 12
        elif "a" in ampm and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute}", ""
    return time_str, ""


def extract_teams_from_standings(table) -> list[dict]:
    """Extract team names from a standings/wikitable table."""
    teams = []
    rows = table.find_all("tr")
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) >= 2:
            link = cells[1].find("a") if cells[1] else None
            if not link:
                link = cells[0].find("a")
            if link and link.get("title"):
                name = link.get_text(strip=True)
                img = cells[1].find("img") if cells[1] else None
                if not img:
                    img = cells[0].find("img")
                flag = img["alt"] if img and img.get("alt") else ""
                if name and name.lower() not in ("team", "pos", ""):
                    teams.append({"name": name, "flag_emoji": flag})
    return teams


def parse_match_table(table, group_letter: str, stage: str) -> list[dict]:
    """Parse a match fixture/result table and return matches.
    Returns both results (with scores) and fixtures (without scores)."""
    matches = []
    rows = table.find_all("tr")
    current_date = ""
    current_time = ""

    for row in rows:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue

        row_text = row.get_text(" ", strip=True)

        # Look for date header like "June 11" or "11 June"
        date_match = re.search(r"(June|July|August)\s+\d+", row_text)
        if not date_match:
            date_match = re.search(r"\d+\s+(June|July|August)", row_text)
        if date_match:
            current_date = date_match.group(0)

        # Look for time like "1:00 p.m." or "13:00"
        time_match = re.search(r"(\d+:\d+)\s*(a\.m\.|p\.m\.)", row_text, re.I)
        if time_match:
            current_time = time_match.group(0)

        # Check if this row contains a match (team vs team with optional scores)
        # Pattern: team [score] – [score] team  OR  team – team (no score yet)
        score_match = re.search(
            r"([A-Za-z][A-Za-z\s.\-()']*?)\s*(\d+)?\s*[–-]\s*(\d+)?\s*([A-Za-z][A-Za-z\s.\-()']*)",
            row_text,
        )
        if not score_match:
            continue

        team1 = score_match.group(1).strip()
        score1_str = score_match.group(2)  # may be None if fixture
        score2_str = score_match.group(3)  # may be None if fixture
        team2 = score_match.group(4).strip()

        # Clean up team names (remove parenthetical qualifiers)
        team1 = re.sub(r"\s*\(.*?\)", "", team1).strip()
        team2 = re.sub(r"\s*\(.*?\)", "", team2).strip()

        if len(team1) < 2 or len(team2) < 2 or team1 == team2:
            continue

        match_entry = {
            "home_team": team1,
            "away_team": team2,
            "date": current_date,
            "time": current_time,
            "group": group_letter,
            "stage": stage,
        }

        if score1_str and score2_str and score1_str.isdigit() and score2_str.isdigit():
            # Completed match with scores
            match_entry["home_score"] = int(score1_str)
            match_entry["away_score"] = int(score2_str)
            match_entry["match_type"] = "result"
        else:
            # Upcoming fixture without scores
            match_entry["match_type"] = "fixture"

        # Deduplicate
        dup = False
        for m in matches:
            if (m["home_team"] == match_entry["home_team"] and
                m["away_team"] == match_entry["away_team"] and
                m["date"] == match_entry["date"]):
                dup = True
                break

        if not dup:
            matches.append(match_entry)

    return matches


def scrape_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    resp = httpx.get(WIKI_URL, timeout=30, follow_redirects=True, headers=headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    teams = []
    matches = []

    # Strategy: find all group/round headings
    sections = soup.find_all("div", class_="mw-heading mw-heading3")
    for section in sections:
        heading = section.find("h3")
        if not heading:
            continue
        heading_text = heading.get_text(strip=True).lower()

        # Check for group headings (Group A, Group B, etc.)
        group_letter = ""
        for g in GROUPS:
            if heading_text == f"group {g.lower()}":
                group_letter = g
                break

        if group_letter:
            stage = "Group Stage"
        elif "round" in heading_text or "knockout" in heading_text:
            # Map round names
            round_map = {
                "round of 32": "Round of 32",
                "round of 16": "Round of 16",
                "quarter": "Quarter-finals",
                "semi": "Semi-finals",
                "third": "Third place",
                "final": "Final",
            }
            stage = "Knockout Stage"
            for key, val in round_map.items():
                if key in heading_text:
                    stage = val
                    break
            group_letter = ""
        else:
            continue

        # Find the next table after this heading
        el = section.find_next_sibling()
        while el:
            tag = el.name if el.name else ""
            # Stop if we hit another section heading
            if tag in ("h2", "h3", "div"):
                cls = el.get("class") or []
                if "mw-heading" in cls:
                    break

            if tag == "table" and "wikitable" in (el.get("class") or []):
                # Determine if it's a standings table or match table
                rows = el.find_all("tr")
                is_standings = False
                for row in rows[:3]:
                    th = row.find("th")
                    if th and re.search(r"Team|Pos|Pld|GP", th.get_text(), re.I):
                        is_standings = True
                        break

                if is_standings:
                    # Extract teams from standings
                    extracted = extract_teams_from_standings(el)
                    for t in extracted:
                        if not any(existing["name"] == t["name"] for existing in teams):
                            teams.append({
                                "name": t["name"],
                                "group": group_letter,
                                "flag_emoji": t["flag_emoji"],
                            })
                else:
                    # Parse match table
                    parsed = parse_match_table(el, group_letter, stage)
                    matches.extend(parsed)

            el = el.find_next_sibling()

    # Fallback: scrape teams from qualified teams list if none found
    if not teams:
        print("Fallback: scraping teams from qualified teams list...")
        team_section = soup.find("span", id="Teams")
        if team_section:
            ul = team_section.find_next("ul")
            while ul:
                for li in ul.find_all("li", recursive=False):
                    text = li.get_text(strip=True)
                    found_team = re.match(r"[•\s]*([A-Za-z\s]+)\s*\((\d+)\)", text)
                    if found_team:
                        name = found_team.group(1).strip()
                        if name and not any(t["name"] == name for t in teams):
                            teams.append({"name": name, "group": "", "flag_emoji": ""})
                ul = ul.find_next("ul")

    # Deduplicate teams
    seen = set()
    unique_teams = []
    for t in teams:
        key = t["name"]
        if key not in seen:
            seen.add(key)
            unique_teams.append(t)

    print(f"Found {len(unique_teams)} teams, {len(matches)} matches")
    results = [m for m in matches if m.get("match_type") == "result"]
    fixtures = [m for m in matches if m.get("match_type") == "fixture"]
    print(f"  → {len(results)} results, {len(fixtures)} fixtures")

    return unique_teams, matches


if __name__ == "__main__":
    print("Scraping 2026 FIFA World Cup data...")
    teams, matches = scrape_data()

    if teams:
        with open("scripts/teams.json", "w", encoding="utf-8") as f:
            json.dump(teams, f, indent=2, ensure_ascii=False)
        print("Saved teams.json")

    if matches:
        with open("scripts/matches.json", "w", encoding="utf-8") as f:
            json.dump(matches, f, indent=2, ensure_ascii=False)
        print("Saved matches.json")
    else:
        print("No matches found!")