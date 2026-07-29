# Owner Setup

Only complete an item when the named milestone requests it. Do not send secret values
in chat, issues or pull requests.

## During the build

- [ ] Provide one public FPL Team ID for realistic smoke tests.
- [ ] Create `fpl-andres-staging` and `fpl-andres-production` Supabase projects in
      the same suitable European region after the migration contract is ready.
- [ ] Enter the requested Supabase values directly into the named Vercel and GitHub
      environments. Share only project refs, URLs and regions.
- [ ] Import `JamieMBright/fpl-andres` into Vercel after the scaffold is pushed.
      Share only the Vercel project/team IDs and generated URL.
- [ ] Before enabling heatmap-derived OOP inference, provide a rights-cleared role/event
      data source or confirm that the feature should remain unavailable. Do not send
      provider credentials in chat.

## Before real email

- [ ] Choose or register the public domain and a sending subdomain such as
      `updates.<domain>`.
- [ ] Create the Resend account, add that subdomain and copy Resend's DNS records at
      the registrar.
- [ ] After verification, create a domain-scoped send-only key and enter it directly
      into Vercel Production when the environment contract requests it.
- [ ] After the webhook route exists, enter its Resend signing secret directly into
      Vercel Production.

## Before public release

- [ ] Provide the requested player-pose reference and confirm either licensed
      derivative brand use or an independently constructed original pose.
- [ ] Choose the source-code license before `v1.0.0`.
- [ ] Approve the first production promotion after the release-candidate report passes.

Everything else, including migrations, RLS, CI, tests, environment names, deployment
configuration, monitoring, backups and release mechanics, is implementation work.
