# Spec Delta

## Purpose

Provides an administrator-managed catalogue of currencies and exchange rates that other capabilities use to record and compare monetary amounts across currencies with a single base currency.

## ADDED Requirements

### Requirement: Currency catalogue

The system SHALL maintain a catalogue of currencies, each identified by a 3-letter uppercase code (e.g. `RUB`, `USD`, `SOM`) that is unique across the catalogue.

#### Scenario: Codes are unique and normalized
- **WHEN** an administrator attempts to create a currency whose code, after uppercasing and trimming, matches an existing currency's code
- **THEN** the system SHALL reject the request with a clear duplicate-code error and no new currency is stored

#### Scenario: Code format is enforced
- **WHEN** an administrator submits a currency with a code that is not exactly three ASCII letters
- **THEN** the system SHALL reject the request with a validation error and no new currency is stored

### Requirement: Base-currency invariant

At all times when at least one currency exists, exactly one currency SHALL be flagged as the base currency. When no currency exists, no base currency exists.

#### Scenario: First currency becomes base automatically
- **WHEN** an administrator creates the very first currency in an empty catalogue
- **THEN** the system SHALL flag that currency as the base currency regardless of the administrator's input

#### Scenario: Promoting another currency demotes the previous base
- **WHEN** an administrator promotes a non-base currency to base while another base currency exists
- **THEN** the system SHALL atomically flag the newly selected currency as base and unflag the previous base

#### Scenario: Base currency cannot be demoted without a replacement
- **WHEN** an administrator attempts to unflag the current base currency without simultaneously promoting another currency
- **THEN** the system SHALL reject the request and keep the current base currency flagged

### Requirement: Default exchange rate per currency

Every currency SHALL have exactly one default exchange rate against the base currency, stored on the currency row itself and required at creation time. The base currency's default rate SHALL be `1`.

#### Scenario: Adding a non-base currency requires a default rate
- **WHEN** an administrator submits a new non-base currency without a positive default exchange rate
- **THEN** the system SHALL reject the request with a validation error

#### Scenario: Base currency default rate is fixed
- **WHEN** the system persists or displays the base currency
- **THEN** its default exchange rate SHALL be `1` and SHALL NOT be editable

### Requirement: Dated exchange rates

For each non-base currency, administrators MAY add zero or more dated exchange rates, each carrying a positive rate value and a specific date. Dates SHALL be unique per (currency, date).

#### Scenario: Duplicate dated rate rejected
- **WHEN** an administrator submits a dated rate for a currency and date that already has a dated rate
- **THEN** the system SHALL reject the request with a duplicate-date error

#### Scenario: Non-positive rate rejected
- **WHEN** an administrator submits a dated rate with a rate value of zero or a negative number
- **THEN** the system SHALL reject the request with a validation error

#### Scenario: Base currency has no dated rates
- **WHEN** an administrator attempts to add a dated exchange rate for the base currency
- **THEN** the system SHALL reject the request

### Requirement: Effective-rate selection

For a currency `C` (not the base) and a target date `D`, the effective exchange rate SHALL be:
1. The dated rate for `C` whose date is the greatest date less than or equal to `D`; otherwise
2. The default exchange rate for `C`.

For the base currency, the effective rate SHALL always be `1`.

#### Scenario: On-or-before dated rate wins over default
- **GIVEN** currency `USD` has default rate `90` and a dated rate `95` on `2026-05-10`
- **WHEN** the effective rate is requested for target date `2026-05-15`
- **THEN** the system SHALL return `95`

#### Scenario: Fall back to default when no dated rate on or before
- **GIVEN** currency `USD` has default rate `90` and a dated rate `95` on `2026-05-10`
- **WHEN** the effective rate is requested for target date `2026-05-01`
- **THEN** the system SHALL return `90`

#### Scenario: Latest dated rate on or before is chosen
- **GIVEN** currency `USD` has dated rates `95` on `2026-05-10` and `97` on `2026-05-12`
- **WHEN** the effective rate is requested for target date `2026-05-13`
- **THEN** the system SHALL return `97`

#### Scenario: Same-day dated rate is chosen
- **GIVEN** currency `USD` has a dated rate `95` on `2026-05-10`
- **WHEN** the effective rate is requested for target date `2026-05-10`
- **THEN** the system SHALL return `95`

### Requirement: Deletion protection

A currency SHALL NOT be deletable while any cost references it, and the base currency SHALL NOT be deletable while any other currency exists.

#### Scenario: Currency with referring costs cannot be deleted
- **GIVEN** currency `USD` is referenced by at least one cost
- **WHEN** an administrator attempts to delete `USD`
- **THEN** the system SHALL reject the request with a clear error message naming the constraint and SHALL NOT delete the currency

#### Scenario: Base currency cannot be deleted while others exist
- **GIVEN** the base currency `RUB` and at least one other currency exist
- **WHEN** an administrator attempts to delete `RUB`
- **THEN** the system SHALL reject the request with a clear error message

#### Scenario: Deleting a currency also removes its dated rates
- **GIVEN** currency `USD` has dated exchange rates and is not referenced by any cost
- **WHEN** an administrator deletes `USD`
- **THEN** the system SHALL remove the currency and all its dated exchange rates atomically

### Requirement: Admin-only access to configuration

Access to the currency catalogue and exchange-rate configuration (the `Конфигурация` Web UI section and its endpoints) SHALL be restricted to authenticated users with the `admin` role.

#### Scenario: Non-admin sees no navigation entry
- **WHEN** a user with a non-`admin` role loads any Web UI page
- **THEN** the navigation SHALL NOT show the `Конфигурация` entry

#### Scenario: Non-admin direct access denied
- **WHEN** a user with a non-`admin` role requests any URL under the `Конфигурация` section
- **THEN** the system SHALL respond with an access-denied error and SHALL NOT expose currency or rate data
