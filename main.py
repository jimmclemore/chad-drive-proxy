import os
import json
import base64
import logging
from threading import Lock
from fastapi import FastAPI, Body, Query
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
import requests
from urllib.parse import urlencode

app = FastAPI(
    title="FastAPI",
    version="1.0.0",
    servers=[{"url": "https://chad-drive-proxy.onrender.com"}]
)

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
    "playlist-modify-private user-top-read user-read-email user-library-read"
)

TOKEN_FILE = "tokens.json"
token_lock = Lock()

logging.basicConfig(level=logging.INFO)

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

class UserInput(BaseModel):
    user_id: str
    content: str

@app.get("/spotify/top-tracks", operation_id="getTopTracks")
def get_top_tracks(user_id: str, time_range: str = "medium_term", limit: int = 10):
    try:
        tokens = load_tokens()
        token = tokens.get(user_id, {}).get('spotify')
        if not token:
            return JSONResponse({"error": "Spotify not authorized"}, status_code=403)
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        params = {"time_range": time_range, "limit": limit}
        resp = requests.get("https://api.spotify.com/v1/me/top/tracks", headers=headers, params=params)
        return resp.json() if resp.status_code == 200 else JSONResponse({"error": "Failed to fetch top tracks"}, status_code=resp.status_code)
    except Exception as e:
        return JSONResponse({"error": "Exception occurred", "details": str(e)}, status_code=500)

@app.get("/spotify/liked-songs")
def get_liked_songs(user_id: str, limit: int = 20, offset: int = 0):
    try:
        tokens = load_tokens()
        token = tokens.get(user_id, {}).get('spotify')
        if not token:
            return JSONResponse({"error": "Spotify not authorized"}, status_code=403)
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        params = {"limit": limit, "offset": offset}
        resp = requests.get("https://api.spotify.com/v1/me/tracks", headers=headers, params=params)
        return resp.json() if resp.status_code == 200 else JSONResponse({"error": "Failed to fetch liked songs"}, status_code=resp.status_code)
    except Exception as e:
        return JSONResponse({"error": "Exception occurred", "details": str(e)}, status_code=500)

@app.get("/read-profile")
def read_profile(user_id: str):
    try:
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
    except Exception as e:
        return JSONResponse({"error": "Exception occurred", "details": str(e)}, status_code=500)

@app.post("/write-profile")
def write_profile(payload: UserInput):
    try:
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
            requests.patch(
                f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media",
                headers={"Authorization": f"Bearer {token['access_token']}", "Content-Type": "text/plain"},
                data=payload.content.encode("utf-8")
            )
        else:
            metadata = {"name": "chad-settings.txt", "parents": [folder_id], "mimeType": "text/plain"}
            files = {"metadata": ("metadata", json.dumps(metadata), "application/json"), "file": ("file", payload.content, "text/plain")}
            requests.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart", headers={"Authorization": f"Bearer {token['access_token']}"}, files=files)
        return {"message": "Profile saved successfully."}
    except Exception as e:
        return JSONResponse({"error": "Exception occurred", "details": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
