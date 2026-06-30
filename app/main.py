from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
import traceback

from app.database import get_supabase, get_supabase_admin
from app.auth import (
    get_current_user, require_auth, create_session_token
)

app = FastAPI(title="WC Predictions")

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

EGYPT_TZ = ZoneInfo("Africa/Cairo")

def egypt_time(utc_iso: str) -> str:
    """Convert UTC ISO datetime string to Egypt time (UTC+3)."""
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
        return dt.astimezone(EGYPT_TZ).strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return utc_iso

templates.env.filters["egypt_time"] = egypt_time


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return templates.TemplateResponse("error.html", {
        "request": request,
        "user": get_current_user(request),
        "error": "Something went wrong. Please try again later.",
    }, status_code=500)


def get_user_context(request: Request) -> dict:
    user = get_current_user(request)
    return {"request": request, "user": user}


# ─── Auth Routes ───

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("register.html", {"request": request, "user": None, "error": None})


@app.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request, "user": None, "error": "Passwords do not match"
        })
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {
            "request": request, "user": None, "error": "Password must be at least 6 characters"
        })

    sb = get_supabase()
    try:
        result = sb.auth.sign_up({"email": email, "password": password})
        if result.user:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse("register.html", {
            "request": request, "user": None, "error": "Registration failed. Email may already be in use."
        })
    except Exception as e:
        return templates.TemplateResponse("register.html", {
            "request": request, "user": None, "error": str(e)
        })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "user": None, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    sb = get_supabase()
    try:
        result = sb.auth.sign_in_with_password({"email": email, "password": password})
        if result.session:
            token = create_session_token(result.session.access_token, result.session.refresh_token)
            response = RedirectResponse(url="/", status_code=303)
            response.set_cookie("session", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7)
            return response
        return templates.TemplateResponse("login.html", {
            "request": request, "user": None, "error": "Invalid email or password"
        })
    except Exception as e:
        return templates.TemplateResponse("login.html", {
            "request": request, "user": None, "error": "Invalid email or password"
        })


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response


# ─── Home / Matches ───

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_current_user(request)
    sb = get_supabase()

    now = datetime.now(timezone.utc)

    try:
        matches_resp = sb.table("matches").select(
            "id, match_datetime, stage, group_letter, venue, status,"
            "home_team:teams!matches_home_team_id_fkey(id, name, flag_emoji),"
            "away_team:teams!matches_away_team_id_fkey(id, name, flag_emoji)"
        ).order("match_datetime", desc=False).execute()
        matches = matches_resp.data if matches_resp.data else []
    except Exception:
        matches = []

    predictions = {}
    if user:
        try:
            pred_resp = sb.table("predictions").select("match_id").eq("user_id", user["id"]).execute()
            if pred_resp.data:
                predictions = {p["match_id"]: True for p in pred_resp.data}
        except Exception:
            predictions = {}

    upcoming = []
    for m in matches:
        match_dt = datetime.fromisoformat(m["match_datetime"].replace("Z", "+00:00"))
        if match_dt < now:
            continue
        m["home_team"] = m.get("home_team") or {"name": "TBD", "flag_emoji": ""}
        m["away_team"] = m.get("away_team") or {"name": "TBD", "flag_emoji": ""}
        m["has_prediction"] = predictions.get(m["id"], False)
        upcoming.append(m)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "upcoming": upcoming,
        "now": now.isoformat(),
    })


# ─── Prediction Page ───

@app.get("/matches/{match_id}/predict", response_class=HTMLResponse)
async def predict_page(request: Request, match_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    sb = get_supabase()

    try:
        match_resp = sb.table("matches").select(
            "id, match_datetime, stage, group_letter, venue, status,"
            "home_team:teams!matches_home_team_id_fkey(id, name, flag_emoji),"
            "away_team:teams!matches_away_team_id_fkey(id, name, flag_emoji)"
        ).eq("id", match_id).single().execute()

        if not match_resp.data:
            raise HTTPException(status_code=404, detail="Match not found")

        match = match_resp.data
        match["home_team"] = match.get("home_team") or {"name": "TBD", "flag_emoji": ""}
        match["away_team"] = match.get("away_team") or {"name": "TBD", "flag_emoji": ""}

        match_dt = datetime.fromisoformat(match["match_datetime"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        locked = now >= match_dt or match["status"] in ("live", "finished")

        existing = None
        pred_resp = sb.table("predictions").select("*").eq("user_id", user["id"]).eq("match_id", match_id).execute()
        if pred_resp.data:
            existing = pred_resp.data[0]

        home_players_resp = sb.table("players").select("id, name, position").eq("team_id", match["home_team"]["id"]).order("name").execute()
        away_players_resp = sb.table("players").select("id, name, position").eq("team_id", match["away_team"]["id"]).order("name").execute()

        return templates.TemplateResponse("predict.html", {
            "request": request,
            "user": user,
            "match": match,
            "home_players": home_players_resp.data or [],
            "away_players": away_players_resp.data or [],
            "existing": existing,
            "locked": locked,
        })
    except HTTPException:
        raise
    except Exception:
        return RedirectResponse(url="/", status_code=303)


@app.post("/matches/{match_id}/predict")
async def submit_prediction(
    request: Request,
    match_id: int,
    chosen_winner: str = Form(...),
    home_score: int = Form(...),
    away_score: int = Form(...),
    home_scorers: str = Form(default=""),
    away_scorers: str = Form(default=""),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if chosen_winner not in ("home", "draw", "away"):
        raise HTTPException(status_code=400, detail="Invalid winner choice")

    if chosen_winner == "home" and home_score <= away_score:
        raise HTTPException(status_code=400, detail="If you choose home win, home score must be greater")
    if chosen_winner == "draw" and home_score != away_score:
        raise HTTPException(status_code=400, detail="If you choose draw, scores must be equal")
    if chosen_winner == "away" and away_score <= home_score:
        raise HTTPException(status_code=400, detail="If you choose away win, away score must be greater")

    sb = get_supabase()
    now = datetime.now(timezone.utc)

    try:
        match_resp = sb.table("matches").select("match_datetime, status").eq("id", match_id).single().execute()
        if not match_resp.data:
            raise HTTPException(status_code=404, detail="Match not found")

        match_dt = datetime.fromisoformat(match_resp.data["match_datetime"].replace("Z", "+00:00"))
        if now >= match_dt or match_resp.data["status"] in ("live", "finished"):
            raise HTTPException(status_code=400, detail="Prediction is locked for this match")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Could not connect to database")

    home_scorers_list = [s.strip() for s in home_scorers.split(",") if s.strip()] if home_scorers else []
    away_scorers_list = [s.strip() for s in away_scorers.split(",") if s.strip()] if away_scorers else []

    prediction_data = {
        "user_id": user["id"],
        "match_id": match_id,
        "chosen_winner": chosen_winner,
        "home_score": home_score,
        "away_score": away_score,
        "home_scorers": home_scorers_list,
        "away_scorers": away_scorers_list,
        "updated_at": now.isoformat(),
    }

    try:
        existing = sb.table("predictions").select("id").eq("user_id", user["id"]).eq("match_id", match_id).execute()
        if existing.data:
            sb.table("predictions").update(prediction_data).eq("id", existing.data[0]["id"]).execute()
        else:
            prediction_data["created_at"] = now.isoformat()
            sb.table("predictions").insert(prediction_data).execute()
    except Exception:
        raise HTTPException(status_code=503, detail="Could not save prediction")

    return RedirectResponse(url="/", status_code=303)


# ─── My Predictions ───

@app.get("/predictions", response_class=HTMLResponse)
async def my_predictions(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    sb = get_supabase()

    try:
        pred_resp = sb.table("predictions").select(
            "id, chosen_winner, home_score, away_score, home_scorers, away_scorers, created_at,"
            "match:matches(id, match_datetime, status,"
            "  home_team:teams!matches_home_team_id_fkey(name, flag_emoji),"
            "  away_team:teams!matches_away_team_id_fkey(name, flag_emoji))"
        ).eq("user_id", user["id"]).order("created_at", desc=True).execute()
        predictions = pred_resp.data or []
    except Exception:
        predictions = []

    return templates.TemplateResponse("predictions.html", {
        "request": request,
        "user": user,
        "predictions": predictions,
    })


# ─── Leaderboard ───

@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request):
    user = get_current_user(request)
    sb = get_supabase()

    try:
        scores_resp = sb.table("user_scores").select(
            "user_id, total_points, updated_at"
        ).order("total_points", desc=True).execute()
        scores = scores_resp.data or []
    except Exception:
        scores = []

    display_names = []
    for s in scores:
        uid = s["user_id"]
        try:
            admin_sb = get_supabase_admin()
            user_resp = admin_sb.auth.admin.get_user_by_id(uid)
            if user_resp and user_resp.user:
                display_names.append({"email": user_resp.user.email, "total_points": s["total_points"]})
            else:
                display_names.append({"email": uid[:8] + "...", "total_points": s["total_points"]})
        except Exception:
            display_names.append({"email": uid[:8] + "...", "total_points": s["total_points"]})

    return templates.TemplateResponse("leaderboard.html", {
        "request": request,
        "user": user,
        "scores": display_names,
    })


# ─── Admin: Calculate Scores ───

@app.post("/admin/calculate-scores")
async def calculate_scores(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=403)

    sb = get_supabase()
    admin_sb = get_supabase_admin()

    results_resp = admin_sb.table("match_results").select("*").execute()
    results = results_resp.data or []

    all_predictions = admin_sb.table("predictions").select("*").execute()
    predictions = all_predictions.data or []

    user_points: dict[str, int] = {}

    for result in results:
        match_id = result["match_id"]
        actual_home = result["home_score"]
        actual_away = result["away_score"]
        actual_home_scorers = set(result.get("home_scorers") or [])
        actual_away_scorers = set(result.get("away_scorers") or [])

        for pred in predictions:
            if pred["match_id"] != match_id:
                continue

            uid = pred["user_id"]
            points = 0

            if actual_home > actual_away:
                actual_winner = "home"
            elif actual_home == actual_away:
                actual_winner = "draw"
            else:
                actual_winner = "away"

            if pred["chosen_winner"] == actual_winner:
                points += 1

            if pred["home_score"] == actual_home and pred["away_score"] == actual_away:
                points += 3

            for scorer in (pred.get("home_scorers") or []):
                if scorer in actual_home_scorers:
                    points += 1
            for scorer in (pred.get("away_scorers") or []):
                if scorer in actual_away_scorers:
                    points += 1

            user_points[uid] = user_points.get(uid, 0) + points

    for uid, total in user_points.items():
        existing = admin_sb.table("user_scores").select("id").eq("user_id", uid).execute()
        if existing.data:
            admin_sb.table("user_scores").update({
                "total_points": total,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("user_id", uid).execute()
        else:
            admin_sb.table("user_scores").insert({
                "user_id": uid,
                "total_points": total,
            }).execute()

    return RedirectResponse(url="/leaderboard", status_code=303)
