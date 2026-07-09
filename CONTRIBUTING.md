# Contributing

Thank you for your interest. This project helps executors administer an estate in England and Wales. A few firm rules keep it safe and correct.

## Ground rules

1. **No personal data in the repository.** Schema and synthetic seed only. Real data belongs in the git-ignored `seed/` directory of a self-hosted install. Pull requests containing personal data will be closed.
2. **Deterministic money.** All tax and accounting figures come from the pure modules in `backend/app/domain/`. No LLM output may produce a figure. Agents explain; they never compute.
3. **Tests required for domain logic.** Any change to `iht_engine.py`, `estate_accounts.py` or `deadlines.py` must come with unit tests. The IHT test table in `backend/tests/test_iht_engine.py` must stay green.
4. **No automated filing or sending.** Agent tools are read and draft only. Do not add tools that send email, file with HMRC, or move money.
5. **UK English throughout the UI and content. No em dashes.**
6. **Accessibility.** Target WCAG 2.2 AA. The interface must stay calm and plain; it is used by people who are recently bereaved.

## Adding a jurisdiction

England and Wales rules live behind `backend/app/domain/jurisdiction/`. To add another regime, implement the same interface in a new jurisdiction module without touching the core engine, and provide the equivalent executable test table for its allowance and tax logic.

## Development

```bash
cp .env.example .env
docker compose up          # Postgres + pgvector, backend, frontend

# Backend tests
cd backend && python -m pytest tests/ -v
```
