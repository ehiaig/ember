"""
Validation Spike Desktop Application
=====================================
A Tkinter GUI app to validate:
1. Browser automation with Playwright (SSO session handling + download)
2. Email connectivity via Microsoft Graph API (Device Code Flow)

Developed for cross-compilation to Windows .exe for enterprise validation.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os
import json
from pathlib import Path

# =============================================================================
# CONFIGURATION - MODIFY THESE VALUES AS NEEDED
# =============================================================================
CONFIG = {
    # Browser Automation URLs
    "BASE_URL": "https://findox.com",
    "LOGIN_URL": "https://findox.com/login",
    "TEST_DOWNLOAD_URL": "https://findox.com/deal/123/download",
    
    # Session state file
    "STATE_FILE": "browser_state.json",
    
    # Download directory (relative to script location)
    "DOWNLOAD_DIR": "downloads",
    
    # Microsoft Graph API settings for Device Code Flow
    # Using Microsoft's well-known public client ID for testing
    # Replace with your own registered app's client ID for production
    "MS_CLIENT_ID": "YOUR_CLIENT_ID_HERE",  # Register at Azure Portal
    "MS_TENANT_ID": "common",  # Use "common" for multi-tenant, or specific tenant ID
    "MS_SCOPES": ["Mail.Read", "User.Read"],
    
    # Windows Edge User-Agent (Windows 11 + Edge latest)
    "USER_AGENT": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    ),
}


# =============================================================================
# BROWSER VALIDATION (Playwright)
# =============================================================================
def run_browser_validation(log_callback, status_callback, save_session_callback):
    """
    Validates browser automation:
    1. Checks for existing session state
    2. Launches Chromium with Edge-like user agent
    3. Handles SSO login if needed
    4. Tests file download capability
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_callback("ERROR: Playwright not installed. Run: pip install playwright")
        log_callback("Then run: playwright install chromium")
        status_callback("Failed - Playwright not installed")
        return

    status_callback("Starting browser validation...")
    log_callback("=" * 50)
    log_callback("BROWSER VALIDATION STARTED")
    log_callback("=" * 50)
    
    # Ensure download directory exists
    download_dir = Path(CONFIG["DOWNLOAD_DIR"]).absolute()
    download_dir.mkdir(exist_ok=True)
    log_callback(f"Download directory: {download_dir}")
    
    state_file = Path(CONFIG["STATE_FILE"])
    has_existing_session = state_file.exists()
    
    if has_existing_session:
        log_callback(f"Found existing session: {state_file}")
    else:
        log_callback("No existing session found. Manual login will be required.")
    
    with sync_playwright() as p:
        # Browser launch options
        browser = p.chromium.launch(
            headless=False,  # Visible browser for user interaction
            channel="msedge" if os.name == 'nt' else None,  # Use Edge on Windows if available
        )
        
        # Context options with Edge-like configuration
        context_options = {
            "user_agent": CONFIG["USER_AGENT"],
            "viewport": {"width": 1280, "height": 720},
            "accept_downloads": True,
        }
        
        # Load existing session if available
        if has_existing_session:
            try:
                log_callback("Loading saved session state...")
                context = browser.new_context(
                    storage_state=str(state_file),
                    **context_options
                )
                log_callback("Session state loaded successfully.")
            except Exception as e:
                log_callback(f"Failed to load session: {e}")
                log_callback("Creating fresh session...")
                context = browser.new_context(**context_options)
        else:
            context = browser.new_context(**context_options)
        
        page = context.new_page()
        
        # Set up download handling
        download_success = {"value": False, "file": None}
        
        def handle_download(download):
            log_callback(f"Download started: {download.suggested_filename}")
            save_path = download_dir / download.suggested_filename
            download.save_as(str(save_path))
            log_callback(f"Download saved to: {save_path}")
            download_success["value"] = True
            download_success["file"] = str(save_path)
        
        page.on("download", handle_download)
        
        try:
            if has_existing_session:
                # Try navigating directly to the main URL
                log_callback(f"Navigating to: {CONFIG['BASE_URL']}")
                page.goto(CONFIG["BASE_URL"], wait_until="networkidle", timeout=30000)
                
                # Check if we're redirected to login
                if "login" in page.url.lower() or "auth" in page.url.lower():
                    log_callback("Session expired. Manual login required.")
                    has_existing_session = False
            
            if not has_existing_session:
                # Navigate to login page
                log_callback(f"Navigating to login: {CONFIG['LOGIN_URL']}")
                page.goto(CONFIG["LOGIN_URL"], wait_until="networkidle", timeout=30000)
                
                log_callback("")
                log_callback("=" * 50)
                log_callback("MANUAL LOGIN REQUIRED")
                log_callback("Please complete the SSO/Intune login in the browser.")
                log_callback("Click 'Save Session' button when done.")
                log_callback("=" * 50)
                log_callback("")
                
                status_callback("Waiting for manual login...")
                
                # Enable the save session button
                save_session_callback(True, context, state_file, log_callback)
                
                # Wait for user to complete login (browser stays open)
                # The save_session button will handle saving the state
                log_callback("Browser is open. Complete login and click 'Save Session'.")
                
                # Keep browser open - user will close it or save session
                try:
                    page.wait_for_timeout(300000)  # 5 minute timeout
                except:
                    pass
                
                return
            
            # Test download functionality
            log_callback("")
            log_callback("Testing download capability...")
            log_callback(f"Navigating to: {CONFIG['TEST_DOWNLOAD_URL']}")
            
            page.goto(CONFIG["TEST_DOWNLOAD_URL"], wait_until="networkidle", timeout=30000)
            
            # Wait a bit for download to trigger
            page.wait_for_timeout(5000)
            
            if download_success["value"]:
                log_callback("")
                log_callback("=" * 50)
                log_callback("SUCCESS! Download validation passed.")
                log_callback(f"File saved: {download_success['file']}")
                log_callback("=" * 50)
                status_callback("SUCCESS - Download validated!")
            else:
                log_callback("")
                log_callback("Download did not auto-trigger.")
                log_callback("You may need to click a download button on the page.")
                log_callback("Browser will remain open for 30 seconds...")
                status_callback("Waiting for manual download...")
                
                page.wait_for_timeout(30000)
                
                if download_success["value"]:
                    log_callback("SUCCESS! Manual download completed.")
                    status_callback("SUCCESS - Download validated!")
                else:
                    log_callback("No download detected. Test inconclusive.")
                    status_callback("Inconclusive - No download detected")
            
        except Exception as e:
            log_callback(f"ERROR: {str(e)}")
            status_callback(f"Failed: {str(e)[:50]}")
        finally:
            log_callback("Closing browser...")
            context.close()
            browser.close()
            log_callback("Browser closed.")


# =============================================================================
# EMAIL VALIDATION (MSAL Device Code Flow)
# =============================================================================
def run_email_validation(log_callback, status_callback, code_callback):
    """
    Validates email connectivity using Microsoft Graph API:
    1. Initiates Device Code Flow authentication
    2. User authenticates at microsoft.com/devicelogin
    3. Fetches the most recent email subject to prove access
    """
    try:
        import msal
        import requests
    except ImportError as e:
        log_callback(f"ERROR: Required library not installed: {e}")
        log_callback("Run: pip install msal requests")
        status_callback("Failed - Dependencies missing")
        return
    
    status_callback("Starting email validation...")
    log_callback("=" * 50)
    log_callback("EMAIL VALIDATION STARTED")
    log_callback("=" * 50)
    
    if CONFIG["MS_CLIENT_ID"] == "YOUR_CLIENT_ID_HERE":
        log_callback("")
        log_callback("WARNING: You need to register an Azure AD app!")
        log_callback("1. Go to: https://portal.azure.com")
        log_callback("2. Navigate to: Azure Active Directory > App Registrations")
        log_callback("3. Create a new registration (Public client/native)")
        log_callback("4. Add 'Mobile and desktop applications' platform")
        log_callback("5. Enable 'Allow public client flows'")
        log_callback("6. Add API permissions: Microsoft Graph > Mail.Read, User.Read")
        log_callback("7. Copy the Application (client) ID to CONFIG['MS_CLIENT_ID']")
        log_callback("")
        log_callback("For testing, you can use Microsoft's public test client:")
        log_callback("Client ID: 04b07795-8ddb-461a-bbee-02f9e1bf7b46 (Azure CLI)")
        status_callback("Configuration needed - See log")
        return
    
    # Create MSAL Public Client Application
    app = msal.PublicClientApplication(
        client_id=CONFIG["MS_CLIENT_ID"],
        authority=f"https://login.microsoftonline.com/{CONFIG['MS_TENANT_ID']}"
    )
    
    # Initiate Device Code Flow
    log_callback("Initiating Device Code Flow...")
    
    flow = app.initiate_device_flow(scopes=CONFIG["MS_SCOPES"])
    
    if "user_code" not in flow:
        log_callback(f"ERROR: Failed to create device flow: {flow.get('error_description', 'Unknown error')}")
        status_callback("Failed - Device flow error")
        return
    
    # Display the device code to user
    user_code = flow["user_code"]
    verification_uri = flow.get("verification_uri", "https://microsoft.com/devicelogin")
    
    log_callback("")
    log_callback("=" * 50)
    log_callback("AUTHENTICATION REQUIRED")
    log_callback("=" * 50)
    log_callback(f"1. Open your browser to: {verification_uri}")
    log_callback(f"2. Enter this code: {user_code}")
    log_callback("3. Sign in with your Microsoft account")
    log_callback("=" * 50)
    log_callback("")
    
    # Update the code display in GUI
    code_callback(user_code, verification_uri)
    
    status_callback(f"Enter code: {user_code} at {verification_uri}")
    
    # Wait for user to authenticate (blocking call)
    log_callback("Waiting for authentication...")
    
    result = app.acquire_token_by_device_flow(flow)
    
    if "access_token" not in result:
        error = result.get("error_description", result.get("error", "Unknown error"))
        log_callback(f"ERROR: Authentication failed: {error}")
        status_callback("Failed - Authentication error")
        return
    
    log_callback("Authentication successful!")
    access_token = result["access_token"]
    
    # Fetch user info to confirm identity
    log_callback("Fetching user information...")
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    user_response = requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers=headers
    )
    
    if user_response.status_code == 200:
        user_data = user_response.json()
        log_callback(f"Authenticated as: {user_data.get('displayName', 'Unknown')}")
        log_callback(f"Email: {user_data.get('mail', user_data.get('userPrincipalName', 'Unknown'))}")
    else:
        log_callback(f"Warning: Could not fetch user info: {user_response.status_code}")
    
    # Fetch the most recent email
    log_callback("")
    log_callback("Fetching most recent email...")
    
    mail_response = requests.get(
        "https://graph.microsoft.com/v1.0/me/messages?$top=1&$select=subject,from,receivedDateTime",
        headers=headers
    )
    
    if mail_response.status_code == 200:
        messages = mail_response.json().get("value", [])
        
        if messages:
            email = messages[0]
            subject = email.get("subject", "(No subject)")
            from_email = email.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
            received = email.get("receivedDateTime", "Unknown")
            
            log_callback("")
            log_callback("=" * 50)
            log_callback("SUCCESS! Email access validated.")
            log_callback("=" * 50)
            log_callback(f"Most recent email:")
            log_callback(f"  Subject: {subject}")
            log_callback(f"  From: {from_email}")
            log_callback(f"  Received: {received}")
            log_callback("=" * 50)
            
            status_callback("SUCCESS - Email access validated!")
            code_callback(None, None, subject)  # Display subject in GUI
        else:
            log_callback("No emails found in mailbox (but access works!)")
            status_callback("SUCCESS - Access works (no emails)")
    else:
        log_callback(f"ERROR: Failed to fetch emails: {mail_response.status_code}")
        log_callback(f"Response: {mail_response.text}")
        status_callback("Failed - Could not fetch emails")


# =============================================================================
# MAIN GUI APPLICATION
# =============================================================================
class ValidationSpikeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Validation Spike - Enterprise Automation Test")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        
        # Store context for save session
        self.browser_context = None
        self.state_file = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text="Validation Spike - Enterprise Automation Test",
            font=("Helvetica", 16, "bold")
        )
        title_label.pack(pady=(0, 10))
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        # Browser validation button
        self.browser_btn = ttk.Button(
            button_frame,
            text="1. Validate Browser Download",
            command=self._start_browser_validation
        )
        self.browser_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        # Save session button (disabled by default)
        self.save_session_btn = ttk.Button(
            button_frame,
            text="Save Session",
            command=self._save_session,
            state=tk.DISABLED
        )
        self.save_session_btn.pack(side=tk.LEFT, padx=5)
        
        # Email validation button
        self.email_btn = ttk.Button(
            button_frame,
            text="2. Validate Email Connection",
            command=self._start_email_validation
        )
        self.email_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        # Status frame
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(
            status_frame, 
            textvariable=self.status_var,
            font=("Helvetica", 10, "bold")
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Device code display frame (for email auth)
        self.code_frame = ttk.LabelFrame(main_frame, text="Authentication Code", padding="10")
        self.code_frame.pack(fill=tk.X, pady=5)
        self.code_frame.pack_forget()  # Hidden by default
        
        self.code_var = tk.StringVar(value="")
        self.code_label = ttk.Label(
            self.code_frame,
            textvariable=self.code_var,
            font=("Courier", 24, "bold"),
            foreground="blue"
        )
        self.code_label.pack()
        
        self.code_url_var = tk.StringVar(value="")
        self.code_url_label = ttk.Label(
            self.code_frame,
            textvariable=self.code_url_var,
            font=("Helvetica", 10)
        )
        self.code_url_label.pack()
        
        # Email result frame
        self.email_result_frame = ttk.LabelFrame(main_frame, text="Latest Email Subject", padding="10")
        self.email_result_frame.pack(fill=tk.X, pady=5)
        self.email_result_frame.pack_forget()  # Hidden by default
        
        self.email_subject_var = tk.StringVar(value="")
        self.email_subject_label = ttk.Label(
            self.email_result_frame,
            textvariable=self.email_subject_var,
            font=("Helvetica", 12),
            wraplength=700
        )
        self.email_subject_label.pack()
        
        # Log area
        log_frame = ttk.LabelFrame(main_frame, text="Log Output", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Courier", 10),
            height=15
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Clear log button
        clear_btn = ttk.Button(
            main_frame,
            text="Clear Log",
            command=self._clear_log
        )
        clear_btn.pack(pady=5)
    
    def _log(self, message):
        """Thread-safe logging to the text widget."""
        def _update():
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
        self.root.after(0, _update)
    
    def _update_status(self, status):
        """Thread-safe status update."""
        def _update():
            self.status_var.set(status)
        self.root.after(0, _update)
    
    def _clear_log(self):
        """Clear the log text widget."""
        self.log_text.delete(1.0, tk.END)
    
    def _enable_save_session(self, enable, context=None, state_file=None, log_callback=None):
        """Enable/disable the save session button and store context."""
        def _update():
            if enable:
                self.browser_context = context
                self.state_file = state_file
                self.log_callback = log_callback
                self.save_session_btn.config(state=tk.NORMAL)
            else:
                self.save_session_btn.config(state=tk.DISABLED)
        self.root.after(0, _update)
    
    def _save_session(self):
        """Save the browser session state."""
        if self.browser_context and self.state_file:
            try:
                self.browser_context.storage_state(path=str(self.state_file))
                self._log(f"Session saved to: {self.state_file}")
                self._log("You can close the browser now.")
                self._update_status("Session saved!")
                messagebox.showinfo("Success", f"Session saved to {self.state_file}")
            except Exception as e:
                self._log(f"Failed to save session: {e}")
                messagebox.showerror("Error", f"Failed to save session: {e}")
        else:
            messagebox.showwarning("Warning", "No active browser session to save.")
    
    def _update_device_code(self, code=None, url=None, email_subject=None):
        """Update the device code display."""
        def _update():
            if email_subject:
                # Show email result
                self.code_frame.pack_forget()
                self.email_result_frame.pack(fill=tk.X, pady=5, before=self.log_text.master)
                self.email_subject_var.set(email_subject)
            elif code:
                # Show device code
                self.email_result_frame.pack_forget()
                self.code_frame.pack(fill=tk.X, pady=5, before=self.log_text.master)
                self.code_var.set(code)
                self.code_url_var.set(f"Go to: {url}")
            else:
                # Hide both
                self.code_frame.pack_forget()
                self.email_result_frame.pack_forget()
        self.root.after(0, _update)
    
    def _start_browser_validation(self):
        """Start browser validation in a separate thread."""
        self.browser_btn.config(state=tk.DISABLED)
        self.email_btn.config(state=tk.DISABLED)
        self._update_device_code()  # Hide code display
        
        def run():
            try:
                run_browser_validation(
                    self._log,
                    self._update_status,
                    self._enable_save_session
                )
            finally:
                def _enable():
                    self.browser_btn.config(state=tk.NORMAL)
                    self.email_btn.config(state=tk.NORMAL)
                self.root.after(0, _enable)
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
    
    def _start_email_validation(self):
        """Start email validation in a separate thread."""
        self.browser_btn.config(state=tk.DISABLED)
        self.email_btn.config(state=tk.DISABLED)
        
        def run():
            try:
                run_email_validation(
                    self._log,
                    self._update_status,
                    self._update_device_code
                )
            finally:
                def _enable():
                    self.browser_btn.config(state=tk.NORMAL)
                    self.email_btn.config(state=tk.NORMAL)
                self.root.after(0, _enable)
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()


# =============================================================================
# ENTRY POINT
# =============================================================================
def main():
    root = tk.Tk()
    app = ValidationSpikeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
