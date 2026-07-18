/*
  When you need help: a calm directory of people who can help, beyond
  this application. Nothing clever: who they are, what they help with,
  and how to reach them, with phone numbers as tel: links. Numbers were
  verified against each organisation's own website; the two that could
  not be fully verified say so.
*/

import { Phone } from "lucide-react"

import { PageHeader } from "@/components/shared/page-header"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ExternalTextLink } from "@/modules/knowledge/shared"

import { HELP_GROUPS, VERIFIED_DATE } from "./help-contacts"

export default function HelpPage() {
  return (
    <section aria-label="When you need help">
      <PageHeader
        title="When you need help"
        description="An app can only do so much. These people can help, whether the load is practical, financial or simply too heavy today. All of these are free to contact."
      />

      <div className="mt-6 space-y-6">
        {HELP_GROUPS.map((group) => (
          <Card key={group.heading}>
            <CardHeader>
              <CardTitle>{group.heading}</CardTitle>
              <CardDescription>{group.intro}</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="divide-y" aria-label={group.heading}>
                {group.contacts.map((contact) => (
                  <li
                    key={contact.name}
                    className="flex flex-col gap-1 py-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6"
                  >
                    <div className="min-w-0">
                      <p className="font-medium">
                        <ExternalTextLink href={contact.url}>
                          {contact.name}
                        </ExternalTextLink>
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {contact.helpsWith}
                      </p>
                    </div>
                    <div className="shrink-0 text-sm sm:text-right">
                      {contact.phone ? (
                        <a
                          href={`tel:${contact.phone.replace(/\s/g, "")}`}
                          className="inline-flex items-center gap-1 font-medium text-primary underline underline-offset-4"
                        >
                          <Phone className="size-3.5" aria-hidden="true" />
                          {contact.phone}
                        </a>
                      ) : (
                        <span className="text-muted-foreground">
                          Online only
                        </span>
                      )}
                      {contact.hours ? (
                        <p className="text-xs text-muted-foreground">
                          {contact.hours}
                        </p>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="mt-6 text-xs text-muted-foreground">
        Numbers checked against each organisation's own website on{" "}
        {VERIFIED_DATE}. If one has changed, the organisation's website is
        the place to look, and please let the project know so it can be
        corrected for others.
      </p>
    </section>
  )
}
