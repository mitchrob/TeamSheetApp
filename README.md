# TeamsheetApp

Minimal Flask app to upload a single teamsheet CSV row (same format as `GRFC_data.csv`) and show player appearance statistics.

Quick start (Windows / PowerShell):

1. Create and activate a virtual environment (optional but recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run the app:

```powershell
python app.py
```

4. Open `http://127.0.0.1:5000/` in your browser, paste one CSV row and upload. Then view `Player Appearances`.

Notes:
- The app appends the provided row to `GRFC_data.csv` in the project root.
- Appearance counts are computed from the CSV file by detecting the first numeric header column (player position columns).

## Deployment to PythonAnywhere

These are concise steps to deploy this app on PythonAnywhere.

1. Create a new web app on PythonAnywhere (choose 'Flask' and the correct Python version).
2. Upload your project files (all repository files) to your PythonAnywhere home directory (use the Files tab or git).
3. Create and activate a virtualenv on PythonAnywhere (match your Python version):

```bash
python3.8 -m venv ~/myenv
source ~/myenv/bin/activate
pip install -r /home/yourusername/TeamsheetApp/requirements.txt
```

4. In the PythonAnywhere Web tab, edit the WSGI configuration file to import your `app` object. Example WSGI snippet (replace `yourusername` and the path as needed):

```python
import sys
project_home = '/home/yourusername/TeamsheetApp'
if project_home not in sys.path:
	sys.path.insert(0, project_home)

from app import app as application
```

5. Configure static files (optional). In the Web tab, add a Static files mapping for `/static/` to your project's `static/` directory if you have static assets.

6. Set environment variables in the Web tab: `SECRET_KEY`, `ADMIN_USER`, and `ADMIN_PASS` (avoid using the defaults in production).

7. Reload the web app from the Web tab. Your app should be live at `yourusername.pythonanywhere.com`.

Notes:
- PythonAnywhere uses WSGI; you do not call `app.run()` in production — the WSGI file imports the `app` object.
- Ensure `GRFC_data.csv` is writable by the web app process (check file permissions in Files tab).
- If you prefer, keep `requirements.txt` updated with pinned versions to ensure reproducible installs.
