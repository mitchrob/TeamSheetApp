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

1.  **Pull changes**: On PythonAnywhere, navigate to your project and pull the latest changes:
    ```bash
    cd TeamsheetApp
    git pull
    ```

2.  **Update Dependencies**:
    ```bash
    source myenv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Update WSGI Configuration**:
    Edit your WSGI configuration file (in the Web tab) to point to the new application factory.

    **Old:**
    ```python
    from app import app as application
    ```

    **New:**
    ```python
    import sys
    import os

    # Add project directory to path
    path = '/home/yourusername/TeamsheetApp'
    if path not in sys.path:
        sys.path.insert(0, path)

    # Import the application factory
    from app import create_app
    application = create_app()
    ```

4.  **Reload**: Reload the web app from the Web tab.

Notes:
- The database `app.db` is in the project root. If you want to keep your existing data, make sure `app.db` is preserved (it is git-ignored by default).
- If you have trouble, check the Error Log in the Web tab.
