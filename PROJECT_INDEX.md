# WA Campaign Sender - Project Index

## Project Overview
A Django-based WhatsApp campaign management system with subscription-based access, PayPal integration, and Google OAuth2 authentication.

## Technology Stack
- **Framework**: Django 5.2.2
- **Database**: SQLite (development) / MySQL (production)
- **Authentication**: Custom User Model + Google OAuth2
- **Payment**: PayPal REST API
- **Email**: SendGrid via django-anymail
- **Frontend**: HTML/CSS/JavaScript
- **Deployment**: PythonAnywhere

## Project Structure

### Core Django Apps

#### 1. `sitevisitor/` - Public Website & Authentication
**Purpose**: Handles public-facing pages, user registration, authentication, and basic user management.

**Key Models**:
- `CustomUser` - Extended user model with email as username
- `Profile` - User profile with free trial tracking
- `WhatsAppNumber` - User's WhatsApp numbers with verification status
- `EmailVerification` - Email verification tokens
- `PasswordReset` - Password reset tokens
- `OTPVerification` - OTP verification system
- `FreeTrialPhone` - Tracks used free trial phone numbers
- `NewsletterSubscriber` - Newsletter subscriptions
- `ContactMessage` - Contact form submissions

**Key Features**:
- Custom user authentication system
- Google OAuth2 integration
- Email verification
- Password reset functionality
- Free trial management (14-day trial)
- Contact form and newsletter
- SEO optimization middleware
- Blog system with best practices content

**Templates**:
- Public pages: home, about, pricing, contact, FAQs
- Authentication: login, signup, password reset
- Blog posts about WhatsApp marketing
- Error pages (400, 401, 403, 404, 429, 500, 503)

#### 2. `userpanel/` - User Dashboard & Subscription Management
**Purpose**: Authenticated user interface for managing subscriptions, orders, and account settings.

**Key Models**:
- `Order` - Purchase orders with PayPal integration
- `OrderItem` - Individual items in orders
- `Address` - User shipping/billing addresses

**Key Features**:
- User dashboard
- Subscription management
- PayPal payment processing
- Order history and invoices
- Address management
- Email notifications for payments
- Timezone handling
- PDF invoice generation

**Templates**:
- Dashboard, settings, pricing
- Order management and invoices
- Payment success/cancel pages
- Email templates for notifications

#### 3. `adminpanel/` - Administrative Interface
**Purpose**: Admin tools for managing users, subscriptions, payments, and system settings.

**Key Models**:
- `Subscription` - User subscriptions with status tracking
- `Payment` - Payment records
- `Invoice` - Invoice generation
- `SubscriptionPlan` - Available subscription plans

**Key Features**:
- User management
- Subscription administration
- Payment tracking
- Invoice management
- Contact message handling
- Newsletter subscriber management
- System settings
- Webhook handling for payments

**Management Commands**:
- `seed_subscription_plans.py` - Initialize subscription plans
- `update_subscription_prices.py` - Update pricing
- `send_pro_reminders.py` - Send upgrade reminders
- `send_trial_reminders.py` - Send trial expiration reminders

### Configuration Files

#### `settings.py` - Main Configuration
**Key Settings**:
- Database configuration (SQLite/MySQL)
- Email backend (SendGrid)
- PayPal API configuration
- Google OAuth2 settings
- Static/media file handling
- Logging configuration
- Session management
- Security settings

#### Environment Variables (`.env`)
**Required Variables**:
- `DJANGO_SECRET_KEY` - Django secret key
- `SENDGRID_API_KEY` - Email service API key
- `PAYPAL_CLIENT_ID_SANDBOX/LIVE` - PayPal credentials
- `PAYPAL_CLIENT_SECRET_SANDBOX/LIVE` - PayPal secrets
- `GOOGLE_OAUTH2_CLIENT_ID` - Google OAuth2 client ID
- `GOOGLE_OAUTH2_CLIENT_SECRET` - Google OAuth2 secret
- `DEFAULT_FROM_EMAIL` - Default sender email

### Static Assets

#### `static/` - Development Assets
- `css/home.css` - Main stylesheet
- `js/index.js` - Main JavaScript functionality
- `js/timezone_detector.js` - Timezone detection
- `image/` - Logo, favicons, blog images, tutorial screenshots
- `robots.txt`, `security.txt`, `site.webmanifest`

#### `staticfiles/` - Production Assets
- Collected static files for production deployment
- Django admin assets
- User panel JavaScript for real-time features

### Templates Structure

#### Public Templates (`sitevisitor/templates/`)
- **Main Pages**: home.html, about.html, pricing.html, contact.html
- **Authentication**: login.html, signup.html, password reset flow
- **Blog**: Multiple blog post templates about WhatsApp marketing
- **Emails**: Verification and password reset email templates
- **Errors**: Comprehensive error page templates

#### User Panel Templates (`userpanel/templates/`)
- **Dashboard**: Main user interface
- **Orders**: Order management and invoice templates
- **Settings**: Account and address management
- **Emails**: Payment notification templates

#### Admin Panel Templates (`adminpanel/templates/`)
- **Management**: User, subscription, and payment management
- **Reports**: System analytics and reporting
- **Settings**: System configuration interface

### Key Features & Functionality

#### Authentication System
- Custom user model with email as primary identifier
- Google OAuth2 integration with account linking
- Email verification system
- Password reset functionality
- Session management for PayPal redirects

#### Subscription Management
- 14-day free trial system
- Multiple subscription plans
- PayPal payment integration
- Automatic subscription renewal
- Trial expiration reminders
- Subscription cancellation handling

#### Payment Processing
- PayPal REST API integration
- Sandbox and live environment support
- Order tracking and invoice generation
- Payment failure handling
- Webhook processing for payment updates

#### User Experience
- Responsive design
- Timezone-aware functionality
- Real-time chat features
- SEO optimization
- Comprehensive error handling
- Email notifications

#### Administrative Tools
- User management interface
- Subscription administration
- Payment tracking
- Contact message handling
- Newsletter management
- System analytics

### Database Schema

#### User Management
- `CustomUser` - Core user data
- `Profile` - Extended user information and trial tracking
- `WhatsAppNumber` - User's WhatsApp numbers

#### Subscription System
- `SubscriptionPlan` - Available plans
- `Subscription` - User subscriptions
- `Payment` - Payment records
- `Invoice` - Invoice generation

#### Order Management
- `Order` - Purchase orders
- `OrderItem` - Order line items
- `Address` - User addresses

#### Communication
- `ContactMessage` - Contact form submissions
- `NewsletterSubscriber` - Newsletter subscriptions
- `EmailVerification` - Email verification tokens

### Deployment Configuration

#### Development
- SQLite database
- Debug mode enabled
- Local PayPal sandbox
- Local static file serving

#### Production (PythonAnywhere)
- MySQL database
- Debug mode disabled
- Live PayPal environment
- Collected static files
- Environment variable configuration

### Security Features
- CSRF protection
- Secure session handling
- Environment variable configuration
- SQL injection prevention
- XSS protection
- Secure password hashing

### Monitoring & Logging
- Django error logging to files
- Payment transaction logging
- User activity tracking
- Email delivery monitoring

### API Integrations
- **PayPal REST API** - Payment processing
- **SendGrid API** - Email delivery
- **Google OAuth2 API** - Social authentication

### File Structure Summary
```
wa_campiagn_sender/
├── adminpanel/          # Admin management interface
├── sitevisitor/         # Public website & auth
├── userpanel/           # User dashboard & subscriptions
├── wa_campiagn_sender/  # Django project settings
├── static/              # Development static files
├── staticfiles/         # Production static files
├── templates/           # Global templates
├── media/               # User uploaded files
├── logs/                # Application logs
├── manage.py            # Django management script
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables
└── README.md           # Setup instructions
```

This project implements a complete SaaS solution for WhatsApp campaign management with subscription billing, user management, and administrative tools.