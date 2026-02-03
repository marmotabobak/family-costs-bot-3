# User Guide: How to Work with Agents

This guide explains how to effectively interact with the agent system. For agent definitions and behavior, see `.cursor/AGENTS.md`.

## 🚀 Quick Start: Correct Initial Message Format

### How to Address business-analyst

**You have 3 options** (all work the same way):

#### Option 1: Explicit address with colon
```
business-analyst: I need to add CSV export for expenses...
```

#### Option 2: Explicit address without colon
```
business-analyst, I need to add CSV export for expenses...
```

#### Option 3: Just state your request (recommended)
```
I need to add CSV export for expenses...
```

**All three options work!** The business-analyst will automatically handle your request regardless of how you address it. Option 3 is simplest and recommended.

### Examples of Correct Addressing

**✅ All of these work:**

```
business-analyst: Add export feature for expenses
```

```
business-analyst, I need to add export feature
```

```
I need to add export feature for expenses
```

```
Add export feature for expenses
```

**❌ Don't do this:**

```
composer: Add export feature  ← Wrong! Will redirect anyway, but inefficient
```

### Minimal Template

```
I need to [add feature / fix bug / refactor component].

[Describe what you want, why, and key details]
```

### Complete Example

```
I need to add CSV export for expenses. Users should be able to export their expenses via /export command. CSV should include: user ID, description, amount, date. Format: comma-separated, UTF-8.
```

---

## How to Build Effective Dialogue for Autonomous Agent Work

**Key Principle**: Structure your dialogue to enable agents to work autonomously. The more explicit and complete your initial request, the better agents can work independently.

## Initial Message Templates

### Template 1: New Feature Request (Recommended)

```
I need to add [feature name]. 

Requirements:
- [What the feature should do]
- [How users will interact with it]
- [Expected behavior]

Details:
- [Specific details, format, constraints]
- [Edge cases or special scenarios]
- [Integration with existing features]

Example:
[Show example of expected behavior or output]
```

**Example**:
```
I need to add CSV export functionality for expenses.

Requirements:
- Users should be able to export their expenses to CSV
- Accessible via a new /export command
- CSV should include all user's expenses

Details:
- CSV format: comma-separated, UTF-8 encoding
- Fields: User ID, expense description, amount, date (YYYY-MM-DD), category
- File name: expenses_YYYYMMDD_HHMMSS.csv
- Include header row
- If no expenses: show message "У вас пока нет расходов для экспорта"

Example:
/export → bot sends CSV file as document
```

### Template 2: Bug Fix Request

```
Fix bug: [brief description]

Problem:
- [What's wrong]
- [When it happens]
- [Steps to reproduce]

Expected behavior:
- [What should happen instead]
```

**Example**:
```
Fix bug: Expense deletion doesn't work for negative amounts

Problem:
- When user tries to delete an expense with negative amount (correction), deletion fails
- Error message shows "Invalid expense ID"
- Happens when using /delete command

Expected behavior:
- Should delete the expense regardless of amount sign
- Should show confirmation message "Расход удалён"
```

### Template 3: Refactoring Request

```
Refactor [component/feature] to [goal]

Current state:
- [What exists now]

Desired state:
- [What should be improved]
- [Goals: performance, maintainability, etc.]

Constraints:
- [What shouldn't break]
- [Compatibility requirements]
```

**Example**:
```
Refactor message parser to support multiple formats

Current state:
- Parser only handles "description amount" format
- Single line parsing

Desired state:
- Support both single-line and multi-line formats
- Better error messages for invalid formats
- More flexible amount parsing (with/without currency symbols)

Constraints:
- Must maintain backward compatibility
- Existing tests should still pass
- Don't change database schema
```

### Template 4: Simple Request (Minimal)

```
[Feature/bug/refactor description]

[Key details]
```

**Example**:
```
Add monthly expense summary feature

Users can see total expenses for current month, breakdown by category, and comparison with previous month via /summary command.
```

**Note**: Business-analyst will ask clarifying questions if more details are needed.

### Quick Reference: What to Include

**Always Include**:
- ✅ What you want (feature/bug/refactor)
- ✅ Why it's needed (context)
- ✅ Key requirements or constraints

**Helpful to Include**:
- ✅ Examples of expected behavior
- ✅ Edge cases you know about
- ✅ Integration points with existing features
- ✅ Format specifications (if applicable)

**Don't Worry About**:
- ❌ Technical implementation details (developer handles this)
- ❌ Exact code structure (agents decide)
- ❌ Test scenarios (tester handles this)

### Phase 1: Initiating Work (Business-Analyst Phase)

**CRITICAL**: Always address initial requirements to **business-analyst**, NOT composer.

**✅ GOOD: Address to Business-Analyst**

**Any of these formats work:**

Format 1 (explicit with colon):
```
business-analyst: I need to add a feature to export expenses to CSV. The CSV should include:
- User ID
- Expense description
- Amount
- Date
- Should be downloadable via a new /export command
- Format: comma-separated, UTF-8 encoding
- Include header row
```

Format 2 (explicit without colon):
```
business-analyst, I need to add a feature to export expenses to CSV...
```

Format 3 (simple - recommended):
```
I need to add a feature to export expenses to CSV. The CSV should include:
- User ID
- Expense description
- Amount
- Date
- Should be downloadable via a new /export command
- Format: comma-separated, UTF-8 encoding
- Include header row
```

**All three formats work the same way!** The business-analyst will automatically handle your request.

**❌ BAD: Addressing Composer Directly**

```
"composer: Add export functionality"
"composer, start work on export feature"
```

**Why**: Composer only works with finalized BRDs. It will redirect to business-analyst anyway, but it's more efficient to start with analyst.

**✅ GOOD: Clear, Specific Requests**

```
"I need to add a feature to export expenses to CSV. The CSV should include:
- User ID
- Expense description
- Amount
- Date
- Should be downloadable via a new /export command
- Format: comma-separated, UTF-8 encoding
- Include header row"
```

**❌ BAD: Vague Requests**

```
"Add export functionality"
"Make it exportable"
"I want to export data"
```

**Best Practices for Initial Requests**:
1. **Be specific**: Include what, why, and how
2. **Provide context**: Mention related features or constraints
3. **Include examples**: Show expected behavior or format
4. **State constraints**: Technical limitations, user requirements
5. **Mention edge cases**: If you know of specific scenarios to handle

### Phase 2: BRD Development (Interactive Phase)

**During BRD Phase - Answer Questions Thoroughly**:

When business-analyst asks questions, provide complete answers:

**✅ GOOD: Complete Answers**

```
Analyst: "What should happen if the user has no expenses to export?"
You: "Show a message: 'У вас пока нет расходов для экспорта' and don't create an empty file."
```

**❌ BAD: Incomplete Answers**

```
Analyst: "What should happen if the user has no expenses to export?"
You: "Handle it"
```

**Dialogue Pattern for BRD Phase**:

1. **Initial Request**: You provide feature request
2. **Analyst Questions**: Analyst asks clarifying questions
3. **Your Answers**: Provide detailed, specific answers
4. **Analyst Follow-ups**: Analyst may ask more questions based on your answers
5. **BRD Review**: Analyst presents BRD, you review and provide feedback
6. **Finalization**: Once BRD is approved, say "BRD approved" or "Looks good"

**Example Dialogue Flow**:

```
You: "Add CSV export feature for expenses"

[Analyst asks questions]

Analyst: "What fields should be included in the CSV?"
You: "User ID, expense description, amount, date (YYYY-MM-DD format), category if available"

Analyst: "What should be the file name format?"
You: "expenses_YYYYMMDD_HHMMSS.csv, using current date/time"

Analyst: "Should it include all expenses or filtered by date range?"
You: "All expenses for now, we can add filtering later"

[Analyst creates BRD]

Analyst: "Here's the BRD: [details]"
You: "BRD looks good, approved"
```

### Phase 3: Autonomous Execution (After BRD Finalization)

**✅ GOOD: Let Agents Work**

Once BRD is finalized, simply say:
- "Proceed"
- "Go ahead"
- "Start implementation"
- Or just wait - agents will work autonomously

**❌ BAD: Micro-managing**

```
"Now implement the export function"
"Make sure you use async"
"Don't forget error handling"
```

**Why**: BRD already contains all these details. Trust the agents to follow the BRD.

**Monitoring Progress**:

You can check progress by:
1. **Reading the log file**: `.cursor/agents.log` shows all agent actions
2. **Asking for status**: "What's the current status?"
3. **Reviewing code**: Check what's been implemented

**When to Intervene**:

Only intervene if:
- ❌ Agents ask for clarification (shouldn't happen after BRD)
- ❌ Quality issues persist after multiple iterations
- ❌ Requirements have changed
- ❌ You need to add new requirements

**✅ GOOD: Adding Requirements Mid-Process**

```
"I need to add one more requirement: the CSV should also include a total row at the bottom"
```

**Response**: Analyst will update BRD, then agents continue.

### Dialogue Patterns by Scenario

#### Scenario 1: New Feature Request

**Pattern**:
```
1. You: [Feature request with details] → **Address to business-analyst** (NOT composer)
2. Analyst: [Asks questions]
3. You: [Answers questions]
4. Analyst: [Presents BRD]
5. You: "BRD approved" or "Looks good"
6. [Analyst passes BRD to composer]
7. [Agents work autonomously]
8. [Check log or ask for status]
```

**❌ WRONG**: "Composer, add export feature"
**✅ CORRECT**: "business-analyst, I need to add export feature" or just "Add export feature" (analyst will handle it)

#### Scenario 2: Bug Fix

**Pattern**:
```
1. You: "Fix bug: [describe bug with steps to reproduce]"
2. Analyst: [Asks questions about expected behavior]
3. You: [Answers]
4. Analyst: [Creates BRD for fix]
5. You: "BRD approved"
6. [Agents work autonomously]
```

#### Scenario 3: Refactoring

**Pattern**:
```
1. You: "Refactor [component] to [goal]"
2. Analyst: [Asks about scope, breaking changes, etc.]
3. You: [Answers]
4. Analyst: [Creates BRD]
5. You: "BRD approved"
6. [Agents work autonomously]
```

### Tips for Effective Dialogue

**DO**:
- ✅ Address initial requirements to **business-analyst** (not composer)
- ✅ Provide context and background
- ✅ Include examples of expected behavior
- ✅ Answer analyst questions completely
- ✅ Review BRD carefully before approval
- ✅ Let agents work after BRD approval
- ✅ Check logs for progress
- ✅ Trust the quality system (95+ threshold)

**DON'T**:
- ❌ Address initial requirements to composer (it will redirect anyway)
- ❌ Give vague requirements
- ❌ Skip answering analyst questions
- ❌ Approve BRD without reviewing
- ❌ Micro-manage after BRD approval
- ❌ Interrupt autonomous work unnecessarily
- ❌ Change requirements mid-implementation without updating BRD

### Example: Complete Dialogue Flow

```
[You initiate]
You: "I need to add a monthly expense summary feature. Users should be able to see:
- Total expenses for the current month
- Breakdown by category
- Comparison with previous month
- Accessible via /summary command"

[Analyst asks questions]
Analyst: "Should the summary include only expenses from the current user or all users?"
You: "Only current user's expenses"

Analyst: "What format should the comparison be in? Percentage change? Absolute difference?"
You: "Both: show absolute difference and percentage change, e.g., '+500₽ (+10%)'"

Analyst: "What if there are no expenses in the current month?"
You: "Show 'Нет расходов за текущий месяц'"

[Analyst creates BRD]
Analyst: "BRD created. Quality: 96/100. [BRD details]"

[You review]
You: "BRD looks good, approved"

[Agents work autonomously - you can check logs]
You: [Later] "What's the status?"
Or: [Check .cursor/agents.log file]

[Completion]
Composer: "Process complete. Quality: 97/100. All tests passing."
```

### Summary

**Effective Dialogue Structure**:
1. **Initiate**: Clear, specific request with context
2. **Clarify**: Answer analyst questions thoroughly
3. **Approve**: Review and approve BRD
4. **Autonomous**: Let agents work, monitor via logs
5. **Complete**: Review final result

**Key Success Factors**:
- Clear initial requirements
- Complete answers during BRD phase
- Trust the autonomous process after BRD
- Monitor via logs, not micro-management
- Only intervene when truly necessary
