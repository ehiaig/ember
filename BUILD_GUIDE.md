# Validation Spike - Build & Deployment Guide
==============================================

## Overview
This document provides instructions for building and deploying the Validation Spike application as a standalone Windows executable.

---

## Development Setup (Mac)

### 1. Create Virtual Environment
```bash
cd /Users/ehiaig/Projects/ember
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Install Playwright Browsers
```bash
playwright install chromium
```

### 4. Run Locally (for testing)
```bash
python main.py
```

---

## Configuration

Before building, update the `CONFIG` section in `main.py`:

```python
CONFIG = {
    # Your FinDox URLs
    "BASE_URL": "https://findox.com",
    "LOGIN_URL": "https://findox.com/login",
    "TEST_DOWNLOAD_URL": "https://findox.com/deal/123/download",
    
    # Azure AD App Registration (REQUIRED for email validation)
    "MS_CLIENT_ID": "your-azure-app-client-id",
    "MS_TENANT_ID": "common",  # or your specific tenant ID
}
```

### Azure AD App Registration (for Email Validation)
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to: **Azure Active Directory** > **App Registrations** > **New Registration**
3. Name: "Validation Spike" (or any name)
4. Supported account types: Choose based on your needs
5. Redirect URI: Leave blank (using Device Code Flow)
6. After creation:
   - Go to **Authentication** > Enable **"Allow public client flows"**
   - Go to **API Permissions** > Add:
     - Microsoft Graph > Delegated > `Mail.Read`
     - Microsoft Graph > Delegated > `User.Read`
7. Copy the **Application (client) ID** to `CONFIG["MS_CLIENT_ID"]`

---

## Building the Windows Executable

### Option A: Build on Windows (Recommended)

Since the target is a Windows machine, it's best to build on Windows:

#### 1. Set up Windows Build Environment
```powershell
# Install Python 3.11+ from python.org
# Open PowerShell as Administrator

cd C:\path\to\project
python -m venv venv
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install pyinstaller
```

#### 2. Install Playwright Browsers
```powershell
playwright install chromium
```

#### 3. Build the Executable
```powershell
pyinstaller --onefile --windowed --name "ValidationSpike" --add-data "browser_state.json;." main.py
```

**Note**: The `--add-data` flag syntax uses `;` on Windows and `:` on Mac/Linux.

#### 4. Important: Playwright Browsers
Playwright browsers are NOT bundled in the exe. You have two options:

**Option 1: Client installs browsers (Simpler)**
1. Send the client the `dist/ValidationSpike.exe`
2. Ask them to run in PowerShell:
   ```powershell
   pip install playwright
   playwright install chromium
   ```
3. Then run `ValidationSpike.exe`

**Option 2: Bundle browsers manually (Larger file, ~200MB+)**
1. Find Playwright browser location:
   ```powershell
   playwright install chromium --with-deps
   # Browsers are typically at: %USERPROFILE%\AppData\Local\ms-playwright
   ```
2. Copy the entire `ms-playwright` folder alongside the exe
3. Set environment variable in your code or batch script:
   ```
   set PLAYWRIGHT_BROWSERS_PATH=.\ms-playwright
   ValidationSpike.exe
   ```

---

### Option B: Cross-compile on Mac (Less Reliable)

Cross-compiling Python to Windows from Mac is not natively supported. Options:
1. Use a Windows VM or Docker container
2. Use GitHub Actions with Windows runner
3. Use a service like PyInstaller in a CI/CD pipeline

---

## Deployment Package for Client

Send the following to your client:

### Files to Send:
1. `ValidationSpike.exe` (from `dist/` folder)
2. `README_CLIENT.txt` (create with instructions below)

### README_CLIENT.txt Content:
```
VALIDATION SPIKE - Quick Start
==============================

PREREQUISITES:
1. Ensure Python 3.11+ is installed
2. Run these commands in PowerShell (one-time setup):
   pip install playwright
   playwright install chromium

RUNNING THE APP:
1. Double-click ValidationSpike.exe
2. Click "Validate Browser Download" to test browser automation
3. Click "Validate Email Connection" to test email access

BROWSER VALIDATION:
- If no session exists, a browser will open for you to login
- Complete the SSO/Intune login manually
- Click "Save Session" to save your login for future runs
- Future runs will use the saved session

EMAIL VALIDATION:
- A code will be displayed (e.g., "A1B2C3")
- Open https://microsoft.com/devicelogin in any browser
- Enter the code and sign in with your Microsoft account
- The app will automatically detect when you've signed in

TROUBLESHOOTING:
- If browser validation fails, delete browser_state.json and retry
- If email validation fails, ensure Mail.Read permissions are granted
- Check the log output for detailed error messages
```

---

## Alternative: Simple Batch Script Approach

If PyInstaller causes issues, provide a simpler batch script:

### run_validation.bat
```batch
@echo off
echo Installing dependencies...
pip install playwright msal requests
playwright install chromium

echo Starting Validation Spike...
python main.py

pause
```

Send `main.py`, `requirements.txt`, and `run_validation.bat` to the client.

---

## Troubleshooting

### Issue: Playwright not finding browsers in exe
**Solution**: Set environment variable before running:
```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "C:\Users\<user>\AppData\Local\ms-playwright"
.\ValidationSpike.exe
```

### Issue: SSL/Certificate errors
**Solution**: May indicate corporate proxy. Add to code:
```python
import os
os.environ['NODE_TLS_REJECT_UNAUTHORIZED'] = '0'  # Only for testing!
```

### Issue: Tkinter not found
**Solution**: Ensure Python was installed with Tcl/Tk option enabled.

### Issue: MSAL authentication fails
**Solution**: 
1. Verify Azure AD app has correct permissions
2. Ensure "Allow public client flows" is enabled
3. Check if organization blocks device code flow

---

## PyInstaller Command Reference

### Basic (console visible for debugging):
```powershell
pyinstaller --onefile --name "ValidationSpike" main.py
```

### Production (no console, windowed app):
```powershell
pyinstaller --onefile --windowed --name "ValidationSpike" main.py
```

### With icon:
```powershell
pyinstaller --onefile --windowed --name "ValidationSpike" --icon=app.ico main.py
```

### Full command with hidden imports (if needed):
```powershell
pyinstaller --onefile --windowed --name "ValidationSpike" ^
  --hidden-import=playwright ^
  --hidden-import=msal ^
  --hidden-import=requests ^
  --collect-all msal ^
  main.py
```

---

## Security Notes

1. **Session File**: `browser_state.json` contains cookies - treat as sensitive
2. **No secrets in code**: Device Code Flow doesn't require client secrets
3. **Token storage**: MSAL tokens are stored in memory only (not persisted)
4. **Download folder**: Created in same directory as exe - ensure write permissions


Notes:
- Had 