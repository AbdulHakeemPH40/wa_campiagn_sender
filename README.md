# WA Campaign Sender

A Django application for sending WhatsApp campaigns.

## Environment Setup

This project uses environment variables for configuration. Follow these steps to set up your environment:

1. Copy the example environment file:
   ```
   cp .env.example .env
   ```

2. Edit the `.env` file and fill in your actual values:
   - Generate a new Django secret key
   - Add your SendGrid API key
   - Add your PayPal credentials
   - Add your Google OAuth2 credentials
   - Update site settings

## PythonAnywhere Deployment

When deploying to PythonAnywhere:

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/wa_campaign_sender.git
   ```

2. Create a `.env` file in the project root:
   ```
   cd wa_campaign_sender
   nano .env
   ```

3. Copy your local `.env` file contents to this file, adjusting values as needed for production:
   - Set `DEBUG=False`
   - Update `SITE_URL` and `SITE_DOMAIN` to your PythonAnywhere domain
   - Update PayPal return URLs to your production domain

4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

5. Run migrations:
   ```
   python manage.py migrate
   ```

6. Collect static files:
   ```
   python manage.py collectstatic
   ```

7. Configure the WSGI file in PythonAnywhere to point to your project.

## Google OAuth2 Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to "APIs & Services" > "Credentials"
4. Create OAuth client ID credentials for a Web application
5. Add your domain to Authorized JavaScript origins
6. Add your redirect URI: `https://yourdomain.com/social-auth/complete/google-oauth2/`
7. Copy the Client ID and Client Secret to your `.env` file