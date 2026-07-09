QRFileshare v1.0.0
© 2026 Marie Apellanes

Share Google Drive folders with expiring QR codes.

First-time setup
----------------
1. Launch QRFileshare from the Start menu or desktop shortcut.
2. Optional: edit .env in the install folder to set BASE_URL to your PC's
   network address (for phone QR scanning), e.g. http://192.168.1.10:5000
3. For Google Drive sync, add credentials.json from Google Cloud Console
   to the install folder (see .env.example).

Data is stored in:
  data\       - share links database
  output\qr\  - generated QR images

Support
-------
Default share expiry can be changed in the app under Settings.
