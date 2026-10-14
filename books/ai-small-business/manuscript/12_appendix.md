# Appendix: The Prompt Library

Every prompt used in this book, gathered in one place, with placeholders marked in brackets so you can see exactly what to change before you paste. Copy the ones matching your tasks into your working file, fill the brackets once, and reuse.

The house rules still apply to all of them: supply the facts the model cannot know, ask for a format you can specify, check any fact you did not supply, and read the draft before anyone else does.

## The Universal Wrapper

Most prompts below work better wrapped like this:

> You are [role — e.g. an experienced small-business owner writing to a customer]. Facts you must use: [paste from your fact sheet]. [Paste the actual input — customer message, notes, numbers.] Task: [what you want]. Format: [length, structure, tone]. Invent nothing — if a fact is missing, say what is missing instead of guessing.

The final instruction — invent nothing, say what is missing — is the single most useful line in this book. It converts a silently wrong answer into a visibly incomplete one, which you can then finish yourself in seconds.

## Enquiry Reply (Chapter 4)

> You are replying to a new customer enquiry for [business name], a [what you do] business in [area]. Tone: friendly but direct, like a competent person answering a text. Facts: [prices/ranges, lead time, what happens next]. Here is their message: [paste]. Write a reply under 150 words that answers the specific thing they asked (not a generic pitch), and end with one specific next step — suggest [your preferred next step, e.g. two times this week]. Invent nothing; if you need a fact I did not give, list it at the end instead of guessing.

## Review Response (Chapter 4)

> [Paste the review.] Write a reply as the owner of [business]. Five stars: warm, under 30 words, mention the specific service they named, no exclamation marks. [Change this line for lower ratings:] Acknowledge their specific complaint in the first sentence, no defensiveness, one sentence on what we are doing about it, invite them to contact us at [channel] to sort it. No corporate apology phrases — never use "we apologise for any inconvenience" or "we value your feedback." Under 60 words.

## Complaint / Difficult Reply (Chapter 4)

> I am going to paste what I actually want to say, then what they sent. [Paste both.] Write a professional reply that: acknowledges their specific point in the first sentence, does not admit fault we have not established, proposes [your resolution or next step], and keeps the tone calm and unhurried. Under 120 words. No legal language, no "unfortunately," no lecturing.

## The Triage List (Chapter 4)

> Here is my unread message list for today: [paste messages with senders]. Sort into three groups: REPLY NOW (problems, money, time-sensitive), REPLY TODAY (enquiries, questions), REPLY WHEN I CAN (everything else). For each item give one line: who, what they want, and a suggested one-line response. Flag anything where waiting a day would clearly cost us.

## Quote (Chapter 6)

> Draft a quote for [job]. Structure exactly: our understanding of what they want, scope of work, line items with prices, what is not included, payment terms [terms], start date [date], validity 30 days. Customer's own words about what they want: [paste their message or your visit notes]. My rates: [rates]. Tone: clear and confident, no sales language. Total the line items and show the sum separately so I can check it. Note at the end: any fact you need that I did not supply.

## Follow-Up Sequence (Chapter 6)

> I sent this quote on [date]: [paste quote]. Draft three follow-up emails, each under 60 words, in my voice (friendly, direct, no pressure language): 1) sent 1 day later — brief, offers to walk them through it; 2) sent 5 days later — adds something useful (answer a likely question / note about schedule filling); 3) sent 14 days later — honest close-the-loop, is the project still live? Never say "just following up" or "circling back."

## Invoice Chase (Chapter 7)

> Invoice [number], [amount], was due [date], now [n] days overdue. Customer: [name, how long we have worked with them]. Draft a payment reminder: [first nudge — assume good faith, give the payment details again, ask if there is a problem paying]. Tone: matter-of-fact, not apologetic and not aggressive, under 80 words. Our payment terms allow [late fee terms, if any — otherwise state "no late fee, do not mention one"].

## Social Post from a Raw Item (Chapter 5)

> Turn this into a social post for [business]: [paste the customer question / job photo description / thing you explained]. Audience: [who buys from us]. Write three versions: (a) 80–120 words, conversational, first person, ends with a question or a clear takeaway; (b) a short version under 40 words; (c) one line. Use this real example of my tone as a guide: [paste a post or message you liked]. Concrete specifics only — no hype words, no "did you know," no emojis unless the example has them. I will fact-check any claim.

## Email to the List (Chapter 5)

> Write a short email to my list using this: [raw item]. From [your name], who [one line about you]. Subject line options: give me 5, under 45 characters each, specific and plain — no clickbait, no ALL CAPS. Body: 150–250 words, one idea, tell it like you would to a customer who asked you this in person, sign off with [your name]. I will add a personal sentence before sending.

## Document from Dictation (Chapter 7)

> I dictated how we do [process] and this is the raw transcript: [paste transcript, typos and all]. Turn it into a numbered step-by procedure with: a one-line purpose at the top, numbered steps, a tools/what-you-need list, and a final quality check of 3 things. Keep my wording where it is clear; do not invent steps I did not describe — list anything you think is missing at the end under "gaps." Audience: a new starter on their first day.

## Weekly Numbers Summary (Chapter 7)

> Here are my figures for [week/month]: [paste numbers]. Do not calculate anything — only organize and describe what I gave me. Write a one-page owner's summary: top line first, then exceptions (anything unusual), then three specific things needing attention, then comparison to [previous period] using the figures I supplied. Plain English, no accounting jargon, no advice about things outside these numbers.

## The Interview Move (Chapter 3)

> Before you draft [task], ask me up to 5 questions whose answers would let you do this properly. Only questions — do not start drafting yet.

Use when output keeps missing. It is the fastest rescue for a prompt going in circles.

## Automating It (Chapter 8)

The same prompts, adjusted for a machine reading them: swap "I will fact-check" for "flag any fact not present in the supplied inputs," and add "return the customer's original message above your draft, prefixed DRAFT — EDIT BEFORE SENDING." Then put your fact sheet where the automation can reach it, keep exactly one copy of it, and keep yourself at the end.
