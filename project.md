Overall projetct idea:
A desktop agent that automate ingestion of document from a specified microsoft outlook email.
It reads the content of the email, to extract the associated downlaod link and Issuer info, visit the linl to autodownload the file(if there's an active session), then upload the file to ember.

Note email body contains sample data:
- Issuer: E.g AcmeCorp
- Download links: e.g 
## Milestone 1
### Validation Spike

Validate key technical assumptions before full development in a representative enterprise environment.

1. Can we automate the managed browser without IT blocks?
2. Can we programmatically access the internal mailbox?
[Milestone Completion: A file linked in a FinDox email is successfully saved locally by a managed browser, with no user keystrokes, once the user has completed initial authentication through its security provider]

### Deliverables
1. Browser Automation Validation
- Launch managed browser (Edge / Chrome channel)
- Navigate to FinDox download URL
- Support interactive Okta SSO login
- Detect Microsoft / AD re-auth redirects and retry flow
- Capture automatic file download and save locally
2. Email Ingestion Validation
- Simple connectivity test to designated Microsoft 365 ingestion mailbox (e.g. SAMCO@emberapp.io)
- Verify permissions are not blocked by firewall or policy.

3. Outcome 
A file linked in a FinDox email is successfully saved locally by a managed browser, with no user keystrokes, once the user has completed initial authentication through its security provider

4. Report
- Clear pass/fail summary
- Identified constraints and recommended path forward


Steps
1. Email Connectivity(Microsoft Graph/IMAP)
I need a Python script to validate email connectivity for a 'Feasibility Spike'.

The Goal: Connect to a Microsoft 365 business mailbox, find the latest email from a specific sender (e.g., 'notifications@findox.com'), and print the body text.

Constraints:

    I have the email address and password.

    Attempt to use imaplib first because it is simplest.

    If IMAP is blocked by modern security, provide a fallback function using msal (Microsoft Authentication Library) using the 'Public Client' flow (Device Code or Interactive) to get a Graph API token.

    The script should be a standalone file.

    Include comments explaining how I can switch between IMAP and Graph logic."



https://findox.com/deal/123/download

I need to build a "Validation Spike" desktop application using Python to verify automation feasibility in a strict enterprise environment.

The Context: I am developing on a Mac, but the end-user (Client) is on a corporate Windows machine with Intune/SSO policies. I need to send him a compiled .exe that he can run to prove the automation works on his secure device.

The App Requirements: Create a simple Tkinter GUI with two buttons:

Button 1: "Validate Browser Download"

    Library: Use playwright (sync API).

    Browser: Launch Chromium (mimicking Edge) in headless=False (visible) mode.

    User-Agent: Force the User-Agent to match a standard Windows 10/11 Edge browser (so it doesn't look like a bot or a Mac).

    Session Logic (Crucial):

        Check for a local file browser_state.json.

        If found: Load cookies and navigate to https://findox.com (use a placeholder URL I can swap).

        If NOT found: Navigate to the Login URL. Pause/Wait for the user to manually perform the SSO/Intune login.

        Add a "Save Session" button or listen for a specific URL change to trigger the save of browser_state.json.

    Download Test: Once logged in, navigate to a test PDF URL and verify a download can occur without error.

Button 2: "Validate Email Connection"

    Library: Use msal (Microsoft Authentication Library).

    Auth Flow: Use the "Device Code Flow" (Public Client).

        Why: This prints a code on the screen (e.g., "A1B2"), telling the user "Go to microsoft.com/devicelogin and enter this code."

        This bypasses the need for client secrets and works well with MFA/Intune.

    Action: Once authenticated, connect to Microsoft Graph API, fetch the Subject Line of the most recent email, and display it in the GUI to prove success.

Deliverable Format:

    Provide the complete main.py code.

    Provide a requirements.txt.

    Crucial: Provide the exact pyinstaller command to compile this into a single standalone .exe file that includes the Playwright browsers (or instructions on how the client ensures browsers are installed).

Milestone Completion: A file linked in a FinDox email is successfully saved locally by a managed browser, with no user keystrokes, once the user has completed initial authentication through its security provider