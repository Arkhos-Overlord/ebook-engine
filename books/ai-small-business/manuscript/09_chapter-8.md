# Chapter 8: Your First Automation (The Part Where the Hours Come Back)

Everything so far has been you, typing into a chat window, faster. Genuinely useful — most owners stop here and still collect the majority of their ten hours. But there is another category of work where the hours multiply, and it is the one people mean when they talk about automation: work that starts without you.

The distinction matters more than the vocabulary. Chatting with AI is like having a very fast assistant you must personally visit, brief, and collect work from each time. Automation is the assistant who knows that when a certain thing happens in your business, this job gets prepared and waits for you, finished, when you next sit down. The first saves minutes per task. The second deletes tasks from your week entirely.

This chapter builds the first one — deliberately small, deliberately safe, end to end, so that you understand the shape before you scale it.

## The Shape of Every Automation

They all look the same, whatever software is involved:

**Trigger** — something happens. An email arrives. A form is submitted. A calendar event is created. A file lands in a folder. A scheduled time comes around.

**Gather** — the relevant information is collected: the contents of that email, the details from the form, today's appointments.

**Process** — the AI does its part: drafts, summarizes, categorizes, extracts, translates.

**Deliver** — the output goes somewhere useful: your inbox for approval, a document, a row in a spreadsheet, a slot in your calendar.

**You** — you review and send, or you do nothing because the job was safe enough to finish itself.

That last box is the one people try to delete first and should delete last. The whole art of building automations that do not damage your business is deciding, per task, where the human review sits — and the honest answer for your first several builds is "at the end, always." Approval-gated automation loses almost none of the time savings, because the expensive part of the work was never your review; it was the drafting, the gathering, the remembering. Keep the review, delete everything before it.

## Choosing Your First One

Good first automations share four properties. The output is a draft for you, not an action taken with a customer. Being wrong is cheap — embarrassing at worst, not costly. It happens often enough to matter, ideally daily or weekly. And it starts from a clear trigger, something with a definite "this just happened" moment.

Strong candidates that fit: a new contact-form or email enquiry triggers a drafted reply waiting in your inbox; a new booking triggers a confirmation plus a line in a spreadsheet plus a reminder draft; a scheduled Monday time triggers your week's list assembled from your calendar and open quotes; a new invoice in your accounting software triggers a follow-up message drafted for the fourteen-days-overdue point.

Weak first choices — and I list these because they are the tempting ones: anything replying to customers without you seeing it; anything touching payments; anything where a wrong output is public; anything involving data you would not paste into a chat window under Chapter 9's rules. Those can come later, some of them, with gates and testing. Your first build should be boring and unembarrassing. You are learning the shape, not proving a thesis.

For what it is worth, the usual first pick — the one I recommend — is the enquiry-to-draft-reply flow, because you already wrote that reply by hand in Chapter 4, you know exactly what good looks like, and comparing the automated draft to your manual ones gives you an instant quality yardstick for everything that follows.

## The Tools (Least Impressive First)

You do not need much, and the order here is from most to least available to you right now.

**What you already have.** Your email client can auto-file, auto-label, and create drafts from rules — Outlook and Gmail both do this, and so does almost every CRM and booking tool worth the name. Set up correctly, "email from our website's form address gets labelled ENQUIRY and pre-drafted from a template" is ten minutes of settings and already qualifies as automation. Check your existing tools for AI features before shopping; you are probably paying for some already.

**Built-in AI in your core software.** Your accounting package, your booking system, your help desk — most now include AI drafting, categorizing, or summaries as a feature rather than an add-on. This is the best-value tier: it arrives pre-connected to your data, needs no plumbing, and costs nothing extra. The downside is it is invisible, which is why Chapter 10 schedules a proper audit of every tool you pay for.

**An automation connector.** Tools like Zapier, Make, or n8n (the last self-hostable, if that appeals) sit between your applications and carry data from trigger to action: new form submission → gather details → AI draft → email to you for approval. Subscription-priced, with generous free tiers that will comfortably cover a first automation. This is where the full shape from the last section gets built without anyone writing code, and where most owners build their first genuinely hands-off flow.

**Custom scripts.** A small program that does exactly what you want, no subscription, no template limits. Maximum control, maximum maintenance — and there is a version of this now where you describe the automation to an AI coding tool and it writes the script for you, which is a real and accelerating option. But it is chapter-seven-level territory at the earliest: only once you know precisely what you want, and never as a first build. When your third automation is running and you can specify its logic in a paragraph, revisit the idea.

Do not spend more than an evening choosing. The capabilities at each tier are far more similar than their marketing suggests, and the differentiator in practice is whether the trigger you need is one of your tools' native events. Check that, pick the tier that covers it, move on.

## Building It: The Enquiry Flow

A concrete build, end to end, so the shape stops being abstract.

**Trigger:** a new message arrives at enquiries@yourbusiness (or lands in your website form's inbox — use whatever address your forms already deliver to).

**Gather:** the sender's address and message body. If your form collects fields — name, service, suburb, timing — include those too; structured fields make better drafts than one blob of text.

**Process:** a prompt you have now written before, in Chapter 4, lightly adapted for the machine: role (you, answering an enquiry), the facts sheet pasted in, the customer's message, format (under 150 words, one specific next step, friendly and direct), and a hard instruction to invent nothing — no prices or dates that were not in the supplied material.

**Deliver:** a new email to you, subject prefixed DRAFT, containing the customer's original message and below it the proposed reply, with a one-line instruction to yourself at the top: edit, then send to the customer.

**You:** tomorrow morning, you open DRAFT emails with your coffee, approve three, fix the tone on one, and send. Total active time: six minutes for what used to be forty.

Two implementation details that separate working automations from ones that break mysteriously in three weeks. First, make the draft email unmistakable — a subject prefix like DRAFT you can spot at a glance — because the failure you are guarding against is future-you sending an unedited draft to a customer at speed; a visible marker makes that habit hard to fall into. Second, keep the facts sheet the automation uses in the same place as the one you paste by hand, so there is exactly one version of your prices, your tone, and your next step, edited in one location. Automations that carry their own frozen copy of your facts are how businesses end up quoting last year's prices from a flow nobody remembers building.

Expect the first week to surface adjustments: a certain customer phrasing that trips the prompt, an enquiry type (complaint rather than sale) that needs routing to you un-drafted rather than drafted. Change one thing at a time and note what you changed. You are tuning, not failing — the same two-week ramp you saw with hand-prompting, except now the ramp is on a system rather than a skill.

## Your Second and Third

Once the first has run untouched for a week, the pattern generalizes fast, and the next two are usually some variation of the same idea applied to different triggers.

The booking flow: appointment created → confirmation drafted for you to send, spreadsheet row added (your new job log, assembling itself), reminder message scheduled for the day before. This one frequently saves more time than the first, because confirmations are pure overhead and no-shows are pure cost.

The Monday-morning flow: scheduled time fires → gather this week's calendar, open quotes, overdue invoices → one email to you that is simply your week, prioritized, with drafted follow-ups attached to each item that needs one. This replaces the Sunday-evening mental load — the lying-awake inventory of everything open — with a document that exists before you wake up. Owners who build this one tend to report it as the biggest psychological win of the whole process, even when the raw hours are modest, because the cost of carrying it all in your head was never only the hours.

Notice what has happened across these three: the unit of your work has shifted from tasks to reviews. You are no longer doing the work, you are approving work that was prepared while you were elsewhere. That shift is where the ten hours come from — not from typing faster, but from the queue of prepared work that replaces the queue of nothing-started.

## What Still Does Not Belong Here

The temptation at this stage is to automate the customer-facing layer entirely: auto-replies, auto-posting, auto-follow-up with no gate, the business running itself while you sleep. Every experienced owner who tried it reports the same finding — it works right up until the first time it does not, and the first time it does not is public, and the cost of that one event exceeds the savings from every automation combined.

The discipline that makes automation safe is keeping humans at the points where output becomes a promise: anything a customer sees as coming from you, anything with a number attached, anything published. Your automations should be producing an inbox full of ready work, not making decisions in your name. If a flow cannot be approval-gated without losing most of its value, it is the wrong flow to automate right now — not forever, but until you have several months of evidence that your drafts are consistently clean.

Chapter 9 draws the full boundary. For now, the rule from the top of the chapter stands: your first three automations all end with you, approving, in seconds.

## This Week

Pick your trigger from the four candidates, check that your existing tools can see it (a five-minute look at your email rules, booking tool, and form's destination address), and choose your tier — likely what you already own, possibly a connector's free plan. Build the flow this week, even roughly; a rough flow that runs beats a perfect one contemplated. Send yourself ten test situations — real past enquiries, resubmitted — and count how many drafts you would have sent with at most a word changed. That approval rate, your second sticky-note number, tells you whether the system is ready to carry real traffic. Then let it run for seven days before changing anything else, and watch the DRAFT queue each morning. It is a strange feeling, the first morning the work is already done. It does not wear off.
