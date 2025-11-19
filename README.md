# LMS Backend - Emerald Learning Management System

A comprehensive Django REST Framework backend for a Learning Management System (LMS) with features including course management, user authentication, payments, AI-powered chatbot, and real-time chat functionality.

## 🚀 Features

- **User Management**: Authentication, authorization, email verification, password reset
- **Course Management**: Courses, lessons, content, assignments, quizzes
- **Assessment System**: Quizzes, assignments, question banks, grading
- **Payment Integration**: Stripe payment processing
- **AI Chatbot**: Gemini AI-powered chatbot with vector search capabilities
- **Real-time Chat**: WebSocket-based chat using Django Channels
- **Analytics**: Course analytics and progress tracking
- **Notifications**: Email notifications and in-app notifications
- **Admin Panel**: Jazzmin-powered Django admin interface

## 📋 Prerequisites

Before you begin, ensure you have the following installed:

- **Python** 3.10 or higher
- **PostgreSQL** 13+ (optional, SQLite is used by default)
- **Redis** 7+ (for caching and WebSocket channels)
- **pip** (Python package manager)
- **virtualenv** (recommended for Python virtual environments)
- **Docker** and **Docker Compose** (optional, for containerized setup)

## 🛠️ Installation

### Option 1: Local Development Setup

#### 1. Clone the Repository

```bash
git clone <repository-url>
cd LMS_Back_end
```

#### 2. Create and Activate Virtual Environment

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Note:** If you encounter issues installing `sentence-transformers` or `numpy`, you may need to install system dependencies:

**On Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install build-essential gcc g++ python3-dev
```

**On macOS:**
```bash
brew install gcc
```

#### 4. Set Up Environment Variables

Create a `.env` file in the `lms_project` directory (same level as `settings.py`):

```env
# Django Settings
DEBUG=True
DJANGO_SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Configuration (Optional - SQLite is used by default)
# DB_NAME=lms
# DB_USER=lms
# DB_PASSWORD=lms
# DB_HOST=localhost
# DB_PORT=5432

# Email Configuration (Resend API)
RESEND_API_KEY=your-resend-api-key

# SMTP Configuration (Fallback)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=no-reply@emerald.edu.et
SUPPORT_EMAIL=support@emerald.edu.et
PROJECT_NAME=Emerald LMS

# Stripe Payment Configuration
STRIPE_SECRET_KEY=your-stripe-secret-key
STRIPE_PUBLISHABLE_KEY=your-stripe-publishable-key
STRIPE_WEBHOOK_SECRET=your-stripe-webhook-secret
FRONTEND_BASE_URL=http://localhost:8888
STRIPE_SUCCESS_PATH=/payment/success
STRIPE_CANCEL_PATH=/payment/cancel

# Gemini AI Configuration
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL_NAME=gemini-1.5-flash

# Vector Database / Embeddings
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

#### 5. Set Up Redis (Required for Caching and WebSockets)

**On Windows:**
- Download Redis from [Redis for Windows](https://github.com/microsoftarchive/redis/releases)
- Or use WSL2 with Redis
- Or use Docker: `docker run -d -p 6379:6379 redis:7`

**On macOS:**
```bash
brew install redis
brew services start redis
```

**On Ubuntu/Debian:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis-server
```

#### 6. Run Database Migrations

```bash
python manage.py migrate
```

#### 7. Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

#### 8. Collect Static Files

```bash
python manage.py collectstatic --noinput
```

#### 9. Index Content for AI Chatbot (Optional but Recommended)

Index course content into the vector database for the AI chatbot to work properly:

```bash
python manage.py index_content
```

This command indexes:
- Published courses
- Lessons from published courses
- Course FAQs
- Course announcements

**Options:**
- `--clear`: Clear existing vector store before indexing
- `--type`: Index specific content type (`courses`, `lessons`, `faqs`, `announcements`, or `all`)

Example:
```bash
# Index all content
python manage.py index_content

# Index only courses
python manage.py index_content --type courses

# Clear and re-index everything
python manage.py index_content --clear
```

#### 10. Start the Development Server

**For HTTP only (standard Django):**
```bash
python manage.py runserver
```

**For HTTP + WebSocket support (ASGI with Daphne):**
```bash
daphne -b 0.0.0.0 -p 8000 lms_project.asgi:application
```

The server will be available at `http://localhost:8000`

**Note:** If Redis is not available, the application will fall back to local memory cache, but WebSocket functionality may be limited.

### Option 2: Docker Setup

#### 1. Create `.env` File

Create a `.env` file in the project root with the same variables as mentioned above.

#### 2. Build and Run with Docker Compose

```bash
docker-compose up --build
```

This will start:
- **PostgreSQL** database on port `5432`
- **Redis** server on port `6379`
- **pgAdmin** on port `8080` (optional database management)
- **Django application** on port `8888`

#### 3. Run Migrations in Docker

```bash
docker-compose exec web python manage.py migrate
```

#### 4. Create Superuser in Docker

```bash
docker-compose exec web python manage.py createsuperuser
```

#### 5. Index Content for AI Chatbot (Optional but Recommended)

Index course content into the vector database for the AI chatbot:

```bash
docker-compose exec web python manage.py index_content
```

This command indexes courses, lessons, FAQs, and announcements into the vector database for semantic search.

**Options:**
- `--clear`: Clear existing vector store before indexing
- `--type`: Index specific content type (`courses`, `lessons`, `faqs`, `announcements`, or `all`)

Example:
```bash
# Index all content
docker-compose exec web python manage.py index_content

# Index only courses
docker-compose exec web python manage.py index_content --type courses

# Clear and re-index everything
docker-compose exec web python manage.py index_content --clear
```

#### 6. Access the Application

- **API**: http://localhost:8888
- **Admin Panel**: http://localhost:8888/admin
- **pgAdmin**: http://localhost:8080

## 📁 Project Structure

```
LMS_Back_end/
├── lms_project/          # Main Django project directory
│   ├── settings.py       # Django settings
│   ├── urls.py          # Main URL configuration
│   ├── asgi.py          # ASGI configuration for WebSockets
│   ├── wsgi.py          # WSGI configuration
│   └── .env             # Environment variables (create this)
├── user_managment/       # User authentication and management app
├── courses/              # Course management app
│   ├── models.py        # Course, lesson, quiz models
│   ├── views/           # API views
│   └── services/        # Business logic services
├── chat/                 # Real-time chat and AI chatbot app
├── payments/             # Payment processing app
├── grading/              # Grading system app
├── requirements.txt      # Python dependencies
├── docker-compose.yml    # Docker Compose configuration
├── Dockerfile           # Docker image configuration
└── manage.py            # Django management script
```

## 🔧 Configuration

### Database Configuration

By default, the project uses **SQLite** for development. To use PostgreSQL:

1. Uncomment the PostgreSQL configuration in `lms_project/settings.py`
2. Comment out the SQLite configuration
3. Update your `.env` file with PostgreSQL credentials
4. Run migrations: `python manage.py migrate`

### Redis Configuration

Redis is used for:
- **Caching**: Django cache backend
- **WebSocket Channels**: Real-time chat functionality

If Redis is unavailable, the app will fall back to local memory cache, but WebSocket features may not work properly.

### CORS Configuration

CORS is configured to allow requests from various origins. Update `CORS_ALLOWED_ORIGINS` in `settings.py` for production.

## 🧪 Testing

Run the test suite:

```bash
python manage.py test
```

## 📚 API Documentation

Once the server is running, you can access:

- **Django Admin Panel**: http://localhost:8000/admin
- **API Root**: http://localhost:8000/api/ (check `urls.py` for specific endpoints)
- **Browsable API**: Available at API endpoints when using Django REST Framework

## 🔐 Authentication

The API uses JWT (JSON Web Tokens) for authentication. Include the token in your requests:

```
Authorization: Bearer <your-access-token>
```

## 🐛 Troubleshooting

### Issue: Redis Connection Error

**Solution:** Ensure Redis is running:
```bash
# Check Redis status
redis-cli ping
# Should return: PONG
```

### Issue: Port Already in Use

**Solution:** Change the port:
```bash
python manage.py runserver 8001
```

### Issue: Migration Errors

**Solution:** Reset migrations (development only):
```bash
python manage.py migrate --run-syncdb
```

### Issue: Static Files Not Loading

**Solution:** Collect static files:
```bash
python manage.py collectstatic
```

### Issue: WebSocket Not Working

**Solution:** 
1. Ensure Redis is running
2. Use Daphne instead of runserver:
```bash
daphne -b 0.0.0.0 -p 8000 lms_project.asgi:application
```

## 📝 Environment Variables Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `DEBUG` | Django debug mode | Yes |
| `DJANGO_SECRET_KEY` | Django secret key | Yes |
| `RESEND_API_KEY` | Resend email API key | For emails |
| `STRIPE_SECRET_KEY` | Stripe secret key | For payments |
| `GEMINI_API_KEY` | Google Gemini API key | For AI chatbot |
| `EMAIL_HOST` | SMTP server host | For email fallback |
| `EMAIL_HOST_USER` | SMTP username | For email fallback |
| `EMAIL_HOST_PASSWORD` | SMTP password | For email fallback |

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is proprietary software. All rights reserved.

## 👥 Support

For support, email support@emerald.edu.et or create an issue in the repository.

## 🎯 Next Steps

After setting up the project:

1. Create a superuser account
2. Access the admin panel at `/admin`
3. Configure your email settings
4. Set up Stripe keys for payment processing
5. Configure Gemini API key for chatbot functionality
6. **Index content for AI chatbot**: Run `python manage.py index_content` (or `docker-compose exec web python manage.py index_content` for Docker) to populate the vector database with course content
7. Review and update CORS settings for your frontend

---

&copy;2025 Emerald Learning Management System 

