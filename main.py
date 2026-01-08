"""
EvergreenPipeline Validation Spike
=======================================
A standalone tool to validate:
1. Browser Automation (Persistent Profile + Vue.js Support)
2. Shared Mailbox Access (App-Only via Graph API)
"""
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

# =============================================================================
# CONFIGURATION
# =============================================================================
CONFIG = {
    "DOWNLOAD_DIR": "downloads",

    # --- EMAIL SETTINGS ---
    "TARGET_MAILBOX": "samco@emberapp.io",
    
    # NEW: Client Email for Auto-fill
    "CLIENT_EMAIL": "ryan@schorecliffam.com",

    # Microsoft Graph (Confidential Client - App Only)
    "MS_CLIENT_ID": "",           # <--- PASTE ID HERE
    "MS_TENANT_ID": "",           # <--- PASTE TENANT ID HERE
    "MS_CLIENT_SECRET_VALUE": ""  # <--- PASTE SECRET HERE
}

# =============================================================================
# BROWSER LOGIC (FIXED: Vue.js "Disabled Button" Handling)
# =============================================================================
def run_browser_validation(test_url, log_callback, status_callback, save_session_callback):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_callback("ERROR: Playwright missing. Run 'pip install playwright'.")
        return

    status_callback("Initializing...")
    log_callback("="*50)
    log_callback("BROWSER VALIDATION STARTED")
    
    # --- PATH SETUP ---
    try:
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            base_path = Path.cwd()
        download_dir = (base_path / CONFIG["DOWNLOAD_DIR"]).absolute()
        download_dir.mkdir(parents=True, exist_ok=True)

        app_data = Path(os.getenv('LOCALAPPDATA')) / "EvergreenPipeline"
        profile_dir = (app_data / "edge_profile").absolute()
        profile_dir.mkdir(parents=True, exist_ok=True)
        log_callback(f"Profile: {profile_dir}")
        
    except Exception as e:
        log_callback(f"Path Error: {e}")
        return

    with sync_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled", 
            "--no-first-run",
            "--password-store=basic"
        ]

        log_callback("Launching Edge...")
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="msedge" if os.name == 'nt' else "chrome",
                headless=False,
                args=launch_args,
                viewport={"width": 1280, "height": 800},
                accept_downloads=True,
                ignore_default_args=["--enable-automation"] 
            )
        except Exception as e:
            log_callback(f"Launch Failed: {e}")
            return

        page = context.pages[0] if context.pages else context.new_page()
        
        # Download Listener
        download_status = {"success": False, "path": None}
        def on_download(download):
            try:
                log_callback(f"\n[+] DOWNLOAD: {download.suggested_filename}")
                f_path = download_dir / download.suggested_filename
                download.save_as(str(f_path))
                download_status["success"] = True
            except: pass
        page.on("download", on_download)
        
        # Navigate
        log_callback(f"\nNavigating to: {test_url}")
        try:
            page.goto(test_url, wait_until="domcontentloaded", timeout=60000)
        except: pass 

        # --- SMART LOOP: Vue.js Specific Strategy ---
        log_callback("\nScanning for Findox Login...")
        
        email_filled = False
        
        for i in range(120): # 2 mins
            if download_status["success"]: break
            
            if not email_filled:
                try:
                    # PRIORITY 1: The "Golden Ticket" Selector (from your HTML)
                    target = page.query_selector("[data-cy='step1-email-input']")
                    
                    # PRIORITY 2: Fallback
                    if not target:
                        target = page.query_selector("input[name='username']")

                    # EXECUTE TYPING
                    if target and target.is_visible() and not target.input_value():
                        log_callback("Found Input (Vue.js detected).")
                        
                        target.click()
                        target.fill("") 
                        
                        # 1. Type with rhythm to wake up Vue
                        log_callback("Typing email...")
                        target.press_sequentially(CONFIG["CLIENT_EMAIL"], delay=100)
                        
                        # 2. THE TRICK: Space + Backspace 
                        # This forces Vue to re-validate that the field is dirty/valid
                        page.wait_for_timeout(500)
                        target.press("Space")
                        page.wait_for_timeout(100)
                        target.press("Backspace")
                        
                        # 3. Trigger Blur
                        target.blur() 
                        page.wait_for_timeout(1000)
                        
                        email_filled = True
                        
                        # 4. Handle the "Disabled" Button
                        # We look for the button specifically by your new ID
                        btn = page.query_selector("[data-cy='step1-next-button']")
                        
                        if btn and btn.is_visible():
                            # Check if it is still disabled
                            is_disabled = btn.get_attribute("disabled") is not None
                            
                            if is_disabled:
                                log_callback("Button is disabled. Sending ENTER key fallback...")
                                target.focus()
                                target.press("Enter")
                            else:
                                log_callback("Button is ENABLED. Clicking...")
                                btn.click()
                        else:
                            # Fallback if button not found
                            target.press("Enter")

                except Exception as e:
                    pass

            # Smart Retry (if stuck on dashboard but no download)
            if not download_status["success"] and i > 25:
                # If we are NOT on a login page, but download failed, refresh
                url_str = page.url.lower()
                is_login_page = "login" in url_str or "signin" in url_str
                if not is_login_page and i % 10 == 0:
                    try: page.reload()
                    except: pass

            page.wait_for_timeout(1000)
            
        if download_status["success"]:
            status_callback("SUCCESS!")
            messagebox.showinfo("Success", "File Downloaded!")
        else:
            status_callback("Inconclusive")
            log_callback("Timed out.")

        try:
            context.close()
        except: pass

# =============================================================================
# EMAIL LOGIC (SHARED MAILBOX - APP ONLY)
# =============================================================================
def run_email_validation(password, log_callback, status_callback, code_callback):
    import re

    import msal
    import requests

    status_callback("Authenticating (App-Only)...")
    log_callback("="*50)
    log_callback(f"Target Inbox: {CONFIG['TARGET_MAILBOX']}")
    log_callback("="*50)

    try:
        # Check for empty config
        if not CONFIG["MS_CLIENT_ID"] or not CONFIG["MS_CLIENT_SECRET_VALUE"]:
             raise ValueError("Missing Credentials! Check CONFIG.")

        # 1. Setup Confidential Client
        app = msal.ConfidentialClientApplication(
            CONFIG["MS_CLIENT_ID"],
            authority=f"https://login.microsoftonline.com/{CONFIG['MS_TENANT_ID']}",
            client_credential=CONFIG["MS_CLIENT_SECRET_VALUE"]
        )

        # 2. Acquire Token
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" in result:
            log_callback("Auth Success! Accessing mailbox as Service...")
            
            headers = {"Authorization": f"Bearer {result['access_token']}"}
            endpoint = f"https://graph.microsoft.com/v1.0/users/{CONFIG['TARGET_MAILBOX']}/messages?$top=1&$select=subject,from,body"
            
            resp = requests.get(endpoint, headers=headers)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("value"):
                    email = data["value"][0]
                    subject = email.get('subject')
                    body_content = email.get('body', {}).get('content', '')
                    
                    log_callback("\n" + "="*50)
                    log_callback(f"Subject: {subject}")
                    
                    match_perfect = re.search(r'href=[\"\'](https?://[^\"\']*findox\.com[^\"\']*download=true[^\"\']*)[\"\']', body_content, re.IGNORECASE)
                    
                    found_link = None
                    if match_perfect:
                        found_link = match_perfect.group(1)
                        log_callback("\n[+] MATCH: Found exact 'findox...download=true' link.")
                    else:
                        match_mime = re.search(r'href=[\"\'](https?://[^\"\']*mimecastprotect\.com[^\"\']*)[\"\']', body_content, re.IGNORECASE)
                        if match_mime:
                            found_link = match_mime.group(1)
                            log_callback("\n[+] MATCH: Found Mimecast Redirect.")
                        else:
                            match_prox = re.search(r"href=[\"']([^\"']+)[\"'].{1,300}?\(Web\)", body_content, re.IGNORECASE | re.DOTALL)
                            if match_prox:
                                found_link = match_prox.group(1)
                                log_callback("\n[+] MATCH: Found link next to '(Web)' label.")

                    if found_link:
                        found_link = found_link.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                        log_callback(f"Extracted URL: {found_link}")
                        code_callback(None, None, subject, found_link)
                    else:
                        log_callback("\n[!] NO DOWNLOAD LINK FOUND.")
                        
                    log_callback("="*50)
                    status_callback("SUCCESS - Email Read!")
                else:
                    log_callback("Mailbox empty.")
                    status_callback("Empty Inbox")
            elif resp.status_code == 403:
                log_callback(f"ACCESS DENIED (403): {resp.text}")
                status_callback("Access Denied")
            else:
                log_callback(f"API Error {resp.status_code}: {resp.text}")
                status_callback("API Error")
        else:
             status_callback("Auth Failed")
             log_callback(f"Could not acquire token: {result.get('error')}")

    except Exception as e:
        log_callback(f"Connection Error: {e}")
        status_callback("Connection Error")

# =============================================================================
# GUI SETUP
# =============================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Evergreen Pipeline")
        self.root.geometry("750x650")
        self.browser_ctx = None
        self._ui()
        
    def _ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main, text="Milestone 1 Validation Tool", font=("Segoe UI", 14, "bold")).pack(pady=5)
        
        # BROWSER SECTION
        b_frame = ttk.LabelFrame(main, text="1. Browser & Download", padding=10)
        b_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(b_frame, text="Paste Download URL (from Email):").pack(anchor=tk.W)
        self.url_var = tk.StringVar()
        ttk.Entry(b_frame, textvariable=self.url_var, width=70).pack(fill=tk.X, pady=5)
        
        self.btn_browser = ttk.Button(b_frame, text="Launch Browser Test", command=self._run_browser)
        self.btn_browser.pack(anchor=tk.W, pady=5)

        # EMAIL SECTION
        e_frame = ttk.LabelFrame(main, text="2. Shared Mailbox Access", padding=10)
        e_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(e_frame, text=f"Scanning Target: {CONFIG['TARGET_MAILBOX']}").pack(anchor=tk.W)
        self.btn_email = ttk.Button(e_frame, text="Validate Mailbox Access", command=self._run_email)
        self.btn_email.pack(anchor=tk.W, pady=5)
        
        # OUTPUT
        self.status = tk.StringVar(value="Ready")
        ttk.Label(main, textvariable=self.status, foreground="blue", font=("Segoe UI", 10)).pack()
        self.code_lbl = ttk.Label(main, text="", foreground="red", font=("Consolas", 12))
        self.code_lbl.pack()
        self.log = scrolledtext.ScrolledText(main, height=12, font=("Consolas", 9))
        self.log.pack(fill=tk.BOTH, expand=True)

    def _log(self, msg):
        self.root.after(0, lambda: self.log.insert(tk.END, msg + "\n"))
        self.root.after(0, lambda: self.log.see(tk.END))

    def _status_upd(self, msg):
        self.root.after(0, lambda: self.status.set(msg))

    def _code_upd(self, code, url, subject=None, extracted_link=None):
        def _do():
            if subject: 
                self.code_lbl.config(text=f"Last Email: {subject}", foreground="green")
                if extracted_link:
                    self.url_var.set(extracted_link)
        self.root.after(0, _do)

    def _run_browser(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please paste the URL first.")
            return
        
        self.btn_browser.config(state=tk.DISABLED)
        threading.Thread(target=run_browser_validation, args=(url, self._log, self._status_upd, None), daemon=True).start()
        self.root.after(3000, lambda: self.btn_browser.config(state=tk.NORMAL))

    def _run_email(self):
        self.btn_email.config(state=tk.DISABLED)
        threading.Thread(target=run_email_validation, args=("", self._log, self._status_upd, self._code_upd), daemon=True).start()
        self.root.after(5000, lambda: self.btn_email.config(state=tk.NORMAL))

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()