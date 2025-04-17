import os
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
import requests
from urllib.parse import urlencode

app = FastAPI()

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
SCOPES = "https://www.googleapis.com/auth/drive.file"

TOKENS = {}

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
        TOKENS[state] = r.json()
        return JSONResponse({"message": f"Authorized successfully for user_id={state}"})
    return JSONResponse({"error": "Authorization failed"}, status_code=400)

@app.post("/write-profile")
def write_profile(payload: UserInput):
    token = TOKENS.get(payload.user_id)
    if not token:
        return JSONResponse({"error": "User not authorized"}, status_code=403)

    headers = {
        "Authorization": f"Bearer {token['access_token']}",
        "Content-Type": "application/json"
    }

    folder_resp = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        headers=headers,
        params={"q": "name='ChadGPT' and mimeType='application/vnd.google-apps.folder' and trashed=false"}
    )
    folder_id = None
    files = folder_resp.json().get("files", [])
    if files:
        folder_id = files[0]["id"]
    else:
        folder_create = {
            "name": "ChadGPT",
            "mimeType": "application/vnd.google-apps.folder"
        }
        r = requests.post("https://www.googleapis.com/drive/v3/files", headers=headers, json=folder_create)
        folder
