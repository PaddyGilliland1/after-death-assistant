/*
  Params section of the admin module. One parameter today: semantic
  search embeddings. Off by default because the local model is a large
  one-time download with a CPU load that not every machine can run;
  everything works on full-text search while off. Only admins can
  change it; enabling starts a background embedding run whose progress
  and failures are reported here.
*/

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api, isApiError } from "@/lib/api"
import { useMe } from "@/lib/auth"

interface Params {
  embeddings_enabled: boolean
  embeddings_status: string
  embedding_model: string
  embedded_chunks: number
  total_chunks: number
  chat_daily_limit: number
  topic_guard_enabled: boolean
}

const PARAMS_KEY = ["/settings/params"]

export function ParamsSection() {
  const { role } = useMe()
  const isAdmin = role === "admin"
  const queryClient = useQueryClient()
  const [error, setError] = React.useState<string | null>(null)

  const query = useQuery({
    queryKey: PARAMS_KEY,
    queryFn: () => api.get<Params>("/settings/params"),
    refetchInterval: (q) =>
      q.state.data?.embeddings_status === "running" ? 4000 : false,
  })

  const toggle = useMutation({
    mutationFn: (change: Partial<Params>) =>
      api.post<Params>("/settings/params", change),
    onSuccess: (data) => {
      setError(null)
      queryClient.setQueryData(PARAMS_KEY, data)
    },
    onError: (err) =>
      setError(
        isApiError(err) ? err.message : "The setting could not be changed.",
      ),
  })

  const params = query.data

  return (
    <Card>
      <CardHeader>
        <CardTitle>Parameters</CardTitle>
        <CardDescription>
          Optional features that change how the application runs on this
          machine.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {query.isLoading || !params ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <div className="space-y-2 rounded-md border p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-medium">Semantic search (embeddings)</p>
                <p className="text-sm text-muted-foreground">
                  Improves how well the knowledge library matches questions
                  phrased in your own words. Uses a local model: a one-time
                  download of about 0.6 GB, nothing leaves this machine. Not
                  every machine can run it; everything works without it.
                </p>
              </div>
              {isAdmin ? (
                <Button
                  variant={params.embeddings_enabled ? "outline" : "default"}
                  onClick={() =>
                    toggle.mutate({
                      embeddings_enabled: !params.embeddings_enabled,
                    })
                  }
                  disabled={toggle.isPending}
                  aria-pressed={params.embeddings_enabled}
                >
                  {params.embeddings_enabled ? "Switch off" : "Switch on"}
                </Button>
              ) : (
                <Badge variant="secondary">Admin only</Badge>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge
                variant={params.embeddings_enabled ? "default" : "secondary"}
              >
                {params.embeddings_enabled ? "On" : "Off"}
              </Badge>
              {params.embeddings_status === "running" ? (
                <span role="status" className="text-muted-foreground">
                  Preparing embeddings: {params.embedded_chunks} of{" "}
                  {params.total_chunks} passages done. The first run also
                  downloads the model, so this can take a few minutes.
                </span>
              ) : null}
              {params.embeddings_status.startsWith("error") ? (
                <span role="alert" className="text-destructive">
                  The embedding run failed on this machine: {params.embeddings_status.replace("error: ", "")}{" "}
                  Search continues on full text. You can switch it off.
                </span>
              ) : null}
              {params.embeddings_status === "complete" ? (
                <span className="text-muted-foreground">
                  {params.embedded_chunks} of {params.total_chunks} passages
                  embedded with {params.embedding_model}.
                </span>
              ) : null}
            </div>
            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
          </div>
        )}
        {params ? (
          <div className="space-y-2 rounded-md border p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-medium">Assistant scope check</p>
                <p className="text-sm text-muted-foreground">
                  Before answering, a quick check asks you to confirm
                  questions that look unrelated to estate administration, so
                  the assistant is not used for other things by mistake.
                </p>
              </div>
              {isAdmin ? (
                <Button
                  variant={params.topic_guard_enabled ? "outline" : "default"}
                  onClick={() =>
                    toggle.mutate({
                      topic_guard_enabled: !params.topic_guard_enabled,
                    })
                  }
                  disabled={toggle.isPending}
                  aria-pressed={params.topic_guard_enabled}
                >
                  {params.topic_guard_enabled ? "Switch off" : "Switch on"}
                </Button>
              ) : (
                <Badge variant="secondary">Admin only</Badge>
              )}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
              <div>
                <p className="font-medium">Daily question limit</p>
                <p className="text-sm text-muted-foreground">
                  The most questions the assistant will answer per day for
                  this estate. A safety ceiling on usage and cost; it resets
                  at midnight UTC.
                </p>
              </div>
              {isAdmin ? (
                <div className="flex items-center gap-2">
                  <label htmlFor="daily-limit" className="sr-only">
                    Daily question limit
                  </label>
                  <input
                    id="daily-limit"
                    type="number"
                    min={1}
                    max={10000}
                    defaultValue={params.chat_daily_limit}
                    className="w-24 rounded-md border border-input bg-transparent px-2 py-1 text-sm"
                    onBlur={(event) => {
                      const value = Number(event.target.value)
                      if (
                        Number.isFinite(value) &&
                        value >= 1 &&
                        value !== params.chat_daily_limit
                      ) {
                        toggle.mutate({ chat_daily_limit: value })
                      }
                    }}
                  />
                </div>
              ) : (
                <Badge variant="secondary">{params.chat_daily_limit} per day</Badge>
              )}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
