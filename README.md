# WA Campaign Sender

WhatsApp bulk messaging and campaign management platform.

## Setup

1. Clone the repository
2. Open `wa_campiagn_sender/settings.py` and set all credentials directly (no `.env` file used)
3. Install dependencies:

```bash
pip install django
pip install pillow
pip install django-anymail[brevo]
pip install pdfkit
pip install django-paypal
pip install "weasyprint<66"
pip install requests
pip install pytz
pip install social-auth-app-django
pip install dj-database-url
pip install mysqlclient
```

4. Run migrations:
```bash
python manage.py migrate
```

5. Create superuser:
```bash
python manage.py createsuperuser
```

6. Run the server:
```bash
python manage.py runserver
```

## Credentials (settings.py)

Configure in `wa_campiagn_sender/settings.py`:

- `SECRET_KEY`: Django secret key
- `DEBUG`: environment toggle
- `BREVO_SMTP_USER`, `BREVO_API_KEY`: email relay credentials
- `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_MODE`, `PAYPAL_RETURN_URL`, `PAYPAL_CANCEL_URL`
- `SOCIAL_AUTH_GOOGLE_OAUTH2_KEY`, `SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET`
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`
- `WASENDER_PERSONAL_ACCESS_TOKEN`, `ENCRYPTION_KEY`
- `DB_PASSWORD`: production database password

## Security

- Keep `wa_campiagn_sender/settings.py` out of version control (already in `.gitignore`).
- Store all secrets in `settings.py` on the server; do not publish them.
- Use strong passwords and rotate API keys when necessary.