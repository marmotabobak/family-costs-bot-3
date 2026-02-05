# E2E Test Plan — Admin Panel

## Approach
Full HTTP request-response journeys through the FastAPI app using `httpx.AsyncClient`
with `ASGITransport`. DB is mocked at the repository layer with a stateful in-memory
store (`FakeDB`); auth sessions are real (in-memory `auth_sessions` dict), so cookie
flow and CSRF validation are exercised end-to-end.

---

## 1. Auth Journey (7 tests)

| # | Scenario | Assert |
|---|----------|--------|
| 1.1 | `GET /` | 307 → `/costs` |
| 1.2 | `GET /costs` without cookie | 303 → `/login` |
| 1.3 | `POST /login` correct password | 303 → `/costs`, `costs_session` cookie set |
| 1.4 | Session cookie persists — `GET /logs` after login | 200, placeholder text |
| 1.5 | One wrong password, then correct | second login succeeds, `/logs` 200 |
| 1.6 | 5 failed logins from same IP | "Слишком много попыток" |
| 1.7 | Logout then access `/logs` | 303 → `/login` |

---

## 2. Users CRUD Journey (8 tests)

| # | Scenario | Assert |
|---|----------|--------|
| 2.1 | Login → `/users` (empty) → add → list | user name in list |
| 2.2 | Pre-seed user → edit name+ID → list | updated values in list |
| 2.3 | Pre-seed user → delete → list | empty-state message |
| 2.4 | Add with empty name | "Имя не может быть пустым" |
| 2.5 | Add with `telegram_id=abc` | "должен быть числом" |
| 2.6 | Add with `telegram_id=0` | "должен быть больше 0" |
| 2.7 | Add same `telegram_id` twice | "уже существует" |
| 2.8 | `GET /users/999/edit` | 404 |

---

## 3. Costs CRUD Journey (6 tests)

| # | Scenario | Assert |
|---|----------|--------|
| 3.1 | Login → `/costs` (empty) → add → list | item name in list |
| 3.2 | Pre-seed message → edit name/amount → list | updated text in list |
| 3.3 | Pre-seed message → delete → list | item name absent |
| 3.4 | Add with `amount=not-a-number` | "Некорректная сумма" |
| 3.5 | `GET /costs/999/edit` | 404 |
| 3.6 | `POST /costs/999/delete` | 404 |

---

## 4. Import Flow Journey (6 tests)

| # | Scenario | Assert |
|---|----------|--------|
| 4.1 | Token → upload JSON → select → save | 200 success page, item count |
| 4.2 | All import endpoints with bad token | 404 |
| 4.3 | `GET select` before upload | 303 back to upload |
| 4.4 | Save with no items selected | "Выберите хотя бы один товар" |
| 4.5 | Upload non-JSON blob | "Ошибка чтения файла" |
| 4.6 | Upload JSON without `checks` key | "Неверный формат файла" |

---

## 5. Security (4 tests)

| # | Scenario | Assert |
|---|----------|--------|
| 5.1 | `POST /users/add` with empty `csrf_token` | 403 |
| 5.2 | `POST /users/add` with tampered `csrf_token` | 403 |
| 5.3 | `GET` all admin routes without cookie | all 303 → `/login` |
| 5.4 | Token A upload, Token B select | B gets 303 (no data) |

---

## 6. Navigation & Health (3 tests)

| # | Scenario | Assert |
|---|----------|--------|
| 6.1 | `GET /health` without auth | 200 `{"status":"ok"}` |
| 6.2 | Authenticated `/logs` page | nav links to `/costs`, `/users`, `/logs`, `/logout` |
| 6.3 | `GET /login` when already authenticated | 303 → `/costs` |

---

**Total: 34 tests**
