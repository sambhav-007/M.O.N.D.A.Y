# M.O.N.D.A.Y. — Google Contacts OAuth2 Integration Setup

This guide walks you through authenticating your Google Account to automatically sync live contacts with **`M.O.N.D.A.Y`**.

---

## 1. Direct Answers to Architecture Questions

### Q1: Do I need to create a Google Cloud Project & Client ID?
**Yes.** Because Google gates user contacts behind OAuth2 privacy protection, Google requires a `credentials.json` file generated from Google Cloud Console.

### Q2: Will a browser consent screen pop up asking me to log in and approve access?
**Yes.** On the first run, `fetch_google_people_api_contacts()` invokes Google's `InstalledAppFlow`, opening a browser tab to `https://accounts.google.com/o/oauth2/auth` for 1-click approval.

### Q3: Where and how is the auth token stored?
The resulting refresh token is saved securely at:
`c:\Users\Siddhant\Desktop\PROJECT_MONDAY\M.O.N.D.A.Y\data\google_token.json`

---

## 2. Setup Instructions (5 Minutes)

1. **Go to Google Cloud Console**:
   Open [https://console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)

2. **Enable Google People API**:
   - Navigate to **Library** $\rightarrow$ Search for **Google People API** $\rightarrow$ Click **Enable**.

3. **Create OAuth Client ID**:
   - Go to **Credentials** $\rightarrow$ Click **Create Credentials** $\rightarrow$ Select **OAuth client ID**.
   - Application type: **Desktop App**.
   - Name: `M.O.N.D.A.Y. Desktop Assistant`.
   - Click **Create**.

4. **Download `credentials.json`**:
   - Click **Download JSON**.
   - Save the file to:
     `c:\Users\Siddhant\Desktop\PROJECT_MONDAY\M.O.N.D.A.Y\data\credentials.json`

5. **Authenticate**:
   - Run any email command in M.O.N.D.A.Y. (`draft email to ...`).
   - Your web browser will open automatically asking you to log in to your Google Account.
   - Once approved, `data/google_token.json` is saved and all contacts sync automatically!
