import os
import json
from threading import Lock
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
import requests
from urllib.parse import urlencode

app = FastAPI()

# --- ENV VARS ---
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

# --- TOKEN STORAGE ---
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

# --- GOOGLE AUTH ---
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

# --- SPOTIFY AUTH ---
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

    user_resp = requests.get(
        "https://api.spotify.com/v1/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    if user_resp.status_code != 200:
        return JSONResponse({"error": "Failed to fetch Spotify user info"}, status_code=500)

    user_info = user_resp.json()
    spotify_user_id = user_info.get("id")

    if not spotify_user_id:
        return JSONResponse({"error": "Spotify user ID missing"}, status_code=500)

    tokens = load_tokens()
    tokens[spotify_user_id] = tokens.get(spotify_user_id, {})
    tokens[spotify_user_id]['spotify'] = token_data
    save_tokens(tokens)

    return JSONResponse({
        "message": f"Spotify connected",
        "spotify_user_id": spotify_user_id,
        "display_name": user_info.get("display_name"),
        "email": user_info.get("email")
    })

# --- SPOTIFY ROUTES ---
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

# --- GOOGLE SERVICES ---
@app.get("/calendar")
def get_calendar_events(user_id: str):
    tokens = load_tokens()
    token = tokens.get(user_id, {}).get('google')
    if not token:
        return JSONResponse({"error": "User not authorized"}, status_code=403)
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    now = datetime.utcnow().isoformat() + "Z"
    future = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
    params = {
        "maxResults": 10,
        "orderBy": "startTime",
        "singleEvents": True,
        "timeMin": now,
        "timeMax": future
    }
    resp = requests.get("https://www.googleapis.com/calendar/v3/calendars/primary/events", headers=headers, params=params)
    return resp.json() if resp.status_code == 200 else JSONResponse({"error": "Failed to fetch calendar", "details": resp.json()}, status_code=resp.status_code)

@app.get("/gmail")
def get_gmail_messages(user_id: str):
    tokens = load_tokens()
    token = tokens.get(user_id, {}).get('google')
    if not token:
        return JSONResponse({"error": "User not authorized"}, status_code=403)
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    resp = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", headers=headers, params={"maxResults": 10})
    return resp.json() if resp.status_code == 200 else JSONResponse({"error": "Failed to fetch Gmail messages", "details": resp.json()}, status_code=resp.status_code)

@app.post("/gmail/modify")
def modify_gmail(user_id: str, message_id: str, labels_to_add: list):
    tokens = load_tokens()
    token = tokens.get(user_id, {}).get('google')
    if not token:
        return JSONResponse({"error": "User not authorized"}, status_code=403)
    headers = {"Authorization": f"Bearer {token['access_token']}", "Content-Type": "application/json"}
    data = {"addLabelIds": labels_to_add}
    resp = requests.post(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify", headers=headers, json=data)
    return resp.json() if resp.status_code == 200 else JSONResponse({"error": "Failed to modify Gmail message", "details": resp.json()}, status_code=resp.status_code)

@app.get("/read-profile")
def read_profile(user_id: str):
    tokens = load_tokens()
    token = tokens.get(user_id, {}).get('google')
    if not token:
        return JSONResponse({"error": "User not authorized"}, status_code=403)
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    folder_resp = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params={"q": "name='ChadGPT' and mimeType='application/vnd.google-apps.folder' and trashed=false"})
    folder_id = folder_resp.json().get("files", [])[0]["id"]
    query = f"'{folder_id}' in parents and name='chad-settings.txt' and trashed=false"
    file_resp = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params={"q": query}).json()
    if not file_resp["files"]:
        return JSONResponse({"error": "Profile file not found."}, status_code=404)
    file_id = file_resp["files"][0]["id"]
    download = requests.get(f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media", headers=headers)
    return {"content": download.text}

@app.post("/write-profile")
def write_profile(payload: UserInput):
    tokens = load_tokens()
    token = tokens.get(payload.user_id, {}).get('google')
    if not token:
        return JSONResponse({"error": "User not authorized"}, status_code=403)
    headers = {"Authorization": f"Bearer {token['access_token']}", "Content-Type": "application/json"}
    folder_resp = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params={"q": "name='ChadGPT' and mimeType='application/vnd.google-apps.folder' and trashed=false"})
    folder_id = None
    files = folder_resp.json().get("files", [])
    if files:
        folder_id = files[0]["id"]
    else:
        folder_create = {"name": "ChadGPT", "mimeType": "application/vnd.google-apps.folder"}
        folder_response = requests.post("https://www.googleapis.com/drive/v3/files", headers=headers, json=folder_create)
        folder_id = folder_response.json()["id"]
    query = f"'{folder_id}' in parents and name='chad-settings.txt' and trashed=false"
    existing = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params={"q": query}).json()
    if existing["files"]:
        file_id = existing["files"][0]["id"]
        requests.patch(f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media", headers={"Authorization": f"Bearer {token['access_token']}", "Content-Type": "text/plain"}, data=payload.content.encode("utf-8"))
    else:
        metadata = {"name": "chad-settings.txt", "parents": [folder_id], "mimeType": "text/plain"}
        files = {"metadata": ("metadata", str(metadata), "application/json"), "file": ("file", payload.content, "text/plain")}
        requests.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart", headers={"Authorization": f"Bearer {token['access_token']}"}, files=files)
    return {"message": "Profile saved successfully."}

@app.get("/debug-env")
def debug_env():
    return {
        "SPOTIFY_CLIENT_ID": SPOTIFY_CLIENT_ID,
        "SPOTIFY_REDIRECT_URI": SPOTIFY_REDIRECT_URI
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
