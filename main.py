"""
Ember Validation Spike - Final Release
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
# BROWSER LOGIC
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
    log_callback(f"Target URL: {test_url}")
    log_callback("="*50)
    
    # Path setup
    try:
        # base_path = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path.cwd()
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            base_path = Path.cwd()

        download_dir = (base_path / CONFIG["DOWNLOAD_DIR"]).absolute()
        download_dir.mkdir(parents=True, exist_ok=True)
        state_file = (base_path / CONFIG["STATE_FILE"]).absolute()
    except Exception as e:
        log_callback(f"Path Error: {e}")
        return

    has_session = state_file.exists()
    
    with sync_playwright() as p:
        # Launch real Edge (if available) to match Intune policies
        try:
            browser = p.chromium.launch(headless=False, channel="msedge" if os.name == 'nt' else "chrome")
        except:
            browser = p.chromium.launch(headless=False) # Fallback

        context_opts = {
            "user_agent": CONFIG["USER_AGENT"],
            "viewport": {"width": 1280, "height": 800},
            "accept_downloads": True
        }
        
        # Load Session if exists
        if has_session:
            try:
                context = browser.new_context(storage_state=str(state_file), **context_opts)
                log_callback("Loaded existing session state.")
            except:
                log_callback("Session invalid. Creating new context.")
                context = browser.new_context(**context_opts)
                has_session = False
        else:
            context = browser.new_context(**context_opts)
            
        page = context.new_page()
        
        # Download Listener
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
        
        # --- LOGIN PHASE ---
        if not has_session:
            log_callback(f"Navigating to Login: {CONFIG['LOGIN_URL']}")
            page.goto(CONFIG['LOGIN_URL'])
            
            log_callback("\n" + "="*40)
            log_callback("ACTION REQUIRED: PLEASE LOGIN")
            log_callback("Complete the SSO/MFA flow manually in the browser.")
            log_callback("When you reach the Dashboard, click 'Save Session'.")
            log_callback("="*40 + "\n")
            
            # Enable Save Button and Wait
            save_session_callback(True, context, state_file, log_callback)
            
            # Keep browser alive until user acts
            while context.pages:
                page.wait_for_timeout(1000)
            return

        # --- DOWNLOAD PHASE ---
        log_callback("\nTesting Download via Link...")
        log_callback("Note: Mimecast/Redirect links are supported.")
        
        try:
            # Navigate to the pasted URL (Mimecast or Direct)
            # If it's a download link, Playwright catches the event, page might not 'load' fully
            page.goto(test_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            # It's common for download links to 'fail' navigation because they don't render HTML
            log_callback(f"Navigation ended (Expected for direct downloads): {e}")

        # Wait for download to finish
        log_callback("Waiting for file stream...")
        for _ in range(15): # Wait up to 15 seconds
            if download_status["success"]:
                break
            page.wait_for_timeout(1000)
            
        if download_status["success"]:
            status_callback("SUCCESS - File Downloaded!")
            log_callback("\n" + "="*50)
            log_callback("MILESTONE PASS: File retrieved via Managed Browser.")
            log_callback("="*50)
        else:
            status_callback("Inconclusive - No file yet")
            log_callback("\nDownload didn't trigger automatically.")
            log_callback("Try clicking the download button manually in the open browser.")
            
            # Keep open for manual test
            page.wait_for_timeout(30000)

        log_callback("Closing Browser...")
        context.close()
        browser.close()

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
        self.root.title("Ember Validation Spike (Final)")
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