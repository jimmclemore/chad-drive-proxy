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

    # Step 1: Check for existing ChadGPT folder
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
        folder_response = requests.post("https://www.googleapis.com/drive/v3/files", headers=headers, json=folder_create)
        folder_id = folder_response.json()["id"]

    # Step 2: Check if the file already exists
    query = f"'{folder_id}' in parents and name='chad-settings.txt' and trashed=false"
    existing = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params={"q": query}).json()
    if existing["files"]:
        file_id = existing["files"][0]["id"]
        requests.patch(
            f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media",
            headers={"Authorization": f"Bearer {token['access_token']}", "Content-Type": "text/plain"},
            data=payload.content.encode("utf-8"))
    else:
        metadata = {
            "name": "chad-settings.txt",
            "parents": [folder_id],
            "mimeType": "text/plain"
        }
        files = {
            "metadata": ("metadata", str(metadata), "application/json"),
            "file": ("file", payload.content, "text/plain")
        }
        requests.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers={"Authorization": f"Bearer {token['access_token']}"},
            files=files
        )

    return {"message": "Profile saved successfully."}
from datetime import datetime, timedelta

@app.get("/calendar")
def get_calendar_events(user_id: str):
    token = TOKENS.get(user_id)
    if not token:
        return JSONResponse({"error": "User not authorized"}, status_code=403)

    headers = {
        "Authorization": f"Bearer {token['access_token']}",
    }

    now = datetime.utcnow().isoformat() + "Z"
    future = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"

    params = {
        "maxResults": 10,
        "orderBy": "startTime",
        "singleEvents": True,
        "timeMin": now,
        "timeMax": future
    }

    resp = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers=headers,
        params=params
    )

    if resp.status_code == 200:
        return resp.json()
    else:
        return JSONResponse({
            "error": "Failed to fetch calendar",
            "details": resp.json()
        }, status_code=resp.status_code)
        
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
