# Proposal

## Why

Every cost is currently recorded without a currency, so all amounts are implicitly in a single currency and cannot be compared across currencies. Family members sometimes pay in different currencies (RUB, USD, SOM, ...), which today either forces manual conversion before entry or produces incorrect totals when different currencies are mixed.

## What Changes

- Add a `currency` dimension to every cost: each cost is stored with an explicit currency reference.
- Introduce an administrator-managed **`Конфигурация`** section in the Web UI containing:
  - A list of currencies (3-letter codes, e.g. `RUB`, `USD`, `SOM`) with exactly one flagged as **base currency**.
  - Per-currency exchange rates against the base currency: one required **default** rate (stored on the currency row) plus zero or more **dated** rates.
- Compute a dynamic **base amount** for each cost on display (never stored) by picking the exchange rate whose date is closest **on or before** the cost's date, falling back to the default rate.
- Display base amount everywhere the amount appears:
  - **Web UI**: base amount shown in its own column next to the amount in cost tables and detail views.
  - **Bot**: when a cost is in the base currency, show only the currency code (e.g. `01: Квартира 32_000 RUB`); otherwise append the base amount in square brackets (e.g. `01: Квартира 32_000 SOM [320.18 RUB]`).
- Extend bot input parsing: `<name> <amount> [<CUR>]` (currency in square brackets, optional). Missing currency → base currency. Unknown currency → line rejected as invalid with a clear error.
- Web UI cost create/edit: currency drop-down defaulting to the base currency.
- Guarantee at least one currency and exactly one base currency at all times; deleting a currency is blocked if any cost references it, and the base currency cannot be deleted or demoted while other currencies exist without another base.
- **BREAKING** (data model): `messages` gains structured `amount` and `currency_id` columns; the existing text-based parse-on-read logic is replaced by reading these columns. A data migration parses existing `messages.text` values and backfills them, assigning all pre-existing costs to the base currency `RUB`.

## Capabilities

### New Capabilities

- `currency-management`: administrator-managed catalogue of currencies, base-currency invariants, default and dated exchange rates, and the base-amount conversion rule.
- `cost-currency`: per-cost currency assignment, structured cost storage (amount + currency), bot input parsing extension, Web UI currency selection, and base-amount display rules across bot and Web UI.

### Modified Capabilities

None — the project has no existing specs (`openspec list --specs` reports "No specs found."). Both areas are introduced as new capabilities.

## Impact

- **Database**: new `currencies` and `exchange_rates` tables; `messages` gains `amount NUMERIC` and `currency_id` FK columns; Alembic migration backfills `RUB` as base currency and populates the new columns by parsing existing `messages.text`.
- **Models / repositories** (`bot/db/models.py`, `bot/db/repositories/messages.py`, new `bot/db/repositories/currencies.py`): `Message` gains typed fields; existing `rsplit`-based amount extraction removed; aggregations sum base amounts (computed) rather than raw amounts.
- **Bot** (`bot/services/message_parser.py`, `bot/routers/messages.py`, `bot/routers/menu.py`): parser accepts optional `[CUR]` suffix and validates against the currency catalogue; bot rendering shows currency code (and bracketed base amount when different).
- **Web UI** (`bot/web/app.py`, `bot/web/costs.py`, new `bot/web/config.py` router, templates under `bot/web/templates/costs/` and new `bot/web/templates/config/`): currency drop-down on cost forms, new base-amount column, new admin-only `Конфигурация` section with pages for currencies and exchange rates. Navigation hides the section from non-admin roles.
- **Access control**: `Конфигурация` requires `role == "admin"`; non-admin GET/POST is denied.
- **Tests**: unit tests for parser (currency suffix, unknown currency, base-currency default), rate-selection logic (default vs dated, on-or-before rule), base-amount rendering; integration tests for currency CRUD, exchange-rate CRUD, deletion-blocking constraints, base-currency invariants, and cost aggregation in mixed currencies; e2e tests for admin `Конфигурация` flow and bot round-trip in a non-base currency.
- **No external dependency additions** expected; conversion arithmetic uses `Decimal`.
