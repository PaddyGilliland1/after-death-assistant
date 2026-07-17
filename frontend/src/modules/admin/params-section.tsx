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
    mutationFn: (enabled: boolean) =>
      api.post<Params>("/settings/params", { embeddings_enabled: enabled }),
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
                  onClick={() => toggle.mutate(!params.embeddings_enabled)}
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
      </CardContent>
    </Card>
  )
}
