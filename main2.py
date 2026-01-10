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
# BROWSER STATE (PERSIST FOR APP LIFETIME)
# =============================================================================
_playwright = None
_browser_context = None
_browser_page = None
_download_handler = None
_browser_lock = threading.Lock()

# =============================================================================
# CONFIGURATION
# =============================================================================
CONFIG = {
    "DOWNLOAD_DIR": "downloads",

    "TARGET_MAILBOX": "samco@emberapp.io",
    "CLIENT_EMAIL": "ryan@shorecliffam.com",

    "MS_CLIENT_ID": "",     
    "MS_TENANT_ID": "",  
    "MS_CLIENT_SECRET_VALUE": "" 
}

# =============================================================================
# BROWSER HELPERS
# =============================================================================
def _ensure_browser_context(profile_dir, log_callback):
    global _playwright, _browser_context, _browser_page

    try:
        if _browser_context and not _browser_context.is_closed():
            if _browser_context.pages:
                _browser_page = _browser_context.pages[0]
            elif _browser_page is None:
                _browser_page = _browser_context.new_page()
            return _browser_context, _browser_page
    except Exception:
        pass

    from playwright.sync_api import sync_playwright

    if _playwright is None:
        _playwright = sync_playwright().start()

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--password-store=basic",
    ]

    log_callback("Launching Edge...")
    _browser_context = _playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel="msedge" if os.name == "nt" else "chrome",
        headless=False,
        args=launch_args,
        viewport={"width": 1280, "height": 800},
        accept_downloads=True,
        ignore_default_args=["--enable-automation"],
    )
    _browser_page = _browser_context.pages[0] if _browser_context.pages else _browser_context.new_page()
    return _browser_context, _browser_page


def _close_browser_resources():
    global _playwright, _browser_context, _browser_page, _download_handler
    try:
        if _browser_context and not _browser_context.is_closed():
            _browser_context.close()
    except Exception:
        pass
    _browser_context = None
    _browser_page = None
    _download_handler = None
    try:
        if _playwright:
            _playwright.stop()
    except Exception:
        pass
    _playwright = None

# =============================================================================
# BROWSER LOGIC
# =============================================================================
def run_browser_validation(test_url, log_callback, status_callback, save_session_callback):
    try:
        from playwright.sync_api import Error as PlaywrightError
    except ImportError:
        log_callback("ERROR: Playwright missing.")
        return

    if not _browser_lock.acquire(blocking=False):
        log_callback("Browser already running. Please wait...")
        return

    status_callback("Initializing...")
    log_callback("="*50)
    log_callback("BROWSER VALIDATION STARTED")
    
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
        _browser_lock.release()
        return

    try:
        context, page = _ensure_browser_context(profile_dir, log_callback)
    except PlaywrightError as e:
        log_callback(f"Launch Failed: {e}")
        _browser_lock.release()
        return
    except Exception as e:
        log_callback(f"Launch Failed: {e}")
        _browser_lock.release()
        return

    try:
        # Download Listener (replace previous)
        download_status = {"success": False, "path": None}
        def on_download(download):
            try:
                log_callback(f"\n[+] DOWNLOAD: {download.suggested_filename}")
                f_path = download_dir / download.suggested_filename
                download.save_as(str(f_path))
                download_status["success"] = True
            except Exception:
                pass

        global _download_handler
        try:
            if _download_handler:
                page.off("download", _download_handler)
        except Exception:
            pass
        _download_handler = on_download
        page.on("download", _download_handler)

    def _log_goto_response(resp, label):
        try:
            if not resp:
                log_callback(f"{label}: no response")
                return
            ctype = resp.headers.get("content-type", "")
            cdisp = resp.headers.get("content-disposition", "")
            log_callback(f"{label}: {resp.status} {resp.url}")
            if ctype or cdisp:
                log_callback(f"{label} headers: content-type='{ctype}' content-disposition='{cdisp}'")
        except Exception:
            pass

    log_callback(f"\nNavigating to: {test_url}")
    try:
        resp = page.goto(test_url, wait_until="domcontentloaded", timeout=60000)
        _log_goto_response(resp, "Initial goto")
    except Exception as e:
        log_callback(f"Initial goto error: {e}")

        log_callback("\nScanning for Findox Login...")

        email_filled = False
        login_submitted = False
        download_retriggered = False

        # Login page detection; SSO/SAML implies post-login redirects
        login_keywords = ["login", "signin", "auth", "logon"]
        post_login_keywords = ["sso", "saml", "oauth", "verify", "identify"]

        for i in range(120): # 2 mins
            if download_status["success"]:
                break

            # 1. Determine State
            current_url = page.url.lower()
            is_on_login_page = any(k in current_url for k in login_keywords)
            is_post_login = any(k in current_url for k in post_login_keywords)

            # Reset if we bounced back to login
            if is_on_login_page and not login_submitted:
                email_filled = False

            # 2. AUTO-FILL LOGIC
            if not email_filled and is_on_login_page:
                try:
                    page.wait_for_timeout(500)
                    target = page.query_selector("[data-cy='step1-email-input']")
                    if not target:
                        target = page.query_selector("input[name='username']")
                    if not target:
                        target = page.query_selector("input[type='email']")

                    if target and target.is_visible():
                        current_val = target.input_value()
                        if not current_val or CONFIG["CLIENT_EMAIL"] not in current_val:
                            log_callback("Found Input. Auto-filling...")
                            target.click()
                            target.fill("")

                            log_callback("Typing email...")
                            target.type(CONFIG["CLIENT_EMAIL"], delay=100)

                            # Wake Up Vue
                            page.wait_for_timeout(200)
                            target.press("Space")
                            page.wait_for_timeout(100)
                            target.press("Backspace")
                            target.blur()
                            page.wait_for_timeout(1000)

                            email_filled = True

                            # Click Continue
                            btn = page.query_selector("[data-cy='step1-next-button']")
                            if not btn:
                                btn = page.query_selector("button:has-text('Continue')")

                            if btn and btn.is_visible():
                                log_callback("Waiting for button to enable...")
                                for _ in range(25):
                                    if btn.get_attribute("disabled") is None:
                                        break
                                    page.wait_for_timeout(200)

                                if btn.get_attribute("disabled") is None:
                                    log_callback("Button Enabled! Clicking...")
                                    btn.click()
                                else:
                                    log_callback("Button stuck. Force clicking...")
                                    btn.click(force=True)
                                login_submitted = True
                            else:
                                log_callback("No button. Sending Enter...")
                                target.focus()
                                target.press("Enter")
                                login_submitted = True

                            page.wait_for_timeout(2000)

                except Exception as e:
                    log_callback(f"Auto-fill error: {e}")

            # 3. QUICK RETRIGGER FOR ALREADY-AUTHED SESSIONS
            if not download_status["success"] and not is_on_login_page and not download_retriggered and i == 5:
                log_callback("\n[!] Already authenticated. Re-visiting download URL...")
                try:
                    resp = page.goto(test_url)
                    _log_goto_response(resp, "Quick re-trigger")
                    download_retriggered = True
                except Exception as e:
                    log_callback(f"Quick re-trigger error: {e}")

            # 4. CRITICAL: RE-TRIGGER DOWNLOAD
            # Only trigger if:
            #   a) No download yet
            #   b) We are DEFINITELY NOT on a login page (url check)
            #   c) We have waited > 15 seconds (to allow redirects to settle)
            if not download_status["success"] and not is_on_login_page and i > 15:
                if not download_retriggered:
                    if is_post_login:
                        log_callback("\n[!] SSO redirect detected. Re-visiting download URL...")
                    else:
                        log_callback("\n[!] Login appears complete (No login keywords in URL).")
                    log_callback("[!] Re-visiting download URL to capture file...")
                    try:
                        resp = page.goto(test_url)
                        _log_goto_response(resp, "Post-login re-trigger")
                        download_retriggered = True
                    except Exception as e:
                        log_callback(f"Post-login re-trigger error: {e}")
                elif i % 15 == 0:
                     # If we tried once and it failed, retry every 15 ticks
                     log_callback("Still waiting... Refreshing page.")
                     try:
                        page.reload()
                    except Exception:
                        pass

            page.wait_for_timeout(1000)

        if download_status["success"]:
            status_callback("SUCCESS!")
            messagebox.showinfo("Success", "File Downloaded!")
        else:
            status_callback("Inconclusive")
            log_callback("Timed out.")
    finally:
        _browser_lock.release()
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
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
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

    def _on_close(self):
        _close_browser_resources()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
