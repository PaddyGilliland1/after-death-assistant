# Anthropic API build brief: cited, conversational RAG on claude-sonnet-5

Researched 2026-07-17 against the live official docs. Note: docs.claude.com now 302-redirects to **platform.claude.com/docs** (same content, new host). All URLs below verified today.

---

## 1. Models and how to address claude-sonnet-5

Source: https://platform.claude.com/docs/en/about-claude/models/overview
Migration detail: https://platform.claude.com/docs/en/about-claude/models/migration-guide (section "Migrating from Claude Sonnet 4.6 to Claude Sonnet 5")
Prompting guide: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5

### Current lineup (Claude API IDs)

| Model | API ID | Context | Max output | Pricing (in/out per MTok) |
|---|---|---|---|---|
| Claude Fable 5 | `claude-fable-5` | 1M | 128k | $10 / $50 |
| Claude Opus 4.8 | `claude-opus-4-8` | 1M | 128k | $5 / $25 |
| **Claude Sonnet 5** | `claude-sonnet-5` | 1M | 128k | $3 / $15 (intro **$2 / $10 until 31 Aug 2026**) |
| Claude Haiku 4.5 | `claude-haiku-4-5` | 200k | 64k | $1 / $5 |

`claude-sonnet-5` is a dateless **pinned snapshot** (the 4.6+ naming convention), not an evergreen pointer. The Models API (`/v1/models`) returns `max_input_tokens`, `max_tokens` and a `capabilities` object per model if you want to introspect programmatically.

### Hard constraints on claude-sonnet-5 (breaking vs Claude 4.x)

1. **Sampling parameters rejected.** Setting `temperature`, `top_p` or `top_k` to any non-default value returns a **400 error**. Remove them entirely; steer style via prompting instead. (This matters for `langchain-anthropic`: do not pass `temperature` in `ChatAnthropic(...)` for this model.)
2. **Manual extended thinking removed.** `thinking: {"type": "enabled", "budget_tokens": N}` returns a **400 error**. Use adaptive thinking + effort.
3. **Adaptive thinking is ON by default.** A request with no `thinking` field runs with adaptive thinking (Sonnet 4.6 ran without). Disable with `thinking: {"type": "disabled"}`. Thinking content defaults to omitted (empty thinking blocks); pass `thinking: {"type": "adaptive", "display": "summarized"}` if you want readable summaries. Raw thinking is never returned.
4. **Effort parameter** replaces `budget_tokens`, syntax `output_config: {"effort": "high"}`. Levels: `low | medium | high (default) | xhigh | max`. Cross-model mapping: Sonnet 5 at `medium` is roughly Sonnet 4.6 at `high`. For a chat RAG assistant, `high` (default) is fine; `medium` or `low` for latency-sensitive chat. Setting `"high"` is identical to omitting the parameter.
5. **New tokenizer: ~30% more tokens for the same text** (tokenizer introduced with Opus 4.7). Re-baseline with `/v1/messages/count_tokens`; do not reuse counts from 4.x models. `max_tokens` values tuned for 4.6 may truncate equivalent output. Per-token price unchanged but effective cost per character rises ~30%.
6. **`max_tokens` is a hard cap on thinking + response text combined.** At `high`+ effort leave headroom, otherwise you can get an answer that is mostly thinking then truncates with `stop_reason: "max_tokens"`.
7. **Assistant prefill returns 400** (same as Sonnet 4.6). Use structured outputs (`output_config.format`) or system-prompt instructions. Note: structured outputs are **incompatible with citations** (see section 2).
8. **Minimum cacheable prompt: 1,024 tokens** on Sonnet 5 (prompt-caching page table; the migration guide says 512 in one place, treat 1,024 from the caching page as authoritative and verify empirically).

### How prompts should differ vs Claude 4.x

- **More literal instruction following**: it does not generalise instructions or infer unmade requests; state scope explicitly ("apply to every section, not just the first").
- **Verbosity is task-calibrated**, not fixed. If you need concision: "Provide concise, focused responses. Skip non-essential context." Positive examples beat "don't" instructions.
- **More agentic tool use** by default. With thinking disabled it is less likely to reach for tools; if you rely on tool calls with thinking off, add an explicit nudge in the system prompt.
- Performs well out of the box on existing Sonnet 4.6 prompts; remove any scaffolding that forced interim progress updates (it produces good ones natively).
- No temperature means run-to-run variety must come from prompting (e.g. "propose options first").

---

## 2. Citations (the centrepiece): native cited answers

Sources:
- https://platform.claude.com/docs/en/build-with-claude/citations
- https://platform.claude.com/docs/en/build-with-claude/search-results

**All active models support citations**; the search-results page explicitly lists Claude Sonnet 5 (`claude-sonnet-5`). No beta header is required for either documents or `search_result` blocks. Search result blocks are available on Claude API, Bedrock and Google Cloud.

Why this beats prompt-asked `[n]` markers (verbatim from docs):
- `cited_text` **does not count toward output tokens** (and is not counted toward input tokens when passed back in later turns).
- Citations are parsed by the API and are "guaranteed to contain valid pointers to the provided documents".
- "significantly more likely to cite the most relevant quotes" than prompt-based approaches.

### 2a. Request: search_result blocks (recommended for RAG)

Two delivery methods, both cite identically:
1. **From tool results** (dynamic RAG: Claude calls your `search_knowledge_base` tool; you return `search_result` blocks inside the `tool_result` content).
2. **As top-level user content** (you retrieve first, then inject results into the user message).

Schema (from docs, verbatim shape):

```json
{
  "type": "search_result",
  "source": "https://example.com/article",
  "title": "Article Title",
  "content": [
    { "type": "text", "text": "The actual content of the search result..." }
  ],
  "citations": { "enabled": true }
}
```

`type`, `source`, `title`, `content` (non-empty array of text blocks) are required. `citations` and `cache_control` optional. **Citations default to disabled for search results; you must set `"citations": {"enabled": true}`.** All-or-nothing: every `search_result` in the request must have the same citations setting or the API errors.

Full request, top-level method, adapted to claude-sonnet-5 (structure copied from the docs example, model swapped):

```json
{
  "model": "claude-sonnet-5",
  "max_tokens": 4096,
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "search_result",
          "source": "https://docs.company.com/api-reference",
          "title": "API Reference - Authentication",
          "content": [
            { "type": "text", "text": "All API requests must include an API key in the Authorization header. Keys can be generated from the dashboard. Rate limits: 1000 requests per hour for standard tier, 10000 for premium." }
          ],
          "citations": { "enabled": true }
        },
        {
          "type": "search_result",
          "source": "https://docs.company.com/quickstart",
          "title": "Getting Started Guide",
          "content": [
            { "type": "text", "text": "To get started: 1) Sign up for an account, 2) Generate an API key from the dashboard, 3) Install our SDK using pip install company-sdk, 4) Initialize the client with your API key." }
          ],
          "citations": { "enabled": true }
        },
        {
          "type": "text",
          "text": "Based on these search results, how do I authenticate API requests and what are the rate limits?"
        }
      ]
    }
  ]
}
```

Tool-result variant: same `search_result` objects go in `"content"` of the `tool_result` block:

```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_...",
      "content": [ { "type": "search_result", "source": "...", "title": "...", "content": [...], "citations": {"enabled": true} } ]
    }
  ]
}
```

### 2b. Response shape (verbatim from docs)

The answer comes back as interleaved text blocks; cited spans carry a `citations` array:

```json
{
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "All API requests must include an API key in the Authorization header. Keys can be generated from the dashboard.",
      "citations": [
        {
          "type": "search_result_location",
          "cited_text": "All API requests must include an API key in the Authorization header. Keys can be generated from the dashboard. Rate limits: 1000 requests per hour for standard tier, 10000 for premium.",
          "source": "https://docs.company.com/api-reference",
          "title": "API Reference - Authentication",
          "search_result_index": 0,
          "start_block_index": 0,
          "end_block_index": 1
        }
      ]
    },
    { "type": "text", "text": "\n\nTo set this up from scratch, you'll need to " },
    {
      "type": "text",
      "text": "sign up for an account, generate an API key from the dashboard, install the SDK using `pip install company-sdk`, and initialize the client with your API key.",
      "citations": [
        {
          "type": "search_result_location",
          "cited_text": "To get started: 1) Sign up for an account, 2) Generate an API key from the dashboard, 3) Install our SDK using pip install company-sdk, 4) Initialize the client with your API key.",
          "source": "https://docs.company.com/quickstart",
          "title": "Getting Started Guide",
          "search_result_index": 1,
          "start_block_index": 0,
          "end_block_index": 1
        }
      ]
    }
  ]
}
```

Citation fields for `search_result_location`: `source`, `title` (or null), `cited_text` (full text of the cited block slice, free of token charge), `search_result_index` (0-based across ALL `search_result` blocks in the request, in order of appearance, across all messages and tool results), `start_block_index` / `end_block_index` (0-based, end exclusive, a slice of that result's `content` array).

**Granularity rule:** the text block is the minimal citable unit; Claude cites whole blocks, not substrings. Split retrieval chunks into smaller text blocks inside one `search_result` to get finer citation boundaries.

**Streaming:** citations arrive as `citations_delta` inside `content_block_delta` events, one citation per delta, appended to the current text block's `citations` list.

### 2c. Document blocks (the alternative)

For whole documents rather than retrieval snippets:

```json
{
  "type": "document",
  "source": { "type": "text", "media_type": "text/plain", "data": "The grass is green. The sky is blue." },
  "title": "My Document",
  "context": "This is a trustworthy document.",
  "citations": { "enabled": true }
}
```

- Three source types: plain text (auto-chunked to sentences, citations are `char_location` with 0-indexed `start_char_index`/`end_char_index`, end exclusive), PDF base64/url/file_id (sentence-chunked, `page_location`, 1-indexed pages, end exclusive; scanned image-only PDFs not citable), and **custom content** (`"source": {"type": "content", "content": [{"type":"text","text":"chunk 1"}, ...]}`, no re-chunking, citations are `content_block_location` with block indices).
- `title` and `context` are passed to the model but never cited from; `context` is the place for metadata (stringified JSON is fine).
- `document_index` in citations is 0-indexed over all document blocks in the request, across all messages.
- Citations must be enabled on **all or none** of the documents in a request.
- Docs' own RAG tip, verbatim: "if you want Claude to be able to cite specific sentences from your RAG chunks, you should put each RAG chunk into a plain text document. Otherwise ... put RAG chunks into custom content document(s)."

### 2d. Limits and compatibility

- Text-only citation (no image citations). Search results: text blocks only, at least one per result.
- **Citations + structured outputs = 400 error** (`output_config.format` cannot be combined with citation-enabled documents/search results).
- Works with prompt caching, token counting, batch processing.
- Slight input-token overhead (system prompt additions + chunking).

---

## 3. Multi-turn chat, caching, and context management

### 3a. Multi-turn request shape

Standard Messages API: stateless, full history each call, alternating `user`/`assistant` entries in `messages`, system prompt in top-level `system` (string or array of text blocks). Append the assistant's previous `content` array verbatim (including its citation-bearing text blocks; `cited_text` passed back is not charged as input). Tool cycles: assistant `tool_use` block, then user `tool_result` block referencing `tool_use_id`.

### 3b. Prompt caching

Source: https://platform.claude.com/docs/en/build-with-claude/prompt-caching

- Syntax: `"cache_control": {"type": "ephemeral"}` (5 minute TTL, default) or `{"type": "ephemeral", "ttl": "1h"}`.
- **Two modes**: request-top-level `"cache_control"` = automatic caching (simplest, moves the breakpoint forward each turn, ideal for multi-turn chat), or explicit per-block breakpoints (up to **4**; automatic mode consumes one slot). 20-block lookback window per breakpoint.
- Cacheable: `tools`, `system` blocks, message content blocks including **documents** and search results, tool use/results. Not cacheable: thinking blocks directly, empty text blocks, citation sub-blocks (cache the top-level document instead).
- Pricing multipliers on base input rate: 5m write 1.25x, 1h write 2.0x, **read 0.1x**. For Sonnet 5 at standard pricing: $3 base, $3.75 5m-write, $6 1h-write, $0.30 read per MTok.
- Minimum cacheable: **1,024 tokens** for Sonnet 5 (512 for Fable 5).
- Invalidation is hierarchical (tools -> system -> messages): changing tool definitions kills everything; toggling citations or web search invalidates only messages cache; changing `tool_choice` or images invalidates messages cache.
- Usage fields in response: `cache_creation_input_tokens`, `cache_read_input_tokens`.
- Best practice for this app: put the **system prompt** (stable, first) and the **injected documents/search results** behind breakpoints; never put a breakpoint on content containing timestamps or per-request variance. Pre-warm with `max_tokens: 0` if latency-sensitive.

Citations doc confirms the combined pattern: `cache_control` directly on the citation-enabled document block:

```json
{
  "type": "document",
  "source": { "type": "text", "media_type": "text/plain", "data": "…long document…" },
  "citations": { "enabled": true },
  "cache_control": { "type": "ephemeral" }
}
```

Same for `search_result` blocks (`cache_control` is an allowed optional field on them).

### 3c. Context management features (current status)

| Feature | Status | Header | Notes |
|---|---|---|---|
| **Compaction** (server-side summarisation) | Beta | `anthropic-beta: compact-2026-01-12` | Supported on Sonnet 5. Anthropic's **recommended primary strategy** for long conversations. `context_management.edits: [{"type": "compact_20260112", "trigger": {"type": "input_tokens", "value": 150000}}]` (trigger min 50k, default 150k; optional `instructions`, `pause_after_compaction`). Response contains a `compaction` block; append it and the API drops everything before it next turn. Put `cache_control` on the compaction block and system prompt. Billing: sum the `usage.iterations` entries. https://platform.claude.com/docs/en/build-with-claude/compaction |
| **Context editing** (clear old tool results / thinking) | Beta | `anthropic-beta: context-management-2025-06-27` | `{"type": "clear_tool_uses_20250919", "trigger": {...}, "keep": {"type": "tool_uses", "value": 3}, "clear_at_least": {...}, "exclude_tools": [...]}` and `{"type": "clear_thinking_20251015", "keep": {...}}` (thinking edit must be listed first when combined). Clearing invalidates cache at the clearing point; `clear_at_least` guards against uneconomic invalidation. Response reports `context_management.applied_edits`. https://platform.claude.com/docs/en/build-with-claude/context-editing |
| **Memory tool** (cross-session persistence) | **GA, no beta header** | none | `tools: [{"type": "memory_20250818", "name": "memory"}]`. Client-side: Claude issues `view/create/str_replace/insert/delete/rename` commands under `/memories`; your handler executes them against your own storage and must enforce path-traversal protection. API auto-injects the memory protocol system prompt. Python SDK ships `BetaLocalFilesystemMemoryTool` + `client.beta.messages.tool_runner`. https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool |

Anthropic's own recommendation for conversation memory: **compaction** (server-side) to keep the active context small, **memory tool** for facts that must survive summarisation across sessions, context editing for agentic tool-heavy loops. Client-side summarisation is described as "not recommended for most use cases" now that compaction exists. Broader pattern write-ups: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents and https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

---

## 4. RAG-specific guidance from the docs

- **Prefer `search_result` blocks over `document` blocks for retrieval output.** The search-results page is explicitly framed for RAG: "brings web search-quality citations to your custom applications", each result carries its own `source` URL/identifier and `title`, and "eliminates the need for document-based workarounds". Use `document` blocks when the unit is a whole file (e.g. a PDF the user wants page-level citations for).
- **Citation granularity is under your control**: one text block per citable unit. Docs: "Splitting content into smaller, focused blocks gives Claude finer citation boundaries; combining content into one block means every citation returns the full text." For sentence-level citation of RAG chunks with document blocks, use one plain-text document per chunk.
- **Combining retrieval with chat history**: both methods coexist in one conversation (top-level pre-fetched results + tool-based dynamic search); `search_result_index` numbering spans all messages, so earlier turns' sources remain citable. Mixing search results with plain text and images in a user turn is supported.
- Best practices (docs verbatim, condensed): clear permanent source URLs; descriptive titles; break long content into logical text blocks; return only the most relevant results to avoid context overflow; on search failure return a plain text block ("No results found." / error message) rather than an empty result; `content` must contain at least one non-empty text block.
- Optional server tool: web search (`web_search`) produces the same citation format if you ever want live-web answers alongside your KB.

---

## 5. What this replaces in hand-rolled code

| Hand-rolled today | API-native replacement |
|---|---|
| Prompting for `[1]`-style markers + regex parsing of the answer | `search_result` blocks with `citations: {enabled: true}`; parse the structured `citations` arrays on response text blocks |
| Asking the model to quote sources verbatim (paying output tokens for quotes) | `cited_text` returned free of output-token charge, guaranteed to point at real provided text |
| Post-hoc validation that cited snippets actually exist in the corpus | API guarantee: citations are "valid pointers to the provided documents" |
| Mapping citation numbers back to chunk IDs/URLs in app code | `source`, `title`, `search_result_index`, block indices returned per citation |
| Prompt-template plumbing that stuffs retrieval chunks into an XML/text blob | Typed content blocks (`search_result` / `document` with `title` + `context` metadata fields) |
| Custom chunk-boundary bookkeeping for "which sentence was cited" | Automatic sentence chunking (plain text/PDF documents) or explicit block-level granularity (custom content / search results) |
| Client-side rolling summarisation of chat history | Server-side compaction beta (`compact_20260112`); or context editing for tool-result pruning |
| Bespoke cross-session "user memory" persistence prompts | GA memory tool (`memory_20250818`) with your own storage backend |
| Manual cost tuning via `temperature`/token budgets | Not available on Sonnet 5: sampling params 400; use `output_config.effort` + adaptive thinking |

### Build notes for our stack

- `langchain-anthropic`: strip `temperature`/`top_p`/`top_k` from any `ChatAnthropic` config for `claude-sonnet-5`. Content blocks (`search_result`, `citations`) may be easier to drive through the plain `anthropic` SDK (already a dependency) for the answer-generation call; keep LangChain/LangGraph for orchestration.
- Streaming UI: handle `citations_delta` alongside `text_delta`.
- Do not combine citations with `output_config.format` (structured outputs); 400.
- Cache order: tools -> system (breakpoint) -> conversation; put per-turn retrieval results late so they don't invalidate the stable prefix; only add `cache_control` to a document/search-result set that will be re-sent unchanged (e.g. pinned knowledge), not to per-query retrieval output.
- Re-baseline `max_tokens` and token budgets for the ~30% tokenizer inflation before comparing costs to any 4.x estimate. Intro pricing $2/$10 per MTok until 31 Aug 2026.

## Source URLs

- Models overview: https://platform.claude.com/docs/en/about-claude/models/overview
- Sonnet 5 migration: https://platform.claude.com/docs/en/about-claude/models/migration-guide
- Prompting Claude Sonnet 5: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5
- Citations: https://platform.claude.com/docs/en/build-with-claude/citations
- Search results: https://platform.claude.com/docs/en/build-with-claude/search-results
- Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Effort: https://platform.claude.com/docs/en/build-with-claude/effort
- Context editing: https://platform.claude.com/docs/en/build-with-claude/context-editing
- Compaction: https://platform.claude.com/docs/en/build-with-claude/compaction
- Memory tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
