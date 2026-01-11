"""
EvergreenPipeline Validation Spike
==================================
Validates:
1) Browser Automation (Persistent Profile + Session Reuse)
2) Shared Mailbox Access (App-Only via Microsoft Graph)

Updates:
- Detects existing cookies in the persistent profile and prefers "download-only" path if session exists
- Adds Okta username (email) + Next automation (email only; no password/MFA automation)
- Fixes "browser doesn't reopen" by using a real liveness check (open/close page)
- Brings new tabs to front
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

    # Email used for SSO username prefill (email only)
    "CLIENT_EMAIL": "ryan@shorecliffam.com",

    # Microsoft Graph (Confidential Client - App Only)
    "MS_CLIENT_ID": "",           # <--- PASTE ID
    "MS_TENANT_ID": "",           # <--- PASTE TENANT
    "MS_CLIENT_SECRET_VALUE": ""  # <--- PASTE SECRET
}


# =============================================================================
# GLOBAL STATE (LONG-LIVED PLAYWRIGHT + PERSISTENT CONTEXT)
# =============================================================================
GLOBAL_PLAYWRIGHT = None
GLOBAL_BROWSER_CONTEXT = None
BROWSER_LOCK = threading.Lock()


# =============================================================================
# PATH HELPERS
# =============================================================================
def _get_profile_dir() -> Path:
    app_data_root = Path(os.getenv("LOCALAPPDATA") or Path.home())
    profile_dir = (app_data_root / "EvergreenPipeline" / "edge_profile").absolute()
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def _get_download_dir() -> Path:
    if getattr(sys, "frozen", False):
        base_path = Path(sys.executable).parent
    else:
        base_path = Path.cwd()

    download_dir = (base_path / CONFIG["DOWNLOAD_DIR"]).absolute()
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


# =============================================================================
# BROWSER CONTEXT LIVENESS + CREATION
# =============================================================================
def _is_context_alive(context) -> bool:
    """
    Robust liveness check.
    context.pages can succeed even if user manually closed window.
    Opening + closing a page is a better indicator.
    """
    try:
        p = context.new_page()
        p.close()
        return True
    except Exception:
        return False


def get_or_create_browser(log_callback):
    """
    Returns existing persistent browser context if alive, otherwise creates a new one.
    Reuses the same profile directory so cookies can persist.
    """
    global GLOBAL_PLAYWRIGHT, GLOBAL_BROWSER_CONTEXT

    with BROWSER_LOCK:
        if GLOBAL_BROWSER_CONTEXT is not None:
            if _is_context_alive(GLOBAL_BROWSER_CONTEXT):
                log_callback("Reusing existing persistent browser session.")
                return GLOBAL_BROWSER_CONTEXT

            log_callback("Existing browser session is stale/closed. Recreating...")
            try:
                GLOBAL_BROWSER_CONTEXT.close()
            except Exception:
                pass
            GLOBAL_BROWSER_CONTEXT = None

        log_callback("Initializing persistent browser session...")

        profile_dir = _get_profile_dir()

        if GLOBAL_PLAYWRIGHT is None:
            GLOBAL_PLAYWRIGHT = sync_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--password-store=basic",
        ]

        # Windows: use Edge channel (managed browser)
        channel = "msedge" if os.name == "nt" else "chrome"

        try:
            GLOBAL_BROWSER_CONTEXT = GLOBAL_PLAYWRIGHT.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel=channel,
                headless=False,
                args=launch_args,
                viewport={"width": 1280, "height": 800},
                accept_downloads=True,
                ignore_default_args=["--enable-automation"],
            )
            log_callback(f"Browser launched with persistent profile: {profile_dir}")
            return GLOBAL_BROWSER_CONTEXT
        except Exception as e:
            log_callback(f"FATAL: Could not launch browser: {e}")
            return None


# =============================================================================
# SESSION / COOKIE DETECTION
# =============================================================================
def has_session_cookies(context, log_callback) -> bool:
    """
    Checks whether the persistent profile currently contains cookies that suggest
    an existing session for Findox/Okta/Microsoft auth.

    Note: presence of cookies does not guarantee they're still valid,
    but it’s a strong signal and helps us prefer the "download-only" path.
    """
    try:
        cookies = context.cookies()
        if not cookies:
            log_callback("[Session] No cookies present in context.")
            return False

        # Common domains encountered in this flow
        session_domains = ("findox.com", "okta.com", "microsoftonline.com", "live.com", "office.com")
        hits = [c for c in cookies if any(d in (c.get("domain") or "") for d in session_domains)]

        if hits:
            log_callback(f"[Session] Found {len(hits)} auth-related cookies (findox/okta/microsoft). Will attempt download without login.")
            return True

        log_callback("[Session] Cookies exist, but none match findox/okta/microsoft domains.")
        return False
    except Exception as e:
        log_callback(f"[Session] Cookie inspection failed: {e}")
        return False


# =============================================================================
# OKTA EMAIL STEP (EMAIL ONLY)
# =============================================================================
def try_okta_username_step(page, log_callback) -> bool:
    """
    If on Okta sign-in page, fill username/email and click Next/Submit.
    Email only; does NOT handle password/MFA.
    """
    try:
        url = (page.url or "").lower()
        if "okta.com" not in url:
            return False

        username = (
            page.query_selector("#okta-signin-username")
            or page.query_selector("input[name='identifier']")
            or page.query_selector("input[name='username']")
            or page.query_selector("input[type='email']")
        )

        # Fallback: any visible text input
        if not username:
            for c in page.query_selector_all("input[type='text']"):
                try:
                    if c.is_visible():
                        username = c
                        break
                except Exception:
                    continue

        if username and username.is_visible():
            current_val = ""
            try:
                current_val = username.input_value() or ""
            except Exception:
                pass

            if CONFIG["CLIENT_EMAIL"] and CONFIG["CLIENT_EMAIL"].lower() not in current_val.lower():
                log_callback("[Okta] Username field detected. Filling email...")
                username.click()
                username.fill("")
                username.type(CONFIG["CLIENT_EMAIL"], delay=40)

            next_btn = (
                page.query_selector("#okta-signin-submit")
                or page.query_selector("input[type='submit']")
                or page.query_selector("button:has-text('Next')")
                or page.query_selector("button:has-text('Sign in')")
                or page.query_selector("button:has-text('Continue')")
            )
            if next_btn and next_btn.is_visible():
                log_callback("[Okta] Clicking Next/Submit...")
                next_btn.click()
                page.wait_for_timeout(1200)
                return True

        return False
    except Exception as e:
        log_callback(f"[Okta] Step failed: {e}")
        return False


# =============================================================================
# FINDoX EMAIL STEP (EMAIL ONLY)
# =============================================================================
def try_findox_email_step(page, log_callback) -> bool:
    """
    If on a Findox login-like page, fill email and click continue.
    Email only; does NOT handle password/MFA.
    """
    try:
        target = (
            page.query_selector("[data-cy='step1-email-input']")
            or page.query_selector("input[name='username']")
            or page.query_selector("input[type='email']")
        )
        if not target or not target.is_visible():
            return False

        current_val = ""
        try:
            current_val = target.input_value() or ""
        except Exception:
            pass

        if CONFIG["CLIENT_EMAIL"] and CONFIG["CLIENT_EMAIL"].lower() not in current_val.lower():
            log_callback("[Findox] Email field detected. Filling email...")
            target.click()
            target.fill("")
            target.type(CONFIG["CLIENT_EMAIL"], delay=60)

            # Nudge front-end validations
            page.wait_for_timeout(150)
            try:
                target.press("Space")
                page.wait_for_timeout(50)
                target.press("Backspace")
            except Exception:
                pass

            try:
                target.blur()
            except Exception:
                pass

            page.wait_for_timeout(600)

        btn = (
            page.query_selector("[data-cy='step1-next-button']")
            or page.query_selector("button:has-text('Continue')")
            or page.query_selector("button:has-text('Next')")
        )
        if btn and btn.is_visible():
            log_callback("[Findox] Clicking Continue/Next...")
            try:
                btn.click()
            except Exception:
                try:
                    btn.click(force=True)
                except Exception:
                    pass
            page.wait_for_timeout(1200)
            return True

        # fallback Enter
        try:
            target.press("Enter")
            page.wait_for_timeout(1200)
            return True
        except Exception:
            return False
    except Exception:
        return False


# =============================================================================
# BROWSER VALIDATION
# =============================================================================
def run_browser_validation(test_url, log_callback, status_callback):
    status_callback("Acquiring Browser...")

    context = get_or_create_browser(log_callback)
    if not context:
        status_callback("Browser Failed")
        return

    # Create a NEW TAB for each run
    page = context.new_page()
    try:
        page.bring_to_front()
    except Exception:
        pass

    status_callback("Tab Opened")
    log_callback("=" * 60)

    download_dir = _get_download_dir()
    download_status = {"success": False, "path": None, "name": None}

    def on_download(download):
        try:
            log_callback(f"\n[+] DOWNLOAD STARTED: {download.suggested_filename}")
            f_path = download_dir / download.suggested_filename
            download.save_as(str(f_path))
            download_status["success"] = True
            download_status["path"] = str(f_path)
            download_status["name"] = download.suggested_filename
            log_callback(f"[+] File Saved Successfully: {f_path}")
        except Exception as e:
            log_callback(f"[!] Download save failed: {e}")

    page.on("download", on_download)

    # Session-aware behavior:
    # If we already have cookies, try download-only first (skip login automation initially).
    session_likely_exists = has_session_cookies(context, log_callback)

    def goto_download():
        try:
            page.goto(test_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log_callback(f"[!] Navigation error (may still continue): {e}")

    log_callback(f"Navigating to: {test_url}")
    goto_download()

    # Heuristic URL checks
    login_indicators = ("login", "signin", "auth", "logon", "okta.com", "microsoftonline.com")
    def on_auth_page() -> bool:
        u = (page.url or "").lower()
        return any(k in u for k in login_indicators)

    # If cookies exist, give it a short window to download without any login automation.
    if session_likely_exists:
        status_callback("Session Detected - Waiting for Download...")
        for _ in range(8):  # ~8 seconds
            if download_status["success"]:
                break
            page.wait_for_timeout(1000)

        # If no download, retry navigation once (common: first nav lands on dashboard)
        if not download_status["success"] and not on_auth_page():
            log_callback("[Session] No download yet; re-triggering download URL once...")
            goto_download()
            for _ in range(8):
                if download_status["success"]:
                    break
                page.wait_for_timeout(1000)

    # If still no download, fall back to login-aware loop.
    if not download_status["success"]:
        status_callback("Waiting (Auth/Download)...")

        for i in range(120):  # up to ~2 minutes
            if download_status["success"]:
                break

            # If we are on any auth page, attempt email-only helper steps
            if on_auth_page():
                acted_findox = try_findox_email_step(page, log_callback)
                acted_okta = try_okta_username_step(page, log_callback)

                # If we acted, give redirects time
                if acted_findox or acted_okta:
                    page.wait_for_timeout(1500)

            # If not on auth page, but still no download, re-trigger periodically
            if not on_auth_page() and i in (10, 25, 45):
                log_callback("[Info] Session may be active but download didn’t trigger; re-triggering download URL...")
                goto_download()

            page.wait_for_timeout(1000)

    # Final outcome
    if download_status["success"]:
        status_callback("SUCCESS!")
        messagebox.showinfo(
            "Success",
            f"File Downloaded:\n{download_status['name']}\n\nSaved to:\n{download_status['path']}"
        )
    else:
        status_callback("Inconclusive")
        log_callback("Timed out waiting for download.")
        messagebox.showwarning(
            "Inconclusive",
            "Timed out waiting for download.\n\n"
            "Common causes:\n"
            "- SSO not completed in the browser\n"
            "- Session invalidated by policy\n"
            "- URL not a direct download link\n"
            "- IT policy blocked automation or download\n"
        )

    # Close TAB only; keep browser context alive for session reuse
    try:
        page.close()
        status_callback("Tab Closed (Session Alive)")
    except Exception:
        pass


# =============================================================================
# EMAIL VALIDATION (Microsoft Graph App-Only)
# =============================================================================
def run_email_validation(password, log_callback, status_callback, code_callback):
    import re

    import msal
    import requests

    status_callback("Authenticating (App-Only)...")
    log_callback("=" * 60)
    log_callback(f"Target Inbox: {CONFIG['TARGET_MAILBOX']}")

    try:
        if not CONFIG["MS_CLIENT_ID"] or not CONFIG["MS_TENANT_ID"] or not CONFIG["MS_CLIENT_SECRET_VALUE"]:
            raise ValueError("Missing Microsoft Graph credentials in CONFIG (MS_CLIENT_ID / MS_TENANT_ID / MS_CLIENT_SECRET_VALUE).")

        app = msal.ConfidentialClientApplication(
            CONFIG["MS_CLIENT_ID"],
            authority=f"https://login.microsoftonline.com/{CONFIG['MS_TENANT_ID']}",
            client_credential=CONFIG["MS_CLIENT_SECRET_VALUE"],
        )

        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" not in result:
            status_callback("Auth Failed")
            log_callback(f"Token Error: {result.get('error')} - {result.get('error_description')}")
            return

        log_callback("Auth Success! Accessing mailbox...")
        headers = {"Authorization": f"Bearer {result['access_token']}"}

        endpoint = f"https://graph.microsoft.com/v1.0/users/{CONFIG['TARGET_MAILBOX']}/messages?$top=1&$select=subject,from,body"
        resp = requests.get(endpoint, headers=headers, timeout=30)

        if resp.status_code != 200:
            status_callback("API Error")
            log_callback(f"API Error {resp.status_code}: {resp.text[:500]}")
            return

        data = resp.json()
        if not data.get("value"):
            status_callback("Empty Inbox")
            log_callback("Mailbox empty.")
            return

        email = data["value"][0]
        subject = email.get("subject")
        body_content = (email.get("body") or {}).get("content", "")

        log_callback(f"Subject: {subject}")

        # Prefer direct findox download=true link if present
        match_perfect = re.search(
            r'href=[\"\'](https?://[^\"\']*findox\.com[^\"\']*download=true[^\"\']*)[\"\']',
            body_content,
            re.IGNORECASE,
        )

        found_link = None
        if match_perfect:
            found_link = match_perfect.group(1)
            log_callback("[+] MATCH: Found direct findox download=true link.")
        else:
            # fallback: something next to "(Web)"
            match_web_label = re.search(
                r"href=[\"']([^\"']+)[\"'].{1,300}?\(Web\)",
                body_content,
                re.IGNORECASE | re.DOTALL,
            )
            if match_web_label:
                found_link = match_web_label.group(1)
                log_callback("[+] MATCH: Found link next to '(Web)' label.")

        if found_link:
            found_link = (
                found_link.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
            )
            log_callback(f"URL: {found_link}")
            code_callback(None, None, subject, found_link)
        else:
            log_callback("[!] NO DOWNLOAD LINK FOUND IN LAST EMAIL.")
            log_callback("Tip: ensure forwarded email includes the (Web) link HTML.")

        status_callback("Email Read!")

    except Exception as e:
        log_callback(f"Connection Error: {e}")
        status_callback("Connection Error")


# =============================================================================
# GUI APP
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

        ttk.Label(main, text="Milestone 1: Validation Spike", font=("Segoe UI", 14, "bold")).pack(pady=5)

        # BROWSER
        b_frame = ttk.LabelFrame(main, text="1) Browser & Download (Persistent Session)", padding=10)
        b_frame.pack(fill=tk.X, pady=5)

        ttk.Label(b_frame, text="Paste Download URL (from Email):").pack(anchor=tk.W)
        self.url_var = tk.StringVar()
        ttk.Entry(b_frame, textvariable=self.url_var, width=70).pack(fill=tk.X, pady=5)

        self.btn_browser = ttk.Button(b_frame, text="Launch Browser + Download Test", command=self._run_browser)
        self.btn_browser.pack(anchor=tk.W, pady=5)

        ttk.Label(
            b_frame,
            text="Note: This tool will reuse cookies if present (persistent profile). "
                 "It can auto-fill email/username fields on Findox/Okta, but will not automate passwords.",
            wraplength=680
        ).pack(anchor=tk.W, pady=5)

        # EMAIL
        e_frame = ttk.LabelFrame(main, text="2) Shared Mailbox Access (Microsoft Graph)", padding=10)
        e_frame.pack(fill=tk.X, pady=10)

        ttk.Label(e_frame, text=f"Scanning: {CONFIG['TARGET_MAILBOX']}").pack(anchor=tk.W)
        self.btn_email = ttk.Button(e_frame, text="Scan Mailbox (Last Email)", command=self._run_email)
        self.btn_email.pack(anchor=tk.W, pady=5)

        # OUTPUT
        self.status = tk.StringVar(value="Ready")
        ttk.Label(main, textvariable=self.status, foreground="blue", font=("Segoe UI", 10)).pack()

        self.code_lbl = ttk.Label(main, text="", foreground="red", font=("Consolas", 12))
        self.code_lbl.pack()

        self.log = scrolledtext.ScrolledText(main, height=14, font=("Consolas", 9))
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

        threading.Thread(target=_worker, daemon=True).start()

    def _run_email(self):
        self.btn_email.config(state=tk.DISABLED)

        def _worker():
            try:
                run_email_validation("", self._log, self._status_upd, self._code_upd)
            finally:
                self.root.after(0, lambda: self.btn_email.config(state=tk.NORMAL))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_close(self):
        global GLOBAL_PLAYWRIGHT, GLOBAL_BROWSER_CONTEXT
        try:
            if GLOBAL_BROWSER_CONTEXT:
                GLOBAL_BROWSER_CONTEXT.close()
            if GLOBAL_PLAYWRIGHT:
                GLOBAL_PLAYWRIGHT.stop()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
