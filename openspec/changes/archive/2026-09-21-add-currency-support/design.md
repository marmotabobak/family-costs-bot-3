# Design

## Context

Today costs live as free-form text in `messages.text` and are re-parsed on every read (`rsplit(maxsplit=1)`), with no `amount` column. See `bot/db/repositories/messages.py` and `bot/services/message_parser.py`. The `Message` model has only `id`, `user_id`, `text`, `created_at`. The web layer (`bot/web/costs.py`, `bot/web/templates/costs/`) renders costs read back through those parsers. Bot ingestion goes `messages router → parse_message → save`. There are no existing specs. Auth uses a session cookie with `User.role` in `{"admin", "user"}`.

See `proposal.md — Why` for motivation.

## Goals / Non-Goals

**Goals:**
- Make currency a first-class dimension of a cost, stored structurally, not embedded in text.
- Keep base-amount purely dynamic so administrators can correct rates retroactively without touching cost rows.
- Confine currency-configuration UI and mutations to admins.
- Preserve every existing cost by backfilling it into `RUB` as base currency.

**Non-Goals:**
- Automatic fetching of exchange rates from any external provider — rates are entered by administrators.
- Historical audit trail for exchange-rate edits (out of scope; changes overwrite in place).
- Multi-base currency or per-user base currency.
- Rewriting the message router or web routers beyond what currency support requires.
- Handling costs entered in a currency that gets deleted (deletion is blocked while referenced — see specs).

## Decisions

### Data model

Add two tables and extend `messages`:

```
currencies
  id              SERIAL PK
  code            VARCHAR(3) UNIQUE NOT NULL  -- uppercase ISO-like 3-letter
  is_base         BOOLEAN NOT NULL DEFAULT FALSE
  default_rate    NUMERIC(20, 10) NOT NULL    -- rate vs base; base row has 1
  created_at      TIMESTAMPTZ DEFAULT now()
  CHECK (default_rate > 0)
  CHECK (code ~ '^[A-Z]{3}$')
  -- partial unique index: at most one is_base=true
  UNIQUE INDEX idx_currencies_single_base ON currencies (is_base) WHERE is_base

exchange_rates
  id              SERIAL PK
  currency_id     INT NOT NULL FK → currencies(id) ON DELETE CASCADE
  rate            NUMERIC(20, 10) NOT NULL CHECK (rate > 0)
  rate_date       DATE NOT NULL
  UNIQUE (currency_id, rate_date)

messages (added columns)
  amount          NUMERIC(20, 4) NULL    -- NULL only during migration window
  currency_id     INT NULL FK → currencies(id) ON DELETE RESTRICT
```

**Why a partial unique index on `is_base`** rather than an app-level check: the "at most one base" invariant is enforced by the database, so concurrent admin edits can't create two bases. Promoting a new base is a two-step transaction: `UPDATE ... SET is_base=false WHERE is_base` then `UPDATE ... SET is_base=true WHERE id=$new`.

**Why `default_rate` lives on `currencies`** rather than as a special row in `exchange_rates`: matches the user's requirement ("default exchange rate is linked to the currency and is stored in the same table"), makes the NOT NULL constraint natural, and removes the ambiguity of "which date does the default belong to."

**Why `NUMERIC` everywhere**: amounts and rates are `Decimal` end-to-end (already the case for amount parsing); avoid floating-point drift in base-amount computation.

**Why not add `cost_date` column**: use `messages.created_at::date` as the cost's date for rate lookup. If a future change lets users backdate costs, the rate-selection call already takes a date parameter.

### Amount column: fill vs. remove text

`messages.text` is kept as-is (still the source of truth for the raw user message and multi-line quirks), but read paths switch to `messages.amount` / `messages.currency_id`. This lets the migration run without a text rewrite and preserves everything users originally typed. Repository helpers stop parsing `text`.

**Alternative considered:** parse `text` on every read forever, and just add `currency_id`. Rejected: rate math and aggregations become O(rows × parse) and every fix to a corner case in the text format silently rewrites historical totals.

### Migration strategy

Single Alembic revision:
1. Create `currencies`, `exchange_rates`.
2. Insert `RUB` with `is_base=true`, `default_rate=1`.
3. Add nullable `amount`, `currency_id` to `messages`.
4. Backfill: for each row, parse the amount with the same `rsplit(maxsplit=1)` + `Decimal` logic the current repositories use (kept as an inline SQL/Python helper in the migration to freeze the semantics). Set `currency_id` to `RUB`'s id.
5. Rows whose text cannot be parsed remain with NULL `amount` and NULL `currency_id`. Log their ids and leave them alone; they're already unparseable today and repositories will continue to skip them by filtering `amount IS NOT NULL`. This is not a regression.
6. **Do not** make `amount`/`currency_id` NOT NULL yet — a second cleanup migration after we're satisfied the backfill covered everything can tighten this.
7. Downgrade drops columns and tables; no data conversion back.

**Why not enforce NOT NULL immediately**: existing prod may contain rows the old parser silently ignored; a NOT NULL migration would fail on those. The write path in application code will always set both columns; reads filter nulls.

### Rate selection

Effective rate for `(currency_id, date)`:

```sql
SELECT rate FROM exchange_rates
WHERE currency_id = :c AND rate_date <= :d
ORDER BY rate_date DESC LIMIT 1
```

If null, fall back to `currencies.default_rate`. For the base currency the code short-circuits to `Decimal("1")` without touching the DB.

**Cache scope**: within a single request/render, cache `(currency_id, date) → rate` in a small dict — cost tables can show hundreds of rows and we don't want N+1 rate lookups. No cross-request caching (rates can change any time and staleness would be visible to admins).

**Batching**: for list views, preload all `(currency_id, date)` pairs used on the page and issue one query per currency selecting the max `rate_date <= max(dates)` window; then resolve each row in memory. Optimization deferred to tasks if profiling shows it matters.

### Bot parser extension

`MESSAGE_RE` becomes:

```
^\s*(?P<text>.+?)\s+(?P<amount>[+-]?\d+(?:[.,]\d+)?)(?:\s+\[(?P<currency>[A-Z]{3})\])?\s*$
```

Parser stays pure (no DB). Currency existence is checked in the message router after parsing so `parse_message` remains synchronous and doesn't depend on a session. Unknown currency is reported per-line via the existing `invalid_lines` channel with a distinct reason.

**Alternative considered:** allow `USD` / `$` / lowercase / no brackets. Rejected: user explicitly specified `[XXX]` format, and it disambiguates from cost names that happen to end in three uppercase letters.

### Web UI configuration section

New router mounted at `/config` under an `admin_required` dependency. Templates in `bot/web/templates/config/`:
- `currencies.html` — list + create/edit form (code, default rate, is_base toggle).
- `rates.html` — per-currency dated-rate list + add form.

Navigation entry appears only when `session.role == "admin"`. Non-admin requests to `/config/*` get a 403 through the same guard used elsewhere.

### Display rules

- **Web templates**: `cost_row.html` gets a second amount cell (`base_amount base_code`). For base-currency rows the two cells are equal.
- **Bot rendering**: a small helper `format_cost_line(cost, base_currency, base_amount)` centralizes the "with/without brackets" logic. Used everywhere the bot echoes a cost (recent lists, monthly reports, confirmation messages).
- Rounding: `Decimal.quantize(Decimal("0.01"), ROUND_HALF_UP)` for display only; storage keeps full precision.

## Risks / Trade-offs

- **Backfill leaves nulls for unparseable rows** → mitigated by keeping columns nullable and having repositories skip nulls (they already skip these rows today).
- **Retroactive rate edits silently change historical totals** → this is the intended behavior per the requirement ("rate may be updated even in the past"). Documented in specs and admin UI copy will warn about it.
- **Partial unique index requires Postgres** → we're already Postgres-only.
- **N+1 rate lookups on large cost pages** → mitigated by per-request rate cache; batched preload can be added if needed.
- **Bot parser change may reject previously valid weird inputs** (lines that happened to look like `name amount [X]` where X isn't a currency) → the bracketed-3-uppercase-letters pattern is deliberately narrow; existing valid data doesn't match it.
- **`is_base` toggle race** → serialized by the partial unique index; the second concurrent transaction fails and retries.

## Migration Plan

1. Deploy migration → creates tables, inserts `RUB`, adds columns, backfills.
2. Deploy application code that writes both `text` and `(amount, currency_id)`, and reads from `(amount, currency_id)`.
3. Observe unparseable rows in logs; correct any manually if desired.
4. **Rollback**: revert application, then `alembic downgrade -1` drops the new tables and columns. Because we didn't destroy `messages.text`, rollback loses nothing.
