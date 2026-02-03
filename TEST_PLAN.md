# Test Plan for Family Costs Bot

**Project**: Family Costs Bot  
**Date**: 2026-02-03  
**Purpose**: Comprehensive test coverage organized by functional scenarios

---

## Table of Contents

1. [Use Case Scenarios](#1-use-case-scenarios)
2. [Message Parsing Scenarios](#2-message-parsing-scenarios)
3. [Message Handling Scenarios](#3-message-handling-scenarios)
4. [Menu & Reports Scenarios](#4-menu--reports-scenarios)
5. [Past Mode Scenarios](#5-past-mode-scenarios)
6. [Undo Operation Scenarios](#6-undo-operation-scenarios)
7. [Database Operations Scenarios](#7-database-operations-scenarios)
8. [Access Control Scenarios](#8-access-control-scenarios)
9. [Error Handling Scenarios](#9-error-handling-scenarios)
10. [Edge Cases & Boundary Testing](#10-edge-cases--boundary-testing)
11. [Integration & E2E Scenarios](#11-integration--e2e-scenarios)

---

## 1. Use Case Scenarios

This section describes real-world user workflows, what actions users can take, and all available options at each step.

### 1.1 Initial Interaction Use Cases

#### UC-1.1: New User First Contact
**Actor**: New user  
**Precondition**: User has never interacted with the bot  
**Main Flow**:
1. User sends `/start` command
2. Bot responds with welcome message and help text
3. **User Options**:
   - Option A: Send expense message immediately
   - Option B: Send `/help` to see format details
   - Option C: Send `/menu` to view expenses (if any exist)
   - Option D: Do nothing

**Alternative Flows**:
- **A1**: User sends expense → [Go to UC-2.1]
- **A2**: User sends `/help` → Bot shows help text → User can send expense or `/menu`
- **A3**: User sends `/menu` → [Go to UC-4.1]

**Postcondition**: User understands bot functionality

---

#### UC-1.2: Returning User Help Request
**Actor**: Returning user  
**Precondition**: User has used bot before  
**Main Flow**:
1. User sends `/help` command
2. Bot responds with help text showing:
   - Message format
   - Examples
   - Limits (max length, max lines, max line length)
3. **User Options**:
   - Option A: Send expense message
   - Option B: Send `/menu` to view expenses
   - Option C: Do nothing

**Alternative Flows**:
- **A1**: User sends expense → [Go to UC-2.1]
- **A2**: User sends `/menu` → [Go to UC-4.1]

---

### 1.2 Expense Entry Use Cases

#### UC-2.1: Single Expense Entry (Happy Path)
**Actor**: User  
**Precondition**: User is authenticated (if access control enabled)  
**Main Flow**:
1. User sends message: `"Продукты 100"`
2. Bot parses message (all valid)
3. Bot saves expense to database
4. Bot responds with success message: "✅ Записано 1 расход: • Продукты: 100"
5. Bot shows keyboard with "↩️ Отменить" button
6. **User Options**:
   - Option A: Click "↩️ Отменить" → [Go to UC-6.1]
   - Option B: Send another expense message → [Repeat UC-2.1 or UC-2.2]
   - Option C: Send `/menu` to view expenses → [Go to UC-4.1]
   - Option D: Do nothing

**Alternative Flows**:
- **A1**: Database error → Bot shows error message → User can retry
- **A2**: Invalid format → [Go to UC-2.5]

**Postcondition**: Expense saved with current date

---

#### UC-2.2: Multiple Expenses Entry (Happy Path)
**Actor**: User  
**Precondition**: User is authenticated  
**Main Flow**:
1. User sends message:
   ```
   Продукты 100
   Вода 50
   Хлеб 30
   ```
2. Bot parses message (all lines valid)
3. Bot saves all expenses to database
4. Bot responds: "✅ Записано 3 расхода: • Продукты: 100 • Вода: 50 • Хлеб: 30"
5. Bot shows keyboard with "↩️ Отменить" button
6. **User Options**:
   - Option A: Click "↩️ Отменить" → All 3 expenses deleted → [Go to UC-6.1]
   - Option B: Send another expense message
   - Option C: Send `/menu` to view expenses
   - Option D: Do nothing

**Postcondition**: All expenses saved with current date

---

#### UC-2.3: Expense Entry with Confirmation (Mixed Valid/Invalid)
**Actor**: User  
**Precondition**: User is authenticated  
**Main Flow**:
1. User sends message:
   ```
   Продукты 100
   invalid line without amount
   Вода 50
   ```
2. Bot parses message (2 valid, 1 invalid)
3. Bot asks for confirmation:
   - Shows invalid lines: "⚠️ Не удалось распарсить строки: • invalid line without amount"
   - Shows valid lines: "Успешно распарсены строки: • Продукты: 100 • Вода: 50"
   - Asks: "Записать распарсенные строки?"
4. Bot shows keyboard with:
   - "✅ Да, записать" button
   - "❌ Нет, отменить" button
5. **User Options**:
   - **Option A**: Click "✅ Да, записать"
     - Bot saves only valid lines (Продукты, Вода)
     - Bot shows success message
     - Bot shows "↩️ Отменить" button
     - [Go to UC-2.1 post-save options]
   - **Option B**: Click "❌ Нет, отменить"
     - Bot clears state
     - Bot shows: "❌ Галя, отмена! Исправьте строки и отправьте сообщение снова."
     - User can correct and resend
   - **Option C**: Send new message (state remains in confirmation)
     - New message processed independently
     - Previous confirmation state may expire

**Alternative Flows**:
- **A1**: User clicks confirm but database error → Bot shows error → User can retry
- **A2**: State expires → User clicks confirm → Bot shows "Нет данных" → User must resend

**Postcondition**: Only valid expenses saved (if confirmed)

---

#### UC-2.4: Expense Entry with Negative Amount (Correction)
**Actor**: User  
**Precondition**: User is authenticated  
**Main Flow**:
1. User sends message: `"корректировка -500"`
2. Bot parses and saves negative amount
3. Bot responds with success message
4. **User Options**:
   - Option A: Click "↩️ Отменить" → Correction deleted
   - Option B: View report via `/menu` → Negative amount shown in total
   - Option C: Send another expense

**Postcondition**: Negative expense saved (for corrections)

---

#### UC-2.5: Invalid Expense Format
**Actor**: User  
**Precondition**: User is authenticated  
**Main Flow**:
1. User sends invalid message: `"invalid message without amount"`
2. Bot cannot parse message
3. Bot responds: "❌ Не удалось распарсить сообщение. Данные не сохранены - повторите ввод."
4. Bot automatically sends help text
5. **User Options**:
   - Option A: Send corrected message → [Go to UC-2.1]
   - Option B: Send `/help` to see format again
   - Option C: Send `/menu` to view existing expenses
   - Option D: Do nothing

**Alternative Flows**:
- **A1**: Message too long (>4096 chars) → Bot shows specific error → User must shorten
- **A2**: Too many lines (>100) → Bot shows specific error → User must reduce lines
- **A3**: Line too long (>100 chars) → Bot shows specific error with problematic line → User must shorten

**Postcondition**: No data saved, user informed of error

---

### 1.3 Past Mode Use Cases

#### UC-3.1: Enable Past Mode and Enter Expense
**Actor**: User  
**Precondition**: User is authenticated, wants to enter expense for past month  
**Main Flow**:
1. User sends `/menu`
2. Bot shows menu with users
3. User clicks "📊 Мои расходы"
4. Bot shows period selection:
   - "📅 Этот месяц"
   - "📅 Прошлый месяц"
   - "📅 Другие месяцы"
   - "✏️ Внести расходы за другой месяц"
5. User clicks "✏️ Внести расходы за другой месяц"
6. Bot shows year selection (current year and previous year)
7. **User Options**:
   - **Option A**: Select current year
     - Bot shows months keyboard (only past months of current year)
     - User selects month (e.g., "Янв" for January)
     - Bot enables past mode
     - Bot shows warning: "⚠️ Внимание! Все последующие расходы будут внесены на 1-е число месяца: Январь 2024."
     - Bot shows "⏹️ Отключить прошлое" button
     - User sends expense: `"Продукты 100"`
     - Bot saves with date: 2024-01-01
     - [Continue to UC-3.2 options]
   - **Option B**: Select previous year
     - Bot shows all 12 months
     - User selects month
     - Bot enables past mode for that month/year
     - User sends expenses → Saved with past date

**Alternative Flows**:
- **A1**: No past months available for current year → Bot shows error → User must select previous year
- **A2**: User clicks month but changes mind → User can click "Отключить прошлое" → [Go to UC-3.3]

**Postcondition**: Past mode enabled, expenses saved with past date

---

#### UC-3.2: Multiple Expenses in Past Mode
**Actor**: User  
**Precondition**: Past mode enabled (from UC-3.1)  
**Main Flow**:
1. User has past mode enabled for specific month/year
2. User sends expense: `"Продукты 100"`
3. Bot saves with past date (1st of selected month)
4. Bot shows success message with "↩️ Отменить" button
5. Bot shows "⏹️ Отключить прошлое" button (if enabled)
6. **User Options**:
   - **Option A**: Send another expense
     - Expense saved with same past date
     - Past mode persists
   - **Option B**: Click "⏹️ Отключить прошлое"
     - [Go to UC-3.3]
   - **Option C**: Click "↩️ Отменить"
     - Last expense deleted
     - Past mode still enabled
   - **Option D**: Send `/menu` and view that month's report
     - All past mode expenses shown in selected month
   - **Option E**: Do nothing
     - Past mode remains enabled for next expenses

**Postcondition**: Multiple expenses saved with past date, past mode persists

---

#### UC-3.3: Disable Past Mode
**Actor**: User  
**Precondition**: Past mode enabled  
**Main Flow**:
1. User clicks "⏹️ Отключить прошлое" button
2. Bot clears past mode from state
3. Bot responds: "✅ Прошлое ушло. Дальнейшие расходы будут занесены на сегодня."
4. **User Options**:
   - Option A: Send expense → Saved with current date
   - Option B: Send `/menu` → View expenses
   - Option C: Re-enable past mode → [Go to UC-3.1]

**Alternative Flows**:
- **A1**: User clicks disable but state expired → Bot may show error or handle gracefully

**Postcondition**: Past mode disabled, future expenses use current date

---

### 1.4 Viewing Expenses Use Cases

#### UC-4.1: View Menu and Select User
**Actor**: User  
**Precondition**: User is authenticated, database has expense data  
**Main Flow**:
1. User sends `/menu`
2. Bot shows menu keyboard:
   - "📊 Мои расходы" (always shown)
   - "👤 Расходы <user_id>" (for each other user in database)
3. **User Options**:
   - **Option A**: Click "📊 Мои расходы"
     - [Go to UC-4.2]
   - **Option B**: Click "👤 Расходы <user_id>" (other user)
     - [Go to UC-4.3]
   - **Option C**: Send expense message
     - [Go to UC-2.1]
   - **Option D**: Do nothing

**Alternative Flows**:
- **A1**: No users in database → Only "Мои расходы" shown
- **A2**: Only current user has expenses → Only "Мои расходы" shown

**Postcondition**: User sees available expense views

---

#### UC-4.2: View Own Expenses - Period Selection
**Actor**: User  
**Precondition**: User clicked "Мои расходы"  
**Main Flow**:
1. Bot shows period selection keyboard:
   - "📅 Этот месяц"
   - "📅 Прошлый месяц"
   - "📅 Другие месяцы"
   - "✏️ Внести расходы за другой месяц"
2. **User Options**:
   - **Option A**: Click "📅 Этот месяц"
     - Bot shows report for current month
     - Shows all expenses with dates and total
     - [Go to UC-4.4]
   - **Option B**: Click "📅 Прошлый месяц"
     - Bot shows report for previous month
     - If current month is January → Shows December of previous year
     - [Go to UC-4.4]
   - **Option C**: Click "📅 Другие месяцы"
     - Bot shows list of available months
     - [Go to UC-4.5]
   - **Option D**: Click "✏️ Внести расходы за другой месяц"
     - [Go to UC-3.1]
   - **Option E**: Go back to menu
     - Send `/menu` again

**Postcondition**: User sees period selection options

---

#### UC-4.3: View Other User's Expenses
**Actor**: User  
**Precondition**: User clicked "Расходы <user_id>"  
**Main Flow**:
1. Bot shows period selection keyboard (same as UC-4.2 but without "Внести расходы за другой месяц"):
   - "📅 Этот месяц"
   - "📅 Прошлый месяц"
   - "📅 Другие месяцы"
2. **User Options**:
   - **Option A**: Click "📅 Этот месяц"
     - Bot shows report for other user's current month expenses
     - Shows: "Январь 2024" header, expenses, total
     - [Go to UC-4.4]
   - **Option B**: Click "📅 Прошлый месяц"
     - Bot shows report for other user's previous month
     - [Go to UC-4.4]
   - **Option C**: Click "📅 Другие месяцы"
     - Bot shows list of available months for that user
     - [Go to UC-4.5]
   - **Option D**: Go back to menu
     - Send `/menu` again

**Postcondition**: User views other user's expenses

---

#### UC-4.4: View Month Report
**Actor**: User  
**Precondition**: User selected period (this month, last month, or specific month)  
**Main Flow**:
1. Bot shows formatted report:
   ```
   Январь 2024
   
   Всего: 162.84
   
   15: Продукты 100.00
   20: Транспорт 50.50
   2: Заказ 12.34
   ```
2. **User Options**:
   - **Option A**: Send `/menu` to view different period
   - **Option B**: Send expense message to add new expense
   - **Option C**: View different user's expenses
   - **Option D**: Do nothing

**Alternative Flows**:
- **A1**: No expenses for period → Bot shows: "📭 Нет расходов за этот период."
- **A2**: Viewing other user with no expenses → Bot shows: "📭 У пользователя <id> нет расходов за этот период."

**Postcondition**: User sees expense report for selected period

---

#### UC-4.5: Select Specific Month from List
**Actor**: User  
**Precondition**: User clicked "Другие месяцы"  
**Main Flow**:
1. Bot shows keyboard with available months (sorted descending):
   - "Январь 2024"
   - "Декабрь 2023"
   - "Ноябрь 2023"
   - etc.
2. **User Options**:
   - **Option A**: Click specific month
     - Bot shows report for that month
     - [Go to UC-4.4]
   - **Option B**: No months available
     - Bot shows: "📭 Нет данных о расходах."
   - **Option C**: Go back
     - Click period selection again

**Alternative Flows**:
- **A1**: User has expenses in multiple years → All shown in list
- **A2**: User has expenses spanning many months → List may be long

**Postcondition**: User sees list of available months

---

### 1.5 Undo Operation Use Cases

#### UC-6.1: Undo Last Expense Entry
**Actor**: User  
**Precondition**: User just saved expense(s) and sees "↩️ Отменить" button  
**Main Flow**:
1. User clicks "↩️ Отменить" button
2. Bot deletes last saved expense(s) from database
3. Bot responds: "↩️ Галя, отмена! Удалено 1 запись." (or "N записей")
4. **User Options**:
   - Option A: Send new expense message
   - Option B: Send `/menu` to view expenses
   - Option C: Do nothing

**Alternative Flows**:
- **A1**: No saved IDs in state → Bot shows: "Нечего отменять"
- **A2**: Database error during delete → Bot shows: "Ошибка при удалении"
- **A3**: User tries to undo other user's expense → Only own expenses deleted (security)

**Postcondition**: Last expense(s) deleted from database

---

#### UC-6.2: Undo After Multiple Operations
**Actor**: User  
**Precondition**: User saved expenses, then saved more expenses  
**Main Flow**:
1. User saved expenses (IDs: [1, 2, 3])
2. User saved more expenses (IDs: [4, 5])
3. User clicks "↩️ Отменить"
4. **User Options**:
   - **Option A**: Bot deletes only last saved batch (IDs: [4, 5])
     - First batch (IDs: [1, 2, 3]) remains
   - **Option B**: User clicks undo again
     - Bot shows: "Нечего отменять" (no more IDs in state)

**Alternative Flows**:
- **A1**: State expired → Bot shows: "Нечего отменять"
- **A2**: IDs don't exist → Bot deletes 0 records → Shows: "Удалено 0 записей"

**Postcondition**: Only last batch deleted

---

### 1.6 Error Handling Use Cases

#### UC-7.1: Database Error During Save
**Actor**: User  
**Precondition**: User sends valid expense message  
**Main Flow**:
1. User sends expense: `"Продукты 100"`
2. Database error occurs (connection lost, constraint violation, etc.)
3. Bot shows: "❌ Ошибка сохранения в базу данных. Данные не сохранены - повторите ввод."
4. **User Options**:
   - Option A: Retry sending same message
   - Option B: Wait and retry later
   - Option C: Send `/menu` to check if previous expenses exist
   - Option D: Contact administrator

**Postcondition**: No data saved, user informed

---

#### UC-7.2: Access Denied
**Actor**: Unauthorized user  
**Precondition**: Access control enabled, user not in allowed list  
**Main Flow**:
1. User sends any message to bot
2. Bot checks user ID against allowed list
3. User not in list
4. Bot responds: "🚫 У вас нет доступа к этому боту."
5. Bot logs access denial
6. **User Options**:
   - Option A: Contact administrator to be added
   - Option B: Do nothing (cannot use bot)

**Postcondition**: User cannot use bot, access logged

---

#### UC-7.3: Message Too Long
**Actor**: User  
**Precondition**: User tries to send very long message  
**Main Flow**:
1. User sends message > 4096 characters
2. Bot detects length violation before parsing
3. Bot responds: "❌ Превышен максимальный размер сообщения (4096 символов). Данные не сохранены - повторите ввод."
4. **User Options**:
   - Option A: Split message into multiple smaller messages
   - Option B: Shorten message
   - Option C: Send `/help` to see limits

**Postcondition**: Message rejected, user informed

---

### 1.7 Complex Workflow Use Cases

#### UC-8.1: Complete Expense Management Workflow
**Actor**: User  
**Precondition**: User wants to manage expenses comprehensively  
**Main Flow**:
1. User sends `/start` → Sees welcome
2. User sends expense: `"Продукты 100"` → Saved
3. User sends `/menu` → Views current month expenses
4. User realizes mistake → Clicks "↩️ Отменить" → Expense deleted
5. User sends corrected expense: `"Продукты 150"`
6. User wants to add past expense → Clicks "Внести расходы за другой месяц"
7. User selects previous month → Past mode enabled
8. User sends: `"Забытый расход 50"` → Saved with past date
9. User clicks "Отключить прошлое" → Past mode disabled
10. User sends current expense: `"Текущий расход 200"` → Saved with current date
11. User sends `/menu` → Views both months separately
12. User views previous month → Sees "Забытый расход"
13. User views current month → Sees "Текущий расход"

**User Options at Each Step**:
- Can undo any save
- Can view reports anytime
- Can enable/disable past mode
- Can add corrections (negative amounts)
- Can view other users' expenses

**Postcondition**: User successfully manages expenses across time periods

---

#### UC-8.2: Family Multi-User Workflow
**Actor**: Multiple family members  
**Precondition**: Multiple users have access to bot  
**Main Flow**:
1. **User A** sends expense: `"Продукты 100"` → Saved for User A
2. **User B** sends expense: `"Транспорт 50"` → Saved for User B
3. **User A** sends `/menu`:
   - Sees "📊 Мои расходы"
   - Sees "👤 Расходы <User B ID>"
4. **User A** clicks "Мои расходы" → Sees only own expenses
5. **User A** clicks "Расходы <User B ID>" → Sees User B's expenses
6. **User B** sends `/menu`:
   - Sees own expenses
   - Sees "👤 Расходы <User A ID>"
7. **User B** views User A's expenses → Sees "Продукты 100"

**User Options**:
- Each user can only add expenses for themselves
- Each user can view all users' expenses
- Each user can only undo own expenses
- Expenses are isolated by user_id

**Postcondition**: Multiple users track expenses independently, can view each other's data

---

#### UC-8.3: Correction Workflow
**Actor**: User  
**Precondition**: User made mistake in expense entry  
**Main Flow**:
1. User sent: `"Продукты 200"` → Saved
2. User realizes should be 150
3. **Option A**: Undo and resend
   - User clicks "↩️ Отменить" → Deletes "Продукты 200"
   - User sends: `"Продукты 150"` → Saved correctly
4. **Option B**: Add correction
   - User sends: `"Корректировка продуктов -50"` → Negative amount saved
   - Total shows: 200 - 50 = 150 effectively
5. User views report → Sees both entries or corrected total

**User Options**:
- Undo and correct
- Add negative correction
- Both methods valid

**Postcondition**: Mistake corrected

---

### 1.8 Edge Case Use Cases

#### UC-9.1: Empty Database Workflow
**Actor**: New user  
**Precondition**: No expenses in database  
**Main Flow**:
1. User sends `/menu`
2. Bot shows only "📊 Мои расходы" (no other users)
3. User clicks "Мои расходы"
4. User clicks "Этот месяц"
5. Bot shows: "📭 Нет расходов за этот период."
6. User clicks "Другие месяцы"
7. Bot shows: "📭 Нет данных о расходах."
8. **User Options**:
   - Option A: Send first expense
   - Option B: Enable past mode to add historical data
   - Option C: Do nothing

**Postcondition**: User understands no data exists, can start adding

---

#### UC-9.2: Maximum Limits Workflow
**Actor**: User  
**Precondition**: User wants to add many expenses  
**Main Flow**:
1. User tries to send 101 lines → Bot rejects: "❌ Превышено максимальное число строк (100)"
2. User sends 100 lines → Bot accepts and saves all
3. User tries to send line with 101 characters → Bot rejects: "❌ Превышен максимальный размер строки"
4. User sends line with exactly 100 characters → Bot accepts
5. User tries to send message with 4097 characters → Bot rejects
6. User sends message with exactly 4096 characters → Bot accepts

**User Options**:
- Split into multiple messages
- Shorten content
- Stay within limits

**Postcondition**: User understands limits and works within them

---

### 1.9 Use Case Summary Table

| Use Case ID | Name | Priority | Status | Test Coverage |
|-------------|------|----------|--------|---------------|
| UC-1.1 | New User First Contact | High | ✅ Covered | `test_common_handlers.py` |
| UC-1.2 | Returning User Help Request | Medium | ✅ Covered | `test_common_handlers.py` |
| UC-2.1 | Single Expense Entry | High | ✅ Covered | `test_handle_message_e2e.py` |
| UC-2.2 | Multiple Expenses Entry | High | ✅ Covered | `test_handle_message_e2e.py` |
| UC-2.3 | Expense with Confirmation | High | ✅ Covered | `test_messages_handler.py` |
| UC-2.4 | Negative Amount Entry | Medium | ✅ Covered | `test_handle_message_e2e.py` |
| UC-2.5 | Invalid Format Handling | High | ✅ Covered | `test_handle_message_e2e.py` |
| UC-3.1 | Enable Past Mode | High | ✅ Covered | `test_menu_handler.py` |
| UC-3.2 | Multiple Expenses in Past Mode | High | ✅ Covered | `test_handle_message_e2e.py` |
| UC-3.3 | Disable Past Mode | High | ✅ Covered | `test_menu_handler.py` |
| UC-4.1 | View Menu | High | ✅ Covered | `test_menu_handler.py` |
| UC-4.2 | Own Expenses Period Selection | High | ✅ Covered | `test_menu_handler.py` |
| UC-4.3 | Other User's Expenses | Medium | ✅ Covered | `test_menu_handler.py` |
| UC-4.4 | View Month Report | High | ✅ Covered | `test_menu_handler.py` |
| UC-4.5 | Select Specific Month | Medium | ✅ Covered | `test_menu_handler.py` |
| UC-6.1 | Undo Last Entry | High | ✅ Covered | `test_handle_message_e2e.py` |
| UC-6.2 | Undo After Multiple Operations | Medium | ⚠️ Partial | Needs explicit test |
| UC-7.1 | Database Error | High | ✅ Covered | `test_messages_handler.py` |
| UC-7.2 | Access Denied | High | ✅ Covered | `test_middleware.py` |
| UC-7.3 | Message Too Long | Medium | ✅ Covered | `test_message_parser.py` |
| UC-8.1 | Complete Expense Management | High | ⚠️ Partial | Covered in parts |
| UC-8.2 | Multi-User Workflow | High | ⚠️ Partial | Covered in isolation |
| UC-8.3 | Correction Workflow | Medium | ✅ Covered | Multiple tests |
| UC-9.1 | Empty Database | Low | ⚠️ Partial | Needs explicit test |
| UC-9.2 | Maximum Limits | Medium | ✅ Covered | `test_message_parser.py` |

---

## 2. Message Parsing Scenarios

## 2. Message Parsing Scenarios

### 2.1 Basic Parsing

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Single line with integer amount | ✅ Covered | `test_message_parser.py::TestParseMessageValidSingleLine::test_simple_integer` | |
| Single line with decimal (dot) | ✅ Covered | `test_message_parser.py::TestParseMessageValidSingleLine::test_decimal_with_dot` | |
| Single line with decimal (comma) | ✅ Covered | `test_message_parser.py::TestParseMessageValidSingleLine::test_decimal_with_comma` | |
| Negative amount | ✅ Covered | `test_message_parser.py::TestParseMessageValidSingleLine::test_negative_amount` | |
| Positive sign (+) | ✅ Covered | `test_message_parser.py::TestParseMessageValidSingleLine::test_positive_sign` | |
| Zero amount | ✅ Covered | `test_message_parser.py::TestParseMessageEdgeCases::test_zero_amount` | |
| Large amount | ✅ Covered | `test_message_parser.py::TestParseMessageEdgeCases::test_large_amount` | |

### 2.2 Multiple Lines Parsing

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Multiple valid lines | ✅ Covered | `test_message_parser.py::TestParseMessageMultipleLines::test_multiple_valid_lines` | |
| Lines with empty lines | ✅ Covered | `test_message_parser.py::TestParseMessageMultipleLines::test_with_empty_lines` | |
| Mixed valid/invalid lines | ✅ Covered | `test_message_parser.py::TestParseMessageMixedLines::test_valid_and_invalid_lines` | |
| Multiple invalid lines | ✅ Covered | `test_message_parser.py::TestParseMessageMixedLines::test_multiple_invalid_lines` | |

### 2.3 Invalid Input Handling

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| None input | ✅ Covered | `test_message_parser.py::TestParseMessageReturnsNone::test_none_input` | |
| Empty string | ✅ Covered | `test_message_parser.py::TestParseMessageReturnsNone::test_empty_string` | |
| Whitespace only | ✅ Covered | `test_message_parser.py::TestParseMessageReturnsNone::test_whitespace_only` | |
| No amount | ✅ Covered | `test_message_parser.py::TestParseMessageReturnsNone::test_no_amount` | |

### 2.4 Special Characters & Unicode

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Unicode characters | ✅ Covered | `test_message_parser.py::TestParseMessageUnicodeAndSpecialCharacters::test_unicode_characters` | |
| Emoji in name | ✅ Covered | `test_message_parser.py::TestParseMessageUnicodeAndSpecialCharacters::test_emoji_in_name` | |
| Special characters (#, @, etc.) | ✅ Covered | `test_message_parser.py::TestParseMessageUnicodeAndSpecialCharacters::test_special_characters_in_name` | |
| HTML characters | ✅ Covered | `test_message_parser.py::TestParseMessageUnicodeAndSpecialCharacters::test_html_characters` | |
| Cyrillic + Latin mixed | ✅ Covered | `test_message_parser.py::TestParseMessageUnicodeAndSpecialCharacters::test_cyrillic_and_latin_mixed` | |
| Chinese characters | ✅ Covered | `test_message_parser.py::TestParseMessageUnicodeAndSpecialCharacters::test_chinese_characters` | |
| Arabic characters | ✅ Covered | `test_message_parser.py::TestParseMessageUnicodeAndSpecialCharacters::test_arabic_characters` | |

### 2.5 Decimal Edge Cases

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Decimal at start (.5) | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalEdgeCases::test_decimal_at_start` | Should be invalid |
| Decimal at end (5.) | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalEdgeCases::test_decimal_at_end` | Should be invalid |
| Multiple decimal separators | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalEdgeCases::test_multiple_decimal_separators_fails` | |
| Scientific notation | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalEdgeCases::test_scientific_notation_fails` | |
| Very large decimal | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalEdgeCases::test_very_large_decimal` | |
| Leading zeros | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalEdgeCases::test_leading_zeros` | |
| Trailing zeros | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalEdgeCases::test_trailing_zeros` | |
| Negative zero | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalEdgeCases::test_negative_zero` | |
| Very small decimal | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalEdgeCases::test_very_small_decimal` | |
| Many decimal places | ✅ Covered | `test_message_parser.py::TestParseMessageAmountEdgeCases::test_amount_with_many_decimal_places` | |

### 2.6 Cost Name Edge Cases

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Name with only spaces | ✅ Covered | `test_message_parser.py::TestParseMessageCostNameEdgeCases::test_cost_name_with_only_spaces` | |
| Empty after strip | ✅ Covered | `test_message_parser.py::TestParseMessageCostNameEdgeCases::test_cost_name_empty_after_strip` | |
| Tabs instead of spaces | ✅ Covered | `test_message_parser.py::TestParseMessageCostNameEdgeCases::test_cost_name_with_tabs` | |
| Name with newlines | ✅ Covered | `test_message_parser.py::TestParseMessageCostNameEdgeCases::test_cost_name_with_newlines` | |
| Very long name | ✅ Covered | `test_message_parser.py::TestParseMessageCostNameEdgeCases::test_very_long_cost_name` | |
| Many spaces in name | ✅ Covered | `test_message_parser.py::TestParseMessageCostNameEdgeCases::test_cost_name_with_many_spaces` | |

### 2.7 Line Endings

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Windows line endings (\r\n) | ✅ Covered | `test_message_parser.py::TestParseMessageLineEndings::test_windows_line_endings` | |
| Mac line endings (\r) | ✅ Covered | `test_message_parser.py::TestParseMessageLineEndings::test_mac_line_endings` | |
| Unix line endings (\n) | ✅ Covered | `test_message_parser.py::TestParseMessageLineEndings::test_unix_line_endings` | |
| Mixed line endings | ✅ Covered | `test_message_parser.py::TestParseMessageLineEndings::test_mixed_line_endings` | |

### 2.8 Message Limits

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Message too long (>4096) | ✅ Covered | `test_message_parser.py::TestMessageLimits::test_message_too_long_raises_exception` | |
| Too many lines (>100) | ✅ Covered | `test_message_parser.py::TestMessageLimits::test_too_many_lines_raises_exception` | |
| Line too long (>100) | ✅ Covered | `test_message_parser.py::TestMessageLimits::test_line_too_long_raises_exception` | |
| Max message length boundary (4096) | ✅ Covered | `test_message_parser.py::TestMessageLimits::test_max_message_length_boundary` | |
| Max lines boundary (100) | ✅ Covered | `test_message_parser.py::TestMessageLimits::test_max_lines_boundary` | |
| Max line length boundary (100) | ✅ Covered | `test_message_parser.py::TestMessageLimits::test_max_line_length_boundary` | |

### 2.9 Whitespace Handling

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Leading whitespace | ✅ Covered | `test_message_parser.py::TestParseMessageValidSingleLine::test_leading_whitespace` | |
| Trailing whitespace | ✅ Covered | `test_message_parser.py::TestParseMessageValidSingleLine::test_trailing_whitespace` | |
| Multiple spaces between name and amount | ✅ Covered | `test_message_parser.py::TestParseMessageValidSingleLine::test_multiple_spaces_between` | |

### 2.10 Error Handling

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| InvalidOperation exception | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalError::test_invalid_decimal_operation` | |

---

## 3. Message Handling Scenarios

### 3.1 Basic Message Handling

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| No text returns early | ✅ Covered | `test_messages_handler.py::TestHandleMessage::test_no_text_returns_early` | |
| No from_user returns early | ✅ Covered | `test_messages_handler.py::TestHandleMessage::test_no_from_user_returns_early` | |
| Invalid format sends error + help | ✅ Covered | `test_messages_handler.py::TestHandleMessage::test_invalid_format_sends_error_and_help` | |
| DB error sends error message | ✅ Covered | `test_messages_handler.py::TestHandleMessage::test_db_error_sends_error_message` | |
| Success sends success message | ✅ Covered | `test_messages_handler.py::TestHandleMessage::test_success_sends_success_message` | |
| Mixed lines asks confirmation | ✅ Covered | `test_messages_handler.py::TestHandleMessage::test_mixed_lines_asks_confirmation` | |

### 3.2 Confirmation Flow

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Confirm saves costs | ✅ Covered | `test_messages_handler.py::TestHandleConfirm::test_saves_on_confirm` | |
| Cancel clears state | ✅ Covered | `test_messages_handler.py::TestHandleCancel::test_cancel_clears_state` | |
| Confirmation keyboard format | ✅ Covered | `test_messages_handler.py::TestBuildConfirmationKeyboard` | |
| Confirmation message format | ✅ Covered | `test_messages_handler.py::TestFormatConfirmationMessage` | |

### 3.3 Success Message Formatting

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Pluralization (1 расход) | ✅ Covered | `test_messages_handler.py::TestFormatSuccessMessage::test_pluralization` | |
| Pluralization (2 расхода) | ✅ Covered | `test_messages_handler.py::TestFormatSuccessMessage::test_pluralization` | |
| Pluralization (5 расходов) | ✅ Covered | `test_messages_handler.py::TestFormatSuccessMessage::test_pluralization` | |
| Success keyboard format | ✅ Covered | `test_messages_handler.py::TestBuildSuccessKeyboard` | |

### 3.4 Past Mode Integration

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Past mode date used when enabled | ⚠️ Partial | Needs explicit test | Should verify date from state |
| Current date used when past mode disabled | ⚠️ Partial | Needs explicit test | Should verify current date |
| Past mode persists across messages | ❌ Not Covered | | |
| Past mode disabled mid-transaction | ❌ Not Covered | | |

### 3.5 HTML Escaping

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| HTML characters escaped in confirmation | ❌ Not Covered | | Test `<script>` tags |
| HTML characters escaped in success | ❌ Not Covered | | Test `&`, `<`, `>` |
| Very long cost names in messages | ❌ Not Covered | | Test message truncation |

---

## 4. Menu & Reports Scenarios

### 4.1 Menu Command

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| /menu shows menu with keyboard | ✅ Covered | `test_menu_handler.py::TestMenuCommand::test_sends_menu_with_keyboard` | |
| Returns early without user | ✅ Covered | `test_menu_handler.py::TestMenuCommand::test_returns_early_without_user` | |
| Empty user list shows only "Мои расходы" | ✅ Covered | `test_menu_handler.py::TestBuildMenuKeyboard::test_empty_user_list` | |
| Current user excluded from list | ✅ Covered | `test_menu_handler.py::TestBuildMenuKeyboard::test_current_user_excluded` | |
| All users shown | ✅ Covered | `test_menu_handler.py::TestBuildMenuKeyboard::test_all_users_shown` | |

### 4.2 Period Selection

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| "Мои расходы" shows period selection | ✅ Covered | `test_menu_handler.py::TestHandleMyCosts::test_shows_period_selection` | |
| "Расходы <user_id>" shows period selection | ✅ Covered | `test_menu_handler.py::TestHandleUserCosts::test_shows_period_selection_for_target_user` | |
| Period keyboard has 4 buttons for own | ✅ Covered | `test_menu_handler.py::TestBuildPeriodKeyboard::test_has_four_buttons_for_own` | |
| Period keyboard has 3 buttons for other | ✅ Covered | `test_menu_handler.py::TestBuildPeriodKeyboard::test_has_three_buttons_for_other` | |
| "Этот месяц" shows current month report | ✅ Covered | `test_menu_handler.py::TestHandlePeriodSelection::test_this_month_shows_report` | |
| "Прошлый месяц" shows previous month | ⚠️ Partial | Needs explicit test | Test January edge case |
| "Другие месяцы" shows months list | ✅ Covered | `test_menu_handler.py::TestHandlePeriodSelection::test_other_shows_months_list` | |

### 4.3 Month Selection

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Month selection shows report | ✅ Covered | `test_menu_handler.py::TestHandleMonthSelection::test_shows_month_report` | |
| Months keyboard format | ✅ Covered | `test_menu_handler.py::TestBuildMonthsKeyboard` | |
| Empty months list handling | ❌ Not Covered | | Test when no data available |

### 4.4 Report Formatting

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Empty report for own costs | ✅ Covered | `test_menu_handler.py::TestFormatMonthReport::test_empty_costs_own` | |
| Empty report for other user | ✅ Covered | `test_menu_handler.py::TestFormatMonthReport::test_empty_costs_other_user` | |
| Report with costs | ✅ Covered | `test_menu_handler.py::TestFormatMonthReport::test_report_with_costs` | |
| Report total calculation | ✅ Covered | `test_menu_handler.py::TestFormatMonthReport::test_report_with_costs` | |
| Report date formatting | ✅ Covered | `test_menu_handler.py::TestFormatMonthReport::test_report_with_costs` | |
| Report with negative amounts | ❌ Not Covered | | Test corrections in report |
| Report sorting by date | ⚠️ Partial | Covered in integration tests | Verify ascending order |
| Report with expenses on same day | ❌ Not Covered | | Test multiple expenses same date |

### 4.5 Period Edge Cases

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| "Прошлый месяц" in January | ❌ Not Covered | | Should show December previous year |
| Invalid callback data format | ❌ Not Covered | | Test error handling |
| Non-existent user_id in callback | ❌ Not Covered | | Test error handling |
| Invalid year/month in callback | ❌ Not Covered | | Test error handling |
| Year/month out of valid range | ❌ Not Covered | | Test boundary dates |

---

## 5. Past Mode Scenarios

### 5.1 Past Mode Activation

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| "Внести расходы за другой месяц" shows year selection | ✅ Covered | `test_menu_handler.py::TestHandleEnterPast::test_shows_year_selection` | |
| Year selection shows current and previous year | ✅ Covered | `test_menu_handler.py::TestBuildPastYearsKeyboard::test_has_two_years` | |
| Month selection shows only past months (current year) | ✅ Covered | `test_menu_handler.py::TestBuildPastMonthsKeyboard::test_current_year_shows_only_past_months` | |
| Month selection shows all months (previous year) | ✅ Covered | `test_menu_handler.py::TestBuildPastMonthsKeyboard::test_past_year_shows_all_months` | |
| Past mode activation saves year/month | ✅ Covered | `test_menu_handler.py::TestHandleEnterPastMonth::test_enables_past_mode` | |
| Past mode message shows correct month | ✅ Covered | `test_menu_handler.py::TestHandleEnterPastMonth::test_shows_warning_message` | |

### 5.2 Past Mode Usage

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Past mode expense saved with correct date | ✅ Covered | `test_handle_message_e2e.py::TestPastModeE2E::test_past_mode_basic_flow` | |
| Past mode persists across messages | ✅ Covered | `test_handle_message_e2e.py::TestPastModeE2E::test_past_mode_basic_flow` | |
| Past mode disabled mid-session | ✅ Covered | `test_handle_message_e2e.py::TestPastModeE2E::test_past_mode_basic_flow` | |
| Past mode with leap year (Feb 29) | ✅ Covered | `test_handle_message_e2e.py::TestEdgeCasesE2E::test_past_mode_leap_year` | |
| Past mode year boundary | ✅ Covered | `test_handle_message_e2e.py::TestEdgeCasesE2E::test_past_mode_year_boundary` | |

### 5.3 Past Mode Deactivation

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| "Отключить прошлое" clears past mode | ✅ Covered | `test_menu_handler.py::TestHandleDisablePast::test_disables_past_mode` | |
| Shows confirmation message | ✅ Covered | `test_menu_handler.py::TestHandleDisablePast::test_shows_confirmation_message` | |
| Disable past keyboard format | ✅ Covered | `test_menu_handler.py::TestBuildDisablePastKeyboard` | |

### 5.4 Past Mode Edge Cases

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Past mode with year < current year | ⚠️ Partial | Covered in E2E | Needs explicit unit test |
| Past mode with invalid year/month | ❌ Not Covered | | Test error handling |
| Past mode disabled mid-transaction | ❌ Not Covered | | Test state consistency |
| Past mode with year 1900 | ❌ Not Covered | | Test edge dates |
| Past mode with year 2100 | ❌ Not Covered | | Test edge dates |
| No available months for year | ⚠️ Partial | Covered in handler | Needs explicit test |

---

## 6. Undo Operation Scenarios

### 6.1 Basic Undo

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Undo deletes records | ✅ Covered | `test_messages_handler.py::TestHandleUndo::test_undo_uses_fsm_ids` | |
| Undo uses FSM IDs | ✅ Covered | `test_messages_handler.py::TestHandleUndo::test_undo_uses_fsm_ids` | |
| Undo without IDs shows error | ✅ Covered | `test_messages_handler.py::TestHandleUndo::test_undo_without_ids` | |
| Undo deletes only own records | ✅ Covered | `test_handle_message_e2e.py::TestUndoE2E::test_undo_does_not_delete_other_users` | |

### 6.2 Undo Edge Cases

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Multiple undo attempts | ✅ Covered | `test_handle_message_e2e.py::TestEdgeCasesE2E::test_multiple_undo_attempts` | |
| Undo with empty IDs list | ❌ Not Covered | | Test error handling |
| Undo with non-existent IDs | ❌ Not Covered | | Test partial deletion |
| Undo with mixed ownership | ❌ Not Covered | | Test security |
| Undo with expired state | ❌ Not Covered | | Test state timeout |
| Undo after database error | ❌ Not Covered | | Test rollback |

---

## 7. Database Operations Scenarios

### 7.1 Save Operations

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Save single message | ✅ Covered | `test_database_operations.py::TestFullMessageFlow::test_full_message_flow` | |
| Save multiple messages | ✅ Covered | `test_database_operations.py::TestMultipleMessages::test_save_multiple_messages` | |
| Save with default created_at | ✅ Covered | `test_database_operations.py::TestTimestamps::test_created_at_is_recent` | |
| Save with custom created_at | ✅ Covered | `test_database_operations.py::TestTimestamps::test_created_at_has_timezone` | |
| Save with timezone-aware datetime | ✅ Covered | `test_database_operations.py::TestTimestamps::test_created_at_has_timezone` | |
| Save with very long text | ❌ Not Covered | | Test text length limits |
| Save with special characters | ✅ Covered | Integration tests | UTF-8 encoding |

### 7.2 Delete Operations

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Delete single message | ✅ Covered | `test_database_operations.py::TestDeleteMessages::test_delete_only_own_messages` | |
| Delete multiple messages | ✅ Covered | `test_database_operations.py::TestDeleteMessages::test_delete_only_own_messages` | |
| Delete only own messages | ✅ Covered | `test_database_operations.py::TestDeleteMessages::test_delete_only_own_messages` | |
| Delete with empty IDs list | ❌ Not Covered | | Test edge case |
| Delete with non-existent IDs | ❌ Not Covered | | Test partial deletion |
| Delete with invalid user_id | ❌ Not Covered | | Test security |

### 7.3 Query Operations

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Get costs for current month | ✅ Covered | Integration tests | |
| Get costs for previous month | ✅ Covered | Integration tests | |
| Get costs for month with no data | ⚠️ Partial | Covered in menu tests | Needs explicit test |
| Get costs sorted by date | ✅ Covered | `test_database_operations.py::TestTimestamps::test_messages_ordered_by_created_at` | |
| Get available months | ✅ Covered | `test_database_operations.py::TestRepositoryFunctions::test_get_user_available_months` | |
| Get unique user IDs | ✅ Covered | Integration tests | |
| Get user costs stats (empty) | ✅ Covered | `test_database_operations.py::TestRepositoryFunctions::test_get_user_costs_stats_empty` | |
| Get user costs stats (with expenses) | ✅ Covered | `test_database_operations.py::TestRepositoryFunctions::test_get_user_costs_stats_with_expenses` | |
| Get recent costs | ✅ Covered | `test_database_operations.py::TestRepositoryFunctions::test_get_user_recent_costs` | |

### 7.4 Data Isolation

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Multiple users isolation | ✅ Covered | `test_database_operations.py::TestMultipleMessages::test_multiple_users_isolation` | |
| User sees only own data | ✅ Covered | Multiple tests | |

### 7.5 Constraints & Schema

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| user_id constraint rejects zero | ✅ Covered | `test_database_operations.py::TestConstraints::test_user_id_constraint_rejects_zero` | |
| user_id constraint rejects negative | ✅ Covered | `test_database_operations.py::TestConstraints::test_user_id_constraint_rejects_negative` | |
| user_id constraint allows positive | ✅ Covered | `test_database_operations.py::TestConstraints::test_user_id_constraint_allows_positive` | |
| Check constraint exists in schema | ✅ Covered | `test_database_operations.py::TestConstraints::test_check_constraint_exists_in_schema` | |
| Index on user_id exists | ✅ Covered | `test_database_operations.py::TestDatabaseSchema::test_user_id_index_exists` | |
| Primary key exists | ✅ Covered | `test_database_operations.py::TestDatabaseSchema::test_primary_key_exists` | |

### 7.6 Transactions

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Transaction rollback on error | ✅ Covered | `test_database_operations.py::TestTransactionBehavior::test_transaction_rollback_on_error` | |
| Save with commit visible in other session | ✅ Covered | `test_database_operations.py::TestTransactionBehavior::test_save_message_with_commit` | |
| Multiple saves in single transaction | ⚠️ Partial | Covered in E2E | Needs explicit test |
| Concurrent transactions isolation | ❌ Not Covered | | Test race conditions |

---

## 8. Access Control Scenarios

### 8.1 Middleware Access Control

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Empty allowed_user_ids allows all | ✅ Covered | `test_middleware.py::TestAllowedUsersMiddleware::test_allows_all_when_list_empty` | |
| User in list allowed | ✅ Covered | `test_middleware.py::TestAllowedUsersMiddleware::test_allows_user_in_list` | |
| User not in list denied | ✅ Covered | `test_middleware.py::TestAllowedUsersMiddleware::test_denies_user_not_in_list` | |
| Non-Message events passed | ✅ Covered | `test_middleware.py::TestAllowedUsersMiddleware::test_passes_non_message_events` | |
| Message without user passed | ✅ Covered | `test_middleware.py::TestAllowedUsersMiddleware::test_passes_message_without_user` | |
| Access denied logged | ✅ Covered | `test_middleware.py::TestAllowedUsersMiddleware::test_logs_denied_access` | |

### 8.2 Access Control Edge Cases

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Very large user_id | ❌ Not Covered | | Test boundary |
| Negative user_id in config | ❌ Not Covered | | Test parsing |
| Zero user_id | ❌ Not Covered | | Test edge case |
| Malformed allowed_user_ids string | ❌ Not Covered | | Test config parsing |
| Concurrent access checks | ❌ Not Covered | | Test race conditions |

---

## 9. Error Handling Scenarios

### 9.1 Database Errors

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| SQLAlchemyError during save | ✅ Covered | `test_messages_handler.py::TestHandleMessage::test_db_error_sends_error_message` | |
| SQLAlchemyError during undo | ❌ Not Covered | | Test rollback |
| Connection lost during operation | ❌ Not Covered | | Test reconnection |
| Transaction timeout | ❌ Not Covered | | Test timeout handling |
| Connection pool exhaustion | ❌ Not Covered | | Test resource limits |

### 9.2 Parsing Errors

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| MessageMaxLengthExceed exception | ✅ Covered | `test_messages_handler.py` + parser tests | |
| MessageMaxLinesCountExceed exception | ✅ Covered | `test_messages_handler.py` + parser tests | |
| MessageMaxLineLengthExceed exception | ✅ Covered | `test_messages_handler.py` + parser tests | |
| InvalidOperation exception | ✅ Covered | `test_message_parser.py::TestParseMessageDecimalError` | |

### 9.3 State Management Errors

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Missing valid_costs in state | ⚠️ Partial | Covered in confirm handler | Needs explicit test |
| Missing last_saved_ids in undo | ✅ Covered | `test_messages_handler.py::TestHandleUndo::test_undo_without_ids` | |
| Expired state handling | ❌ Not Covered | | Test state timeout |
| State conflicts (multiple operations) | ❌ Not Covered | | Test concurrent state |

---

## 10. Edge Cases & Boundary Testing

### 10.1 Boundary Values

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Message length: 4095, 4096, 4097 | ✅ Covered | `test_message_parser.py::TestMessageLimits` | |
| Line count: 99, 100, 101 | ✅ Covered | `test_message_parser.py::TestMessageLimits` | |
| Line length: 99, 100, 101 | ✅ Covered | `test_message_parser.py::TestMessageLimits` | |
| Amount: -999999999.99, 0, 999999999.99 | ⚠️ Partial | Covered in parser tests | Needs explicit boundary test |
| Year boundaries (1900, 2100) | ❌ Not Covered | | Test date limits |
| Month boundaries (Jan 1, Dec 31) | ❌ Not Covered | | Test date edge cases |

### 10.2 Special Input Cases

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Very long cost names | ✅ Covered | `test_message_parser.py::TestParseMessageCostNameEdgeCases::test_very_long_cost_name` | |
| Amount with many decimal places | ✅ Covered | `test_message_parser.py::TestParseMessageAmountEdgeCases::test_amount_with_many_decimal_places` | |
| Negative large amount | ✅ Covered | `test_message_parser.py::TestParseMessageAmountEdgeCases::test_negative_large_amount` | |
| Very small amount | ✅ Covered | `test_message_parser.py::TestParseMessageAmountEdgeCases::test_very_small_amount` | |

### 10.3 Concurrent Operations

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Concurrent saves from same user | ✅ Covered | `test_handle_message_e2e.py::TestEdgeCasesE2E::test_concurrent_saves` | |
| Concurrent saves from different users | ⚠️ Partial | Covered in isolation tests | Needs explicit concurrent test |
| Concurrent menu operations | ❌ Not Covered | | Test race conditions |
| Concurrent undo operations | ❌ Not Covered | | Test state conflicts |

---

## 11. Integration & E2E Scenarios

### 11.1 Full Message Flow

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Parse → Save → Retrieve → Delete | ✅ Covered | `test_database_operations.py::TestFullMessageFlow` | |
| Single cost saved E2E | ✅ Covered | `test_handle_message_e2e.py::TestHandleMessageE2E::test_single_cost_saved` | |
| Multiple costs saved E2E | ✅ Covered | `test_handle_message_e2E::TestHandleMessageE2E::test_multiple_costs_saved` | |
| Invalid message not saved E2E | ✅ Covered | `test_handle_message_e2e.py::TestHandleMessageE2E::test_invalid_message_not_saved` | |
| Negative amount allowed E2E | ✅ Covered | `test_handle_message_e2e.py::TestHandleMessageE2E::test_negative_amount_allowed` | |

### 11.2 Telegram API Integration

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Full update processing sends response | ✅ Covered | `test_telegram_api_integration.py::TestTelegramAPIIntegration::test_full_update_processing_sends_response` | |
| Help command sends help text | ✅ Covered | `test_telegram_api_integration.py::TestTelegramAPIIntegration::test_help_command_sends_help_text` | |
| Invalid message sends error and help | ✅ Covered | `test_telegram_api_integration.py::TestTelegramAPIIntegration::test_invalid_message_sends_error_and_help` | |
| Multiple costs single transaction | ✅ Covered | `test_telegram_api_integration.py::TestTelegramAPIIntegration::test_multiple_costs_single_transaction` | |
| Telegram API error handling | ✅ Covered | `test_telegram_api_integration.py::TestTelegramAPIIntegration::test_telegram_api_error_handling` | |
| Start command sends welcome | ✅ Covered | `test_telegram_api_integration.py::TestTelegramAPIIntegration::test_start_command_sends_welcome` | |

### 11.3 Complex Workflows

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Complete expense management flow | ⚠️ Partial | Covered in parts | Needs full workflow test |
| Family multi-user flow | ⚠️ Partial | Covered in isolation tests | Needs explicit multi-user E2E |
| Past mode workflow | ✅ Covered | `test_handle_message_e2e.py::TestPastModeE2E::test_past_mode_basic_flow` | |
| Menu → Select user → Select period → View report | ⚠️ Partial | Covered in parts | Needs full menu flow E2E |

### 11.4 Error Scenarios E2E

| Scenario | Status | Test Location | Notes |
|----------|--------|---------------|-------|
| Invalid message format E2E | ✅ Covered | `test_handle_message_e2e.py::TestErrorScenariosE2E::test_invalid_message_format` | |
| Mixed valid/invalid lines E2E | ✅ Covered | `test_handle_message_e2e.py::TestErrorScenariosE2E::test_mixed_valid_invalid_lines` | |
| Empty message E2E | ✅ Covered | `test_handle_message_e2e.py::TestErrorScenariosE2E::test_empty_message` | |
| Undo without saved IDs E2E | ✅ Covered | `test_handle_message_e2e.py::TestErrorScenariosE2E::test_undo_without_saved_ids` | |

---

## Summary Statistics

### Coverage by Category

| Category | Covered | Partial | Not Covered | Total | Coverage % |
|----------|---------|--------|-------------|-------|------------|
| Message Parsing | 45 | 0 | 0 | 45 | 100% |
| Message Handling | 12 | 3 | 5 | 20 | 60% |
| Menu & Reports | 15 | 3 | 8 | 26 | 58% |
| Past Mode | 10 | 2 | 6 | 18 | 56% |
| Undo Operation | 4 | 0 | 6 | 10 | 40% |
| Database Operations | 25 | 2 | 8 | 35 | 71% |
| Access Control | 6 | 0 | 5 | 11 | 55% |
| Error Handling | 8 | 1 | 6 | 15 | 53% |
| Edge Cases | 8 | 2 | 4 | 14 | 57% |
| Integration & E2E | 12 | 4 | 0 | 16 | 75% |
| **TOTAL** | **145** | **17** | **48** | **210** | **69%** |

### Priority Areas for Testing

#### High Priority (Critical Functionality)
1. **Undo Operation Edge Cases** (40% coverage)
   - Undo with non-existent IDs
   - Undo with mixed ownership
   - Undo after database error

2. **Past Mode Edge Cases** (56% coverage)
   - Invalid year/month handling
   - Past mode disabled mid-transaction
   - Edge dates (1900, 2100)

3. **Error Handling** (53% coverage)
   - SQLAlchemyError during undo
   - Connection lost scenarios
   - State timeout handling

#### Medium Priority (Important Functionality)
1. **Menu & Reports** (58% coverage)
   - Empty months list handling
   - Report with negative amounts
   - Period edge cases (January)

2. **Message Handling** (60% coverage)
   - HTML escaping in messages
   - Past mode persistence
   - Very long cost names

3. **Access Control Edge Cases** (55% coverage)
   - Malformed config handling
   - Concurrent access checks

#### Low Priority (Nice to Have)
1. **Concurrent Operations**
   - Concurrent menu operations
   - Concurrent undo operations

2. **Performance Testing**
   - Load testing
   - Stress testing

---

## Test Execution Recommendations

### Phase 1: Critical Gaps (Week 1)
- Undo operation edge cases
- Past mode edge cases
- Error handling scenarios

### Phase 2: Important Gaps (Week 2)
- Menu & reports edge cases
- Message handling HTML escaping
- Access control edge cases

### Phase 3: Completeness (Week 3)
- Concurrent operations
- Performance testing
- Full workflow E2E tests

---

## Notes

- ✅ = Fully covered with tests
- ⚠️ = Partially covered (needs more tests)
- ❌ = Not covered (needs tests)

Test locations reference:
- `test_message_parser.py` - Unit tests for message parsing
- `test_messages_handler.py` - Unit tests for message handlers
- `test_menu_handler.py` - Unit tests for menu handlers
- `test_middleware.py` - Unit tests for middleware
- `test_database_operations.py` - Integration tests for database
- `test_handle_message_e2e.py` - E2E tests for message handling
- `test_telegram_api_integration.py` - Integration tests for Telegram API
