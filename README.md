(# Mental Model Generator)

Minimal FastAPI app boilerplate.

Run locally (from project root):

1. Activate your virtual environment (Windows PowerShell):

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies (if needed):

   ```powershell
   pip install fastapi uvicorn
   ```

3. Run with Uvicorn:

   ```powershell
   uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

Or run directly:

```powershell
python main.py
```

Open http://127.0.0.1:8000 for the API root or http://127.0.0.1:8000/docs for Swagger UI.

If you get `WinError 10013`, try a different port (e.g. 8001):

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8001
```
