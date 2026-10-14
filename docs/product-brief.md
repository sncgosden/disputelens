# DisputeLens: Verifiable Policy Answers

## User and problem

A small merchant receives a chargeback notification from its payment provider and needs to understand what the request means, which guidance applies and what information to check before responding. The merchant may have little payments expertise and records spread across an order system, booking platform, till, delivery service and customer emails.

The product should work across online shops, cafés and physical retailers, subscription businesses, hotels and holiday rentals, and small service businesses. Their disputes may concern an unrecognised transaction, an undelivered order, an item or service described as unsatisfactory, a duplicate or incorrect charge, a cancelled subscription, or a refund the customer says never arrived. These are plain-English situations, not a universal scheme-code taxonomy.

Searching documents takes time, and a plausible answer can be harmful if it uses an outdated rule, invents a requirement or hides conflicting guidance.

## Job to be done

“When my payment provider sends me a chargeback request, help me understand the relevant guidance for my situation, identify what I need to check, show where the answer comes from, and tell me what is missing so I can decide how to respond before my provider’s deadline.”

## Realistic merchant questions

| Merchant and situation | Question the assistant should help answer |
| --- | --- |
| Online shop; customer says the parcel never arrived | “Tracking says delivered but the customer disagrees. What does my provider’s guidance say I should check?” |
| Café; customer does not recognise a card payment | “Could the statement name explain the confusion, and what transaction details should I look at?” |
| Subscription business; customer says they cancelled | “Which cancellation date and billing-period rules apply to this request?” |
| Hotel; guest disputes a cancellation or no-show charge | “Which booking terms apply, and does the guidance address how those terms were communicated?” |
| Tradesperson; customer disputes service quality | “How does the guidance distinguish an unfinished service from dissatisfaction with completed work?” |
| Retailer; customer reports two charges | “What should I check to establish whether these are two settled payments or something else?” |
| Shop; customer says a promised refund is missing | “What does the guidance say about checking refund status and transaction references?” |
| Any merchant; request has a short deadline | “Which deadline actually applies to this notification, and what information do you need to establish it?” |

These examples define questions to support, not verified scheme rules or guaranteed evidence requirements.

## Proposed experience

The merchant provides a question and, where available, the payment provider, dispute wording or reason code, merchant type, transaction/service dates and the deadline shown on the notification. Missing details remain explicit; the assistant must not infer a scheme, deadline or policy from the merchant type alone.

For the prototype, the merchant asks in a terminal. DisputeLens retrieves relevant passages and uses a language model to give: a plain-English explanation, the guidance that applies, practical checks supported by that guidance, citations and excerpts, and any missing information or need for provider clarification. It uses current approved sources, excludes superseded versions, and exposes unresolved conflicts between current sources. When the documents do not support an answer, it says so.

Scheme, provider, jurisdiction, channel and policy version may affect applicability. A provider deadline and a scheme-level limit are not interchangeable. Until the relevant source and notification are available, the assistant must avoid stating an exact deadline or claiming a rule applies.

The merchant remains responsible for the decision. The prototype does not submit evidence or act on their behalf.

## In scope

- Six explicitly fictional control policies with source IDs, versions, dates and authority metadata for ambiguity, conflict and superseded-version tests.
- Seven real sources: whole Visa and Mastercard guides plus Stripe, Adyen, Square UK and PayPal UK guidance. Preserve source editions, regional/date qualifications and provider applicability.
- Local embedding-based retrieval and concise policy answers with verifiable citations.
- Missing-evidence responses, current-source conflict disclosure and basic error handling.
- Sixty Claude-drafted questions checked against source passages by Codex: 45 development and 15 reserved holdout. Include exact codes, paraphrases, provider distractors, regional dates, missing facts, controlled conflicts and unsupported requests. Independent personal review is optional and recorded separately.
- Qwen 4B, Qwen 9B and Claude comparison using identical retrieved context per question.
- A documented failure diagnosis, or an honest statement if no failure is observed, and a reproducible terminal demo.

## Out of scope

Automatic dispute classification, fixed evidence-ID recommendations, predictions or guarantees of winning, model-confidence routing, automatic submissions, a web interface, fine-tuning and production deployment. The assistant explains source-supported policy passages and checks. It does not make submission decisions for merchants. Actual merchant impact will be measured in a later pilot.

## Success and evaluation

A question passes only when required facts are correct, material claims are supported by cited passages, and missing or conflicting evidence is handled appropriately. Valid citation IDs alone do not establish support; the cited passages are reviewed manually. Reviews to date were AI-assisted, not independent.

Report scored and passed cases, failures to run, citation-support failures and generation time separately for each model and for development versus holdout cases. Record actual Claude token usage and cost. Select a model from observed quality, latency and cost rather than size or fluency alone.

There is no production launch threshold at this stage. The small synthetic evaluation can support a prototype decision, not a reliability claim for real merchants or all chargeback categories. Report which merchant types and situations were tested and where coverage is absent. A later pilot would test time to a verified answer, successful identification of missing information and usefulness with representative merchants, realistic notifications and authoritative policies.

## Main risks and controls

- **Wrong or stale source:** use explicit source status and version metadata; inspect retrieval independently of generation.
- **Unsupported answer:** expose supporting excerpts and manually check claim-level support.
- **Conflicting guidance:** show the conflict rather than silently blending incompatible rules.
- **Instructions embedded in documents:** treat retrieved text as evidence, not commands, and test a harmless injection example.
- **Misleading evaluation:** define expected answers before runs, reserve holdout cases and keep diagnostic retries separate from normal results.
- **Privacy and cost:** use public guidance and fictional merchant scenarios, keep keys and interview notes local, make Claude calls explicit and record usage. No automatic cloud fallback.

## Delivery constraint and related work

The expanded corpus uses the complete Visa and Mastercard guides, four payment providers and 60 source-reviewed questions split 45 development / 15 holdout. Implementation and source review were done with AI assistance (Codex). The author owns scope, scoring and the model decision; independent review of the gold set is still outstanding.

The earlier dispute-triage project investigated classification, evidence selection and routing. DisputeLens adds a distinct question: can a merchant verify each policy claim, and can the PM identify whether a failure came from source quality, retrieval or generation?
