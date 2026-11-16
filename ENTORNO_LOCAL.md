# Local Python Environment

Run these commands in PowerShell from the repository root.
Use a virtual environment so that the server and tests share the same Python interpreter.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe server.py
```

If the `py` launcher cannot locate Python, use the full path to the installed
interpreter to create the environment. Activating the environment is unnecessary:
the commands above explicitly target its interpreter.

Open `http://127.0.0.1:5173` and keep the server terminal open.
CI scripts prefer `.venv`. The suite uses `pytest`: `unittest` does not collect
every standalone test function. Exploratory scripts in `scratch/` and dependencies
downloaded into `tmp` are not part of the test suite.

When a `.venv` is provisioned locally with Python 3.13 and locally cached wheels
(numpy, shapely, pytest, and transitive dependencies), network downloads are skipped.
To install the complete dependency set—including FastAPI, Uvicorn, and pyproj—use
`requirements-dev.txt` when network access is available.
