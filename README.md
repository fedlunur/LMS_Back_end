# 🧠 LMS Backend Setup Guide (Windows + Docker + PostgreSQL + Django)

This guide will help you set up the **LMS backend** using **Docker**, **PostgreSQL**, **pgAdmin**, and **Django** on **Windows**.

---

## 🐳 Step 1: Install Docker Desktop for Windows

1. Download **Docker Desktop** from the official site:  
   👉 [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
2. Install and launch Docker Desktop.
3. Make sure **WSL 2** integration is enabled.
4. Verify installation in PowerShell or CMD:
   ```bash
   docker --version
   docker-compose --version
5.clone the repo activate venv and run accordingly

## ▶️ Step 2: Start Docker, run containers, and apply migrations

1. Make sure Docker Desktop is running (WSL2 enabled if on Windows) and open a terminal in the project root (where docker-compose.yml lives).

2. Build and start containers in detached mode:
```bash
docker-compose up --build -d
```

3. Create and apply Django migrations inside the web container:
```bash
docker-compose exec web python manage.py makemigrations
docker-compose exec web python manage.py migrate
```

4. If you change models or need to rebuild images, rebuild and restart:
```bash
docker-compose build web
docker-compose up -d
```
(or simply `docker-compose up --build -d` to rebuild all services)

5. Open the API in your browser:
http://localhost:8888/api

Optional: follow logs if you need to troubleshoot
```bash
docker-compose logs -f web
```
