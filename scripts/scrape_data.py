"""
Scrape World Cup match schedule from Wikipedia.
Requires: pip install beautifulsoup4 httpx

Usage:
    py -3.14 scripts/scrape_matches.py

Output: scripts/matches.json
"""

import json
import httpx
from bs4 import BeautifulSoup

WIKI_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup"

GROUPS = "ABCDEFGH"


def scrape_matches():
    resp = httpx.get(WIKI_URL, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    matches = []
    tables = soup.find_all("table", class_="wikitable")

    for table in tables:
        caption = table.find("caption")
        if not caption:
            continue

        caption_text = caption.get_text(strip=True).lower()

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 4:
                continue

            try:
                date_cell = cells[0].get_text(strip=True)
                time_cell = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                team1_cell = cells[2]
                team2_cell = cells[3]
                score_cell = cells[4] if len(cells) > 4 else None

                team1 = team1_cell.get_text(strip=True).replace("[edit]", "").strip()
                team2 = team2_cell.get_text(strip=True).replace("[edit]", "").strip()

                if not team1 or not team2 or team1 == "Team 1":
                    continue

                group = ""
                for g in GROUPS:
                    if f"group {g}" in caption_text:
                        group = g
                        break

                stage = "Group Stage"
                if "round of 16" in caption_text:
                    stage = "Round of 16"
                elif "quarter" in caption_text:
                    stage = "Quarter-final"
                elif "semi" in caption_text:
                    stage = "Semi-final"
                elif "third" in caption_text:
                    stage = "Third Place"
                elif "final" in caption_text:
                    stage = "Final"

                matches.append({
                    "home_team": team1,
                    "away_team": team2,
                    "date": date_cell,
                    "time": time_cell,
                    "group": group,
                    "stage": stage,
                })
            except (IndexError, ValueError):
                continue

    return matches


def scrape_groups():
    resp = httpx.get(WIKI_URL, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    teams = []
    tables = soup.find_all("table", class_="wikitable")

    for table in tables:
        caption = table.find("caption")
        if not caption:
            continue

        caption_text = caption.get_text(strip=True).lower()

        group = ""
        for g in GROUPS:
            if f"group {g}" in caption_text:
                group = g
                break

        if not group:
            continue

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            team_name = cells[1].get_text(strip=True) if len(cells) > 1 else cells[0].get_text(strip=True)
            team_name = team_name.replace("[edit]", "").strip()
            if team_name and team_name != "Team":
                teams.append({"name": team_name, "group": group})

    return teams


if __name__ == "__main__":
    print("Scraping groups...")
    groups = scrape_groups()
    print(f"Found {len(groups)} teams")

    print("Scraping matches...")
    matches = scrape_matches()
    print(f"Found {len(matches)} matches")

    with open("scripts/teams.json", "w", encoding="utf-8") as f:
        json.dump(groups, f, indent=2, ensure_ascii=False)
    print("Saved teams.json")

    with open("scripts/matches.json", "w", encoding="utf-8") as f:
        json.dump(matches, f, indent=2, ensure_ascii=False)
    print("Saved matches.json")
