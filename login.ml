module: login
purpose: Reusable Playwright login helper for PM2020.

source_selectors:
  username: '#txtUserName'
  password: '#txtPassword'
  login_button: '#btnLogin'

flow:
  1. Load credentials from creds.json or PM2020_USERNAME / PM2020_PASSWORD.
  2. Go to https://pm2020.preferredparking.com:2020/Login.aspx.
  3. Fill username.
  4. Fill password.
  5. Click Login so the ASP.NET __doPostBack handler runs normally.
  6. Return the current page URL to the caller.

notes:
  - Do not hard-code real credentials in login.py.
  - Browser context should use ignore_https_errors=True for this backend URL.
  - Path defaults are anchored to this folder via Path(__file__).resolve().parent,
    so renaming the project folder should not break creds.json or storage_state.json.
