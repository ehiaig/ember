"""
EvergreenPipeline Validation Spike
=======================================
A standalone tool to validate:
1. Browser Automation (Persistent Profile + Long-Lived Session)
2. Shared Mailbox Access (App-Only via Graph API)
3. Okta Automation Support
"""
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from playwright.sync_api import sync_playwright

# =============================================================================
# CONFIGURATION
# =============================================================================
CONFIG = {
    "DOWNLOAD_DIR": "downloads",
    "TARGET_MAILBOX": "samco@emberapp.io",
    "CLIENT_EMAIL": "ryan@shorecliffam.com", 
    
    # Microsoft Graph (Confidential Client - App Only)
    "MS_CLIENT_ID": "",           # <--- PASTE ID
    "MS_TENANT_ID": "",           # <--- PASTE TENANT
    "MS_CLIENT_SECRET_VALUE": ""  # <--- PASTE SECRET
}

# =============================================================================
# GLOBAL STATE (THE LONG-LIVED BROWSER)
# =============================================================================
GLOBAL_PLAYWRIGHT = None
GLOBAL_BROWSER_CONTEXT = None
BROWSER_LOCK = threading.Lock()

def get_or_create_browser(log_callback, force_restart=False):
    """
    Returns an existing browser instance or creates a new one.
    Handles 'Zombie' browsers by restarting if force_restart is True.
    """
    global GLOBAL_PLAYWRIGHT, GLOBAL_BROWSER_CONTEXT
    
    with BROWSER_LOCK:
        # 1. Cleanup if forcing restart
        if force_restart and GLOBAL_BROWSER_CONTEXT:
            log_callback("Force-restarting browser...")
            try: GLOBAL_BROWSER_CONTEXT.close()
            except: pass
            GLOBAL_BROWSER_CONTEXT = None

        # 2. Check existing
        if GLOBAL_BROWSER_CONTEXT is not None:
            try:
                # Lightweight check to see if browser is responsive
                if not GLOBAL_BROWSER_CONTEXT.pages: pass 
                return GLOBAL_BROWSER_CONTEXT
            except:
                log_callback("Existing browser was closed. Creating new one...")
                GLOBAL_BROWSER_CONTEXT = None

        log_callback("Initializing Long-Lived Browser Session...")
        
        # Path Setup
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            base_path = Path.cwd()
            
        app_data = Path(os.getenv('LOCALAPPDATA')) / "EvergreenPipeline"
        profile_dir = (app_data / "edge_profile").absolute()
        profile_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Playwright (Once per app lifetime)
        if GLOBAL_PLAYWRIGHT is None:
            GLOBAL_PLAYWRIGHT = sync_playwright().start()
            
        launch_args = [
            "--disable-blink-features=AutomationControlled", 
            "--no-first-run",
            "--password-store=basic"
        ]

        try:
            GLOBAL_BROWSER_CONTEXT = GLOBAL_PLAYWRIGHT.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="msedge" if os.name == 'nt' else "chrome",
                headless=False,
                args=launch_args,
                viewport={"width": 1280, "height": 800},
                accept_downloads=True,
                ignore_default_args=["--enable-automation"]
            )
            log_callback(f"Browser Launched. Profile: {profile_dir}")
            return GLOBAL_BROWSER_CONTEXT
        except Exception as e:
            log_callback(f"FATAL: Could not launch browser: {e}")
            return None

# =============================================================================
# BROWSER LOGIC
# =============================================================================
def run_browser_validation(test_url, log_callback, status_callback):
    status_callback("Acquiring Browser...")
    
    # 1. Get Context (Safe Mode)
    context = get_or_create_browser(log_callback)
    page = None
    
    try:
        # Try to open a tab. If this fails, the browser is dead (Zombie state).
        page = context.new_page()
    except:
        log_callback("Browser connection lost. Launching fresh instance...")
        context = get_or_create_browser(log_callback, force_restart=True)
        if context:
            page = context.new_page()
        else:
            status_callback("Launch Failed")
            return

    status_callback("Tab Opened")
    log_callback("="*50)
    
    # Download Setup
    if getattr(sys, 'frozen', False):
        base_path = Path(sys.executable).parent
    else:
        base_path = Path.cwd()
    download_dir = (base_path / CONFIG["DOWNLOAD_DIR"]).absolute()
    download_dir.mkdir(parents=True, exist_ok=True)

    download_status = {"success": False}
    def on_download(download):
        try:
            log_callback(f"\n[+] DOWNLOAD STARTED: {download.suggested_filename}")
            f_path = download_dir / download.suggested_filename
            download.save_as(str(f_path))
            download_status["success"] = True
            log_callback("[+] File Saved Successfully.")
        except: pass
    page.on("download", on_download)
    
    # 2. NAVIGATE
    log_callback(f"Navigating to: {test_url}")
    try:
        page.goto(test_url, wait_until="domcontentloaded", timeout=60000)
    except: pass 

    # --- SMART LOOP ---
    email_filled = False
    okta_filled = False  # Track Okta status
    login_submitted = False
    download_retriggered = False
    
    # Keywords
    login_keywords = ["login", "signin", "auth", "logon"]
    post_login_keywords = ["sso", "saml", "oauth", "verify", "identify"]
    
    for i in range(120): # 2 mins max
        if download_status["success"]: break
        
        current_url = page.url.lower()
        is_on_login_page = any(k in current_url for k in login_keywords)
        is_okta_page = "okta" in current_url
        is_post_login = any(k in current_url for k in post_login_keywords)
        
        # Reset if we bounced back
        if is_on_login_page and not login_submitted and not is_okta_page:
            email_filled = False
        
        # ====================================================
        # A. FINDOX LOGIN AUTOMATION
        # ====================================================
        if not email_filled and is_on_login_page and not is_okta_page:
            try:
                page.wait_for_timeout(500)
                # Selectors for Findox
                target = page.query_selector("[data-cy='step1-email-input']")
                if not target: target = page.query_selector("input[name='username']")
                if not target: target = page.query_selector("input[type='email']")

                if target and target.is_visible():
                    val = target.input_value()
                    if not val or CONFIG["CLIENT_EMAIL"] not in val:
                        log_callback("Findox Login Detected.")
                        target.click(); target.fill("")
                        target.type(CONFIG["CLIENT_EMAIL"], delay=50) # Faster typing
                        
                        # Vue.js Wake Up
                        page.wait_for_timeout(100); target.press("Space"); target.press("Backspace")
                        target.blur(); page.wait_for_timeout(500)
                        email_filled = True
                        
                        # Click Continue
                        btn = page.query_selector("[data-cy='step1-next-button']")
                        if not btn: btn = page.query_selector("button:has-text('Continue')")

                        if btn and btn.is_visible():
                            # Quick wait for enable
                            for _ in range(10): 
                                if btn.get_attribute("disabled") is None: break
                                page.wait_for_timeout(100)
                            if btn.get_attribute("disabled") is None: btn.click()
                            else: btn.click(force=True)
                            login_submitted = True
                        else:
                            target.press("Enter")
                            login_submitted = True
                        page.wait_for_timeout(1000)
            except: pass

        # ====================================================
        # B. OKTA LOGIN AUTOMATION
        # ====================================================
        if is_okta_page and not okta_filled:
            try:
                # Okta usually has an 'identifier' or 'username' field
                # Common Okta Selectors: input[name="identifier"], input[name="username"], #okta-signin-username
                okta_user = page.query_selector("input[name='identifier']")
                if not okta_user: okta_user = page.query_selector("input[name='username']")
                if not okta_user: okta_user = page.query_selector("#okta-signin-username")
                
                if okta_user and okta_user.is_visible():
                    val = okta_user.input_value()
                    # Only type if empty or doesn't match
                    if not val or CONFIG["CLIENT_EMAIL"] not in val:
                        log_callback("Okta Login Detected. Auto-filling...")
                        okta_user.click()
                        okta_user.fill("")
                        okta_user.type(CONFIG["CLIENT_EMAIL"], delay=50)
                        okta_filled = True
                        
                        # Click Next
                        # Okta buttons: input[type="submit"], #okta-signin-submit, button[type="submit"]
                        okta_next = page.query_selector("input[type='submit']")
                        if not okta_next: okta_next = page.query_selector("#okta-signin-submit")
                        
                        if okta_next and okta_next.is_visible():
                            log_callback("Clicking Okta Next...")
                            okta_next.click()
                        else:
                            okta_user.press("Enter")
                        
                        page.wait_for_timeout(2000)
            except Exception as e:
                log_callback(f"Okta Error: {e}")

        # ====================================================
        # C. RE-TRIGGER LOGIC (Dashboard / Post-Login)
        # ====================================================
        if not download_status["success"] and not is_on_login_page and not is_okta_page and i > 15:
            if not download_retriggered:
                if is_post_login: log_callback("\n[!] SSO/Post-Login Detected.")
                else: log_callback("\n[!] Session Active (Dashboard Detected).")
                
                log_callback("Triggering Download URL again...")
                try:
                    page.goto(test_url)
                    download_retriggered = True
                except: pass
            elif i % 15 == 0:
                 try: page.reload()
                 except: pass

        page.wait_for_timeout(1000)
        
    if download_status["success"]:
        status_callback("SUCCESS!")
        messagebox.showinfo("Success", "File Downloaded!")
    else:
        status_callback("Inconclusive")
        log_callback("Timed out.")

    # Close Tab ONLY (Keep Browser Alive)
    try: page.close()
    except: pass

# =============================================================================
# EMAIL LOGIC (UNCHANGED)
# =============================================================================
def run_email_validation(password, log_callback, status_callback, code_callback):
    import re

    import msal
    import requests

    status_callback("Authenticating (App-Only)...")
    log_callback("="*50)
    log_callback(f"Target Inbox: {CONFIG['TARGET_MAILBOX']}")
    
    try:
        if not CONFIG["MS_CLIENT_ID"] or not CONFIG["MS_CLIENT_SECRET_VALUE"]:
             raise ValueError("Missing Credentials! Check CONFIG.")

        app = msal.ConfidentialClientApplication(
            CONFIG["MS_CLIENT_ID"],
            authority=f"https://login.microsoftonline.com/{CONFIG['MS_TENANT_ID']}",
            client_credential=CONFIG["MS_CLIENT_SECRET_VALUE"]
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" in result:
            log_callback("Auth Success! Accessing mailbox...")
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
                        log_callback("[+] MATCH: Found exact 'findox' link.")
                    else:
                        match_mime = re.search(r'href=[\"\'](https?://[^\"\']*mimecastprotect\.com[^\"\']*)[\"\']', body_content, re.IGNORECASE)
                        if match_mime:
                            found_link = match_mime.group(1)
                            log_callback("[+] MATCH: Found Mimecast Redirect.")
                        else:
                            match_prox = re.search(r"href=[\"']([^\"']+)[\"'].{1,300}?\(Web\)", body_content, re.IGNORECASE | re.DOTALL)
                            if match_prox:
                                found_link = match_prox.group(1)
                                log_callback("[+] MATCH: Found link next to '(Web)' label.")

                    if found_link:
                        found_link = found_link.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                        log_callback(f"URL: {found_link}")
                        code_callback(None, None, subject, found_link)
                    else:
                        log_callback("[!] NO DOWNLOAD LINK FOUND.")
                    
                    status_callback("Email Read!")
                else:
                    log_callback("Mailbox empty.")
                    status_callback("Empty Inbox")
            else:
                log_callback(f"API Error {resp.status_code}")
                status_callback("API Error")
        else:
             status_callback("Auth Failed")
             log_callback(f"Token Error: {result.get('error')}")

    except Exception as e:
        log_callback(f"Connection Error: {e}")
        status_callback("Connection Error")

# =============================================================================
# GUI SETUP
# =============================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("EvergreenPipeline Validation Tool")
        self.root.geometry("750x650")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._ui()
        
    def _ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main, text="Milestone 1: Production Logic Spike", font=("Segoe UI", 14, "bold")).pack(pady=5)
        
        # BROWSER
        b_frame = ttk.LabelFrame(main, text="1. Browser & Download (Long-Lived Session)", padding=10)
        b_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(b_frame, text="Paste Download URL (from Email):").pack(anchor=tk.W)
        self.url_var = tk.StringVar()
        ttk.Entry(b_frame, textvariable=self.url_var, width=70).pack(fill=tk.X, pady=5)
        
        self.btn_browser = ttk.Button(b_frame, text="Launch Browser (Maintains Session)", command=self._run_browser)
        self.btn_browser.pack(anchor=tk.W, pady=5)

        # EMAIL
        e_frame = ttk.LabelFrame(main, text="2. Shared Mailbox Access", padding=10)
        e_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(e_frame, text=f"Scanning: {CONFIG['TARGET_MAILBOX']}").pack(anchor=tk.W)
        self.btn_email = ttk.Button(e_frame, text="Scan Mailbox", command=self._run_email)
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

        def _worker():
            try:
                run_browser_validation(url, self._log, self._status_upd)
            finally:
                self.root.after(0, lambda: self.btn_browser.config(state=tk.NORMAL))

        # Start the thread
        threading.Thread(target=_worker, daemon=True).start()
        
    def _run_email(self):
        self.btn_email.config(state=tk.DISABLED)
        threading.Thread(target=run_email_validation, args=("", self._log, self._status_upd, self._code_upd), daemon=True).start()
        self.root.after(3000, lambda: self.btn_email.config(state=tk.NORMAL))

    def _on_close(self):
        """Cleanup browser on App Close"""
        global GLOBAL_PLAYWRIGHT, GLOBAL_BROWSER_CONTEXT
        try:
            if GLOBAL_BROWSER_CONTEXT:
                GLOBAL_BROWSER_CONTEXT.close()
            if GLOBAL_PLAYWRIGHT:
                GLOBAL_PLAYWRIGHT.stop()
        except: pass
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()