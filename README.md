# PM2020UpdateAllLots

Playwright automation scaffold for PM2020.

## Setup

```bash
cd PM2020UpdateAllLots
pip install -r requirements.txt
python -m playwright install chromium
```

Fill `creds.json`:

```json
{
  "username": "YOUR_USERNAME",
  "password": "YOUR_PASSWORD"
}
```

Or use environment variables:

```bash
export PM2020_USERNAME="YOUR_USERNAME"
export PM2020_PASSWORD="YOUR_PASSWORD"
```

## Run

From inside the project folder:

```bash
python main.py --keep-open
```

From the parent folder:

```bash
python -m PM2020UpdateAllLots.main --keep-open
```
