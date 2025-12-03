# Settings Configuration Guide

This Django project supports both **LOCAL DEVELOPMENT** and **PRODUCTION (PythonAnywhere)** environments with automatic configuration switching.

## How It Works

The `settings.py` file automatically detects the environment based on the `DEBUG` setting and configures:
- ✅ Database (SQLite for local, MySQL for production)
- ✅ Static files paths
- ✅ Media files paths
- ✅ Allowed hosts
- ✅ Security settings

---

## Local Development Setup

### 1. Copy Environment File
```bash
cp .env.example .env
```

### 2. Edit `.env` File
```bash
DEBUG=True
SECRET_KEY=your-local-secret-key
# Add your API keys for testing
```

### 3. Run Locally
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

**Access:** http://localhost:8000

### Local Configuration:
- **Database:** SQLite (`db.sqlite3`)
- **Static Files:** `./static/` and `./staticfiles/`
- **Media Files:** `./media/`
- **Allowed Hosts:** localhost, 127.0.0.1

---

## Production Setup (PythonAnywhere)

### 1. Set Environment Variables

On PythonAnywhere, you can set environment variables in two ways:

#### Option A: In WSGI file (`/var/www/abdul40_pythonanywhere_com_wsgi.py`)
```python
import os
os.environ['DEBUG'] = 'False'
os.environ['SECRET_KEY'] = 'your-production-secret-key'
os.environ['DB_PASSWORD'] = 'your-mysql-password'
# ... add other secrets
```

#### Option B: Or hardcode in settings.py (not recommended, use WSGI method)

### 2. Production Configuration
When `DEBUG=False`, the settings automatically use:
- **Database:** MySQL (`Abdul40$wacampaign`)
- **Static Files:** `/home/Abdul40/wa_campiagn_sender/staticfiles/`
- **Media Files:** `/home/Abdul40/wa_campiagn_sender/media/`
- **Allowed Hosts:** abdul40.pythonanywhere.com, wacampaignsender.com

### 3. Deploy on PythonAnywhere
```bash
cd ~/wa_campiagn_sender
git pull origin main
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
touch /var/www/abdul40_pythonanywhere_com_wsgi.py
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DEBUG` | Yes | `True` for local, `False` for production |
| `SECRET_KEY` | Yes | Django secret key |
| `DB_PASSWORD` | Production | MySQL database password |
| `BREVO_API_KEY` | Yes | Email service API key |
| `SOCIAL_AUTH_GOOGLE_OAUTH2_KEY` | Optional | Google OAuth client ID |
| `SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET` | Optional | Google OAuth secret |
| `PAYPAL_CLIENT_ID` | Optional | PayPal integration |
| `PAYPAL_CLIENT_SECRET` | Optional | PayPal secret |
| `RAZORPAY_KEY_ID` | Optional | Razorpay integration |
| `RAZORPAY_KEY_SECRET` | Optional | Razorpay secret |
| `WASENDER_API_TOKEN` | Yes | WhatsApp API token |
| `CLOUDINARY_URL` | Optional | Media uploads |
| `OPENAI_API_KEY` | Optional | AI features |

---

## Quick Check

To verify which environment is active, check the console output when Django starts:

```
🔧 Django Settings Loaded:
   DEBUG: True
   ALLOWED_HOSTS: ['localhost', '127.0.0.1', '[::1]']
   DATABASE ENGINE: django.db.backends.sqlite3
   STATIC_ROOT: /path/to/staticfiles
   MEDIA_ROOT: /path/to/media
```

---

## Troubleshooting

### Issue: "DisallowedHost" Error
**Solution:** Make sure your domain is in `ALLOWED_HOSTS` when `DEBUG=False`

### Issue: Static files not loading
**Solution:** Run `python manage.py collectstatic` on production

### Issue: Database connection error
**Solution:** Check `DB_PASSWORD` environment variable is set correctly

---

## Security Notes

⚠️ **IMPORTANT:**
- Never commit `.env` file or `settings.py` with secrets to GitHub
- Always use `DEBUG=False` in production
- Use strong `SECRET_KEY` in production
- Enable HTTPS and set `SECURE_SSL_REDIRECT=True` when using custom domain

---

## File Structure

```
wa_campiagn_sender/
├── wa_campiagn_sender/
│   └── settings.py          # Main settings (auto-switches)
├── .env.example             # Environment variable template
├── .env                     # Your local secrets (git-ignored)
└── SETTINGS_GUIDE.md        # This file
```

---

**Questions?** Contact: hi@wacampaignsender.com
