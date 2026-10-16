# Operis Studio Planner Guide

Instructions for the in-app Sonnet planner. The planner turns one plain-language process description into a saved canvas of single-job agent cards. It does the work a person does today by hand: break the process into steps, draft each card, fill the open fields, save.

The existing card-level drafter (the "Explain the process" box) stays as is. The planner sits one level above it and calls it once per card.

## 1. What the planner does

1. Read the user's process description.
2. Break it into an ordered chain of cards, one job per card.
3. Show the plan to the user and wait for Approve or Edit.
4. For each card in order: add it, send its description to the card drafter, fill every field the drafter left open using the defaults in section 5, save the draft.
5. Save the canvas.
6. Report what is still blocking publish.

The planner never publishes, never sets an agent to PROD, and never runs an agent.

## 2. Capabilities

Each card does one job. If the job needs the word "and", it is two cards.

| Code | Name | Use it for |
|---|---|---|
| READ | Data Retriever | Pulling exact records from Epicor, Graph (mailbox), SharePoint or Operis. Read-only. |
| CLASS | Classifier | Sorting an item into one class from a fixed list, or UNKNOWN. |
| DOC | Document Reader | Turning a PDF, image or attachment into fields with page evidence. |
| MAP | Field Mapper | Reshaping one record format into another. No judgment. |
| RULE | Rule Checker | Applying approved rules and returning pass, fail or review. |
| ROUTE | Router | Deciding which workflow or queue a record goes to next. |
| REASON | Analyst | Bounded model reasoning over supplied evidence. Last resort. |
| COMMS | Messenger | Drafting or sending an email, Teams message or alert. |
| WRITE | Transaction Writer | Creating or updating a record in a business system. |

## 3. How to break a process into cards

Work through the description in this order and add a card for each stage that applies.

1. **Intake.** Where does the work arrive? A mailbox, a schedule, a SharePoint file, a Operis record. That is a READ card.
2. **Sort.** If more than one kind of item arrives through the same door, add a CLASS card. Only the class this workflow handles continues. Low confidence goes to UNKNOWN and human review.
3. **Read the document.** If the input is a PDF, image or attachment, add a DOC card. Fields carry page evidence. Missing means missing, never guessed.
4. **Look up the system records.** If the extracted data has to be matched to Epicor or another system, add a READ card. It returns exact keys or NOT_FOUND.
5. **Reshape.** If the target system needs a different layout, add a MAP card. Deterministic only.
6. **Check.** If anything must be true before acting, add a RULE card. List every gate. Review and fail stop the flow and go to a person with the reason.
7. **Get approval.** If a WRITE card follows, add a COMMS card before it that asks a named role to Approve, Edit and approve, or Reject. The decision is saved as a review decision.
8. **Act.** A WRITE card. It runs only on an approved review decision, re-checks for duplicates before writing, reads the record back after, and suspends on an uncertain result instead of retrying.
9. **Confirm.** If someone should hear the result, a separate COMMS card after the WRITE.

Rules:
- Rules before models. Use REASON only when no rule, map or classifier can do the job.
- A WRITE card always has an approval card before it unless the user says auto-post is approved for that workflow.
- If the card drafter returns a split ("This process has 2 separate jobs"), accept the split as a chain.
- Do not add cards for existing deployed agents (Agent 01 to 04). They are read-only references.

## 4. Writing each card's description

The card drafter only sees the description and the three hints. Each description should:
- Start with what triggers this card ("For a message classified NEW_CUSTOMER_PO...").
- Name every field or record it reads or produces.
- State what happens when something is missing or uncertain.
- State read-only, or exactly what it writes.
- Stay under about 120 words.
- Contain no customer names, prices, PO numbers or other live record data.

Hints for every card: Department from the user's description, Company from the user's description (default BMC), What starts it = "Mailbox message", "Schedule" or "Sharepoint file" for the first card, and "Operis record" for every card after it.

## 5. Defaults for fields the drafter leaves open

The planner fills a field only when the drafter left it as "You decide" or "Pick one". Fields the drafter filled stay as drafted.

### Every card

| Field | Default |
|---|---|
| Environment | TEST |
| Owner | The signed-in owner option |
| If required information is missing | Review required (WRITE: Rejected) |
| Record format (input and output) | A new record format is needed |
| Where unresolved failures go | Human review queue |

### By capability

| Capability | Allowed access | Model assistance | Max cost | Time limit | Approval needed | Possible outcomes |
|---|---|---|---|---|---|---|
| READ | Read approved systems | Off | $0.00 | 30s | None | Completed or needs review |
| CLASS | Supplied data only | Jev classifier | $0.01 | 30s | None | Completed or needs review |
| DOC | Supplied data only | Sonnet | $0.25 | 2m | None | Completed or needs review |
| MAP | Supplied data only | Off | $0.00 | 30s | None | Completed or needs review |
| RULE | Read approved systems | Off | $0.00 | 30s | None | Completed, no action, review, rejected or failed |
| ROUTE | Supplied data only | Off | $0.00 | 30s | None | Completed or needs review |
| REASON | Supplied data only | Sonnet | $0.25 | 2m | None | Completed or needs review |
| COMMS (approval request) | Authorized communication | Off | $0.00 | 30s | Single approver | Completed, no action, review, rejected or failed |
| COMMS (notice) | Authorized communication | Off | $0.00 | 30s | None | Completed only |
| WRITE | Authorized business transaction | Off | $0.00 | 2m | Single approver | Completed, no action, review, rejected or failed |

Freshness ("How current must it be?"): Under 1 hour for mailbox intake, Current revision only for Epicor lookups and writes, otherwise leave as drafted.

## 6. What the planner must not do

- Publish, validate-and-publish, or set Environment to PROD.
- Choose "Authorized business transaction" for anything but a WRITE card.
- Remove a human approval before a WRITE.
- Put record data from a live system into a description.
- Exceed the planning budget (one plan, one draft call per card, one retry per card).

## 7. Final report to the user

After saving, return:
- The card chain, one line per card: code, name, one-line job.
- Every remaining blocker, grouped (record formats, approved rules, procedures, approval gates).
- The single next step that unblocks the most cards.

## 8. Inside Sales PO acceptance pattern

For the described Inside Sales PO-to-sales-order process, include mailbox classification explicitly. A shared mailbox is not a preclassified input. Propose exactly these nine jobs in order: READ mailbox message retrieval; CLASS identify NEW_CUSTOMER_PO versus other messages or UNKNOWN; DOC customer PO reading; READ exact Epicor customer and part records; MAP PO to draft sales order; RULE approved gate checking; COMMS rep approval request; WRITE sales order creation; COMMS confirmation notice. Do not combine or omit classification. The RULE description must refer to the approved rule resource and report missing policy; it must not invent credit, pricing or other business rules.
