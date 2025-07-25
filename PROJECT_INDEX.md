# WA Campaign Sender - Project Index

## Project Overview
A Django-based WhatsApp campaign sender application with subscription management, PayPal integration, and Google OAuth2 authentication.

## Technology Stack
- **Framework**: Django 5.2.2
- **Database**: SQLite (dev) / MySQL (production)
- **Authentication**: Custom User Model + Google OAuth2
- **Payment**: PayPal REST API
- **Email**: SendGrid via django-anymail
- **Deployment**: PythonAnywhere

## Project Structure

### Core Django Apps

#### 1. `sitevisitor/` - Public Website & Authentication
**Purpose**: Handles public pages, user authentication, and visitor management

**Key Models**:
- `CustomUser` - Extended user model with email as username
- `Profile` - User profile with free trial management
- `WhatsAppNumber` - User's WhatsApp numbers with verification
- `EmailVerification` - Email verification tokens
- `ContactMessage` - Contact form submissions
- `NewsletterSubscriber` - Newsletter subscriptions

**Key Features**:
- Custom user authentication system
- Email verification workflow
- Free trial management (14-day trial)
- Contact forms and newsletter
- SEO middleware and sitemaps
- Blog system with static content
- Error handling (400, 401, 403, 404, 429, 500, 503)

**Templates**: Public pages (home, about, pricing, login, signup, blogs, etc.)

#### 2. `userpanel/` - User Dashboard & Orders
**Purpose**: User dashboard, subscription management, and order processing

**Key Models**:
- `Order` - User orders with PayPal integration
- `OrderItem` - Individual items in orders
- `Address` - User shipping/billing addresses

**Key Features**:
- User dashboard with subscription status
- PayPal payment integration
- Order management and invoicing
- PDF invoice generation
- Email notifications for payments
- Timezone handling for users
- Real-time chat functionality

**Templates**: Dashboard, orders, payments, settings, invoices

#### 3. `adminpanel/` - Admin Management
**Purpose**: Administrative interface for managing users, subscriptions, and payments

**Key Models**:
- `Subscription` - User subscriptions with plans
- `Payment` - Payment records
- `Invoice` - Invoice management
- `SubscriptionPlan` - Available subscription plans

**Key Features**:
- Admin dashboard with analytics
- User management (view, edit, grant subscriptions)
- Subscription management (create, cancel, modify)
- Payment tracking and invoicing
- Contact message management
- Newsletter subscriber management
- Webhook handling for payments

**Management Commands**:
- `seed_subscription_plans.py` - Initialize subscription plans
- `send_pro_reminders.py` - Send reminder emails
- `send_trial_reminders.py` - Send trial expiration reminders

#### 4. `wa_campiagn_sender/` - Django Configuration
**Purpose**: Main Django project configuration

**Files**:
- `settings.py` - Development settings
- `setting_pythonanywhere.py` - Production settings for PythonAnywhere
- `urls.py` - Main URL routing
- `wsgi.py` / `asgi.py` - WSGI/ASGI configuration

## Key Configuration Files

### Environment & Dependencies
- `.env` - Environment variables (API keys, database config)
- `requirements.txt` - Python dependencies
- `manage.py` - Django management script

### Static Assets
- `static/` - CSS, JavaScript, images
- `staticfiles/` - Collected static files for production
- `media/` - User uploaded files (profile pictures)

## Database Schema

### User Management
- **CustomUser**: Email-based authentication
- **Profile**: User profiles with trial management
- **WhatsAppNumber**: Multiple WhatsApp numbers per user

### Subscription System
- **SubscriptionPlan**: Available plans (Basic, Pro, etc.)
- **Subscription**: User subscriptions with status tracking
- **Payment**: Payment records with PayPal integration
- **Invoice**: Generated invoices

### Order Management
- **Order**: User orders with shipping info
- **OrderItem**: Individual order items
- **Address**: User addresses

### Communication
- **ContactMessage**: Contact form submissions
- **NewsletterSubscriber**: Newsletter subscriptions
- **EmailVerification**: Email verification tokens

## Key Features

### Authentication & User Management
- Custom user model with email as username
- Google OAuth2 integration
- Email verification system
- Password reset functionality
- Profile management with pictures

### Subscription System
- 14-day free trial (one-time per phone number)
- Multiple subscription plans
- PayPal payment integration
- Automatic subscription management
- Invoice generation (PDF)

### WhatsApp Integration
- Multiple WhatsApp number support
- Number verification system
- Campaign sending capabilities (via browser extension)

### Admin Features
- Comprehensive admin dashboard
- User and subscription management
- Payment tracking
- Contact message handling
- Newsletter management

### SEO & Marketing
- Sitemap generation
- Blog system
- Newsletter subscription
- Contact forms
- Security.txt implementation

## Deployment Configuration

### Development
- SQLite database
- Debug mode enabled
- Local PayPal sandbox
- Development email backend

### Production (PythonAnywhere)
- MySQL database
- Debug disabled
- Live PayPal integration
- SendGrid email backend
- Static file serving
- Domain-specific settings

## Security Features
- CSRF protection
- Secure session handling
- Email verification
- Rate limiting (429 errors)
- Secure cookie configuration
- Environment variable protection

## API Endpoints
- `/api/verify-license/` - License verification for browser extension
- Social auth endpoints via `social_django`
- PayPal webhook endpoints

## Browser Extension Integration
- License verification system
- WhatsApp Web integration
- Campaign sending functionality
- User authentication sync

## Email System
- SendGrid integration for transactional emails
- Email templates for various notifications
- Newsletter functionality
- Password reset emails
- Payment confirmation emails

## Logging & Monitoring
- Django error logging
- File-based log storage
- Console logging for development
- Request logging for debugging

## File Structure Summary
```
wa_campiagn_sender/
├── adminpanel/          # Admin management
├── sitevisitor/         # Public site & auth
├── userpanel/           # User dashboard
├── wa_campiagn_sender/  # Django config
├── static/              # Static assets
├── media/               # User uploads
├── logs/                # Application logs
├── templates/           # Global templates
└── requirements.txt     # Dependencies
```

This project implements a complete SaaS solution for WhatsApp campaign management with subscription billing, user management, and browser extension integration.