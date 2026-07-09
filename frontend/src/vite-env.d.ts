/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the AD Assistant API. Defaults to http://localhost:8471. */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
