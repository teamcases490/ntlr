import os
import time
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


# ================= WAIT =================
def wait_for_task(task):
    print("⏳ Waiting for GEE task...")

    while True:
        status = task.status()
        state = status["state"]

        print(f"State: {state}")

        if state == "COMPLETED":
            print("✅ Task completed")
            return
        elif state == "FAILED":
            raise Exception(f"❌ Task failed: {status}")

        time.sleep(20)


# ================= AUTH =================
def authenticate_drive():
    gauth = GoogleAuth()

    # Try loading saved credentials
    gauth.LoadCredentialsFile("credentials.json")

    if gauth.credentials is None:
        # First-time login
        print("🌐 First-time authentication required...")
        gauth.LocalWebserverAuth()
        gauth.SaveCredentialsFile("credentials.json")

    elif gauth.access_token_expired:
        # Token expired → refresh silently
        print("🔄 Refreshing expired credentials...")
        gauth.Refresh()
        gauth.SaveCredentialsFile("credentials.json")

    else:
        # Valid credentials → silent login
        print("✅ Using saved credentials")
        gauth.Authorize()

    return GoogleDrive(gauth)


# ================= DOWNLOAD =================
def download_latest_file(prefix="ntlr_features", output=None):

    if output is None:
        output = f"data/ntlr_features_{int(time.time())}.csv"

    print("🔐 Authenticating Drive...")

    os.makedirs(os.path.dirname(output), exist_ok=True)

    drive = authenticate_drive()

    print("🔍 Searching for file...")

    file_list = drive.ListFile({
        "q": f"title contains '{prefix}' and trashed=false"
    }).GetList()

    if not file_list:
        raise Exception("❌ No file found")

    # Sort latest first
    file_list.sort(key=lambda x: x["modifiedDate"], reverse=True)

    file = file_list[0]

    print(f"📁 Found: {file['title']}")

    file.GetContentFile(output)

    print(f"📥 Downloaded → {output}")

    return output  # ✅ critical for pipeline