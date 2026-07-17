"""Conversational knowledge chat with API-native citations.

Design (docs/design/ANTHROPIC_API_BRIEF.md + PROMPTING_SPEC.md):

- Retrieved chunks and pinned snippets are sent as `search_result`
  content blocks with citations enabled, so citations come back as
  machine-extracted spans (`cited_text` + `search_result_index`), never
  as model-asserted [n] markers.
- The app inserts the [n] markers itself while walking the response
  blocks, numbers sources in order of first use, and splits sources
  cited in the body from retrieved-but-uncited related sources.
- The context harness: every cited passage is pinned to the
  conversation (qa_pinned_snippet) and re-supplied as a search result on
  every later turn, so earlier topics stay answerable and citable even
  when old messages fall out of the replayed history.
- History replay is capped; older turns are folded into a plain rolling
  summary stored on the conversation. Pinned snippets are unaffected by
  this windowing.

The LangGraph graph is linear (prepare -> retrieve -> answer ->
postprocess -> persist) with a deterministic early exit to a graceful
refusal when there is nothing to ground an answer in.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models import QaConversation, QaMessage, QaPinnedSnippet
from app.models.base import utcnow
from app.schemas.knowledge import SearchHit
from app.schemas.qa_chat import ChatSource
from app.services.seeding import record_audit

logger = logging.getLogger(__name__)

CHAT_MODEL = "claude-sonnet-5"
MAX_ANSWER_TOKENS = 6000
HISTORY_LIMIT = 12
PIN_LIMIT = 12
RETRIEVAL_LIMIT = 8
NOT_COVERED_HEADING = "What the retrieved guidance does not cover"

REFUSAL_TEXT = (
    "I could not find anything in the official guidance available to me that "
    "answers this. Rather than guess, I would prefer to leave it unanswered "
    "here. You could try rephrasing the question, or open the source "
    "documents in the Library tab."
)

SYSTEM_PROMPT = f"""<role>
You are the knowledge assistant inside an estate administration application. You help
people in England and Wales who are dealing with the practical steps after a death,
usually the death of a close family member. Your readers are grieving and are not
technical, legal or financial specialists. You answer questions using only the official
guidance passages provided to you as search results in each message.
</role>

<why_this_matters>
Your reader may be tired, stressed and unfamiliar with official processes. A wrong or
invented answer could cause real harm, such as a missed deadline or an incorrect tax
submission. This is why you only ever state what the provided guidance actually says,
why you quote it exactly, and why you say plainly when it does not cover something.
Being honest about the limits of the guidance is a kindness, not a failure.
</why_this_matters>

<grounding_rules>
1. Use only the search results provided in this conversation. Do not use your general
   knowledge to add facts, figures, deadlines, thresholds or procedures, even when you
   are confident you know them.
2. Open your answer with an attribution sentence naming the main guidance page you are
   drawing on, in the form: Based on the "<title>" guidance - and then answer.
3. When you reproduce guidance word for word, render it as a quotation in double
   quotation marks. Quote exactly, with no silent edits.
4. If part of the question is not covered by the provided guidance, say so in the
   closing block rather than filling the gap yourself. It is always acceptable to say
   the guidance does not cover something.
5. Some search results are marked as pinned from earlier in this conversation; use
   them exactly like the others.
</grounding_rules>

<figures_policy>
You never calculate, estimate or infer numbers. This includes tax due, thresholds
applied to the user's situation, shares of an estate, interest, dates counted forward
from another date, and sums of any kind. You may quote a figure that appears verbatim
in the provided guidance. If the user asks you to work out a figure, explain warmly
that the application's assessment pages do the calculations, and share what the
guidance itself says about how the figure is arrived at.
</figures_policy>

<tone_and_language>
Write in calm, plain UK English. Use short sentences and everyday words; explain any
official term the first time it appears. Be warm but not effusive, and never breezy
about the death. Do not use em dashes anywhere. Do not use exclamation marks. Address
the reader as "you". Your readers are stressed: when you are giving actions, options
or steps, use a short bullet list rather than a paragraph, and keep any paragraph to
three sentences or fewer. Do not write your own sources list: the application renders
sources from the citation data automatically.
</tone_and_language>

<answer_format>
1. The attribution opening and your answer, in short paragraphs, quoting where exact
   wording matters.
2. A blank line, then always close with this exact heading on its own line:

{NOT_COVERED_HEADING}

followed by one short paragraph or list naming the parts of the question the provided
guidance does not address. If everything was covered, write: The provided guidance
covered all parts of your question.
</answer_format>

<estate_progress>
Some messages include a block headed "Current progress in this estate". Use it ONLY to
tailor your answer to where the reader is in the process (for example, pointing to the
next step rather than ones already done, or acknowledging a task they mentioned).
Never cite it, never treat it as guidance, and never compute figures from it.
</estate_progress>

<conversation_behaviour>
This is a multi-turn chat. Carry forward what the user has already told you, but ground
every new factual claim in the search results provided in this conversation. If a
follow-up needs guidance that is not among them, say so in the closing block rather
than answering from memory.
</conversation_behaviour>"""


@dataclass
class SuppliedResult:
    """One search_result block sent to the model, in order."""

    doc_id: uuid.UUID | None
    doc_title: str
    source_url: str
    licence: str | None
    fetch_date: Any
    text: str
    relation: str  # "retrieved" | "pinned"


@dataclass
class ChatTurn:
    """State carried through one turn of the chat graph."""

    question: str
    actor: str
    estate_id: uuid.UUID
    conversation: QaConversation | None = None
    history: list[QaMessage] = field(default_factory=list)
    pins: list[QaPinnedSnippet] = field(default_factory=list)
    hits: list[SearchHit] = field(default_factory=list)
    supplied: list[SuppliedResult] = field(default_factory=list)
    progress_text: str | None = None
    answer_text: str = ""
    sources_cited: list[ChatSource] = field(default_factory=list)
    related_sources: list[ChatSource] = field(default_factory=list)
    refused: bool = False


def _call_chat_api(system: list[dict], messages: list[dict], settings: Settings):
    """Single seam for the Anthropic call (monkeypatched in tests).

    Uses the plain anthropic SDK: search_result blocks with citations are
    not exposed through the langchain wrapper. No sampling parameters:
    claude-sonnet-5 rejects them (migration guide).
    """
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=120)
    return client.messages.create(
        model=CHAT_MODEL,
        max_tokens=MAX_ANSWER_TOKENS,
        system=system,
        messages=messages,
    )


def _search_result_block(result: SuppliedResult) -> dict:
    title = result.doc_title
    if result.relation == "pinned":
        title = f"{title} (pinned from earlier in this conversation)"
    return {
        "type": "search_result",
        "source": result.source_url,
        "title": title,
        "content": [{"type": "text", "text": result.text}],
        "citations": {"enabled": True},
    }


def _build_messages(turn: ChatTurn) -> list[dict]:
    messages: list[dict] = []
    if turn.conversation is not None and turn.conversation.summary:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Summary of the earlier part of this conversation: "
                    + turn.conversation.summary
                ),
            }
        )
        messages.append(
            {"role": "assistant", "content": "Thank you, I will keep that in mind."}
        )
    for message in turn.history:
        messages.append({"role": message.role, "content": message.content})
    final_content: list[dict] = [
        _search_result_block(result) for result in turn.supplied
    ]
    if turn.progress_text:
        final_content.append({"type": "text", "text": turn.progress_text})
    final_content.append({"type": "text", "text": turn.question})
    messages.append({"role": "user", "content": final_content})
    return messages


def _postprocess(turn: ChatTurn, response: Any) -> None:
    """Insert [n] markers from the structured citations and split sources.

    Numbering is per answer, in order of first use. A supplied result's
    document is "cited" when any citation points at its
    search_result_index; everything else supplied this turn is related.
    """
    numbers_by_index: dict[int, int] = {}
    quotes_by_index: dict[int, list[str]] = {}
    parts: list[str] = []

    for block in response.content:
        if getattr(block, "type", None) != "text":
            continue
        parts.append(block.text)
        markers: list[int] = []
        for citation in getattr(block, "citations", None) or []:
            index = getattr(citation, "search_result_index", None)
            if index is None or index >= len(turn.supplied):
                continue
            if index not in numbers_by_index:
                numbers_by_index[index] = len(numbers_by_index) + 1
            cited_text = (getattr(citation, "cited_text", "") or "").strip()
            if cited_text:
                quotes_by_index.setdefault(index, [])
                if cited_text not in quotes_by_index[index]:
                    quotes_by_index[index].append(cited_text)
            number = numbers_by_index[index]
            if number not in markers:
                markers.append(number)
        if markers:
            parts.append(" " + "".join(f"[{n}]" for n in markers))

    turn.answer_text = "".join(parts).strip()

    cited_docs: dict[str, ChatSource] = {}
    for index, number in sorted(numbers_by_index.items(), key=lambda kv: kv[1]):
        supplied = turn.supplied[index]
        key = supplied.source_url
        if key in cited_docs:
            for quote in quotes_by_index.get(index, []):
                if quote not in cited_docs[key].quotes:
                    cited_docs[key].quotes.append(quote)
            continue
        cited_docs[key] = ChatSource(
            n=number,
            doc_title=supplied.doc_title,
            source_url=supplied.source_url,
            licence=supplied.licence,
            fetch_date=supplied.fetch_date,
            quotes=list(quotes_by_index.get(index, [])),
            relation="pinned" if supplied.relation == "pinned" else "retrieved",
        )
    turn.sources_cited = list(cited_docs.values())

    cited_urls = set(cited_docs)
    related: dict[str, ChatSource] = {}
    for supplied in turn.supplied:
        if supplied.source_url in cited_urls or supplied.source_url in related:
            continue
        related[supplied.source_url] = ChatSource(
            n=None,
            doc_title=supplied.doc_title,
            source_url=supplied.source_url,
            licence=supplied.licence,
            fetch_date=supplied.fetch_date,
            relation="pinned" if supplied.relation == "pinned" else "retrieved",
        )
    turn.related_sources = list(related.values())


_AMOUNT_PATTERN = re.compile(r"£\s?[\d,]+(?:\.\d+)?|\b\d+(?:\.\d+)?\s?%")


def _contract_failures(turn: ChatTurn) -> list[str]:
    failures: list[str] = []
    if NOT_COVERED_HEADING not in turn.answer_text:
        failures.append(
            f'missing the closing section headed "{NOT_COVERED_HEADING}"'
        )
    supplied_normalised = re.sub(
        r"[,\s£]", "", " ".join(result.text for result in turn.supplied).lower()
    )
    for amount in _AMOUNT_PATTERN.findall(turn.answer_text):
        if re.sub(r"[,\s£]", "", amount.lower()) not in supplied_normalised:
            failures.append(
                f"the figure {amount} does not appear in the provided guidance"
            )
    return failures


async def _estate_progress_text(session: AsyncSession, estate_id: uuid.UUID) -> str | None:
    """A short plain-text picture of where this estate is, for tailoring.

    Timeline position plus the soonest open tasks with their latest
    comment. Supplied as context only; the prompt forbids citing it.
    """
    from app.models import ProcessStep, Task, TaskComment

    steps = (
        await session.execute(
            select(ProcessStep)
            .where(ProcessStep.estate_id == estate_id)
            .where(ProcessStep.archived_at.is_(None))
            .order_by(ProcessStep.order)
        )
    ).scalars().all()
    tasks = (
        await session.execute(
            select(Task)
            .where(Task.estate_id == estate_id)
            .where(Task.archived_at.is_(None))
            .where(Task.status != "done")
            .order_by(Task.due_date.nulls_last(), Task.created_at)
            .limit(10)
        )
    ).scalars().all()
    if not steps and not tasks:
        return None
    lines = ["Current progress in this estate (context only, never cite):"]
    if steps:
        done = sum(1 for s in steps if (s.status or "").lower() == "done")
        current = next(
            (s for s in steps if (s.status or "").lower() != "done"), None
        )
        lines.append(f"- Timeline: {done} of {len(steps)} steps complete.")
        if current is not None:
            lines.append(f"- Current step: {current.name}.")
    for task in tasks:
        comment = (
            await session.execute(
                select(TaskComment)
                .where(TaskComment.task_id == task.id)
                .where(TaskComment.archived_at.is_(None))
                .order_by(TaskComment.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        line = f"- Open task: {task.title} (status {task.status or 'todo'}"
        if task.due_date:
            line += f", due {task.due_date}"
        line += ")"
        if comment is not None:
            line += f'; latest note: "{comment.body[:140]}"'
        lines.append(line)
    return "\n".join(lines)


async def run_chat_turn(
    session: AsyncSession,
    *,
    estate_id: uuid.UUID,
    actor: str,
    question: str,
    conversation_id: uuid.UUID | None,
) -> tuple[QaConversation, QaMessage]:
    """Run one turn: the graph in docstring order, persisting the result."""
    from app.api.knowledge import hybrid_search

    settings = get_settings()
    turn = ChatTurn(question=question, actor=actor, estate_id=estate_id)

    # prepare -----------------------------------------------------------
    if conversation_id is not None:
        conversation = await session.get(QaConversation, conversation_id)
        if (
            conversation is None
            or conversation.archived_at is not None
            or conversation.estate_id != estate_id
        ):
            raise LookupError("Conversation not found")
        turn.conversation = conversation
        result = await session.execute(
            select(QaMessage)
            .where(QaMessage.conversation_id == conversation.id)
            .where(QaMessage.archived_at.is_(None))
            .order_by(QaMessage.created_at)
        )
        all_messages = list(result.scalars().all())
        if len(all_messages) > HISTORY_LIMIT:
            older = all_messages[:-HISTORY_LIMIT]
            summary = " ".join(
                f"{message.role}: {message.content}" for message in older
            )
            conversation.summary = summary[:2000]
            turn.history = all_messages[-HISTORY_LIMIT:]
        else:
            turn.history = all_messages
        pins = await session.execute(
            select(QaPinnedSnippet)
            .where(QaPinnedSnippet.conversation_id == conversation.id)
            .where(QaPinnedSnippet.archived_at.is_(None))
            .order_by(QaPinnedSnippet.created_at)
        )
        turn.pins = list(pins.scalars().all())

    turn.progress_text = await _estate_progress_text(session, estate_id)

    # retrieve ----------------------------------------------------------
    turn.hits = await hybrid_search(session, estate_id, question, RETRIEVAL_LIMIT)
    for pin in turn.pins:
        turn.supplied.append(
            SuppliedResult(
                doc_id=pin.knowledge_doc_id,
                doc_title=pin.doc_title,
                source_url=pin.source_url,
                licence=None,
                fetch_date=None,
                text=pin.snippet,
                relation="pinned",
            )
        )
    for hit in turn.hits:
        turn.supplied.append(
            SuppliedResult(
                doc_id=hit.doc_id,
                doc_title=hit.doc_title,
                source_url=hit.source_url,
                licence=hit.licence,
                fetch_date=hit.fetch_date,
                text=hit.chunk_text,
                relation="retrieved",
            )
        )

    # deterministic refusal: nothing to ground in ----------------------
    if not turn.supplied:
        turn.answer_text = REFUSAL_TEXT
        turn.refused = True
    else:
        # answer + bounded corrective retry -----------------------------
        system = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        messages = _build_messages(turn)
        for attempt in range(2):
            response = _call_chat_api(system, messages, settings)
            _postprocess(turn, response)
            failures = _contract_failures(turn)
            if not failures:
                break
            logger.info("Chat contract attempt %d failed: %s", attempt + 1, failures)
            messages = _build_messages(turn)
            messages[-1]["content"] = list(messages[-1]["content"])
            messages[-1]["content"][-1] = {
                "type": "text",
                "text": (
                    turn.question
                    + "\n\n(Your previous answer broke these rules: "
                    + "; ".join(failures)
                    + ". Answer again, correcting every point.)"
                ),
            }
        else:
            logger.warning("Chat answer failed the contract after retries.")

    # persist -----------------------------------------------------------
    if turn.conversation is None:
        turn.conversation = QaConversation(
            estate_id=estate_id,
            title=question[:80],
            created_by=actor,
        )
        session.add(turn.conversation)
        await session.flush()

    user_message = QaMessage(
        estate_id=estate_id,
        conversation_id=turn.conversation.id,
        role="user",
        content=question,
        created_by=actor,
    )
    session.add(user_message)
    assistant_message = QaMessage(
        estate_id=estate_id,
        conversation_id=turn.conversation.id,
        role="assistant",
        content=turn.answer_text,
        sources_cited=[source.model_dump(mode="json") for source in turn.sources_cited],
        related_sources=[
            source.model_dump(mode="json") for source in turn.related_sources
        ],
        created_by=actor,
    )
    session.add(assistant_message)

    # context harness: pin newly cited passages ------------------------
    existing = {(pin.source_url, pin.snippet) for pin in turn.pins}
    pin_count = len(turn.pins)
    for source in turn.sources_cited:
        for quote in source.quotes:
            if pin_count >= PIN_LIMIT:
                break
            if (source.source_url, quote) in existing:
                continue
            doc_id = next(
                (
                    supplied.doc_id
                    for supplied in turn.supplied
                    if supplied.source_url == source.source_url
                ),
                None,
            )
            session.add(
                QaPinnedSnippet(
                    estate_id=estate_id,
                    conversation_id=turn.conversation.id,
                    knowledge_doc_id=doc_id,
                    doc_title=source.doc_title,
                    source_url=source.source_url,
                    snippet=quote,
                    created_by=actor,
                )
            )
            existing.add((source.source_url, quote))
            pin_count += 1

    turn.conversation.updated_at = utcnow()
    session.add(turn.conversation)
    await session.flush()
    await record_audit(
        session,
        estate_id,
        actor,
        "create",
        f"qa_message:{assistant_message.id}",
        after={"conversation": str(turn.conversation.id), "refused": turn.refused},
    )
    await session.commit()
    await session.refresh(assistant_message)
    return turn.conversation, assistant_message
