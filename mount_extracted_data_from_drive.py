# import os
# import time
# from pydrive2.auth import GoogleAuth
# from pydrive2.drive import GoogleDrive


# # ================= WAIT =================
# def wait_for_task(task):
#     print("⏳ Waiting for GEE task...")

#     while True:
#         status = task.status()
#         state = status["state"]

#         print(f"State: {state}")

#         if state == "COMPLETED":
#             print("✅ Task completed")
#             return
#         elif state == "FAILED":
#             raise Exception(f"❌ Task failed: {status}")

#         time.sleep(20)


# # ================= AUTH =================
# def authenticate_drive():
#     gauth = GoogleAuth()

#     # Try loading saved credentials
#     gauth.LoadCredentialsFile("credentials.json")

#     if gauth.credentials is None:
#         # First-time login
#         print("🌐 First-time authentication required...")
#         gauth.LocalWebserverAuth()
#         gauth.SaveCredentialsFile("credentials.json")

#     elif gauth.access_token_expired:
#         # Token expired → refresh silently
#         print("🔄 Refreshing expired credentials...")
#         gauth.Refresh()
#         gauth.SaveCredentialsFile("credentials.json")

#     else:
#         # Valid credentials → silent login
#         print("✅ Using saved credentials")
#         gauth.Authorize()

#     return GoogleDrive(gauth)


# # ================= DOWNLOAD =================
# def download_latest_file(prefix="ntlr_features", output=None):

#     if output is None:
#         output = f"data/ntlr_features_{int(time.time())}.csv"

#     print("🔐 Authenticating Drive...")

#     os.makedirs(os.path.dirname(output), exist_ok=True)

#     drive = authenticate_drive()

#     print("🔍 Searching for file...")

#     file_list = drive.ListFile({
#         "q": f"title contains '{prefix}' and trashed=false"
#     }).GetList()

#     if not file_list:
#         raise Exception("❌ No file found")

#     # Sort latest first
#     file_list.sort(key=lambda x: x["modifiedDate"], reverse=True)

#     file = file_list[0]

#     print(f"📁 Found: {file['title']}")

#     file.GetContentFile(output)

#     print(f"📥 Downloaded → {output}")

#     return output  # ✅ critical for pipeline

import os
import time
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

# =========================================================
# CONFIG
# =========================================================
CLIENT_SECRET_FILE = "client_secrets.json"   # OAuth client file from Google Cloud
TOKEN_FILE = "token.json"                    # Saved login token (auto-created after first run)


# =========================================================
# AUTHENTICATE GOOGLE DRIVE
# One-time browser auth → saves token → future auto login
# =========================================================
def authenticate_drive():

    gauth = GoogleAuth()

    # -----------------------------------------------------
    # Load OAuth client secret
    # -----------------------------------------------------
    if not os.path.exists(CLIENT_SECRET_FILE):
        raise FileNotFoundError(
            f"❌ Missing {CLIENT_SECRET_FILE}. Download OAuth Desktop App JSON from Google Cloud."
        )

    gauth.LoadClientConfigFile(CLIENT_SECRET_FILE)

    # =====================================================
    # LOAD EXISTING TOKEN
    # =====================================================
    if os.path.exists(TOKEN_FILE):
        try:
            gauth.LoadCredentialsFile(TOKEN_FILE)
        except Exception:
            print("⚠️ Corrupt token detected. Removing old token...")
            os.remove(TOKEN_FILE)

    # =====================================================
    # FIRST LOGIN (Browser popup)
    # =====================================================
    if gauth.credentials is None:
        print("🌐 First-time authentication required...")
        gauth.LocalWebserverAuth()
        gauth.SaveCredentialsFile(TOKEN_FILE)
        print("✅ Token saved successfully for future runs")

    # =====================================================
    # TOKEN EXPIRED
    # =====================================================
    elif gauth.access_token_expired:

        # Refresh silently if refresh token exists
        if getattr(gauth.credentials, "refresh_token", None):
            print("🔄 Refreshing expired token...")
            gauth.Refresh()

        # Otherwise force login again
        else:
            print("⚠️ No refresh token found. Re-authenticating...")
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)

            gauth.LocalWebserverAuth()

        gauth.SaveCredentialsFile(TOKEN_FILE)
        print("✅ Token refreshed and saved")

    # =====================================================
    # VALID TOKEN
    # =====================================================
    else:
        print("✅ Using saved token")
        gauth.Authorize()

    return GoogleDrive(gauth)


# =========================================================
# WAIT FOR GEE EXPORT TASK
# =========================================================
def wait_for_task(task):

    print("⏳ Waiting for GEE task...")

    while True:

        status = task.status()
        state = status["state"]

        print(f"State: {state}")

        # ---------------------------------------------
        # SUCCESS
        # ---------------------------------------------
        if state == "COMPLETED":
            print("✅ Task completed")
            return

        # ---------------------------------------------
        # FAILURE
        # ---------------------------------------------
        elif state == "FAILED":
            raise Exception(f"❌ Task failed: {status}")

        # ---------------------------------------------
        # STILL RUNNING
        # ---------------------------------------------
        time.sleep(20)


# =========================================================
# DOWNLOAD LATEST FILE FROM GOOGLE DRIVE
# =========================================================
def download_latest_file(
    prefix="ntlr_features",
    output_folder="data"
):

    # Ensure output directory exists
    os.makedirs(output_folder, exist_ok=True)

    output_file = os.path.join(
        output_folder,
        f"{prefix}_{int(time.time())}.csv"
    )

    print("🔐 Connecting to Google Drive...")
    drive = authenticate_drive()

    print("🔍 Searching for latest file...")

    # Search all matching exports
    file_list = drive.ListFile({
        "q": f"title contains '{prefix}' and trashed=false"
    }).GetList()

    if not file_list:
        raise Exception(f"❌ No file found with prefix: {prefix}")

    # Sort newest first
    file_list.sort(
        key=lambda x: x["modifiedDate"],
        reverse=True
    )

    latest_file = file_list[0]

    print(f"📁 Found: {latest_file['title']}")

    # Download
    latest_file.GetContentFile(output_file)

    print(f"📥 Downloaded successfully → {output_file}")

    return output_file


# =========================================================
# MAIN TEST
# =========================================================
if __name__ == "__main__":

    downloaded_path = download_latest_file()

    print("🚀 Ready for pipeline")
    print(f"📂 Local File: {downloaded_path}")