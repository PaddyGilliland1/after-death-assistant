/*
  The "When you need help" directory. Every entry was verified against
  the organisation's own website on the date below; entries that could
  not be fully verified say so rather than guessing at hours.
*/

export const VERIFIED_DATE = "18 July 2026"

export interface HelpContact {
  name: string
  helpsWith: string
  phone: string | null
  hours: string | null
  url: string
  verified: boolean
}

export interface HelpGroup {
  heading: string
  intro: string
  contacts: HelpContact[]
}

export const HELP_GROUPS: HelpGroup[] = [
  {
    heading: "Someone to talk to",
    intro:
      "Grief is heavy, and you do not have to carry it alone. These lines exist for exactly this.",
    contacts: [
      {
        name: "Samaritans",
        helpsWith:
          "Someone to talk to in distress or despair, any time. They listen without judging.",
        phone: "116 123",
        hours: "24 hours a day, 365 days a year, free to call",
        url: "https://www.samaritans.org/how-we-can-help/contact-samaritan/",
        verified: true,
      },
      {
        name: "NHS urgent mental health help",
        helpsWith:
          "Urgent NHS mental health support. Call 111 and choose the mental health option.",
        phone: "111",
        hours: "24 hours every day, free",
        url: "https://www.nhs.uk/nhs-services/mental-health-services/where-to-get-urgent-help-for-mental-health/",
        verified: true,
      },
      {
        name: "Cruse Bereavement Support",
        helpsWith:
          "Free helpline offering a safe space to talk about grief with trained bereavement volunteers.",
        phone: "0808 808 1677",
        hours: "Check the website for current hours",
        url: "https://www.cruse.org.uk/get-support/helpline/",
        verified: false,
      },
      {
        name: "Marie Curie Support Line",
        helpsWith:
          "Emotional and practical support around terminal illness, dying and bereavement, whatever your situation.",
        phone: "0800 090 2309",
        hours: "Monday to Friday 8am to 6pm, weekends 10am to 4pm",
        url: "https://www.mariecurie.org.uk/help/support/marie-curie-support-line",
        verified: true,
      },
      {
        name: "The Silver Line (run by Age UK)",
        helpsWith:
          "Free, confidential phone line for older people who would like conversation, friendship or support.",
        phone: "0800 4 70 80 90",
        hours: "24 hours a day, every day",
        url: "https://www.thesilverline.org.uk/",
        verified: true,
      },
      {
        name: "WAY Widowed and Young",
        helpsWith:
          "Peer support network for people aged 50 or under when their partner died.",
        phone: null,
        hours: "Join online; members get a 24-hour helpline",
        url: "https://www.widowedandyoung.org.uk/",
        verified: true,
      },
    ],
  },
  {
    heading: "Practical help and money",
    intro:
      "Free advice on the paperwork, the benefits you may be owed, and money worries.",
    contacts: [
      {
        name: "Bereavement Advice Centre",
        helpsWith:
          "Free practical advice on what to do after a death, including probate and paperwork.",
        phone: "0800 634 9494",
        hours: "Monday to Friday 9am to 5pm (check the website)",
        url: "https://www.bereavementadvice.org/",
        verified: false,
      },
      {
        name: "National Bereavement Service",
        helpsWith:
          "Practical guidance after a death, from registration to probate, with emotional support signposting.",
        phone: "0800 0246 121",
        hours: "Monday to Friday 9am to 6pm, Saturday 10am to 2pm",
        url: "https://thenbs.org/",
        verified: true,
      },
      {
        name: "Tell Us Once",
        helpsWith:
          "Reports a death to most government departments in one go, online or by phone.",
        phone: null,
        hours: "The registrar gives you the phone number when you register the death",
        url: "https://www.gov.uk/after-a-death/organisations-you-need-to-contact-and-tell-us-once",
        verified: true,
      },
      {
        name: "DWP Bereavement Service",
        helpsWith:
          "Checks benefits you may claim after a death and takes Bereavement Support Payment claims.",
        phone: "0800 151 2012",
        hours: "Monday to Friday 8am to 6pm",
        url: "https://www.gov.uk/bereavement-support-payment/how-to-claim",
        verified: true,
      },
      {
        name: "Citizens Advice Adviceline (England)",
        helpsWith:
          "Free, confidential advice on benefits, debt, housing and everyday legal problems.",
        phone: "0800 144 8848",
        hours: "Monday to Friday 9am to 5pm, not public holidays",
        url: "https://www.citizensadvice.org.uk/about-us/contact-us/contact-us/contact-us/",
        verified: true,
      },
      {
        name: "Age UK Advice Line",
        helpsWith:
          "Free national advice line for older people, their families and carers.",
        phone: "0800 678 1602",
        hours: "8am to 7pm, 365 days a year",
        url: "https://www.ageuk.org.uk/services/age-uk-advice-line/",
        verified: true,
      },
      {
        name: "StepChange Debt Charity",
        helpsWith:
          "Free, confidential debt advice and practical help with money worries.",
        phone: "0800 138 1111",
        hours: "Monday to Friday 8am to 8pm, Saturday 9am to 2pm",
        url: "https://www.stepchange.org/contact-us.aspx",
        verified: true,
      },
    ],
  },
  {
    heading: "Armed forces families",
    intro: "Support for veterans' families, from charities and government.",
    contacts: [
      {
        name: "SSAFA Forcesline",
        helpsWith:
          "Free, confidential support for serving personnel, veterans and their families.",
        phone: "0800 260 6767",
        hours: "Monday to Thursday 9am to 5pm, Friday 9am to 4pm",
        url: "https://www.ssafa.org.uk/get-help/forcesline/",
        verified: true,
      },
      {
        name: "Veterans UK helpline",
        helpsWith:
          "Government helpline for veterans' pensions, compensation and welfare support.",
        phone: "0808 1914 218",
        hours: "Monday to Friday 8am to 4pm",
        url: "https://www.gov.uk/government/organisations/veterans-uk",
        verified: true,
      },
    ],
  },
  {
    heading: "Tax and probate",
    intro: "The official helplines for the formal steps.",
    contacts: [
      {
        name: "Probate helpline (HM Courts and Tribunals Service)",
        helpsWith:
          "Help with applying for probate, including the online application.",
        phone: "0300 303 0648",
        hours: "Monday to Friday 9am to 1pm, closed bank holidays",
        url: "https://www.gov.uk/applying-for-probate/apply-for-probate",
        verified: true,
      },
      {
        name: "HMRC Inheritance Tax helpline",
        helpsWith:
          "HMRC help with Inheritance Tax responsibilities and completing the forms.",
        phone: "0300 123 1072",
        hours: "Monday to Friday 9am to 5pm, closed bank holidays",
        url: "https://www.gov.uk/find-hmrc-contacts/inheritance-tax-general-enquiries",
        verified: true,
      },
    ],
  },
]
