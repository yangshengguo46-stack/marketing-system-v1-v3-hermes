# Platform operation boundaries

## Ownership

- Hermes SessionDB owns conversation-to-account binding.
- Marketing Browser MCP owns browser profiles, login windows, tabs, downloads, and page execution.
- Account lifecycle owns connect, disconnect, delete, and profile retention decisions.
- ContentAsset owns approved content; the browser editor is not the canonical draft store.
- PublishAction and ReceiptRef own intent, idempotency, outcome, verification, and metric checkpoints.

## Evidence grades

Treat these as publish evidence, from strongest to weakest:

1. Platform post ID plus official work detail page.
2. Stable platform post URL plus creator-center list match.
3. Creator-center work list entry with title, time, and account match.
4. Success toast without a durable work reference: insufficient; keep outcome `unknown`.
5. Click completed, editor disappeared, timeout, or navigation error: never success.

## Login and risk control

- QR scan, SMS verification, captcha, device confirmation, identity checks, and risk-control challenges
  are human checkpoints, not automation failures.
- Keep the headed login window available until authenticated identity is verified.
- After verification, background execution may continue in the same account profile.
- Do not export authentication state into prompts, logs, receipts, skills, or business databases.
- Disconnect stops use of the profile. Delete removes it only after explicit account lifecycle intent.

## Platform knowledge

Selectors, URLs, editor fields, limits, and recommendation rules change. Store versioned platform
knowledge with source and observation time; discover the current page by snapshot instead of freezing
DOM selectors in this Skill.
