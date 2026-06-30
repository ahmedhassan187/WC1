"""
Generate comprehensive 2026 World Cup fixtures.

Since Wikipedia has blocked scraping, this script generates:
1. Group stage results (already completed) using data from matches.json
2. Synthetic knockout round fixtures with FUTURE dates so users can make predictions

With 48 teams in 12 groups (A-L), the format is:
- Top 2 from each group (24 teams) + 8 best 3rd place teams → Round of 32
- Round of 32 → Round of 16 → Quarter-finals → Semi-finals → Final

Usage:
    py -3 scripts/generate_fixtures.py
"""

import json
import random

random.seed(42)  # deterministic for reproducibility


def format_time_12h(hour_24: int) -> str:
    """Convert 24h hour to 12h time string like '1:00 p.m.'"""
    if hour_24 == 0:
        return "12:00 a.m."
    elif hour_24 < 12:
        return f"{hour_24}:00 a.m."
    elif hour_24 == 12:
        return "12:00 p.m."
    else:
        return f"{hour_24 - 12}:00 p.m."


def generate_knockout_fixtures():
    """Generate synthetic but realistic knockout fixtures for user predictions."""

    # All 48 teams by group (from existing data)
    teams_by_group = {
        "A": ["Mexico", "South Africa", "South Korea", "Czech Republic"],
        "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
        "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
        "D": ["United States", "Paraguay", "Australia", "Turkey"],
        "E": ["Germany", "Ivory Coast", "Ecuador", "Curaçao"],
        "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
        "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
        "H": ["Spain", "Uruguay", "Cape Verde", "Saudi Arabia"],
        "I": ["France", "Senegal", "Iraq", "Norway"],
        "J": ["Argentina", "Austria", "Algeria", "Jordan"],
        "K": ["Portugal", "Colombia", "DR Congo", "Uzbekistan"],
        "L": ["England", "Croatia", "Ghana", "Panama"],
    }

    # Simulate group standings (shuffle to determine who advances)
    advancing = []
    for group, group_teams in teams_by_group.items():
        shuffled = group_teams[:]
        random.shuffle(shuffled)
        # Top 2 from each group automatically advance (24 teams)
        advancing.extend(shuffled[:2])
    # Add 8 best 3rd places (just take 8 more teams at random)
    all_teams = [t for gt in teams_by_group.values() for t in gt]
    remaining = [t for t in all_teams if t not in advancing]
    random.shuffle(remaining)
    advancing.extend(remaining[:8])

    # We now have 32 teams, shuffle for bracket
    random.shuffle(advancing)
    advancing = advancing[:32]

    # Round of 32: 16 matches - July 1-2 (future dates)
    times_r32 = ["12:00 p.m.", "3:00 p.m.", "6:00 p.m.", "9:00 p.m."]
    round_of_32 = []
    for i in range(16):
        day = 1 if i < 8 else 2
        round_of_32.append({
            "home_team": advancing[i * 2],
            "away_team": advancing[i * 2 + 1],
            "date": f"July {day}",
            "time": times_r32[i % 4],
            "group": "",
            "stage": "Round of 32",
            "match_type": "fixture",
        })

    # Round of 16: 8 matches - July 4-5
    times_r16 = ["12:00 p.m.", "3:00 p.m.", "6:00 p.m.", "9:00 p.m."]
    round_of_16 = []
    for i in range(8):
        day = 4 if i < 4 else 5
        round_of_16.append({
            "home_team": advancing[i],
            "away_team": advancing[i + 8],
            "date": f"July {day}",
            "time": times_r16[i % 4],
            "group": "",
            "stage": "Round of 16",
            "match_type": "fixture",
        })

    # Quarter-finals: 4 matches - July 7-8
    times_qf = ["3:00 p.m.", "6:00 p.m."]
    quarter_finals = []
    for i in range(4):
        day = 7 if i < 2 else 8
        quarter_finals.append({
            "home_team": advancing[i],
            "away_team": advancing[i + 4],
            "date": f"July {day}",
            "time": times_qf[i % 2],
            "group": "",
            "stage": "Quarter-finals",
            "match_type": "fixture",
        })

    # Semi-finals: 2 matches - July 11
    semi_finals = [
        {"home_team": advancing[0], "away_team": advancing[2], "date": "July 11", "time": "3:00 p.m.", "group": "", "stage": "Semi-finals", "match_type": "fixture"},
        {"home_team": advancing[1], "away_team": advancing[3], "date": "July 11", "time": "8:00 p.m.", "group": "", "stage": "Semi-finals", "match_type": "fixture"},
    ]

    # Third place: July 14
    third_place = [
        {"home_team": advancing[4], "away_team": advancing[5], "date": "July 14", "time": "5:00 p.m.", "group": "", "stage": "Third place", "match_type": "fixture"},
    ]

    # Final: July 15
    final = [
        {"home_team": advancing[6], "away_team": advancing[7], "date": "July 15", "time": "6:00 p.m.", "group": "", "stage": "Final", "match_type": "fixture"},
    ]

    fixtures = round_of_32 + round_of_16 + quarter_finals + semi_finals + third_place + final
    print(f"Generated {len(fixtures)} knockout fixtures:")
    print(f"  Round of 32: {len(round_of_32)}")
    print(f"  Round of 16: {len(round_of_16)}")
    print(f"  Quarter-finals: {len(quarter_finals)}")
    print(f"  Semi-finals: {len(semi_finals)}")
    print(f"  Third place: {len(third_place)}")
    print(f"  Final: {len(final)}")
    return fixtures


if __name__ == "__main__":
    # Load existing matches (group stage results)
    try:
        with open("scripts/matches.json", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"Loaded {len(existing)} existing matches from matches.json")
    except FileNotFoundError:
        print("ERROR: scripts/matches.json not found. Run scrape_data.py first.")
        exit(1)

    # Generate knockout fixtures
    knockouts = generate_knockout_fixtures()

    # Merge: keep existing group stage matches, add knockout fixtures
    all_matches = existing + knockouts

    # Save merged matches
    with open("scripts/matches.json", "w", encoding="utf-8") as f:
        json.dump(all_matches, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(all_matches)} total matches to scripts/matches.json")
    print(f"  → {len(existing)} group stage (results)")
    print(f"  → {len(knockouts)} knockout fixtures (for predictions)")