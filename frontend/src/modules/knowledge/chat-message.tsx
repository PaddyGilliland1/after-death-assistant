/*
  Renders one message in a knowledge chat thread. User messages sit right
  aligned in a quiet bubble; assistant messages take the full width and
  render markdown with [n] citations linked to the message's own numbered
  sources, the mandatory "what the retrieved guidance does not cover"
  section pinned in an amber panel, then the cited and related sources.

  Citation anchors are scoped by message id so numbers never collide
  across messages in the same thread.
*/

import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { Badge } from "@/components/ui/badge"

import {
  NOT_COVERED_HEADING,
  type ChatMessage,
  type ChatSource,
} from "./knowledge-meta"
import { ExternalTextLink, LicenceLine } from "./shared"

/** Splits an answer into the body and the always-visible caveats. */
function splitAnswer(answer: string): { body: string; caveats: string | null } {
  const index = answer.indexOf(NOT_COVERED_HEADING)
  if (index === -1) return { body: answer, caveats: null }
  return {
    body: answer.slice(0, index).trimEnd(),
    caveats: answer.slice(index),
  }
}

/*
  Renders assistant markdown (headings demoted, raw HTML escaped by
  react-markdown) while turning every [n] citation into an in-page link
  to its source entry. Non-citation links render as plain text: authority
  comes only from the sources list below the message.
*/
function AnswerText({
  answer,
  sources,
  anchorPrefix,
}: {
  answer: string
  sources: ChatSource[]
  anchorPrefix: string
}) {
  const known = new Set(
    sources.filter((source) => source.n !== null).map((source) => source.n),
  )
  const withCitationLinks = answer.replace(/\[(\d+)\]/g, (whole, digits) => {
    const n = Number(digits)
    return known.has(n) ? `[\\[${n}\\]](#${anchorPrefix}-source-${n})` : whole
  })
  return (
    <div className="markdown-answer text-sm leading-relaxed">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h4>{children}</h4>,
          h2: ({ children }) => <h5>{children}</h5>,
          h3: ({ children }) => <h6>{children}</h6>,
          a: ({ href, children }) => {
            const match = /-source-(\d+)$/.exec(href ?? "")
            if (match) {
              const source = sources.find(
                (candidate) => candidate.n === Number(match[1]),
              )
              return (
                <a
                  href={href}
                  className="font-medium text-primary underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  aria-label={
                    source
                      ? `Citation ${match[1]}: ${source.doc_title}`
                      : `Citation ${match[1]}`
                  }
                >
                  {children}
                </a>
              )
            }
            /* Non-citation links are rendered as plain text. */
            return <>{children}</>
          },
        }}
      >
        {withCitationLinks}
      </Markdown>
    </div>
  )
}

function SourceTitle({ source }: { source: ChatSource }) {
  return source.source_url ? (
    <ExternalTextLink href={source.source_url}>
      {source.doc_title}
    </ExternalTextLink>
  ) : (
    <span>{source.doc_title}</span>
  )
}

function PinnedBadge({ source }: { source: ChatSource }) {
  if (source.relation !== "pinned") return null
  return <Badge variant="outline">Pinned from earlier</Badge>
}

function CitedSources({
  sources,
  anchorPrefix,
}: {
  sources: ChatSource[]
  anchorPrefix: string
}) {
  if (sources.length === 0) return null
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold">Sources cited</h4>
      <ol aria-label="Sources cited" className="space-y-2">
        {sources.map((source, index) => (
          <li
            key={source.n ?? `cited-${index}`}
            id={
              source.n !== null
                ? `${anchorPrefix}-source-${source.n}`
                : undefined
            }
            className="text-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-muted-foreground">
                [{source.n}]
              </span>
              <SourceTitle source={source} />
              <PinnedBadge source={source} />
            </div>
            <LicenceLine licence={source.licence} fetchDate={source.fetch_date} />
            {source.quotes.map((quote, quoteIndex) => (
              <p
                key={quoteIndex}
                className="mt-1 border-l-2 border-muted pl-2 text-xs italic text-muted-foreground"
              >
                {"“"}
                {quote}
                {"”"}
              </p>
            ))}
          </li>
        ))}
      </ol>
    </div>
  )
}

function RelatedSources({ sources }: { sources: ChatSource[] }) {
  if (sources.length === 0) return null
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold text-muted-foreground">
        Also retrieved, not cited
      </h4>
      <ul aria-label="Also retrieved, not cited" className="space-y-2">
        {sources.map((source, index) => (
          <li key={index} className="text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <SourceTitle source={source} />
              <PinnedBadge source={source} />
            </div>
            <LicenceLine licence={source.licence} fetchDate={source.fetch_date} />
          </li>
        ))}
      </ul>
    </div>
  )
}

export function ChatMessageItem({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-muted px-3 py-2 text-sm">
          <span className="sr-only">You asked: </span>
          {message.content}
        </div>
      </div>
    )
  }

  const anchorPrefix = `msg-${message.id}`
  const { body, caveats } = splitAnswer(message.content)

  return (
    <div className="space-y-4">
      <div>
        <span className="sr-only">Assistant answered: </span>
        <AnswerText
          answer={body}
          sources={message.sources_cited}
          anchorPrefix={anchorPrefix}
        />
        {caveats ? (
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900 dark:bg-amber-950">
            <AnswerText
              answer={caveats}
              sources={message.sources_cited}
              anchorPrefix={anchorPrefix}
            />
          </div>
        ) : null}
      </div>
      <CitedSources sources={message.sources_cited} anchorPrefix={anchorPrefix} />
      <RelatedSources sources={message.related_sources} />
    </div>
  )
}
