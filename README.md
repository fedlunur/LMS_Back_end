# LMS Backend Setup Guide (Windows + Docker + PostgreSQL + Django)

This guide will help you quickly set up the **LMS backend** using **Docker**, **PostgreSQL**, **pgAdmin**, and **Django** on **Windows**.

---

## 🐳 Step 1: Install Docker Desktop

1. Download **Docker Desktop**: [Docker Desktop](https://www.docker.com/products/docker-desktop)  
2. Install and launch Docker Desktop.  
3. Ensure **WSL 2 integration** is enabled.  
4. Verify installation in PowerShell or CMD:

   ```bash
   docker --version
   docker-compose --version
   ```

---

## 🐍 Step 2: Set Up Python Virtual Environment

1. Navigate to your project folder:

   ```bash
   cd LMS_BACK_END
   ```
2. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```
3. Activate the virtual environment:

   - Windows PowerShell:

     ```powershell
     # PowerShell (Windows)
     .\.venv\Scripts\Activate.ps1
     ```

   - Command Prompt (cmd.exe):

     ```cmd
     REM Command Prompt (Windows)
     .\.venv\Scripts\activate.bat
     ```

   - Git Bash (Windows):

     ```bash
     # Git Bash (Windows)
     source .venv/Scripts/activate
     ```

   - macOS / Linux (bash, zsh):

     ```bash
     # macOS / Linux
     source .venv/bin/activate
     ```

   - fish shell:

     ```fish
     # fish
     source .venv/bin/activate.fish
     ```

   - csh / tcsh:

     ```csh
     # csh / tcsh
     source .venv/bin/activate.csh
     ```

   To deactivate the virtual environment, run:

   ```bash
   deactivate
   ```
4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

---

## 🐘 Step 3: Initialize PostgreSQL with Docker

1. Make sure `docker-compose.yml` is in your project root.  
2. Start Docker containers:

   ```bash
   docker-compose up --build
   ```
3. PostgreSQL will detect if the data folder is empty and initialize the database automatically.

---

## ⚙️ Step 4: Setup Django Backend

1. Apply database migrations:

   ```bash
   docker-compose exec web python manage.py migrate
   ```
2. Create a Django superuser:

   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

---
