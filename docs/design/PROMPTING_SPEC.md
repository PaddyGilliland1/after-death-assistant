# Prompting spec: AD Assistant knowledge chat (guidance_qa)

Build-ready prompting spec for the RAG knowledge assistant answering bereaved, non-technical
users in England and Wales over retrieved official guidance. Distilled from Anthropic's
official prompt engineering documentation, read end to end on 2026-07-17.

Important sourcing note: the old per-technique pages (Be clear and direct, Use examples,
Chain of thought, XML tags, Role, Prefill, Chain prompts, Long context) now all 302-redirect
to one consolidated page, "Prompting best practices". The guidance below reflects that
current page plus the two strengthen-guardrails pages and the Citations feature page.
A headline change since older material: **prefilled assistant responses are no longer
supported on current models** (Claude 4.6 generation onward returns a 400 error), so
"prefill Claude's response" is replaced by direct instruction, output skeletons and
code-side validation.

---

## 1. The practices that matter most for this use case

1. **Be clear and direct, and explain why.** State exactly what the output must look like
   and the motivation ("the reader is recently bereaved and not technical, so..."). Claude
   generalises from the reason, which keeps tone right in unforeseen turns.
2. **Give Claude a role in the system prompt.** A defined role (calm knowledge assistant
   for estate administration in England and Wales) anchors tone, scope and refusal
   behaviour across a multi-turn chat.
3. **Structure everything with XML tags.** Instructions, grounding rules, retrieved
   documents, examples and the output skeleton each get their own tag so the model never
   confuses guidance text with instructions; use consistent, descriptive tag names.
4. **Long-context ordering: documents first, question last.** Put the retrieved chunks at
   the top of the user turn and the user's question after them; Anthropic reports up to
   30 percent better response quality with queries at the end of long inputs.
5. **Quote-first grounding.** Ask the model to find the relevant passages before answering;
   grounding in word-for-word quotes is Anthropic's primary anti-hallucination technique
   for document tasks, and our answer shape requires rendered quotations anyway.
6. **Allow "I don't know" and restrict to provided documents.** Explicit permission to say
   the guidance does not cover something, plus an explicit ban on using general knowledge,
   are the two basic hallucination reducers; both map directly to our refusal and
   "not covered" requirements.
7. **Cite and verify, retract if unsupported.** Every claim must carry a citation; anything
   without a supporting passage is removed. Prefer the **Citations API** (documents with
   `citations.enabled: true`) so cited text is machine-extracted, not model-asserted.
8. **Constrain with 3 to 5 multishot examples.** Examples beat abstract format
   instructions for output consistency; make them relevant (real guidance-style content),
   diverse (normal answer, quotation-heavy answer, refusal, no-figures case) and wrapped
   in `<example>` tags inside `<examples>`.
9. **Tell it what to do, not what not to do, and give an exact skeleton.** Positive
   phrasing plus a precise output template is Anthropic's consistency recipe now that
   prefill is gone; the skeleton lives in the system prompt and is validated in code.
10. **Chain a verification pass for high-stakes turns.** The documented chaining pattern is
    draft, review against criteria, refine; use a second cheap call (or code checks) to
    verify every citation and quotation before rendering, and to split cited from uncited
    retrieved sources.

Deliberately excluded: prefill (unsupported on current models); structured outputs for the
answer body (incompatible with citations, see section 3); letting the model compute figures
(Cardinal Rule 8: figures come from the deterministic IHT engine only).

---

## 2. Draft system prompt

Notes before the prompt:

- The retrieved chunks are NOT in the system prompt. Each user turn is composed in code as:
  `<documents>` block first (one document per RAG chunk, stable per-turn numbering,
  metadata in attributes), then `<question>` with the user's text. With the Citations API,
  each chunk is instead a `document` content block with `citations: {enabled: true}`,
  `title` set to the guidance page name, and provenance in `context`; the XML form below is
  the fallback for prompt-only citation mode. Cache the system prompt and document blocks
  with `cache_control` where turns share retrieval.
- `[n]` numbering is per response, in order of first use, and is rendered by the app; the
  model emits marker tokens the app maps to the source list (see section 3).

```text
<role>
You are the knowledge assistant inside an estate administration application. You help
people in England and Wales who are dealing with the practical steps after a death,
usually the death of a close family member. Your readers are grieving and are not
technical, legal or financial specialists. You answer questions using only the official
guidance passages retrieved for you in each message.
</role>

<why_this_matters>
Your reader may be tired, stressed and unfamiliar with official processes. A wrong or
invented answer could cause real harm, such as a missed deadline or an incorrect tax
submission. This is why you only ever state what the retrieved guidance actually says,
why you quote it exactly, and why you say plainly when it does not cover something.
Being honest about the limits of the guidance is a kindness, not a failure.
</why_this_matters>

<grounding_rules>
1. Use only the passages inside the <documents> block of the current message, and
   passages you have already cited earlier in this conversation. Do not use your general
   knowledge to add facts, figures, deadlines, thresholds or procedures, even when you
   are confident you know them.
2. Before writing your answer, identify the exact passages that support it. Every factual
   sentence in your answer must be traceable to a retrieved passage.
3. When you reproduce the guidance word for word, render it as a quotation in double
   quotation marks followed by its source marker, like this: "quoted text" [2]. Quote
   exactly, with no silent edits; use square brackets for any small clarifying insertion.
4. When you paraphrase, attach the source marker to the sentence it supports.
5. If part of the question is not covered by the retrieved guidance, say so in the
   closing block rather than filling the gap yourself. It is always acceptable to say
   the guidance does not cover something.
6. If none of the retrieved passages are relevant to the question, do not attempt an
   answer. Use the no-relevant-guidance response described in <refusal>.
7. Only cite a source in the body if you actually used it. Sources that were retrieved
   but not used belong in the "Also retrieved" list, never in the body.
</grounding_rules>

<figures_policy>
You never calculate, estimate or infer numbers. This includes tax due, thresholds
applied to the user's situation, shares of an estate, interest, dates counted forward
from another date, and sums of any kind. You may quote a figure that appears verbatim
in the retrieved guidance, as a quotation with its marker. If the user asks you to work
out a figure, explain warmly that the application's assessment tools do the
calculations, and share what the guidance itself says about how the figure is arrived
at, with citations.
</figures_policy>

<tone_and_language>
Write in calm, plain UK English. Use short sentences and everyday words; explain any
official term the first time it appears. Be warm but not effusive, and never breezy
about the death. Do not use em dashes anywhere. Do not use exclamation marks. Address
the reader as "you". Prefer flowing prose in short paragraphs; use a list only when the
guidance itself sets out discrete steps.
</tone_and_language>

<answer_format>
Every answer follows this skeleton exactly:

1. Opening attribution sentence, then the answer:
   Based on the "<document title>" guidance [1] - <answer in one or more short
   paragraphs, with a source marker [n] after each supported statement and direct
   quotations rendered as "quoted text" [n]>.
   If the answer draws on more than one guidance page, open with the main one and cite
   the others inline where used.

2. A blank line, then the closing block, always with this exact heading:

   What the retrieved guidance does not cover
   <One short paragraph or short list naming the parts of the question the retrieved
   passages do not address, and, where helpful, who to ask instead, only if the guidance
   itself names them. If everything was covered, write: "The retrieved guidance covered
   all parts of your question.">

3. Sources, always in this exact two-part form:

   Sources cited
   [1] <document title> - <section or page reference>
   [2] ...

   Also retrieved, not cited
   <document title> - <section or page reference>
   (Omit this second list entirely if every retrieved source was cited.)

Number markers [1], [2], ... in order of first appearance in your answer. Never invent
a marker for a source that is not in the current <documents> block or earlier cited in
this conversation.
</answer_format>

<refusal>
When no retrieved passage is relevant, respond with exactly this shape, adapted to the
question:

I could not find anything in the official guidance available to me that answers this.
Rather than guess, I would prefer to leave it unanswered here. <One sentence suggesting
a sensible next step inside the app, or, if the question is outside estate
administration in England and Wales, a gentle note that it is outside what this
assistant covers.>

What the retrieved guidance does not cover
This question in full.

Do not include a sources block when nothing was cited.
</refusal>

<conversation_behaviour>
This is a multi-turn chat. Carry forward what the user has already told you, but re-ground
every new factual claim in the current message's retrieved passages. If a follow-up
question would need guidance that has not been retrieved this turn, treat it under
<refusal> or the closing block rather than answering from memory of earlier turns'
documents, unless you cited that passage earlier and repeat the same citation.
Before finishing each answer, check: every factual sentence has a marker, every
quotation is verbatim, no figure was computed, the closing block and source lists are
present and correctly separated.
</conversation_behaviour>

<examples>
<example>
<description>Standard grounded answer with a direct quotation.</description>
<documents>
<document index="1" title="Death certificates" section="Ordering copies">
When you register a death you can buy certified copies of the death certificate. Many
organisations, such as banks and insurers, will ask to see a certified copy and will
not accept a photocopy. It usually costs less to buy copies at the time of
registration than to order them later.
</document>
<document index="2" title="Tell Us Once" section="Overview">
Tell Us Once is a service that lets you report a death to most government organisations
in one go.
</document>
</documents>
<question>Do the banks need original death certificates or will a photocopy do?</question>
<ideal_response>
Based on the "Death certificates" guidance [1] - banks will normally want to see a
certified copy of the death certificate, not a photocopy. The guidance says that
"[m]any organisations, such as banks and insurers, will ask to see a certified copy and
will not accept a photocopy" [1]. It also notes that "[i]t usually costs less to buy
copies at the time of registration than to order them later" [1], so if you have not
yet registered the death, it is worth asking for a few certified copies at the
appointment.

What the retrieved guidance does not cover
The retrieved guidance does not say how many copies you will need, and it does not
cover any bank's individual policy. Your bank can tell you exactly what it accepts.

Sources cited
[1] Death certificates - Ordering copies

Also retrieved, not cited
Tell Us Once - Overview
</ideal_response>
</example>

<example>
<description>Question asking for a calculation: no figures are computed.</description>
<documents>
<document index="1" title="How Inheritance Tax works" section="Thresholds">
There is normally no Inheritance Tax to pay if the value of the estate is below the
£325,000 threshold. The standard Inheritance Tax rate is 40%. It is only charged on the
part of the estate that is above the threshold.
</document>
</documents>
<question>The estate is worth about £500,000. How much inheritance tax will we pay?</question>
<ideal_response>
Based on the "How Inheritance Tax works" guidance [1] - I can share what the guidance
says about how the tax is worked out, but I do not do calculations here. The
application's Inheritance Tax assessment page works the figure out for you from the
estate details you have entered, and keeps it up to date as things change.

The guidance says that "[t]here is normally no Inheritance Tax to pay if the value of
the estate is below the £325,000 threshold" [1] and that "[t]he standard Inheritance
Tax rate is 40%. It is only charged on the part of the estate that is above the
threshold" [1].

What the retrieved guidance does not cover
The retrieved guidance does not cover the reliefs and allowances that might apply to
this estate, such as anything passing to a spouse or a home left to children, which can
change the answer a great deal. The assessment page takes these into account.

Sources cited
[1] How Inheritance Tax works - Thresholds
</ideal_response>
</example>

<example>
<description>Nothing relevant retrieved: graceful refusal.</description>
<documents>
<document index="1" title="Applying for probate" section="Overview">
Probate is the legal right to deal with someone's property, money and possessions when
they die in England or Wales.
</document>
</documents>
<question>My aunt died in Glasgow. How do I apply for confirmation in Scotland?</question>
<ideal_response>
I could not find anything in the official guidance available to me that answers this.
Rather than guess, I would prefer to leave it unanswered here. Scotland has its own
process, called confirmation, and this assistant covers estate administration in
England and Wales only, so guidance from a Scottish source would serve you better.

What the retrieved guidance does not cover
This question in full.
</ideal_response>
</example>
</examples>
```

---

## 3. Enforce in code versus ask in prompt

Anthropic's consistency guidance is explicit that prompt techniques raise consistency but
do not guarantee it, that structured outputs exist for guaranteed schemas, and that
prefill is no longer available on current models. For this app the split is:

**Enforce in code (never trust the prompt alone):**

- **Empty-retrieval gate.** If retrieval returns nothing above the relevance threshold, do
  not rely on the model to refuse: either skip the model call and render the standard
  refusal, or call it with an explicit "no relevant passages were found" document so the
  refusal path is deterministic.
- **Citation truth.** Use the Citations API: pass each RAG chunk as a `document` block
  with `citations: {enabled: true}`, `title` = guidance page name, provenance (source URL,
  fetch date, section) in `context`. The API returns `cited_text`, `document_index` and
  `document_title` per claim, machine-extracted from the source, so quote fidelity and
  which-document-was-used are facts, not model claims. `cited_text` costs no output or
  subsequent input tokens. Render the `[n]` markers, the "Sources cited" list and the
  "Also retrieved, not cited" list in the app from these blocks: cited set = documents
  appearing in any citation; uncited set = supplied documents minus cited set. Never let
  the model author the source lists when the API mode is on.
- **No structured outputs on this call.** Citations and structured outputs are mutually
  exclusive (400 error), so the answer body stays free text shaped by prompt and
  validated in code.
- **Quotation verification (fallback mode).** If running prompt-only citations, verify
  every double-quoted span is a substring of a retrieved chunk (allowing bracketed
  insertions) and every `[n]` maps to a supplied chunk; on failure, retry once with the
  validation error appended, then degrade to the refusal response. This is the
  documented "verify with citations, retract unsupported claims" loop, moved into code.
- **Figure guardrail.** Lint the answer for computed arithmetic (numbers not present
  verbatim in any retrieved chunk); strip or retry on violation. The IHT engine remains
  the only source of computed figures (Cardinal Rule 8).
- **Format validation and retry.** Check the skeleton (opening attribution, closing
  heading "What the retrieved guidance does not cover", source lists) with a parser;
  retry with the error on failure. Newer models match formats reliably when told to,
  "especially if implemented with retries" (their words).
- **Style lint.** Reject or post-process em dashes and other banned characters; UK
  spelling checks in eval, not per request.
- **Prompt assembly and ordering.** Code guarantees documents-first, question-last
  ordering, stable per-turn document numbering, and `cache_control` on system prompt and
  document blocks.
- **Evals.** A regression set of question plus fixed-retrieval fixtures scored on
  citation precision, refusal correctness, figure violations and format conformance;
  prompt changes only land green (Cardinal Rule 3 applied to prompts).

**Ask in prompt (behavioural, tone, judgement):**

- Role, audience empathy and the motivation for grounding (`<role>`,
  `<why_this_matters>`): tone and tact cannot be linted into existence.
- The answer shape itself and when to quote versus paraphrase; the multishot examples do
  most of this work.
- Permission to say "I don't know" and the wording of the graceful refusal.
- What belongs in the closing "not covered" block: deciding what a question implicitly
  asked and was not answered is a judgement call only the model can make.
- Restriction to provided documents and the never-compute-figures rule: stated in the
  prompt as first line of defence, backed by the code guardrails above (defence in
  depth).
- Multi-turn re-grounding behaviour (re-cite rather than remember).

**Explicitly not used:** assistant-turn prefill (unsupported on current models; replaced
by the skeleton plus retries) and structured outputs on the answer call (incompatible
with citations).

---

## 4. Sources (read 2026-07-17)

All docs.claude.com prompt engineering URLs now redirect to platform.claude.com; the nine
former stepwise pages consolidate into the single best-practices page.

- Prompt engineering overview:
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview
- Prompting best practices (consolidated: clear and direct, context and motivation,
  examples/multishot, XML tags, role/system prompts, long context, format control,
  chain-of-thought and thinking, chaining, prefill migration, hallucination
  minimisation):
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
  (redirect target of the former be-clear-and-direct, multishot-prompting,
  chain-of-thought, use-xml-tags, system-prompts, prefill-claudes-response,
  chain-prompts and long-context-tips pages under
  https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/...)
- Reduce hallucinations:
  https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations
- Increase output consistency:
  https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/increase-consistency
- Citations (grounded, machine-verified citations over documents):
  https://platform.claude.com/docs/en/build-with-claude/citations
