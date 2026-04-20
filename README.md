# Shop Manager Backend

This backend provides a Python REST API for the Shop Manager Flutter app.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
cd backend
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## Deployment on Render

1. Push this backend code to a Git repository (e.g., GitHub).

2. Create a new Web Service on Render:
   - Connect your Git repository.
   - Set the runtime to Python 3.
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`

3. Deploy! The API will be available at the URL provided by Render.

## API Endpoints

- `GET /products`
- `POST /products`
- `PUT /products/{product_id}`
- `GET /sales`
- `POST /sales`
- `GET /reports/daily?days=7`

## Notes

- The backend stores data in `backend/shop_manager.db`.
- Use the Flutter app with `USE_BACKEND=true` and `BACKEND_URL=http://10.0.2.2:8000` when running on Android emulator.
