# Asset Lookup - Comprehensive Asset Renewal Tracking System

A powerful, full-featured web application for tracking and managing organizational assets with advanced warranty notification capabilities.

<div align="center">
<img src="app/static/image/AL_logo.png" alt="Asset Lookup Logo" width="50%">
</div>

## Support This Project

If my work helped you, consider buying me a coffee! ☕

**https://ko-fi.com/tokshernandez**

## 🚀 Features

### Core Asset Management
- **Complete Asset Tracking** - Track products, models, serial numbers, locations, and vendors
- **Warranty Management** - Automated warranty expiration tracking and alerts
- **File Attachments** - Upload receipts, manuals, and documentation per asset
- **Tag Organization** - Categorize assets with customizable color-coded tags
- **Advanced Search & Filtering** - Find assets quickly with powerful search capabilities

### User & Permission Management
- **Role-Based Access Control** - Three-tier permission system (Admin, Group Admin, User)
- **Group-Based Asset Assignment** - Organize users into groups with specific asset access
- **User Profile Management** - Customizable user preferences and settings
- **Two-Factor Authentication** - Enhanced security with TOTP-based 2FA

### Intelligent Notification System
- **Multi-Stage Alerts** - Initial alerts (30 days) and follow-up reminders (15 days)
- **Flexible Scheduling** - Configurable notification frequencies and timing
- **Email Response Tracking** - Users can respond directly to warranty alerts
- **Response Analytics** - Dashboard showing renewal decisions and response rates

### Advanced Features
- **Real-Time Dashboard** - Visual charts and status cards for asset overview
- **Bulk Operations** - Import/export assets, bulk deletion with permission checks
- **Comprehensive Audit Logging** - Track all system changes and user activities
- **Timezone Support** - Global timezone handling for international organizations
- **Responsive Design** - Works seamlessly on desktop, tablet, and mobile devices

## Screenshots

### Dashboard & Overview
<div align="center">
  <img src="screenshots/Asset Dashboard.png" alt="Asset Dashboard" width="800"/>
  <p><em>Main Asset Dashboard showing warranty status overview and expiring assets</em></p>
</div>

<div align="center">
  <img src="screenshots/Admin dashboard.png" alt="Admin Dashboard" width="800"/>
  <p><em>Administrative dashboard with system statistics and quick actions</em></p>
</div>

### Asset Management
<div align="center">
  <img src="screenshots/Asset List.png" alt="Asset List" width="800"/>
  <p><em>Comprehensive asset listing with filtering, sorting, and bulk operations</em></p>
</div>

### User & Access Management
<div align="center">
  <img src="screenshots/User Management.png" alt="User Management" width="800"/>
  <p><em>User management interface with role-based permissions</em></p>
</div>

### SSO management
<div align="center">
  <img src="screenshots/SSO Settings.png" alt="User Management" width="800"/>
  <p><em>SSO Integration</em></p>
</div>

### Group management

<div align="center">
  <img src="screenshots/Group Management.png" alt="Group Management" width="800"/>
  <p><em>Group management for organizing users and permissions</em></p>
</div>

### Organization & Categorization
<div align="center">
  <img src="screenshots/Tags Management.png" alt="Tags Management" width="800"/>
  <p><em>Tag management system for asset categorization and filtering</em></p>
</div>

### System Configuration
<div align="center">
  <img src="screenshots/System Settings.png" alt="System Settings" width="800"/>
  <p><em>System-wide configuration including timezone and registration settings</em></p>
</div>

<div align="center">
  <img src="screenshots/Email SMTP Settings.png" alt="Email SMTP Settings" width="800"/>
  <p><em>SMTP configuration for email notifications and alerts</em></p>
</div>

### Notification System
<div align="center">
  <img src="screenshots/Notification Settings 1.png" alt="Notification Settings Overview" width="800"/>
  <p><em>Comprehensive notification settings and scheduling configuration</em></p>
</div>

<div align="center">
  <img src="screenshots/Notification Settings 2.png" alt="Notification Settings Details" width="800"/>
  <p><em>Advanced notification preferences and alert customization</em></p>
</div>

### Email Notifications & Responses
<div align="center">
  <img src="screenshots/Email Notification.png" alt="Email Notification" width="800"/>
  <p><em>Sample warranty expiration email notification sent to users</em></p>
</div>

<div align="center">
  <img src="screenshots/Email Response1.png" alt="Email Response - Renewal" width="800"/>
  <p><em>User response interface for warranty renewal decisions</em></p>
</div>

<div align="center">
  <img src="screenshots/Email Reponse2.png" alt="Email Response - Options" width="800"/>
  <p><em>Response options for warranty expiration notifications</em></p>
</div>

<div align="center">
  <img src="screenshots/Email Response3.png" alt="Email Response - Confirmation" width="800"/>
  <p><em>Confirmation screen after user response submission</em></p>
</div>

<div align="center">
  <img src="screenshots/Email Response4.png" alt="Email Response - Details" width="800"/>
  <p><em>Detailed response tracking and management interface</em></p>
</div>

### Audit & Compliance
<div align="center">
  <img src="screenshots/Audit Logs.png" alt="Audit Logs" width="800"/>
  <p><em>Comprehensive audit logging for compliance and security monitoring</em></p>
</div>

### Database Backup Settings
<div align="center">
  <img src="screenshots/Database Backup Settings.png" alt="Audit Logs" width="800"/>
  <p><em>Comprehensive database settings</em></p>
</div>
---

## 🏗️ Architecture

### Technology Stack
- **Backend**: Python Flask with SQLAlchemy ORM
- **Frontend**: Bootstrap 5 with Chart.js for visualizations
- **Database**: SQLite (easily upgradeable to PostgreSQL)
- **Authentication**: Flask-Login with optional 2FA (pyotp)
- **Email**: SMTP integration with HTML/text templates
- **Scheduler**: APScheduler for automated notifications

### Key Components
- **Models**: User, Asset, Group, Notification, Audit logging
- **Services**: Email notifications, configuration management, time utilities
- **API**: RESTful endpoints for dashboard data and search
- **Security**: Input validation, XSS protection, permission-based access control

## 📦 Installation

### Using Docker (Recommended)

1. **Clone the repository**
```bash
git clone https://github.com/thokzz/asset-lookup.git
cd asset-lookup
```

2. **Configure environment**
```bash
nano docker-compose.yml
# Update EXTERNAL_URL to your actual domain
```

3. **Deploy with Docker Compose**
```bash
docker compose up -d --build
```
4. **Access the application**
Open your browser to http://localhost:3443
Default login: admin / admin123


# 👥 Default Users
The system creates three default users for testing:

admin | admin123 | Administrator | Full system access

groupadmin | groupadmin123 | Group Admin | Manage assigned groups and assets

user | user123| Regular User | View and edit assigned assets

⚠️ Important: Change default passwords immediately in production!


🔒 Security Features

# Access Control

Role-Based Permissions - Granular control over user capabilities

Group-Based Asset Access - Users only see assets assigned to their groups

Secure File Uploads - Validated file types and secure storage

Input Sanitization - Protection against XSS and injection attacks

# Authentication

Password Hashing - Bcrypt encryption for all passwords

Two-Factor Authentication - Optional TOTP-based 2FA

Session Management - Secure session handling with timeout

Audit Logging - Complete audit trail of all system activities

# Data Protection

Database Security - Parameterized queries prevent SQL injection

File Security - Secure file handling and access controls

Privacy Controls - Users only access authorized data

# 📊 Dashboard & Analytics
# Visual Dashboard

Status Overview - Active, expiring, and expired warranty counts

Interactive Charts - Warranty status distribution and expiration timeline

Response Analytics - User response tracking for warranty notifications

Recent Activity - Latest asset changes and notifications

# Reporting Features

Asset Export - CSV export with comprehensive asset data

Audit Reports - Detailed activity logs with filtering options

Notification Reports - Response rates and renewal decisions

Custom Filtering - Advanced search across all asset attributes

# 🔔 Notification System
# Smart Alerts

Initial Notifications - Sent 30 days before warranty expiration

Follow-up Reminders - Escalating alerts starting 15 days before expiration

Response Tracking - Users can respond directly from email notifications

Automated Scheduling - Configurable frequency (hourly to daily)

# Email Features

HTML & Text Versions - Rich HTML emails with text fallbacks

One-Click Responses - Direct links for warranty renewal decisions

Personalized Content - Customized based on asset and user information

Mobile-Friendly - Responsive email templates for all devices

# 🛠️ API Endpoints
# Dashboard Data

http

GET /api/dashboard/stats

GET /api/dashboard/expiration-timeline

GET /api/dashboard/notification-responses

# Search & Assets
http

GET /api/search/assets?q=query

GET /api/tags

POST /api/tags

# Time & Configuration
http

GET /api/current_time

GET /api/timezones

#🔧 Customization
# Extending the System

Custom Fields - Add new asset attributes by extending the Asset model

Additional File Types - Modify ALLOWED_EXTENSIONS in configuration

Custom Notifications - Extend notification templates and triggers

Integration APIs - Build custom integrations using the REST API

[![Star History Chart](https://api.star-history.com/svg?repos=thokzz/asset-lookup&type=Date)](https://star-history.com/#thokzz/asset-lookup&Date)

# Theming

CSS Customization - Modify app/static/css/style.css

Logo Replacement - Update app/static/image/AL_logo.png

Color Schemes - Customize Bootstrap variables for company branding

# 📝 Changelog

Version 2.0 (2025.05.02)

Enhanced Notification System - Multi-stage alerts with response tracking

Two-Factor Authentication - TOTP-based 2FA support

Improved Dashboard - Real-time charts and analytics

Group-Based Permissions - Advanced access control system

Timezone Support - Global timezone configuration

Mobile Responsiveness - Optimized for all device types

# Reporting Issues

Use the GitHub Issues page

Include detailed steps to reproduce

Specify your environment (OS, Python version, etc.)

# Permitted Uses

Personal use

Educational use

Research and development

Non-profit organizations

Government use

Internal business use (non-commercial)

# Prohibited Uses

Selling the software

SaaS/hosting services for profit

Commercial products incorporating this software

Any revenue-generating activities

For commercial licensing, please contact: thokzz.github@gmail.com

# 👨‍💻 About the Developer

Asset Lookup was developed by Toks Hernandez to address critical needs in asset tracking and management. The platform was designed to make asset management more straightforward and efficient for organizations of all sizes.

Issues: Report bugs on GitHub Issues

Commercial Support: Contact thokzz.github@gmail.com

