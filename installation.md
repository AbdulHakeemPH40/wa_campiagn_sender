# WA Campaign Sender - Installation Guide

python manage.py qcluster

https://console.upstash.com/redis/0ef67cf8-fe39-4819-a007-523cc22e1ae1?teamid=0

admin login
admin@wacampaignsender.com
winDOws@10



pip install Django>=5.2.2
pip install Pillow>=10.0.0
pip install "django-anymail[brevo]>=10.0"
pip install pdfkit>=1.0.0
pip install django-paypal>=2.0
pip install razorpay>=2.0.0
pip install "weasyprint<66"
pip install requests>=2.28.0
pip install mysqlclient>=2.1.0
pip install pytz>=2023.3
pip install social-auth-app-django>=5.2.0
pip install cryptography>=41.0.0
pip install qrcode>=7.4.2
pip install pandas>=2.0.0
pip install openpyxl>=3.1.0
pip install emoji>=2.8.0
pip install cloudinary>=1.36.0
pip install django-q2>=1.6.0
pip install redis>=7.0.1
pip install channels>=4.0.0
pip install daphne>=4.0.0

## Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Git
- Virtual environment (recommended)

---

## Installation Steps

### 1. Clone the Repository

```bash
git clone <repository-url>
cd wa_campiagn_sender_django
```

### 2. Create Virtual Environment

**Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Required packages will be installed:**
- Django 5.2.8
- Pillow (image processing)
- django-paypal (PayPal integration)
- razorpay (Razorpay payment gateway)
- social-auth-app-django (Google OAuth2)
- weasyprint (PDF generation)
- requests
- pytz

### 4. Configure Settings

**Development:** Use `settings.py` (already configured)

**Production:** Copy and configure `pythonanywhere_settings.py`

### 5. Run Migrations

```bash
python manage.py migrate
```

### 6. Create Superuser

```bash
python manage.py createsuperuser
```

### 7. Collect Static Files (Production Only)

```bash
python manage.py collectstatic
```

### 8. Run Development Server

**Local Development:**
```bash
python manage.py runserver
```

Visit: http://127.0.0.1:8000

### 9. Start Django-Q Worker (Required for Background Tasks)

**IMPORTANT:** Django-Q worker must be running for background campaign sending to work.

**Local Development:**
Open a **separate terminal** and run:
```bash
cd "c:\Users\Hakeem1\OneDrive\Desktop\WA Campaign Sender30-09-2025\WAC Sender\wa_campiagn_sender_django"
python manage.py qcluster
```

**Keep both terminals running:**
- Terminal 1: `python manage.py runserver` (Django server)
- Terminal 2: `python manage.py qcluster` (Background worker)

**PythonAnywhere Deployment:**
See "Django-Q Configuration on PythonAnywhere" section below.

---

## Configuration

### Email Settings (Brevo SMTP)
- Configured in `settings.py`
- SMTP: smtp-relay.brevo.com:587

### Payment Gateways

**PayPal:**
- Sandbox keys in development
- Live keys in production

**Razorpay:**
- Test keys: `rzp_test_*`
- Live keys: `rzp_live_*`

### Google OAuth2
- Configure in Google Cloud Console
- Add credentials to settings

---

## Deployment (PythonAnywhere)

### Basic Setup

1. Upload code to PythonAnywhere
2. Create virtual environment
3. Install dependencies: `pip install -r requirements.txt`
4. Configure `pythonanywhere_settings.py`
5. Run migrations
6. Configure WSGI file
7. Reload web app

### Django-Q Configuration on PythonAnywhere

**CRITICAL:** Django-Q worker is required for background campaign sending.

#### Option 1: Always-On Task (Recommended - Paid Accounts)

1. Go to **PythonAnywhere Dashboard** → **Tasks** tab
2. Click **"Create a new always-on task"**
3. **Command:**
   ```bash
   /home/Abdul40/.virtualenvs/YOUR_VENV_NAME/bin/python /home/Abdul40/wa_campiagn_sender_django/manage.py qcluster
   ```
4. **Working directory:** `/home/Abdul40/wa_campiagn_sender_django`
5. Click **Create**

**Replace `YOUR_VENV_NAME`** with your actual virtualenv name (e.g., `myenv`, `venv3.10`)

#### Option 2: Scheduled Task (Free Accounts Alternative)

If Always-On tasks not available:

1. Go to **Tasks** tab → **Scheduled tasks**
2. **Command:**
   ```bash
   cd /home/Abdul40/wa_campiagn_sender_django && /home/Abdul40/.virtualenvs/YOUR_VENV_NAME/bin/python manage.py qcluster --run-once
   ```
3. **Schedule:** Every minute
4. **Interval:** `* * * * *`

#### Verify Django-Q is Running

- Check Django admin: `https://abdul40.pythonanywhere.com/admin/django_q/`
- View task history and scheduled tasks
- Monitor campaign progress in real-time

---

## Troubleshooting

**mysqlclient fails on Windows:**
- Skip it - SQLite is used in development

**WeasyPrint PDF errors:**
- Windows: Use browser print-to-PDF
- Linux: GTK libraries available

**Email not sending:**
- Check SMTP credentials
- Verify EMAIL_BACKEND setting

---

## Support

For issues, contact: hi@wacampaignsender.com
