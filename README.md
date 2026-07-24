# Framework Browser Jobs

A modular Python framework for scraping job listings from websites using Playwright, storing structured data in SQLite with auto-detected tags, and sending formatted job alerts via Telegram through Hermes Agent.

## Features

- **Playwright-based scraping** — headless browser automation for JavaScript-rendered job boards
- **SQLite persistence** — lightweight local database for job listings and metadata
- **Auto-detected tags** — modality, location, salary, company, schedule, vacancies, publication date
- **Telegram alerts** — formatted job notifications via Hermes Agent integration
- **Credential management** — secrets managed with ansible-vault

## Planned Stack

| Component    | Technology       |
|------------- |----------------- |
| Language     | Python 3.11+     |
| Browser      | Playwright       |
| Database     | SQLite           |
| Alerts       | Telegram (Hermes)|
| Secrets      | ansible-vault    |
| Testing      | pytest           |

## Getting Started

```bash
# Clone the repo
git clone https://github.com/rbedani/devops.git
cd devops

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install

# Run tests
pytest
```

## Project Structure

```
devops/
├── src/               # Application source code
│   ├── scrapers/      # Playwright-based web scrapers
│   ├── db/            # SQLite database layer
│   ├── models/        # Data models for job listings
│   ├── alerts/        # Telegram alert formatting and sending
│   └── config/        # Configuration and credential management
├── tests/             # pytest test suite
│   ├── unit/          # Unit tests
│   ├── integration/   # Integration tests
│   └── e2e/           # End-to-end tests with Playwright
├── .secrets.yml       # ansible-vault encrypted secrets (gitignored)
└── pyproject.toml     # Project metadata and dependencies
```

## License

MIT
