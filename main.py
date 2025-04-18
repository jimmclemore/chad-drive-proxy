import os
import json
import base64
from threading import Lock
from fastapi import FastAPI, Body
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
import requests
from urllib.parse import urlencode

app = FastAPI()

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

SCOPES = (
    "https://www.googleapis.com/auth/drive.file "
    "https://www.googleapis.com/auth/calendar.readonly "
    "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/gmail.modify"
)

SPOTIFY_SCOPES = (
    "user-read-currently-playing user-read-playback-state "
    "user-modify-playback-state playlist-read-private "
    "playlist-modify-private user-top-read user-read-email"
)

TOKEN_FILE = "tokens.json"
token_lock = Lock()

def load_tokens():
    with token_lock:
        if not os.path.exists(TOKEN_FILE):
            return {}
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)

def save_tokens(tokens):
    with token_lock:
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f)

TOKENS = load_tokens()

class UserInput(BaseModel):
    user_id: str
    content: str

@app.get("/")
def root():
    return {"status": "Running", "auth_url": "/authorize?user_id=example"}

@app.get("/authorize")
def authorize(user_id: str):
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": user_id
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url)

@app.get("/oauth/callback")
def oauth_callback(code: str, state: str):
    data = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    r = requests.post("https://oauth2.googleapis.com/token", data=data)
    if r.status_code == 200:
        tokens = load_tokens()
        tokens[state] = tokens.get(state, {})
        tokens[state]['google'] = r.json()
        save_tokens(tokens)
        return JSONResponse({"message": f"Authorized successfully for user_id={state}"})
    return JSONResponse({"error": "Authorization failed"}, status_code=400)

@app.get("/spotify-authorize")
def spotify_authorize(user_id: str):
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "state": user_id
    }
    url = f"https://accounts.spotify.com/authorize?{urlencode(params)}"
    return RedirectResponse(url)

@app.get("/spotify-callback")
def spotify_callback(code: str, state: str):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET
    }
    r = requests.post("https://accounts.spotify.com/api/token", data=data)
    if r.status_code != 200:
        return JSONResponse({"error": "Spotify auth failed"}, status_code=400)
    token_data = r.json()
    access_token = token_data.get("access_token")
    user_resp = requests.get("https://api.spotify.com/v1/me", headers={"Authorization": f"Bearer {access_token}"})
    if user_resp.status_code != 200:
        return JSONResponse({"error": "Failed to fetch Spotify user info"}, status_code=500)
    user_info = user_resp.json()
    spotify_user_id = user_info.get("id")
    tokens = load_tokens()
    tokens[spotify_user_id] = tokens.get(spotify_user_id, {})
    tokens[spotify_user_id]['spotify'] = token_data
    save_tokens(tokens)
    return JSONResponse({"message": "Spotify connected", "spotify_user_id": spotify_user_id, "display_name": user_info.get("display_name"), "email": user_info.get("email")})

@app.get("/spotify/playlists")
def get_playlists(user_id: str):
    tokens = load_tokens()
    token = tokens.get(user_id, {}).get('spotify')
    if not token:
        return JSONResponse({"error": "Spotify not authorized"}, status_code=403)
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    resp = requests.get("https://api.spotify.com/v1/me/playlists", headers=headers)
    return resp.json() if resp.status_code == 200 else JSONResponse({"error": "Spotify fetch failed"}, status_code=resp.status_code)

@app.get("/spotify/current-track")
def get_current_track(user_id: str):
    tokens = load_tokens()
    token = tokens.get(user_id, {}).get('spotify')
    if not token:
        return JSONResponse({"error": "Spotify not authorized"}, status_code=403)
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    resp = requests.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers)
    return resp.json() if resp.status_code == 200 else JSONResponse({"error": "Spotify fetch failed"}, status_code=resp.status_code)

@app.put("/spotify/play")
def play_track(user_id: str):
    tokens = load_tokens()
    token = tokens.get(user_id, {}).get('spotify')
    if not token:
        return JSONResponse({"error": "Spotify not authorized"}, status_code=403)
    headers = {"Authorization": f"Bearer {token['access_token']}", "Content-Type": "application/json"}
    resp = requests.put("https://api.spotify.com/v1/me/player/play", headers=headers)
    return JSONResponse({"message": "Playback started"}) if resp.status_code in [200, 204] else JSONResponse({"error": "Playback failed"}, status_code=resp.status_code)

@app.get("/calendar")
def get_calendar_events(user_id: str):
    tokens = load_tokens()
    token = tokens.get(user_id, {}).get('google')
    if not token:
        return JSONResponse({"error": "User not authorized"}, status_code=403)
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    now = datetime.utcnow().isoformat() + "Z"
    future = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
    params = {"maxResults": 10, "orderBy": "startTime", "singleEvents": True, "timeMin": now, "timeMax": future}
    resp = requests.get("https://www.googleapis.com/calendar/v3/calendars/primary/events", headers=headers, params=params)
    return resp.json() if resp.status_code == 200 else JSONResponse({"error": "Failed to fetch calendar", "details": resp.json()}, status_code=resp.status_code)

@app.get("/gmail")
def get_gmail_messages(user_id: str, max_results: int = 100):
    tokens = load_tokens()
    token = tokens.get(user_id, {}).get('google')
    if not token:
        return JSONResponse({"error": "User not authorized"}, status_code=403)
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    list_resp = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", headers=headers, params={"maxResults": max_results})
    if list_resp.status_code != 200:
        return JSONResponse({"error": "Failed to fetch Gmail messages", "details": list_resp.json()}, status_code=list_resp.status_code)
    messages = []
    for msg in list_resp.json().get("messages", []):
        msg_id = msg.get("id")
        detail_resp = requests.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}", headers=headers, params={"format": "full"})
        if detail_resp.status_code == 200:
            msg_json = detail_resp.json()
            headers_data = msg_json.get("payload", {}).get("headers", [])
            subject = next((h['value'] for h in headers_data if h['name'] == 'Subject'), "(No Subject)")
            sender = next((h['value'] for h in headers_data if h['name'] == 'From'), "(Unknown Sender)")
            date = next((h['value'] for h in headers_data if h['name'] == 'Date'), "(No Date)")
            parts = msg_json.get("payload", {}).get("parts", [])
            body = ""
            for part in parts:
                if part.get("mimeType") in ["text/plain", "text/html"]:
                    data = part.get("body", {}).get("data")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        break
            messages.append({"id": msg_id, "subject": subject, "from": sender, "date": date, "body": body or "(No content found)"})
    return {"messages": messages}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
