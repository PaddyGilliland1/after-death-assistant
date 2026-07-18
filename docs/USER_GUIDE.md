# AD Assistant User Guide

**A guide for executors using AD Assistant to administer an estate in England and Wales.**

This guide is written for you, the executor. You do not need any technical knowledge to use the tool, and you do not need any technical knowledge to read this guide. If a word is unfamiliar, it is explained the first time it appears.

Three things to hold on to before anything else:

1. **This tool informs and drafts. It is not legal or financial advice.** When the stakes are high, or anything feels unclear, speak to a solicitor, accountant or tax adviser.
2. **Nothing is ever sent or filed automatically.** The tool prepares drafts; a person reviews and approves them; a person submits the form or posts the letter, outside the tool.
3. **Every tax figure is calculated by fixed, tested rules, never by an AI model.** The assistant can explain a figure to you in plain words, but it cannot invent one.

---

## Contents

1. [Signing in](#1-signing-in)
2. [The dashboard](#2-the-dashboard)
3. [The timeline: working through the process](#3-the-timeline-working-through-the-process)
4. [Tasks and dependencies](#4-tasks-and-dependencies)
5. [Assets, liabilities and valuations](#5-assets-liabilities-and-valuations)
6. [Contacts and the notification tracker](#6-contacts-and-the-notification-tracker)
7. [Costs](#7-costs)
8. [Estate accounts](#8-estate-accounts)
9. [The inheritance tax workbench](#9-the-inheritance-tax-workbench)
10. [The knowledge library and the assistant](#10-the-knowledge-library-and-the-assistant)
11. [Drafts and approval](#11-drafts-and-approval)
12. [PDF exports](#12-pdf-exports)
13. [Further modules](#13-further-modules)
14. [When you need help](#14-when-you-need-help)
15. [Roles and privacy](#15-roles-and-privacy)
16. [The audit trail](#16-the-audit-trail)

---

## 1. Signing in

### In production (the normal case)

There are no passwords to remember. When you open the app's address in your browser, a sign-in page asks for your email address and sends you a **one-time PIN** by email. Type the PIN in and you are signed in. This is provided by Cloudflare Access, a login service that sits in front of the app; only email addresses on the estate's approved list can get in at all.

Behind the scenes your email address also decides what you are allowed to do: administrator, executor or viewer. Section 15 explains the roles.

If your PIN email does not arrive, check your spam folder, and check with whoever set the tool up that your email address is on the approved list.

### On a local development copy

If you are running the tool on your own computer for development or evaluation, there is no email step. A simple sign-in screen appears instead, asking which user you want to be. Type an email address that the local configuration recognises and continue. This screen exists only in development; it never appears on a production installation.

## 2. The dashboard

The dashboard is the home page, and it is designed so that you never have to hold the whole administration in your head. At a glance it shows:

- **Open tasks**, with anything overdue or due soon at the top, and the next step on the critical path.
- **How far through the process you are**: a progress bar across the administration timeline, naming the current step.
- **Money in and out**: money still owed to the estate, bills still to settle, costs spent so far, and who is owed reimbursement.
- **The estate position**: what the estate is worth in total, what it owes, the net figure, and a provisional split between the beneficiaries.
- **Outstanding notifications**: organisations that still need to be told about the death.
- **Deadline countdowns** for the statutory dates.
- **Tax status**: the estimated inheritance tax, how much headroom there is to the tax threshold, and, prominently, whether a full tax return (form IHT400) is required.
- **Data completeness**: how many of your valuations are confirmed figures rather than estimates.

You can click through from any dashboard card to the module behind it.

## 3. The timeline: working through the process

Administering an estate in England and Wales follows a broadly standard order, from registering the death through to final distribution and record keeping. The **Timeline** page carries that order as a checklist of **41 steps**, each with a plain description of what it involves and why.

- Each step is linked to its tasks, so a step shows as done when its tasks are done.
- Steps that depend on earlier steps say so, so you can see why something cannot be started yet.
- Each step links to the relevant official guidance in the knowledge library.

You do not need to work strictly in order, and many steps run in parallel. The timeline is there so that nothing is forgotten, not to hurry you.

## 4. Tasks and dependencies

The **Tasks** page is the working heart of the tool: one living list of everything that needs doing, who is doing it, and by when.

- Tasks come from four places: ones you add yourself; ones seeded from the standard process checklist; ones created automatically from statutory deadlines; and ones the assistant suggests (which only become tasks when you approve them, see section 11).
- A task can be **blocked by** another task. A blocked task cannot be marked done while the task it depends on is still open, and the page tells you which task is in the way. This is how the tool protects the right order of events, for example not distributing money before the creditor notice period has closed.
- Each task has a status (not started, in progress, blocked, waiting on a third party, done, or cancelled), a priority, dates, an optional checklist of subtasks, and comments.
- A small chart at the top shows your open work by status, so you can see the shape of what remains.
- Adding things elsewhere creates tasks automatically where it should: recording a property, for example, adds tasks to get it valued and to tell the insurer it is unoccupied.

## 5. Assets, liabilities and valuations

The **Assets** page is the register of everything the person who died owned, from a library card to a bank account, and everything they owed.

For each asset you record:

- What it is (a category such as property, bank account, shares, vehicle, household goods).
- **Its value at the date of death.** This is the figure inheritance tax is based on, so each value also records where it came from (**the valuation source**, such as a bank statement or a surveyor) and whether it is an **estimate** or a **confirmed** figure. Start with estimates; replace them with confirmed figures as statements and valuations arrive. The dashboard shows how much of the estate is still estimated.
- **How it was owned.** Solely, jointly with a right of survivorship (where the asset passes straight to the co-owner), or as tenants in common (where a share belongs to the estate). Assets that pass outside the estate are still recorded, so nothing is lost, but they are excluded from the taxable total.
- Extra flags where relevant, such as whether a home is passing to children or grandchildren (this matters for a tax allowance explained in section 9).

Liabilities (a mortgage, a credit card balance, care fees, the funeral) are recorded with the creditor, the amount, and whether they are deductible for inheritance tax. Genuine debts and the funeral reduce the taxable estate; that is handled for you.

Two behaviours worth knowing:

- **Everything recalculates as you type.** Adding or editing any asset or liability immediately updates the net estate, the beneficiary shares and the tax assessment, and re-derives which forms are required. If a change is material, for example the estate crossing a tax threshold, the tool raises an alert so both executors see it.
- **Nothing is ever deleted.** If something was recorded in error, you archive it with a reason. The history is kept.

Every valuation is kept in a history per asset, which matters later: if the estate sells a property or shares, capital gains tax is worked out against the date-of-death value.

## 6. Contacts and the notification tracker

The **Contacts** page holds everyone and every organisation involved: banks, insurers, pension providers, utility companies, HMRC, the probate registry, the GP surgery, the solicitor, the beneficiaries, and so on.

Its most useful view is the **notification tracker**: one screen answering the question that dominates the early weeks, "who still needs to be told, how, and have they replied?". Each contact that needs notifying carries a status (to notify, notified, awaiting response, actioned, closed), the method used, and the date.

Built-in entries cover the centralised routes that save you the most effort:

- **Tell Us Once**, the government service that informs DWP, HMRC, DVLA, the Passport Office and the council in one go.
- **The Gazette**, for the statutory creditor notice (see section 13, executor protection).
- The free bank-and-insurer bulk services (the Death Notification Service and similar), which notify many financial institutions in one submission.

You can log each interaction with a contact (a call, a letter, an email) and set a follow-up date; the follow-up becomes a task so it cannot be forgotten. Contacts link to the assets they hold, the tasks about them and the costs they generated, so from any record you can reach the people, actions, money and paperwork attached to it.

## 7. Costs

Every cost of administering the estate goes on the **Costs** page: probate fees, valuation fees, insurance for the empty house, postage, travel, the Gazette notice.

For each cost you record what it was, who paid it (the estate's account, or a named person out of their own pocket), and whether it is reimbursable. The tool keeps a per-person reimbursement ledger, so it is always clear who is owed what.

- **Co-executor transparency is built in.** When one executor records or edits a cost, the other executors are notified. This is deliberate: money spent on the estate should never be a surprise to anyone.
- **The by-type view** groups costs by category with a chart and a running total, filterable by date and by who paid, so the answer to "where has the money gone?" is always one click away and explainable line by line.
- Costs feed the estate accounts automatically. The tax treatment is applied for you: the funeral is deductible for inheritance tax; general administration costs are not, but they do reduce what is left for the beneficiaries.

## 8. Estate accounts

The **Estate accounts** page is the transparent set of books that residuary beneficiaries are entitled to see. It is arranged as four connected accounts:

1. **Capital account**: everything owned at the date of death, less deductible debts and the funeral, giving the net estate.
2. **Administration account**: the net estate, adjusted for any gains or losses when assets were sold, less administration costs, less any inheritance tax, less the fixed gifts in the will, giving the **residue** (what is left to share).
3. **Income account**: any income the estate earned during the administration (interest, dividends, rent), less expenses and tax on it.
4. **Distribution account**: the residue and income split between the residuary beneficiaries by their shares, less anything already paid out, giving the balance still due to each person.

At the top of the page is a **balance indicator**. The accounts obey a strict arithmetic identity: everything that came into the estate must equal everything that went out plus everything still held. When that identity holds, the page shows **balanced**. If it ever shows unbalanced, something has been recorded inconsistently, and the page will help you find it. A balanced set of accounts is your evidence, to the beneficiaries and to HMRC, that every pound is accounted for.

Beneficiary entitlements update live: replace an estimated valuation with a confirmed one and each residuary share changes on screen. Interim payments to beneficiaries are guarded; the tool will not treat the residue as safe to pay out until the statutory creditor notice window has closed and known creditors are settled or provided for (section 13 explains this protection).

## 9. The inheritance tax workbench

The **Inheritance tax** page computes the estate's tax position from what you have recorded, and, just as importantly, tells you **which reporting route applies**. Everything on this page is calculated by fixed, tested rules from published HMRC figures; the sources and their dates are shown alongside.

### The settings

Estate-level settings drive the calculation, and you can review them in the settings dialog on this page:

- The **nil rate band** (NRB): the standard tax-free allowance, 325,000 pounds.
- The **residence nil rate band** (RNRB): an extra allowance, up to 175,000 pounds, available when a home passes to direct descendants (children or grandchildren).
- **Transferred allowances**: if the person who died was widowed and their late spouse did not use their own allowances, the unused percentage can be transferred, potentially doubling both allowances.
- The **charity rate**: if 10 per cent or more of the estate goes to charity, the tax rate on the rest drops from 40 per cent to 36 per cent.
- The **taper**: estates worth more than 2,000,000 pounds start losing the residence allowance, at a rate of 1 pound for every 2 pounds over.

### Recompute and the assessment

The assessment recomputes automatically whenever you change an asset, a liability or the settings, and you can trigger it manually with the **Recompute** button. Every recompute is saved as a snapshot, so you can always look back and see how the position changed and why.

The assessment shows, line by line: the total estate, the allowances that apply, the taxable amount, and the estimated tax. Worked example with round numbers: an estate of 900,000 pounds, with full transferred allowances and a home worth at least 350,000 pounds passing to descendants, has allowances of 1,000,000 pounds and pays no tax; the same estate at 1,100,000 pounds would pay 40 per cent on the 100,000 pounds above the allowance, which is 40,000 pounds.

### "Excepted estate" and "must file IHT400", in plain words

HMRC has two reporting routes:

- An **excepted estate** is one simple or small enough that no full inheritance tax account is needed; the figures are reported as part of the probate application instead. Most estates well below the thresholds take this route, and it is far less work.
- **IHT400** is the full inheritance tax account: a long main form plus supporting schedules, one per type of asset. It is required when the estate does not meet the excepted conditions, and, crucially, **it is always required if you claim the residence nil rate band**, even if no tax ends up being due. The workbench applies this rule for you and shows the result prominently.

When IHT400 is required, the workbench derives the **schedules checklist** from what the estate actually contains: a property means schedule IHT405, bank accounts mean IHT406, household goods IHT407, shares IHT411 or IHT412, transferred allowances IHT402 and IHT436, the residence allowance IHT435, and so on. Each required schedule can create its own preparation task.

One more safeguard: a **professional review checkpoint** sits on the tax output and is switched on by default. It is a reminder that a near-threshold estate deserves a professional's eye before anything is submitted. You can record that review as done, or decide with your co-executor that it is not needed; the tool will not make that judgement for you.

## 10. The knowledge library and the assistant

The **Knowledge library** page holds the HMRC forms, form notes and guidance the administration relies on, fetched from the official and support-organisation sources (gov.uk, The Gazette, NHS England, NS&I, and bereavement references from organisations such as Age UK, Marie Curie and Citizens Advice) and cached inside the tool. That means:

- You can **read the guidance in-app**, alongside your own records, even if gov.uk is temporarily unavailable.
- Every document shows its **source address and the date it was fetched**, so you always know what you are reading and how current it is.
- When a source document changes on its website, the tool flags it, so figures and process steps that depend on it get looked at again.

**Search** finds passages across the whole cached corpus.

**The assistant** (the Ask tab) is a conversation, not a one-shot question box. Put a question in plain English, such as "how do I complete box 91 on the IHT400" or "when is the tax due", and follow up naturally; it remembers the conversation. Its answers follow strict rules:

1. **Every answer cites its sources.** Numbered citations sit next to the statements they support, each source lists the exact passages it was quoted for, and anything the assistant retrieved but did not rely on is listed separately as *related sources*, so you can always tell the two apart.
2. **It only answers from the cached official guidance.** Every answer ends by saying plainly **what the retrieved guidance does not cover**, and it will suggest gov.uk or a professional rather than improvise from general knowledge.
3. **It gives guidance, not advice.** It can tell you what the official guidance says; it cannot tell you what you should decide. A disclaimer to that effect is always visible.
4. **It knows where you are, but never invents a figure.** Alongside the guidance, the assistant sees your estate's current position: the registers, task and timeline progress including your comments, and the latest tax assessment, with anything still an estimate clearly flagged as such. It carries key passages and facts forward between conversations until your records change. Every figure it mentions comes from your registers and the deterministic tax engine, never from the AI model itself.

Two simple guardrails sit around it: a question that looks unrelated to estate administration is paused for your confirmation before anything is spent or stored, and there is a daily question limit as a cost ceiling. An administrator can adjust both on the **Settings** page under **Parameters**, and every change is recorded in the audit trail. The same page offers optional **semantic search**: switched off by default because it downloads and runs a local language model that not every machine can manage; when on, it improves how well the library matches questions phrased in your own words, and nothing leaves your machine. The assistant itself needs an AI service key to be configured (see the installation guide); the library and search work fully without one.

An administrator keeps the library up to date with the **Ingest** button on the Library tab, or with the bundled `scripts/fetch-knowledge.sh` helper that fetches the whole starter library from the official sources (see the installation guide). Ingest needs an internet connection because it fetches from the source websites.

## 11. Drafts and approval

The assistant can prepare paperwork for you: a draft of the IHT400 based on your registers, a draft notification letter to a bank or insurer, a plain-English narration of the tax assessment, or suggested tasks. All of it lands on the **Drafts** page, and all of it obeys one rule:

**Nothing is sent or filed automatically. A person approves, and a person submits.**

The flow is always the same:

1. You request a draft (for example, "draft a notification letter to Alex Example's bank").
2. The assistant prepares it and stores it as a **draft**, together with its sources and a list of any gaps it found (missing values, estimates not yet confirmed).
3. An approval request appears, and the executors are notified.
4. You read the draft. You can approve it, or note what is wrong and have it redrafted, or reject it.
5. Approving records **who approved it and when**, permanently. Only then is the draft treated as final.
6. **You** then act on it outside the tool: you post the letter, you submit the form to HMRC, you make the payment. The tool has no ability to do any of those things, by design. There is no send button anywhere in it, and the safeguards are covered by automated tests.

The same discipline applies to figures: any number appearing in a draft form or narration comes from your registers and the deterministic tax engine, never from the AI model itself.

## 12. PDF exports

Several documents export to PDF, stored in the documents vault and downloadable:

- **Estate accounts**: the full four-account statement, suitable for sharing with residuary beneficiaries for their approval.
- **IHT draft**: the current assessment and figures arranged for checking against the official form, clearly marked as a draft. It is not the official HMRC form and is never submitted by the tool.
- **Clearance application draft**: a content sheet for form IHT30, the certificate that confirms HMRC has no further tax claim on the estate.
- **Approved notification letters**: once a letter draft is approved, it renders to a printable PDF for you to sign and post.

Every export is recorded in the audit trail.

## 13. Further modules

**Reliefs (money back if values fall).** If quoted shares are sold within 12 months of death at an overall loss, or land or buildings within 4 years below their probate value, tax already paid can be reclaimed (forms IHT35 and IHT38). The Reliefs page watches for these situations in your records, tracks the claim windows, and estimates the reclaim. Real money is lost when nobody watches these windows; this page watches them.

**Administration tax.** Income tax and capital gains tax can arise while the estate is being administered, separate from inheritance tax. This page tracks income per tax year, works out whether the simple "informal" reporting route applies or the estate must register as complex, and enforces the hard 60-day deadline for reporting a residential property sale (a task is created automatically the moment a sale is recorded).

**Asset tracing.** Confidence that nothing has been missed, using the free official services: My Lost Account for forgotten bank and savings accounts, the Pension Tracing Service, and the Unclaimed Assets Register. Each search becomes a task. A clear warning is shown: never pay a "reclaim firm" for these searches, because they are free.

**Digital assets.** The non-financial digital life: email accounts, photo storage, social media, subscriptions, memberships, loyalty schemes. Each item records whether the login is known and what should happen to it (cancel, memorialise, transfer, close, download). Recurring subscription costs surface here so they get cancelled rather than quietly renewing.

**Veteran checklist.** If the person who died served in the armed forces, this checklist covers the service-specific notifications and support routes: the pension scheme, the benevolent funds and associations, and possible funeral-cost help. Each item is worked as a contact and a task, so it is logged, not just read.

**Executor protection and decisions.** Two protections for you personally. First, the **Section 27 creditor notice**: placing a notice in The Gazette and a local paper opens a two-month window for unknown creditors to come forward; distribute after it closes and you are protected from personal liability for debts you did not know about. The tool derives the deadline and blocks "safe to distribute" until the window has closed. Second, the **decision log**: an immutable record of the significant decisions the executors take, with the date, the rationale and who agreed. Entries cannot be edited or deleted, which is exactly what makes the log worth having; to correct one, record a new entry that refers to it.

## 14. When you need help

Even with the tool to lean on, some moments in an administration are simply too much, and some people are doing all of this alone. The **When you need help** page (in the Guidance section) is a plain directory of organisations that can help when the app cannot: who they are, what they help with, their phone number (tap it on a phone to dial), their hours, and a link to their website.

It is organised the way need tends to arrive:

- **Someone to talk to**: Samaritans, NHS urgent mental health support, bereavement charities, and lines for older and younger bereaved people.
- **Practical help and money**: free advice on the paperwork, the benefits you may be owed, and money worries.
- **Armed forces families**: support routes when the person who died served.
- **Tax and probate**: the official HMRC and probate helplines.

Everything listed is free to contact. Each number was checked against the organisation's own website, and the page says when; where a number could not be fully verified, the page says to check the organisation's website rather than guessing.

## 15. Roles and privacy

Every user has one of three roles, fixed on the server, decided by email address:

| | Administrator | Executor | Viewer |
|---|---|---|---|
| See estate data | Yes | Yes | Read-only, minus private items |
| Add and edit records | Yes | Yes | No |
| Approve drafts | Yes | Yes | No |
| Configure settings and users | Yes | Limited | No |
| Export or erase the estate | Yes | With confirmation | No |

The **viewer** role suits a beneficiary or family member who should be able to follow progress without being able to change anything. Viewers never receive notifications and never see editing controls.

Individual records can be marked **executor-private**, which hides them from the viewer entirely. This is for the occasional item that is sensitive within the family; use it sparingly, since transparency is the default.

These rules are enforced on the server, not just hidden in the browser, so they cannot be bypassed.

## 16. The audit trail

Everything that happens in the tool is recorded, permanently:

- **Every change**: who created, edited, viewed or approved what, and when, with the before and after values.
- **Every approval**: the register of every draft that was approved before it was treated as final.
- **An activity feed**: the recent changes across the estate, so co-executors can follow along day to day.
- **Sensitive reads too**: downloading a document, or viewing an executor-private item, is itself logged.

Nothing is ever hard-deleted in normal use; records are archived with a reason instead, so the history stays complete. The one exception is the estate-erase function (administrator only, with explicit confirmation), which exists so that your data can leave with you.

The audit trail is not surveillance; it is protection. If a beneficiary, HMRC or a court ever asks "who decided this, and when?", the answer is on record.

---

*AD Assistant is open-source software provided under the MIT licence. It informs and drafts; it is not legal, tax or financial advice, and it is not a substitute for professional help. UK Government content in the knowledge library is used under the Open Government Licence with attribution.*
