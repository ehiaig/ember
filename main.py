"""
EvergreenPipeline Validation Spike
=======================================
A standalone tool to validate:
1. Browser Automation (Bypassing Intune/SSO & capturing Mimecast downloads)
2. Shared Mailbox Access (via Graph API Device Code Flow)

Developed for Windows Enterprise Environments.
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
    # Base URLs
    "BASE_URL": "https://findox.com",
    "LOGIN_URL": "https://findox.com/login",

    "STATE_FILE": "browser_state.json",
    "DOWNLOAD_DIR": "downloads",

    "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",

    # --- EMAIL SETTINGS ---
    "ADMIN_EMAIL": "dev-admin@emberapp.io",
    "TARGET_MAILBOX": "samco@emberapp.io",

    # Microsoft Graph (Azure CLI Public Client - Safe for Enterprise)
    "MS_CLIENT_ID": "268bea51-ff50-4d3d-b09d-396cfad6764d",
    "MS_TENANT_ID": "bd18e10f-0f57-4b5e-813d-98086df34ca1",
}

# =============================================================================
# BROWSER LOGIC (UPDATED: Persistent Profile)
# =============================================================================
def run_browser_validation(test_url, log_callback, status_callback, save_session_callback):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_callback("ERROR: Playwright missing. Run 'pip install playwright'.")
        return

    status_callback("Initializing Browser...")
    log_callback("="*50)
    log_callback("BROWSER VALIDATION STARTED")
    log_callback("Mode: Persistent Profile (Intune Compliance)")
    log_callback(f"Target URL: {test_url}")
    log_callback("="*50)
    
    # Path setup
    try:
        # Determine paths
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            base_path = Path.cwd()

        download_dir = (base_path / CONFIG["DOWNLOAD_DIR"]).absolute()
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # NEW: Persistent Profile Directory
        # This folder will store the "Signed In" state of the browser itself
        profile_dir = (base_path / "edge_profile").absolute()
        log_callback(f"Profile Path: {profile_dir}")
        
    except Exception as e:
        log_callback(f"Path Error: {e}")
        return

    with sync_playwright() as p:
        # LAUNCH ARGS: Make it look like a real user's browser, not a bot
        # This helps bypass "AutomationControlled" flags that trigger stricter policies
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-service-autorun",
            "--password-store=basic",
        ]

        log_callback("Launching Edge with Persistent Profile...")
        
        try:
            # SWITCH TO: launch_persistent_context
            # This is the key fix. It creates a permanent user data folder.
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="msedge" if os.name == 'nt' else "chrome",
                headless=False,
                args=launch_args,
                viewport={"width": 1280, "height": 800},
                accept_downloads=True,
                # Try to ignore the 'Chrome is being controlled by automation' banner
                ignore_default_args=["--enable-automation"] 
            )
        except Exception as e:
            log_callback(f"Launch Failed: {e}")
            log_callback("Try closing all other Edge windows and running again.")
            return

        # Persistent contexts open a page by default
        page = context.pages[0] if context.pages else context.new_page()
        
        # Setup Download Listener
        download_status = {"success": False, "path": None}
        def on_download(download):
            try:
                log_callback(f"\nDownload Detected! Filename: {download.suggested_filename}")
                f_path = download_dir / download.suggested_filename
                download.save_as(str(f_path))
                log_callback(f"Saved to: {f_path}")
                download_status["success"] = True
                download_status["path"] = str(f_path)
            except Exception as e:
                log_callback(f"Save failed: {e}")

        page.on("download", on_download)
        
        # --- NAVIGATION ---
        log_callback(f"\nNavigating to: {test_url}")
        log_callback("NOTE: If you see 'Sign in to Edge', please do so.")
        log_callback("We need the browser to be 'Managed' to download the file.")
        
        try:
            page.goto(test_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log_callback(f"Navigation note: {e}")

        # --- WAIT LOOP ---
        # We wait longer now to allow him to handle the "Switch Profile" or Login prompts
        log_callback("\nWaiting for download...")
        log_callback("If stuck on login screens, please complete them manually.")
        
        # Wait up to 3 minutes for user to fight through the login screens
        for i in range(180): 
            if download_status["success"]:
                break
            if i % 10 == 0:
                # Keep session alive
                page.wait_for_timeout(100)
            page.wait_for_timeout(1000)
            
        if download_status["success"]:
            status_callback("SUCCESS - File Downloaded!")
            log_callback("\n" + "="*50)
            log_callback("MILESTONE PASS: File retrieved via Managed Browser.")
            log_callback("="*50)
            messagebox.showinfo("Success", "File Downloaded Successfully!")
        else:
            status_callback("Inconclusive - No file yet")
            log_callback("\nTimed out waiting for download.")
            log_callback("Browser will remain open for manual testing...")
            page.wait_for_timeout(30000) # Keep open for 30s more

        try:
            context.close()
        except:
            pass
# =============================================================================
# UPDATED EMAIL LOGIC (Targeting "(Web)" links specifically)
# =============================================================================
def run_email_validation(password, log_callback, status_callback, code_callback):
    import re

    import msal
    import requests
    
    status_callback("Connecting to Graph API...")
    log_callback("="*50)
    log_callback(f"Target Inbox: {CONFIG['TARGET_MAILBOX']}")
    log_callback("="*50)
    
    # 1. Auth Flow
    app = msal.PublicClientApplication(
        client_id=CONFIG["MS_CLIENT_ID"],
        authority=f"https://login.microsoftonline.com/{CONFIG['MS_TENANT_ID']}"
    )
    
    flow = app.initiate_device_flow(scopes=["User.Read", "Mail.Read.Shared"])
    if "user_code" not in flow:
        log_callback(f"Auth Init Error: {flow.get('error_description')}")
        return
        
    code_callback(flow["user_code"], flow["verification_uri"])
    log_callback(f"\nACTION REQUIRED:\n1. Go to {flow['verification_uri']}\n2. Enter {flow['user_code']}")
    
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        status_callback("Auth Failed")
        return
        
    log_callback("Auth Success! Scanning email...")
    
    # 2. Query Message
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
            
            found_link = None

            # --- STRATEGY 1: The 'Golden Key' (download=true) ---
            # This is the most robust method based on your latest data.
            # It ignores the 'Deal' link because that doesn't have download=true.
            
            # Regex: href=" (any url containing findox.com AND download=true) "
            match_perfect = re.search(r'href=[\"\'](https?://[^\"\']*findox\.com[^\"\']*download=true[^\"\']*)[\"\']', body_content, re.IGNORECASE)
            
            if match_perfect:
                found_link = match_perfect.group(1)
                log_callback("\n[+] MATCH: Found exact 'findox...download=true' link.")
            
            else:
                # --- STRATEGY 2: Mimecast Rewritten URLs ---
                # Sometimes security software hides the parameters.
                match_mime = re.search(r'href=[\"\'](https?://[^\"\']*mimecastprotect\.com[^\"\']*)[\"\']', body_content, re.IGNORECASE)
                if match_mime:
                    found_link = match_mime.group(1)
                    log_callback("\n[+] MATCH: Found Mimecast Redirect.")
                
                else:
                    # --- STRATEGY 3: Fallback to Proximity (Web) ---
                    match_prox = re.search(r"href=[\"']([^\"']+)[\"'].{1,300}?\(Web\)", body_content, re.IGNORECASE | re.DOTALL)
                    if match_prox:
                        found_link = match_prox.group(1)
                        log_callback("\n[+] MATCH: Found link next to '(Web)' label.")

            if found_link:
                # Sanitize HTML entities (e.g. &amp; -> &)
                found_link = found_link.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                
                log_callback(f"Extracted URL: {found_link}")
                log_callback("Auto-filling Browser Input...")
                code_callback(None, None, subject, found_link)
            else:
                log_callback("\n[!] NO DOWNLOAD LINK FOUND.")
                log_callback("Debug Dump (All hrefs):")
                all_links = re.findall(r'href=[\"\']([^\"\']+)[\"\']', body_content)
                for i, link in enumerate(all_links):
                    log_callback(f" #{i+1}: {link[:100]}...") # Print first 100 chars

            log_callback("="*50)
            status_callback("SUCCESS - Email Read!")
        else:
            log_callback("Mailbox empty.")
            status_callback("Empty Inbox")
    else:
        log_callback(f"API Error: {resp.text}")
        status_callback("API Error")

# =============================================================================
# GUI SETUP
# =============================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Evergreen Pipeline")
        self.root.geometry("750x650")
        
        self.browser_ctx = None
        self.state_file = None
        
        self._ui()
        
    def _ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        
        # Header
        ttk.Label(main, text="Milestone 1 Validation Tool", font=("Segoe UI", 14, "bold")).pack(pady=5)
        
        # --- SECTION 1: BROWSER ---
        b_frame = ttk.LabelFrame(main, text="1. Browser & Download", padding=10)
        b_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(b_frame, text="Paste Download URL (from Email):").pack(anchor=tk.W)
        self.url_var = tk.StringVar()
        ttk.Entry(b_frame, textvariable=self.url_var, width=70).pack(fill=tk.X, pady=5)
        
        btn_box = ttk.Frame(b_frame)
        btn_box.pack(fill=tk.X)
        self.btn_browser = ttk.Button(btn_box, text="Launch Browser Test", command=self._run_browser)
        self.btn_browser.pack(side=tk.LEFT, padx=5)
        self.btn_save = ttk.Button(btn_box, text="Save Session", state=tk.DISABLED, command=self._save)
        self.btn_save.pack(side=tk.LEFT, padx=5)

        # --- SECTION 2: EMAIL ---
        e_frame = ttk.LabelFrame(main, text="2. Shared Mailbox Access", padding=10)
        e_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(e_frame, text=f"Admin: {CONFIG['ADMIN_EMAIL']}  |  Target: {CONFIG['TARGET_MAILBOX']}").pack(anchor=tk.W)
        
        self.btn_email = ttk.Button(e_frame, text="Validate Mailbox Access", command=self._run_email)
        self.btn_email.pack(anchor=tk.W, pady=5)
        
        # --- OUTPUT ---
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
                # AUTO-FILL THE INPUT FIELD
                if extracted_link:
                    self.url_var.set(extracted_link)
            elif code: 
                self.code_lbl.config(text=f"CODE: {code}  (Enter at {url})", foreground="red")
            else: 
                self.code_lbl.config(text="")
        self.root.after(0, _do)

    def _enable_save(self, enable, ctx=None, f=None, l=None):
        def _do():
            if enable:
                self.browser_ctx = ctx
                self.state_file = f
                self.btn_save.config(state=tk.NORMAL)
            else:
                self.btn_save.config(state=tk.DISABLED)
        self.root.after(0, _do)

    def _save(self):
        if self.browser_ctx:
            self.browser_ctx.storage_state(path=str(self.state_file))
            self._log(f"Session Saved to {self.state_file}")
            messagebox.showinfo("Saved", "Session captured! You can now re-run to test auto-download.")

    def _run_browser(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please paste the Mimecast/Findox link from the email first.")
            return
        
        self.btn_browser.config(state=tk.DISABLED)
        threading.Thread(target=run_browser_validation, args=(url, self._log, self._status_upd, self._enable_save), daemon=True).start()
        self.root.after(3000, lambda: self.btn_browser.config(state=tk.NORMAL))

    def _run_email(self):
        self.btn_email.config(state=tk.DISABLED)
        threading.Thread(target=run_email_validation, args=("", self._log, self._status_upd, self._code_upd), daemon=True).start()
        self.root.after(5000, lambda: self.btn_email.config(state=tk.NORMAL))

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()