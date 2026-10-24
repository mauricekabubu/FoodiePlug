# FoodiePlug 🇰🇪

### Smart Food Planning for Everyday Life

**FoodiePlug is a food planning and management platform designed to help people make better decisions about what they eat, manage their kitchen inventory, plan meals, track food expenses, and organize grocery shopping — all in one place.**

Built with Django and designed with Kenyan food culture and everyday budgeting in mind, FoodiePlug brings meal planning, pantry management, budgeting, shopping lists, and AI-assisted guidance together in a single platform.

The goal is simple: make food planning easier, reduce unnecessary spending, minimize food waste, and help people make the most of the ingredients they already have.

---

## Table of Contents

- [Overview](#overview)
- [The Problem](#the-problem)
- [Our Solution](#our-solution)
- [Key Features](#key-features)
- [Technology Stack](#technology-stack)
- [Application Architecture](#application-architecture)
- [How FoodiePlug Works](#how-foodieplug-works)
- [Security and Privacy](#security-and-privacy)
- [Getting Started](#getting-started)
- [Environment Configuration](#environment-configuration)
- [Running the Application](#running-the-application)
- [Database and Media Storage](#database-and-media-storage)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Testing and Code Quality](#testing-and-code-quality)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Author](#author)
- [License](#license)

---

## Overview

FoodiePlug is a web-based food management application that combines several everyday activities into one connected experience.

Instead of managing grocery lists separately from meal plans, forgetting ingredients in the kitchen, or losing track of food expenses, users can organize these activities within one platform.

FoodiePlug is designed around five core ideas:

1. **Plan better:** Organize meals and create a practical meal schedule.
2. **Waste less:** Keep track of available ingredients, low-stock items, and approaching expiry dates.
3. **Spend wisely:** Understand food expenses and manage a food budget.
4. **Shop smarter:** Organize shopping lists around actual needs.
5. **Make informed decisions:** Use an AI assistant to get contextual food-planning guidance.

The platform prioritizes practical everyday use, a clean user experience, and support for the Kenyan food context.

## The Problem

Food management can become unnecessarily complicated when information is scattered across notes, shopping applications, spreadsheets, and memory.

Common challenges include:

- Not knowing what to cook with ingredients already available at home.
- Buying groceries that are already in the pantry.
- Forgetting food items until they expire.
- Struggling to plan meals within a limited budget.
- Losing track of grocery prices and food expenses.
- Repeatedly deciding what to cook every day.
- Maintaining shopping lists and meal schedules manually.

These challenges can contribute to food waste, unnecessary expenditure, and poor meal-planning habits.

## Our Solution

FoodiePlug brings these activities together through a connected food-management workflow.

Users can organize their food inventory, explore food options, plan meals, monitor expenses, prepare shopping lists, and access an AI assistant for additional guidance.

Rather than treating food planning as an isolated activity, FoodiePlug aims to connect the decisions that happen before, during, and after shopping and cooking.

The application is built with a modular Django architecture so that individual features can be developed, tested, and maintained independently.

---

## Key Features

### 1. Dashboard and Overview

The dashboard provides a central place for users to understand their food-planning activities and access the application's main features.

It serves as the entry point for navigating meal planning, pantry management, shopping, budgeting, the food library, and other available tools.

### 2. Food Library

The Food Library provides a place to explore and manage food information.

It supports the broader goal of helping users discover food options and make informed decisions about what to prepare.

The library is intended to provide a foundation for connecting food discovery with meal planning and ingredient management.

### 3. Pantry Management

The Pantry module helps users organize the ingredients and food items they have available.

Its functionality includes:

- Recording pantry items.
- Reviewing available stock.
- Identifying items running low.
- Tracking approaching expiry dates.
- Viewing estimated pantry value where data is available.

By keeping inventory information organized, FoodiePlug aims to help users make better use of what they already own.

### 4. Meal Planning

The Meals module helps users organize what they intend to prepare.

The meal-planning workflow includes meal discovery, meal details, creating and managing meals, and organizing a meal timetable.

Meal planning helps users move from making daily decisions at the last minute to following a more deliberate food plan.

### 5. Shopping Lists

The Shopping module helps users organize items they need to purchase.

Shopping lists complement pantry management and meal planning by providing a clearer picture of what is needed.

The objective is to make grocery shopping more organized and reduce unnecessary purchases.

### 6. Food Budgeting

The Budget module focuses on managing food-related expenses.

FoodiePlug is designed around practical budgeting needs, including the ability to reason about ingredient costs, meal expenses, and grocery spending.

Prices can be represented in Kenyan shillings (KES), supporting the platform's Kenyan context.

### 7. AI Food Assistant

FoodiePlug includes an AI assistant designed to provide conversational food-planning support.

The assistant is built around Google's Gemini model integration and the application's AI service layer.

Its intended role is to help users interact with food-planning information more naturally and obtain guidance relevant to their activities.

The AI integration is designed to work alongside the Django application rather than replace its core business logic.

**AI availability:** Features that require a configured AI provider and valid API credentials depend on the current AI configuration.

### 8. User Accounts and Preferences

FoodiePlug includes an account and profile system for managing user-specific information and preferences.

The platform is designed to support personalization, including language preferences and Kenyan conversational styles such as Kiswahili, Sheng, and mixed Kenyan English.

### 9. Insights and Settings

The Insights area provides a foundation for presenting useful information about a user's food-management activities.

Settings provide a dedicated place for configuring supported account and application preferences.

The exact insights and settings available depend on the current implementation.

### 10. Responsive User Experience

FoodiePlug is designed as a web application with a consistent visual identity and an interface focused on everyday usability.

Its design direction emphasizes clear navigation, readable information, practical workflows, and a warm food-oriented visual style.

---

## Technology Stack

FoodiePlug uses a Python-based web architecture.

| Technology | Purpose |
|---|---|
| Python | Core application language |
| Django | Web framework, routing, views, models, and application logic |
| Django ORM | Database access and model management |
| HTML | Page structure and templates |
| CSS | Styling and responsive layouts |
| JavaScript | Client-side interactions |
| SQLite | Local development database where configured |
| PostgreSQL | Intended production database option |
| Google Gemini API | AI assistant integration |
| Git | Version control |
| GitHub | Source code hosting and collaboration |
| Docker | Containerization and deployment workflow |
| Nginx | Reverse proxy in the planned containerized deployment |
| Cloudinary | Planned cloud storage for uploaded media |

**Implementation note:** SQLite is suitable for local development. PostgreSQL, Docker, Nginx, and Cloudinary should be considered deployment components only where they have been configured and verified in the current version.

---

## Application Architecture

FoodiePlug follows a modular Django application structure.

Each major functional area is separated into its own Django app, helping keep responsibilities organized and reducing unnecessary coupling between features.

The architecture includes the following functional areas:

| Django app | Responsibility |
|---|---|
| `accounts` | User accounts, profiles, and preferences |
| `foods` | Food library and food-related functionality |
| `pantry` | Pantry inventory and stock management |
| `prices` | Food pricing information |
| `budgets` | Food-budget management |
| `meals` | Meal management and planning |
| `shopping` | Shopping-list functionality |
| `ai` | AI assistant and conversational integration |

Additional services, settings, templates, and static assets support the main application.

### Architectural principles

- **Separation of concerns:** Keep features organized by responsibility.
- **Reusable business logic:** Place reusable operations in appropriate service modules.
- **Maintainability:** Make individual features easier to understand and extend.
- **Security:** Keep credentials and sensitive configuration out of source control.
- **Scalability:** Provide a foundation for improving storage, deployment, and application performance as requirements grow.

### Request lifecycle

A typical request follows this general workflow:

1. A user interacts with the web interface.
2. Django receives the request through the URL configuration.
3. The relevant view validates input and applies application rules.
4. Models and services handle database access and business operations.
5. Django returns the appropriate response or rendered template.

AI-assisted requests additionally pass through the AI service layer and its configured provider.

---

## How FoodiePlug Works

FoodiePlug is intended to connect everyday food-management activities into one workflow.

**Example: Planning meals for the week**

1. A user reviews the ingredients available in their pantry.
2. The user explores suitable food options in the Food Library.
3. The user organizes meals using the meal-planning functionality.
4. The user identifies ingredients that are missing or running low.
5. The user organizes required purchases using shopping lists.
6. The user considers food costs when managing their budget.
7. The AI assistant can provide additional guidance when configured and available.

This workflow illustrates the platform's intended direction: connecting inventory, meal decisions, shopping, and budgeting rather than managing them independently.

---

## Security and Privacy

Security is an important part of building a food-management platform that stores user-specific information.

FoodiePlug's security approach should include the following practices as applicable to the deployed version:

- Store secret keys and API credentials in environment variables or an appropriate secrets manager.
- Never commit `.env` files, API keys, database passwords, or production secrets.
- Use Django's authentication and authorization mechanisms to protect user-specific functionality.
- Validate and sanitize user-submitted data using appropriate Django forms and validation logic.
- Configure `DEBUG=False` in production.
- Set `ALLOWED_HOSTS` and trusted origins appropriately for the deployment environment.
- Enforce HTTPS in production.
- Review file-upload validation and storage permissions.
- Apply database migrations through controlled deployment procedures.
- Avoid logging API keys, passwords, or other sensitive information.

AI provider credentials should be handled carefully and must not be exposed to browser-side code.

These are security requirements and recommendations; their implementation should be verified against the current codebase before claiming that every control is active.

---

## Getting Started

Follow these instructions to set up FoodiePlug in a local development environment.

### Prerequisites

Install the following:

- Python compatible with the version required by the project.
- Git.
- pip.
- A terminal such as PowerShell, Command Prompt, or Bash.

An AI provider API key is required only for functionality that depends on a configured AI integration.

### 1. Clone the repository

Replace the repository URL below with the correct clone URL for the FoodiePlug repository.

```bash
git clone https://github.com/mauricekabubu/FoodiePlug.git
cd FoodiePlug
```

If the Django project is located inside a nested directory, navigate into the directory containing `manage.py` before continuing.

### 2. Create a virtual environment

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

A virtual environment keeps the project's Python dependencies separate from other applications on your machine.

### 3. Install dependencies

If the repository contains a `requirements.txt` file:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Use the dependency-management method documented by the actual project if it differs.

### 4. Configure environment variables

Create a local `.env` file if the project uses environment-based configuration.

Use the [Environment Configuration](#environment-configuration) section as a starting point. Confirm the variable names against Django's settings and the relevant service modules before running the application.

Never commit real secrets to Git.

### 5. Apply database migrations

From the directory containing `manage.py`, run:

```bash
python manage.py check
python manage.py migrate
```

These commands validate Django's configuration and apply the database migrations.

### 6. Create an administrator account

```bash
python manage.py createsuperuser
```

Follow the prompts to create a superuser for the Django administration interface.

### 7. Start the development server

```bash
python manage.py runserver
```

Open the local development address printed by Django in your browser. By default, this is:

`http://127.0.0.1:8000/`

The development server is intended for local development, not production hosting.

---

## Environment Configuration

FoodiePlug may use environment variables for application settings, database connections, AI integrations, authentication providers, and media storage.

The following is a **configuration reference**, not a guarantee that every variable is already implemented. Use the names actually read by the project's settings and services.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django's secret key |
| `DEBUG` | Enables or disables Django debug mode |
| `ALLOWED_HOSTS` | Permitted hostnames |
| `DATABASE_URL` | Database connection string, if supported |
| `GEMINI_API_KEY` | Gemini API credentials, if configured globally |
| `GEMINI_MODEL` | AI model selection, if configured through the environment |
| `CLOUDINARY_URL` | Cloudinary connection configuration, if integrated |
| `EMAIL_HOST` | SMTP server configuration, if applicable |
| `EMAIL_HOST_USER` | SMTP username, if applicable |
| `EMAIL_HOST_PASSWORD` | SMTP credentials, if applicable |

Example structure:

```dotenv
DEBUG=True
SECRET_KEY=replace-with-a-local-development-secret
ALLOWED_HOSTS=127.0.0.1,localhost
```

Add other variables only when the corresponding integration requires them.

**Important:** Do not copy this example into production unchanged. Use a strong secret key, disable debug mode, and configure the correct hosts, database, email, authentication, and storage settings for the deployment environment.

If users configure their own AI credentials through FoodiePlug's settings, follow the application's actual per-user configuration workflow rather than assuming a single global API key is required.

---

## Running the Application

### Django development commands

Run these commands from the directory containing `manage.py`.

| Command | Description |
|---|---|
| `python manage.py check` | Check Django configuration |
| `python manage.py migrate` | Apply database migrations |
| `python manage.py makemigrations` | Generate migrations for model changes |
| `python manage.py createsuperuser` | Create an administrator account |
| `python manage.py runserver` | Start the local development server |
| `python manage.py test` | Run Django's configured tests |
| `python manage.py collectstatic` | Collect static files for deployment |

Commands involving migrations, static files, and production settings should be used in accordance with the project's configuration and deployment process.

### Django administration

After creating a superuser, visit the admin URL configured by the project, commonly:

`http://127.0.0.1:8000/admin/`

The admin interface provides access to registered Django models according to the user's permissions and the project's admin configuration.

---

## Database and Media Storage

### Database

FoodiePlug can use SQLite for local development where configured.

PostgreSQL is the intended production database option because it supports a robust relational database workflow suitable for a deployed Django application.

Before switching databases, ensure that:

- The database driver is installed.
- The connection settings are configured correctly.
- Required migrations are applied.
- Existing data is migrated or imported appropriately.
- Production credentials are stored securely.

Changing the database configuration alone does not transfer existing records between database engines.

### Media storage

User-uploaded files, such as profile images or food-related images, require an appropriate media-storage configuration.

Cloudinary is a planned option for hosting uploaded media separately from the Django application server.

Before relying on it in production, configure the integration, validate upload behavior, and verify that stored image URLs remain accessible after deployment.

Static files and uploaded media are different: Django's static-file collection process does not automatically provide persistent storage for user uploads.

---

## Project Structure

The following illustrates the major architectural areas. It is a logical overview, not an exact inventory of every file in the repository.

```text
FoodiePlug/
├── foodplanner/
│   ├── manage.py
│   ├── config/
│   │   └── Django project configuration
│   ├── apps/
│   │   ├── accounts/
│   │   ├── foods/
│   │   ├── pantry/
│   │   ├── prices/
│   │   ├── budgets/
│   │   ├── meals/
│   │   ├── shopping/
│   │   └── ai/
│   ├── services/
│   ├── templates/
│   ├── static/
│   └── media/
├── requirements.txt
├── .gitignore
└── README.md
```

The actual directory names may differ. Keep this section synchronized with the repository's real structure as the project evolves.

---

## Development Workflow

FoodiePlug is developed incrementally, with features organized into manageable units of work.

A typical development workflow is:

1. Identify a feature or bug to address.
2. Review the relevant Django app and its dependencies.
3. Implement the change using the existing architecture.
4. Run Django's system checks and relevant tests.
5. Verify the feature in the local development environment.
6. Review the changes before staging them.
7. Commit the work using a descriptive Git commit message.

Useful Git commands:

```bash
git status
git diff
git add <files>
git commit -m "feat: describe the implemented feature"
git push
```

Prefer staging specific files rather than blindly adding everything. Keep environment files, local databases, virtual environments, uploaded development media, and secrets out of version control where appropriate.

---

## Testing and Code Quality

FoodiePlug uses Django's built-in system checks and testing framework as part of its development workflow.

Before submitting a change, run:

```bash
python manage.py check
python manage.py test
```

Where appropriate, also test:

- Authentication and authorization.
- Model validation and database operations.
- Meal creation and planning workflows.
- Pantry inventory updates.
- Shopping-list operations.
- Budget calculations.
- AI integration failures and missing credentials.
- File uploads and invalid file types.
- Error handling and user-facing messages.
- Mobile and desktop layouts.

Testing should reflect the functionality currently implemented. Additional automated tests should be added as the project grows.

---

## Roadmap

FoodiePlug is an evolving project. Potential areas for continued development include:

- [ ] Complete production deployment and environment configuration.
- [ ] Finalize PostgreSQL integration and production database procedures.
- [ ] Finalize Docker-based deployment and reverse-proxy configuration.
- [ ] Complete Cloudinary integration for persistent media storage.
- [ ] Expand automated testing and regression coverage.
- [ ] Improve the integration between pantry inventory and meal planning.
- [ ] Refine food-budget insights and shopping workflows.
- [ ] Improve AI-assisted planning and contextual recommendations.
- [ ] Strengthen production logging, monitoring, and error reporting.
- [ ] Improve documentation, onboarding, and contributor guidance.

Roadmap items should be checked off only after the relevant functionality has been implemented and verified.

---

## Contributing

Contributions, suggestions, and constructive feedback are welcome.

To propose a change:

1. Fork the repository.
2. Create a feature branch.
3. Implement your changes.
4. Run relevant checks and tests.
5. Commit your changes with a clear message.
6. Open a pull request describing the problem, solution, and any relevant testing.

For substantial changes, consider opening an issue first to discuss the proposed approach.

Please avoid committing secrets, personal data, local database files, or unrelated generated files.

---

## Author

**Maurice Kabubu**

Computer Science student and software developer interested in Python, Django, AI-powered applications, and practical software solutions.

FoodiePlug is a project focused on applying software engineering to everyday food planning, kitchen management, and budgeting challenges, with a particular interest in the Kenyan context.

- GitHub: [@mauricekabubu](https://github.com/mauricekabubu)
- Project repository: [FoodiePlug](https://github.com/mauricekabubu/FoodiePlug)

---

## License

A license has not been specified in this document.

Before distributing FoodiePlug as an open-source project, add a `LICENSE` file and update this section to reflect the license you choose. Without an explicit license, others generally do not receive permission to reuse, modify, or redistribute your copyrighted code beyond applicable legal exceptions.

---

*FoodiePlug — Plan your meals. Manage your food. Spend smarter.*
