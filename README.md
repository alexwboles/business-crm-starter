# SignalDesk Business CRM Starter

A dependency-free, local-first CRM demonstration for small businesses. It
turns scattered contacts into a simple pipeline with follow-up priorities and
clear next-action recommendations.

## What it demonstrates

- Responsive browser dashboard for leads, pipeline value, stages, and wins.
- SQLite persistence with duplicate-email protection.
- Lead capture and fast search.
- Deterministic follow-up recommendations that remain explainable and testable.
- Reusable stages and data model suitable for later Airtable, Shopify, email,
  or agent integrations.
- Local operation without sending business or customer data to third parties.
- Automated unit and HTTP integration tests.

## Run

```powershell
python app.py
```

Open `http://127.0.0.1:8765`.

## Verify

```powershell
python -m unittest -v
```

The included demo records use reserved `.test` email addresses and synthetic
business names. Production integration should add authentication, role-based
permissions, backups, deployment monitoring, and client-specific acceptance
tests before handling real customer data.
