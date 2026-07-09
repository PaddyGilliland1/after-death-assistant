import type * as React from "react"
import { Toaster as Sonner, type ToasterProps } from "sonner"

/*
  Toast notifications. Fixed to the light theme for now; revisit when a
  dark theme is introduced.
*/
function Toaster(props: ToasterProps) {
  return (
    <Sonner
      theme="light"
      className="toaster group"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
