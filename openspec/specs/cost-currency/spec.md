# Spec

## Purpose

Attaches an explicit currency to every recorded cost and defines how amounts and their base-currency equivalents are entered, stored, and displayed across the bot and the Web UI.

## Requirements

### Requirement: Cost carries an explicit currency

Every stored cost SHALL reference exactly one currency from the currency catalogue. The referenced currency SHALL always resolve to a valid catalogue entry at read time.

#### Scenario: Cost is persisted with a currency reference
- **WHEN** a valid cost is saved through any entry point
- **THEN** the persisted record SHALL carry a non-null reference to a currency in the catalogue

#### Scenario: Existing costs are migrated to the base currency
- **GIVEN** costs recorded before this change existed without any currency
- **WHEN** the migration is applied
- **THEN** every pre-existing cost SHALL reference the currency `RUB`, which SHALL be created as the base currency if not already present

### Requirement: Bot input accepts optional currency in brackets

The bot input format SHALL be `<name> <amount> [<CUR>]`, where the currency code is uppercase 3 letters wrapped in square brackets. If the bracketed currency is omitted, the base currency SHALL be used. If a bracketed currency is provided but not present in the catalogue, the line SHALL be rejected as invalid.

#### Scenario: Missing currency defaults to base
- **GIVEN** the base currency is `RUB`
- **WHEN** the user sends `coffee 250`
- **THEN** the system SHALL save one cost `coffee` with amount `250` and currency `RUB`

#### Scenario: Explicit known currency is accepted
- **GIVEN** currency `USD` exists in the catalogue
- **WHEN** the user sends `lunch 12.50 [USD]`
- **THEN** the system SHALL save one cost `lunch` with amount `12.50` and currency `USD`

#### Scenario: Unknown currency is rejected as invalid line
- **GIVEN** currency `XYZ` does not exist in the catalogue
- **WHEN** the user sends `lunch 12.50 [XYZ]`
- **THEN** the system SHALL reject that line as invalid, SHALL NOT save it, and SHALL surface an error indicating the currency is unknown

#### Scenario: Malformed currency segment is rejected as invalid line
- **WHEN** the user sends a line with a bracketed segment that is not exactly `[<3-uppercase-letters>]`
- **THEN** the system SHALL reject that line as invalid and SHALL NOT save it

### Requirement: Web UI cost form uses a currency drop-down

Create and edit forms for costs in the Web UI SHALL offer a drop-down of all currencies from the catalogue, ordered with the base currency first. When creating a new cost, the base currency SHALL be pre-selected.

#### Scenario: Base currency is the default selection
- **WHEN** a user opens the "create cost" form
- **THEN** the currency drop-down SHALL be pre-selected to the base currency

#### Scenario: Only catalogue currencies are selectable
- **WHEN** a user submits the cost form with a currency value that is not present in the catalogue
- **THEN** the system SHALL reject the submission with a validation error

### Requirement: Base amount is a dynamic display field

For each cost display, the system SHALL compute a `base_amount` as `amount * effective_rate(currency, cost_date)` using the effective-rate rule from the currency-management capability. `base_amount` SHALL NOT be stored in the database and SHALL be recomputed on every read.

#### Scenario: Base amount reflects updated historical rate
- **GIVEN** cost `C` was recorded on `2026-05-10` in currency `USD` with amount `100`, and the effective rate for `USD` on `2026-05-10` was `90`
- **WHEN** an administrator later changes the dated rate for `USD` on `2026-05-10` to `95`
- **THEN** subsequent displays of `C` SHALL show a base amount computed with `95`, without any modification to the stored cost record

#### Scenario: Base-currency cost has base amount equal to amount
- **WHEN** a cost is stored in the base currency
- **THEN** its displayed base amount SHALL equal its stored amount

### Requirement: Web UI displays base amount alongside amount

In every Web UI view that shows a cost amount (list tables and detail views), the system SHALL display the base amount in its own column or field immediately adjacent to the amount, together with the base currency code.

#### Scenario: Cost table shows both columns
- **WHEN** the Web UI renders the main cost table
- **THEN** each row SHALL show the stored amount with its currency code and, in the next column, the computed base amount with the base currency code

### Requirement: Bot rendering distinguishes base and non-base amounts

When the bot renders a cost:
- If the cost is in the base currency, the rendering SHALL show `<amount> <BASE_CODE>` (no square brackets).
- Otherwise the rendering SHALL show `<amount> <CUR_CODE> [<base_amount> <BASE_CODE>]` where `<base_amount>` is the dynamically computed base amount rounded to 2 decimal places.

#### Scenario: Base-currency cost rendering
- **GIVEN** base currency is `RUB` and cost `01: Квартира` is `32000` `RUB`
- **WHEN** the bot renders the cost
- **THEN** the output line SHALL be `01: Квартира 32_000 RUB` (no bracketed base amount)

#### Scenario: Non-base-currency cost rendering
- **GIVEN** base currency is `RUB`, cost `01: Квартира` is `32000` `SOM`, and the effective rate `SOM → RUB` for the cost date is `0.010005625`
- **WHEN** the bot renders the cost
- **THEN** the output line SHALL be `01: Квартира 32_000 SOM [320.18 RUB]`

### Requirement: Aggregation across currencies uses base amount

Any aggregation, total, or comparison across costs whose currencies may differ SHALL sum and compare base amounts, not stored amounts.

#### Scenario: Monthly total across mixed currencies
- **GIVEN** a user has one cost `100 USD` and one cost `1000 RUB` in the same month with `USD → RUB` effective rate `90` for both dates and base currency `RUB`
- **WHEN** the system computes the user's monthly total
- **THEN** the total SHALL equal `10_000 RUB` (i.e. `100 * 90 + 1000`)

### Requirement: Cost stored with structured amount and currency

Cost records SHALL persist the amount as a decimal value and the currency as a foreign-key reference to the currency catalogue. Amount extraction from message text SHALL NOT be used at read time.

#### Scenario: Amount is stored as decimal
- **WHEN** a cost is saved
- **THEN** the persisted amount SHALL be a decimal value equal to the parsed input amount, independent of the original message text
