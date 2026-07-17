/*
  Ask the knowledge assistant: a conversational chat thread over
  POST /knowledge/chat. A slim sidebar lists recent conversations (a
  select on small screens); the thread pane shows messages oldest to
  newest with the question input pinned at the bottom. Questions need a
  write role, so viewers see a calm read-only note instead of the input.
  A 503 means the assistant is not configured yet. The guidance
  disclaimer stays visible at the top of the module.
*/

import * as React from "react"
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import { Archive, SendHorizontal } from "lucide-react"

import { ArchiveDialog } from "@/components/shared/archive-dialog"
import { formatDate } from "@/components/shared/formatters"
import { Button } from "@/components/ui/button"
import { api, isApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import { cn } from "@/lib/utils"

import { ChatMessageItem } from "./chat-message"
import {
  type ChatConversation,
  type ChatMessage,
  type ChatResponse,
} from "./knowledge-meta"

const CONVERSATIONS_KEY = ["knowledge-chat-conversations"] as const

function messagesKey(conversationId: string) {
  return ["knowledge-chat-messages", conversationId] as const
}

export function AskSection() {
  const { role } = useMe()
  const writer = canWrite(role)
  const queryClient = useQueryClient()

  /** null means a fresh conversation not yet created on the server. */
  const [activeId, setActiveId] = React.useState<string | null>(null)
  const [question, setQuestion] = React.useState("")
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)
  const [archiveOpen, setArchiveOpen] = React.useState(false)

  const textareaId = React.useId()
  const selectId = React.useId()
  const threadRef = React.useRef<HTMLDivElement>(null)

  const conversationsQuery = useQuery({
    queryKey: CONVERSATIONS_KEY,
    queryFn: () => api.get<ChatConversation[]>("/knowledge/chats"),
  })
  const conversations = conversationsQuery.data ?? []
  const activeConversation =
    conversations.find((conversation) => conversation.id === activeId) ?? null

  const messagesQuery = useQuery({
    queryKey: activeId ? messagesKey(activeId) : ["knowledge-chat-messages"],
    queryFn: () =>
      api.get<ChatMessage[]>(`/knowledge/chats/${activeId}/messages`),
    enabled: activeId !== null,
  })
  const messages = React.useMemo(
    () => (activeId ? (messagesQuery.data ?? []) : []),
    [activeId, messagesQuery.data],
  )

  const ask = useMutation({
    mutationFn: (asked: string) =>
      api.post<ChatResponse>(
        "/knowledge/chat",
        activeId
          ? { conversation_id: activeId, question: asked }
          : { question: asked },
      ),
    onSuccess: (response, asked) => {
      setErrorMessage(null)
      setQuestion("")
      /* Seed the thread cache with the turn just completed: the API
         returns only the assistant message, so the question is echoed
         locally until the server copy is refetched. */
      queryClient.setQueryData<ChatMessage[]>(
        messagesKey(response.conversation_id),
        (existing = []) => [
          ...existing,
          {
            id: `local-question-${response.message.id}`,
            role: "user",
            content: asked,
            sources_cited: [],
            related_sources: [],
            created_at: response.message.created_at,
          },
          response.message,
        ],
      )
      setActiveId(response.conversation_id)
      void queryClient.invalidateQueries({ queryKey: CONVERSATIONS_KEY })
    },
    onError: (error) => {
      if (isApiError(error) && error.status === 503) {
        setErrorMessage("The assistant is not configured yet.")
      } else {
        setErrorMessage(
          isApiError(error)
            ? error.message
            : "The question could not be answered. Please try again.",
        )
      }
    },
  })

  /* Keep the newest message in view as the thread grows. */
  React.useEffect(() => {
    const node = threadRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages.length, ask.isPending])

  function submitQuestion() {
    const trimmed = question.trim()
    if (!trimmed || ask.isPending) return
    ask.mutate(trimmed)
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    submitQuestion()
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      submitQuestion()
    }
  }

  function selectConversation(conversationId: string | null) {
    setActiveId(conversationId)
    setErrorMessage(null)
  }

  async function archiveActiveConversation(reason: string) {
    if (!activeId) return
    await api.delete(`/knowledge/chats/${activeId}`, { reason })
    queryClient.removeQueries({ queryKey: messagesKey(activeId) })
    setActiveId(null)
    await queryClient.invalidateQueries({ queryKey: CONVERSATIONS_KEY })
  }

  return (
    <div className="flex flex-col gap-4 md:flex-row">
      {/* Small screens: a labelled select stands in for the sidebar. */}
      <div className="space-y-1.5 md:hidden">
        <label htmlFor={selectId} className="text-sm font-medium">
          Conversation
        </label>
        <select
          id={selectId}
          value={activeId ?? ""}
          onChange={(event) =>
            selectConversation(event.target.value || null)
          }
          className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <option value="">New conversation</option>
          {conversations.map((conversation) => (
            <option key={conversation.id} value={conversation.id}>
              {conversation.title}
            </option>
          ))}
        </select>
      </div>

      {/* Wider screens: a slim conversation sidebar. */}
      <aside className="hidden w-56 shrink-0 md:block">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mb-3 w-full"
          onClick={() => selectConversation(null)}
        >
          New conversation
        </Button>
        <nav aria-label="Conversations">
          {conversationsQuery.isError ? (
            <p className="text-sm text-muted-foreground">
              Conversations could not be loaded.
            </p>
          ) : conversations.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No conversations yet.
            </p>
          ) : (
            <ul className="space-y-1">
              {conversations.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    type="button"
                    onClick={() => selectConversation(conversation.id)}
                    aria-current={
                      activeId === conversation.id ? "true" : undefined
                    }
                    className={cn(
                      "w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                      activeId === conversation.id
                        ? "bg-muted font-medium"
                        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                    )}
                  >
                    <span className="block truncate">{conversation.title}</span>
                    <span className="block text-xs font-normal text-muted-foreground">
                      {formatDate(conversation.updated_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>
      </aside>

      {/* The thread pane: messages oldest to newest, input pinned below. */}
      <div className="flex h-[50.4rem] max-h-[85vh] min-w-0 flex-1 flex-col rounded-lg border">
        <div className="flex items-center justify-between gap-2 border-b px-4 py-2">
          <h3 className="truncate text-sm font-semibold">
            {activeConversation ? activeConversation.title : "New conversation"}
          </h3>
          {activeId && writer ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label="Archive conversation"
              onClick={() => setArchiveOpen(true)}
            >
              <Archive aria-hidden="true" />
              Archive
            </Button>
          ) : null}
        </div>

        <div
          ref={threadRef}
          role="log"
          aria-live="polite"
          aria-label="Conversation messages"
          className="flex-1 space-y-4 overflow-y-auto p-4"
          tabIndex={0}
        >
          {activeId && messagesQuery.isError ? (
            <p className="text-sm text-muted-foreground">
              The conversation could not be loaded. Please try again.
            </p>
          ) : null}
          {!activeId && messages.length === 0 && !ask.isPending ? (
            <p className="max-w-prose text-sm text-muted-foreground">
              Ask a question about the cached HMRC forms and official
              guidance. Answers cite their sources, and each conversation is
              kept so you can return to it.
            </p>
          ) : null}
          {messages.map((message) => (
            <ChatMessageItem key={message.id} message={message} />
          ))}
          {ask.isPending && ask.variables ? (
            <div className="flex justify-end">
              <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-muted px-3 py-2 text-sm">
                <span className="sr-only">You asked: </span>
                {ask.variables}
              </div>
            </div>
          ) : null}
          {ask.isPending ? (
            <p
              role="status"
              className="animate-pulse text-sm text-muted-foreground"
            >
              Thinking
            </p>
          ) : null}
        </div>

        {writer ? (
          <form
            onSubmit={handleSubmit}
            className="space-y-2 border-t p-3"
            noValidate
          >
            {errorMessage ? (
              <p role="alert" className="text-sm text-muted-foreground">
                {errorMessage}
              </p>
            ) : null}
            <label htmlFor={textareaId} className="sr-only">
              Your question
            </label>
            <div className="flex items-end gap-2">
              <textarea
                id={textareaId}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={handleKeyDown}
                rows={2}
                disabled={ask.isPending}
                placeholder="For example: when is form IHT400 needed instead of IHT205?"
                className="flex min-h-16 w-full min-w-0 flex-1 rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-sm transition-colors placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring md:text-sm"
              />
              <Button
                type="submit"
                disabled={ask.isPending || !question.trim()}
              >
                <SendHorizontal aria-hidden="true" />
                Ask
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Press Enter to ask, Shift and Enter for a new line.
            </p>
          </form>
        ) : role ? (
          <p className="border-t px-4 py-3 text-sm text-muted-foreground">
            Your access is read only, so you can read these conversations but
            not ask new questions.
          </p>
        ) : null}
      </div>

      <ArchiveDialog
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
        itemLabel="conversation"
        onConfirm={archiveActiveConversation}
      />
    </div>
  )
}
