# Comprehensive Test Plan for Family Costs Bot

**Prepared by**: Orchestrator  
**Date**: 2026-02-03  
**Purpose**: Comprehensive test coverage on all levels (unit, integration, e2e) with focus on edge cases and multiple user scenarios

## Executive Summary

This test plan covers comprehensive testing of the Family Costs Bot using multiple test design methodologies:
- **Equivalence Partitioning**: Grouping inputs into equivalent classes
- **Boundary Value Analysis**: Testing at boundaries and limits
- **Decision Table Testing**: Testing all combinations of conditions
- **State Transition Testing**: Testing FSM states and transitions
- **Error Guessing**: Testing common error scenarios
- **Use Case Testing**: Testing real-world user scenarios
- **Security Testing**: Testing access control and data isolation

## Test Coverage Goals

- **Unit Tests**: 95%+ code coverage
- **Integration Tests**: All database operations, repository methods
- **E2E Tests**: All user flows, edge cases, error scenarios
- **Edge Cases**: Boundary conditions, error conditions, race conditions

---

## 1. UNIT TESTS

### 1.1 Message Parser (`bot/services/message_parser.py`)

#### Current Coverage Analysis
✅ Good coverage exists, but missing:
- Edge cases with Unicode characters
- Very large decimal numbers
- Scientific notation attempts
- Multiple decimal separators in one number
- Empty cost names
- Cost names with only spaces

#### Test Cases to Add

**Equivalence Partitioning:**
- [ ] Valid: Single line with integer amount
- [ ] Valid: Single line with decimal amount (dot)
- [ ] Valid: Single line with decimal amount (comma)
- [ ] Valid: Multiple lines (2-99 lines)
- [ ] Invalid: No amount
- [ ] Invalid: No cost name
- [ ] Invalid: Empty message
- [ ] Invalid: Whitespace only

**Boundary Value Analysis:**
- [ ] Message length: 4095 chars (valid), 4096 chars (valid), 4097 chars (invalid)
- [ ] Line count: 99 lines (valid), 100 lines (valid), 101 lines (invalid)
- [ ] Line length: 99 chars (valid), 100 chars (valid), 101 chars (invalid)
- [ ] Amount: -999999999.99, 0, 999999999.99
- [ ] Amount with many decimal places: 123.12345678901234567890

**Edge Cases:**
- [ ] Unicode characters in cost name: "Продукты 🍎 100"
- [ ] Emoji in cost name: "Покупка 😊 200"
- [ ] Special characters: "Cost #123 @test 100"
- [ ] Cost name with only spaces: "   100"
- [ ] Multiple spaces between name and amount: "Name    100"
- [ ] Tabs instead of spaces: "Name\t100"
- [ ] Mixed line endings: "\r\n" and "\n"
- [ ] Amount with leading zeros: "Product 00100"
- [ ] Amount with trailing zeros: "Product 100.00"
- [ ] Scientific notation attempt: "Product 1e5" (should fail)
- [ ] Multiple decimal separators: "Product 12.34.56" (should fail)
- [ ] Decimal separator at start: "Product .5"
- [ ] Decimal separator at end: "Product 5."
- [ ] Very long cost name (99 chars)
- [ ] Cost name with newlines: "Line1\nLine2 100" (should be invalid)

**Error Handling:**
- [ ] InvalidOperation exception handling
- [ ] MessageMaxLengthExceed exception
- [ ] MessageMaxLinesCountExceed exception
- [ ] MessageMaxLineLengthExceed exception with correct line content

### 1.2 Message Handlers (`bot/routers/messages.py`)

#### Current Coverage Analysis
✅ Basic coverage exists, but missing:
- Past mode edge cases
- State transitions
- Concurrent operations
- Database rollback scenarios
- HTML escaping edge cases

#### Test Cases to Add

**State Transition Testing:**
- [ ] Initial state → handle_message → waiting_confirmation (with invalid lines)
- [ ] waiting_confirmation → handle_confirm → cleared (success)
- [ ] waiting_confirmation → handle_cancel → cleared
- [ ] Success → handle_undo → records deleted
- [ ] Past mode enabled → handle_message → past date used
- [ ] Past mode disabled → handle_message → current date used

**Edge Cases:**
- [ ] Message with HTML characters: "<script>alert('xss')</script> 100"
- [ ] Message with special HTML entities: "&amp; &lt; &gt; 100"
- [ ] Very long cost names in confirmation message
- [ ] Empty valid_costs in state (should handle gracefully)
- [ ] Missing last_saved_ids in undo (should show error)
- [ ] Undo with empty IDs list
- [ ] Undo with non-existent IDs
- [ ] Confirm with expired state
- [ ] Multiple users saving simultaneously
- [ ] Database connection lost during save
- [ ] Partial save failure (some records saved, some failed)

**Past Mode:**
- [ ] Past mode with year < current year
- [ ] Past mode with year = current year, month < current month
- [ ] Past mode with invalid year/month combination
- [ ] Past mode disabled mid-transaction
- [ ] Past mode with leap year (February 29)
- [ ] Past mode with year 1900 (edge case)
- [ ] Past mode with year 2100 (edge case)

**Error Scenarios:**
- [ ] SQLAlchemyError during save_costs_to_db
- [ ] SQLAlchemyError during undo
- [ ] Session rollback verification
- [ ] Database constraint violations
- [ ] User ID validation (negative, zero, very large)

### 1.3 Menu Handlers (`bot/routers/menu.py`)

#### Current Coverage Analysis
⚠️ Limited coverage - needs comprehensive testing

#### Test Cases to Add

**Menu Flow:**
- [ ] /menu command shows all users
- [ ] /menu with no users in database
- [ ] /menu with single user
- [ ] /menu with multiple users
- [ ] Current user appears as "Мои расходы"
- [ ] Other users appear as "Расходы {user_id}"

**Period Selection:**
- [ ] "Этот месяц" shows current month data
- [ ] "Прошлый месяц" shows previous month (normal case)
- [ ] "Прошлый месяц" in January (should show December of previous year)
- [ ] "Другие месяцы" shows available months list
- [ ] "Другие месяцы" with no data shows empty message
- [ ] Month selection shows correct report
- [ ] Month selection with no data shows empty message

**Past Mode Entry:**
- [ ] "Внести расходы за другой месяц" shows year selection
- [ ] Year selection shows current and previous year
- [ ] Month selection shows only past months for current year
- [ ] Month selection shows all months for previous year
- [ ] Past mode activation saves correct year/month
- [ ] Past mode message shows correct month name
- [ ] "Отключить прошлое" clears past mode
- [ ] Past mode persists across multiple messages
- [ ] Past mode disabled mid-session

**Edge Cases:**
- [ ] Invalid callback data format
- [ ] Non-existent user_id in callback
- [ ] Invalid year/month in callback
- [ ] Year/month out of valid range
- [ ] Month selection with no available months
- [ ] Concurrent menu operations
- [ ] Menu with very large user_id list

**Report Formatting:**
- [ ] Report with single expense
- [ ] Report with multiple expenses
- [ ] Report with zero expenses
- [ ] Report with negative amounts (corrections)
- [ ] Report with very large amounts
- [ ] Report date formatting (day only)
- [ ] Report total calculation
- [ ] Report sorting by date
- [ ] Report with expenses on same day

### 1.4 Middleware (`bot/middleware.py`)

#### Current Coverage Analysis
⚠️ Needs more edge case testing

#### Test Cases to Add

**Access Control:**
- [ ] Empty allowed_user_ids list (allows all)
- [ ] Single user in allowed_user_ids
- [ ] Multiple users in allowed_user_ids
- [ ] User not in allowed_user_ids (denied)
- [ ] User in allowed_user_ids (allowed)
- [ ] Message without from_user (allowed)
- [ ] Non-Message events (allowed, not checked)

**Edge Cases:**
- [ ] Very large user_id
- [ ] Negative user_id (should be denied if in list)
- [ ] Zero user_id
- [ ] User_id as string in config (should parse correctly)
- [ ] Malformed allowed_user_ids string
- [ ] Concurrent access checks

### 1.5 Database Repositories (`bot/db/repositories/messages.py`)

#### Current Coverage Analysis
⚠️ Needs comprehensive testing

#### Test Cases to Add

**save_message:**
- [ ] Save with default created_at
- [ ] Save with custom created_at
- [ ] Save with timezone-aware datetime
- [ ] Save with timezone-naive datetime
- [ ] Save with None created_at (should use default)
- [ ] Save multiple messages in transaction
- [ ] Save with very long text
- [ ] Save with special characters in text
- [ ] Save with negative user_id (should fail constraint)
- [ ] Save with zero user_id (should fail constraint)
- [ ] Save with very large user_id

**delete_messages_by_ids:**
- [ ] Delete single message
- [ ] Delete multiple messages
- [ ] Delete with empty IDs list
- [ ] Delete with non-existent IDs
- [ ] Delete other user's messages (should not delete)
- [ ] Delete own messages (should delete)
- [ ] Delete with mixed ownership (should only delete own)
- [ ] Delete with invalid user_id
- [ ] Delete with very large ID list
- [ ] Delete in transaction with rollback

**get_user_costs_by_month:**
- [ ] Get costs for current month
- [ ] Get costs for previous month
- [ ] Get costs for month with no data
- [ ] Get costs for leap year February
- [ ] Get costs for invalid month (should return empty)
- [ ] Get costs for invalid year
- [ ] Get costs sorted by date
- [ ] Get costs with timezone handling
- [ ] Get costs for month boundary dates

**get_user_available_months:**
- [ ] Get months for user with single month
- [ ] Get months for user with multiple months
- [ ] Get months for user with no data
- [ ] Get months sorted descending
- [ ] Get months with leap year
- [ ] Get months spanning multiple years

**get_unique_user_ids:**
- [ ] Get IDs with single user
- [ ] Get IDs with multiple users
- [ ] Get IDs with no users
- [ ] Get IDs sorted ascending
- [ ] Get IDs with duplicate user_ids (should dedupe)

**get_user_costs_stats:**
- [ ] Stats for user with no expenses
- [ ] Stats for user with single expense
- [ ] Stats for user with multiple expenses
- [ ] Stats with negative amounts
- [ ] Stats with very large amounts
- [ ] Stats total calculation accuracy
- [ ] Stats date range correctness
- [ ] Stats with invalid text format (should skip)

**get_user_recent_costs:**
- [ ] Get recent with default limit (10)
- [ ] Get recent with custom limit
- [ ] Get recent with limit > available
- [ ] Get recent with limit = 0
- [ ] Get recent with negative limit
- [ ] Get recent sorted descending
- [ ] Get recent with no expenses

### 1.6 Configuration (`bot/config.py`)

#### Test Cases to Add

**Settings Validation:**
- [ ] Valid bot_token format
- [ ] Invalid bot_token (too short)
- [ ] Invalid bot_token (no colon)
- [ ] Empty bot_token
- [ ] Valid database_url (postgresql://)
- [ ] Valid database_url (postgresql+asyncpg://)
- [ ] Invalid database_url (wrong prefix)
- [ ] Empty database_url
- [ ] allowed_user_ids as string "123,456,789"
- [ ] allowed_user_ids as list [123, 456, 789]
- [ ] allowed_user_ids with spaces "123, 456, 789"
- [ ] allowed_user_ids empty string
- [ ] allowed_user_ids empty list
- [ ] allowed_user_ids with invalid values
- [ ] Environment enum values (dev, test, prod)
- [ ] Debug property based on env

### 1.7 Utils (`bot/utils.py`)

#### Test Cases to Add

**Pluralization:**
- [ ] 1 → "расход"
- [ ] 2 → "расхода"
- [ ] 3 → "расхода"
- [ ] 4 → "расхода"
- [ ] 5 → "расходов"
- [ ] 11 → "расходов"
- [ ] 21 → "расход"
- [ ] 22 → "расхода"
- [ ] 101 → "расход"
- [ ] 102 → "расхода"
- [ ] 105 → "расходов"
- [ ] 0 → "расходов"
- [ ] Negative numbers

---

## 2. INTEGRATION TESTS

### 2.1 Database Operations

#### Test Cases

**Transaction Handling:**
- [ ] Multiple saves in single transaction (all succeed)
- [ ] Multiple saves in single transaction (one fails, all rollback)
- [ ] Save and delete in same transaction
- [ ] Concurrent transactions (isolation)
- [ ] Transaction timeout handling
- [ ] Connection pool exhaustion
- [ ] Database connection lost during operation

**Data Integrity:**
- [ ] Foreign key constraints (if any)
- [ ] Check constraint on user_id > 0
- [ ] Unique constraints
- [ ] Index performance on user_id queries
- [ ] Date/timezone consistency
- [ ] Text encoding (UTF-8)

**Repository Integration:**
- [ ] save_message → get_user_costs_by_month (verify saved)
- [ ] save_message → delete_messages_by_ids (verify deleted)
- [ ] Multiple users → get_unique_user_ids (verify all)
- [ ] Save with past date → get_user_costs_by_month (verify date)
- [ ] Large batch operations performance

### 2.2 Message Flow Integration

#### Test Cases

**Full Message Flow:**
- [ ] Parse → Save → Retrieve → Delete
- [ ] Parse with invalid lines → Confirm → Save
- [ ] Parse with invalid lines → Cancel → No save
- [ ] Save → Undo → Verify deleted
- [ ] Past mode → Save → Verify date
- [ ] Multiple messages → Menu → Verify reports

**State Management:**
- [ ] FSM state persistence across handlers
- [ ] State cleanup after operations
- [ ] State conflicts (multiple operations)
- [ ] State timeout/expiration

### 2.3 Menu Flow Integration

#### Test Cases

**Complete Menu Flow:**
- [ ] /menu → Select user → Select period → View report
- [ ] /menu → Select user → Select "Другие месяцы" → Select month → View report
- [ ] /menu → "Мои расходы" → "Внести расходы за другой месяц" → Select year → Select month → Save expense → Verify date
- [ ] Multiple users → Menu shows all → Each user sees own data

**Data Consistency:**
- [ ] Save expense → Menu shows updated data
- [ ] Delete expense → Menu shows updated data
- [ ] Past mode expense → Menu shows in correct month
- [ ] Multiple users → Data isolation verified

---

## 3. END-TO-END (E2E) TESTS

### 3.1 Happy Path Scenarios

#### Scenario 1: Basic Expense Entry
1. User sends: "Продукты 100"
2. Bot saves expense
3. Bot responds with success message
4. User can undo if needed
5. **Verify**: Expense saved with correct amount and date

#### Scenario 2: Multiple Expenses Entry
1. User sends: "Продукты 100\nВода 50\nХлеб 30"
2. Bot saves all expenses
3. Bot responds with success message
4. **Verify**: All expenses saved correctly

#### Scenario 3: View Expenses Menu
1. User sends /menu
2. User selects "Мои расходы"
3. User selects "Этот месяц"
4. Bot shows expense report
5. **Verify**: Report shows correct expenses with totals

#### Scenario 4: Past Month Entry
1. User sends /menu
2. User selects "Мои расходы" → "Внести расходы за другой месяц"
3. User selects year and month
4. User sends expense: "Продукты 100"
5. Bot saves with past date
6. User views that month's report
7. **Verify**: Expense appears in correct month

### 3.2 Error Scenarios

#### Scenario 5: Invalid Message Format
1. User sends: "invalid message"
2. Bot responds with error and help
3. **Verify**: No data saved, user sees help

#### Scenario 6: Mixed Valid/Invalid Lines
1. User sends: "Продукты 100\ninvalid\nВода 50"
2. Bot asks for confirmation
3. User confirms
4. **Verify**: Only valid lines saved

#### Scenario 7: Database Error
1. Simulate database error
2. User sends valid expense
3. Bot responds with DB error message
4. **Verify**: No partial saves, user notified

#### Scenario 8: Message Too Long
1. User sends message > 4096 chars
2. Bot responds with length error
3. **Verify**: No parsing attempted, user notified

#### Scenario 9: Too Many Lines
1. User sends message with > 100 lines
2. Bot responds with line count error
3. **Verify**: No parsing attempted, user notified

### 3.3 Edge Case Scenarios

#### Scenario 10: Negative Amount (Correction)
1. User sends: "корректировка -500"
2. Bot saves negative amount
3. User views report
4. **Verify**: Negative amount shown correctly, affects total

#### Scenario 11: Zero Amount
1. User sends: "бесплатно 0"
2. Bot saves zero amount
3. **Verify**: Zero amount saved and displayed

#### Scenario 12: Very Large Amount
1. User sends: "квартира 10000000.99"
2. Bot saves large amount
3. User views report
4. **Verify**: Large amount displayed correctly

#### Scenario 13: Unicode Characters
1. User sends: "Продукты 🍎 100"
2. Bot saves expense
3. **Verify**: Unicode characters preserved

#### Scenario 14: Special Characters in Name
1. User sends: "заказ #123 @test 100"
2. Bot saves expense
3. **Verify**: Special characters preserved

#### Scenario 15: HTML Characters (XSS Prevention)
1. User sends: "<script>alert('xss')</script> 100"
2. Bot saves expense
3. Bot displays in report
4. **Verify**: HTML escaped, no script execution

#### Scenario 16: Past Mode Edge Cases
1. User enables past mode for February (leap year)
2. User sends expense
3. **Verify**: Date set to Feb 1 of that year
4. User enables past mode for January (previous year)
5. User sends expense
6. **Verify**: Date set to Jan 1 of previous year

#### Scenario 17: Undo Edge Cases
1. User saves expense
2. User clicks undo
3. **Verify**: Expense deleted
4. User clicks undo again
5. **Verify**: Error message, no crash

#### Scenario 18: Multiple Users Isolation
1. User A saves expense
2. User B saves expense
3. User A views menu
4. **Verify**: User A sees only own expenses
5. User B views menu
6. **Verify**: User B sees only own expenses

#### Scenario 19: Concurrent Operations
1. User sends multiple messages rapidly
2. **Verify**: All processed correctly, no race conditions
3. User clicks multiple buttons rapidly
4. **Verify**: All handled correctly, state consistent

#### Scenario 20: Access Control
1. User not in allowed_user_ids sends message
2. **Verify**: Access denied message
3. User in allowed_user_ids sends message
4. **Verify**: Message processed normally

### 3.4 Complex User Workflows

#### Scenario 21: Complete Expense Management Flow
1. User enters multiple expenses over time
2. User views monthly reports
3. User corrects mistake with negative amount
4. User enters past month expense
5. User views different months
6. User deletes incorrect expense
7. **Verify**: All operations work correctly, data consistent

#### Scenario 22: Family Multi-User Flow
1. User A enters expenses
2. User B enters expenses
3. User A views own expenses
4. User A views User B's expenses
5. User B views own expenses
6. User B views User A's expenses
7. **Verify**: Data isolation, correct reports for each user

#### Scenario 23: Past Mode Workflow
1. User enables past mode for March 2024
2. User enters multiple expenses
3. User disables past mode
4. User enters current expense
5. User views March 2024 report
6. User views current month report
7. **Verify**: Past expenses in March, current expense in current month

### 3.5 Boundary Testing

#### Scenario 24: Maximum Message Length
1. User sends message with exactly 4096 characters
2. **Verify**: Message processed successfully
3. User sends message with 4097 characters
4. **Verify**: Error message, no processing

#### Scenario 25: Maximum Line Count
1. User sends message with exactly 100 lines
2. **Verify**: Message processed successfully
3. User sends message with 101 lines
4. **Verify**: Error message, no processing

#### Scenario 26: Maximum Line Length
1. User sends line with exactly 100 characters
2. **Verify**: Line processed successfully
3. User sends line with 101 characters
4. **Verify**: Error message, no processing

#### Scenario 27: Boundary Dates
1. User enables past mode for January 1, 1900
2. User sends expense
3. **Verify**: Date set correctly
4. User enables past mode for December 31, 2099
5. User sends expense
6. **Verify**: Date set correctly

### 3.6 Security Testing

#### Scenario 28: User ID Validation
1. Attempt to save with negative user_id
2. **Verify**: Constraint violation, error handled
3. Attempt to save with zero user_id
4. **Verify**: Constraint violation, error handled

#### Scenario 29: Data Isolation
1. User A saves expense with ID 1
2. User B attempts to delete expense ID 1
3. **Verify**: Delete fails (not User B's expense)
4. User A deletes own expense
5. **Verify**: Delete succeeds

#### Scenario 30: SQL Injection Attempt
1. User sends: "'; DROP TABLE messages; -- 100"
2. **Verify**: Treated as cost name, no SQL execution
3. Expense saved with literal text
4. **Verify**: Database intact

#### Scenario 31: XSS Prevention
1. User sends: "<img src=x onerror=alert(1)> 100"
2. Bot displays in report
3. **Verify**: HTML escaped, no script execution

---

## 4. PERFORMANCE TESTS

### Test Cases

**Load Testing:**
- [ ] Save 1000 expenses sequentially
- [ ] Save 100 expenses concurrently
- [ ] Query reports with 1000 expenses
- [ ] Menu with 100 users
- [ ] Database connection pool under load

**Stress Testing:**
- [ ] Maximum message length processing time
- [ ] Maximum line count processing time
- [ ] Large batch operations
- [ ] Concurrent user operations

---

## 5. TEST DATA REQUIREMENTS

### Test Data Sets

**Basic Data:**
- Single expense
- Multiple expenses (2-10)
- Expenses with various amounts (positive, negative, zero)
- Expenses with various date ranges

**Edge Case Data:**
- Very long cost names
- Unicode characters
- Special characters
- HTML characters
- Maximum length messages
- Maximum line count messages

**User Scenarios:**
- Single user
- Multiple users (2-10)
- Users with no expenses
- Users with many expenses

**Date Scenarios:**
- Current month
- Previous month
- Leap year February
- Year boundaries
- Month boundaries

---

## 6. TEST EXECUTION PLAN

### Phase 1: Unit Tests (Week 1)
1. Complete all unit test cases
2. Achieve 95%+ code coverage
3. Fix any issues found
4. Re-run tests to verify fixes

### Phase 2: Integration Tests (Week 1-2)
1. Complete all integration test cases
2. Test database operations thoroughly
3. Test message flow integration
4. Test menu flow integration

### Phase 3: E2E Tests (Week 2)
1. Execute all happy path scenarios
2. Execute all error scenarios
3. Execute all edge case scenarios
4. Execute all complex workflows
5. Execute boundary tests
6. Execute security tests

### Phase 4: Performance Tests (Week 2)
1. Execute load tests
2. Execute stress tests
3. Analyze results
4. Optimize if needed

### Phase 5: Regression Testing (Week 2)
1. Re-run all tests after fixes
2. Verify no regressions
3. Final quality check

---

## 7. TEST METRICS AND REPORTING

### Metrics to Track

**Coverage Metrics:**
- Code coverage percentage (target: 95%+)
- Line coverage
- Branch coverage
- Function coverage

**Quality Metrics:**
- Number of test cases executed
- Number of test cases passed
- Number of test cases failed
- Number of bugs found
- Number of bugs fixed

**Performance Metrics:**
- Average response time
- Maximum response time
- Throughput (operations/second)
- Database query performance

### Reporting

- Daily test execution reports
- Weekly coverage reports
- Bug reports with severity
- Final test summary report

---

## 8. RISK ANALYSIS

### High Risk Areas

1. **Data Isolation**: Multiple users must not see each other's data
2. **Past Mode**: Date handling must be correct
3. **Undo Operation**: Must only delete own records
4. **Database Transactions**: Must handle errors correctly
5. **Concurrent Operations**: Must handle race conditions

### Mitigation Strategies

1. Extensive testing of user isolation
2. Comprehensive date/timezone testing
3. Security testing of undo operation
4. Transaction rollback testing
5. Concurrent operation testing

---

## 9. TEST ENVIRONMENT

### Requirements

- Python 3.10+
- PostgreSQL database
- Test database (separate from production)
- Mock Telegram API
- Test fixtures and data

### Setup

1. Create test database
2. Run migrations
3. Set ENV=test
4. Configure test fixtures
5. Prepare test data sets

---

## 10. SIGN-OFF CRITERIA

### Completion Criteria

- [ ] All unit tests written and passing
- [ ] 95%+ code coverage achieved
- [ ] All integration tests written and passing
- [ ] All E2E scenarios tested and passing
- [ ] All edge cases covered
- [ ] All security tests passing
- [ ] Performance tests completed
- [ ] No critical bugs remaining
- [ ] Documentation updated
- [ ] Test reports generated

---

## APPENDIX: Test Design Methodologies Used

### Equivalence Partitioning
Grouping inputs into equivalent classes that should produce the same output.

### Boundary Value Analysis
Testing at the boundaries of input ranges (min, max, min+1, max-1).

### Decision Table Testing
Testing all combinations of conditions and actions.

### State Transition Testing
Testing FSM states and transitions between states.

### Error Guessing
Using experience to guess common error scenarios.

### Use Case Testing
Testing real-world user scenarios and workflows.

### Security Testing
Testing access control, data isolation, and injection prevention.

---

**End of Test Plan**
