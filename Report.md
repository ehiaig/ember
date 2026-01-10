EvergreenPipeline – Milestone 1 Validation Report
1. Pass/Fail Summary

OVERALL STATUS: PASS

    Shared Mailbox Access: PASS

    -   Successfully authenticated via Microsoft Graph API (App-Only context).

    -   Successfully scanned target inbox and extracted download links via Regex.

    Browser Automation (Findox): PASS

    -   Successfully identified Vue.js input fields using Cypress selectors.

    -   Solved "Zero-Keystroke" requirement via automated event simulation.

    SSO & Session Persistence: PASS

    -   Persistent profile architecture successfully saves cookies to LOCALAPPDATA.

    File Download: PASS

    -   Solved "Redirect Amnesia" by implementing logic to re-trigger the download link after SSO completion.

2. Identified Constraints

    -   Human-Dependent Persistence: The bot cannot force a persistent session on its own. The user must manually check the "Remember Me" / "Keep me signed in" box on the SSO (Okta/Microsoft) screen during the initial setup run. If this is missed, the bot will require re-authentication.

    -   Vue.js Input Sensitivity: The Findox login page utilizes reactive Vue.js listeners that reject instant "pasting." The automation requires a specific "human-like" typing cadence (100ms delay) and synthetic key presses (Space + Backspace) to unlock the "Continue" button.

    -   Execution Speed: Due to the required typing delays and "Patience Loops" (waiting for buttons to enable), the login process takes approximately 5–8 seconds. This is acceptable but intentional to ensure stability.

3. Recommended Path Forward
    -   Implement Ember upload API: To automate file upload on the ember side

    -   Refactor for Production: Move the logic from the single-file main.py spike into a modular architecture (Services/Controllers).

    -   Enable Headless Mode: Switch the browser flag to headless=True so the automation runs invisibly in the background without interrupting the user.

    -   Implement Polling Logic: Develop the main event loop to check the mailbox continuously (e.g., every 5 minutes) rather than manually triggering a scan.

    -   Storage Integration: Implement state tracking (SQLite) to ensure the same email is not processed twice.

4. Technical Note

    -   Profile Storage: Browser profiles are now stored in %LOCALAPPDATA%\EvergreenPipeline\edge_profile. This ensures authentication persists even if the executable file is moved or updated.