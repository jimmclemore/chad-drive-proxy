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
    else:@app.post("/write-profile")
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
        requests.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers={"Authorization": f"Bearer {token['access_token']}"},
            files={
                "metadata": ("metadata", str(metadata), "application/json"),
                "file": ("file", payload.content, "text/plain")
            }
        )

    return {"message": "Profile saved successfully."}
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
            "mimeType":
