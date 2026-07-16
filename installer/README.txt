QRFileshare v1.7.1
© 2026 Marie Apellanes

Share Google Drive folders with QR codes.

First-time setup
----------------
1. Launch QRFileshare from the Start menu or desktop shortcut.
2. Click "Sign in with Google Drive" and use your normal Google account.
   No API keys or Google Cloud setup is required for end users.
3. Optional: edit .env in the install folder to set BASE_URL to your PC's
   network address (for phone QR scanning), e.g. http://192.168.1.10:5000

Data is stored in:
  data\       - share links database
  output\qr\  - generated QR images

Support
-------
Default share expiry can be changed in the app under Settings.

For the app developer (building the installer)
----------------------------------------------
Place credentials.json in the project folder before running build_installer.bat.
See credentials.json.example for the required format.
