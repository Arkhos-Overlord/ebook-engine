# Chapter 9: The Boundaries (What Not to Automate, and How Not to Get Hurt)

Every chapter so far has been about what to do. This one is about what to refuse, and it is not a caution appended for legal comfort — the boundaries in here are the difference between a business that adopts AI well and one that adopts it into a problem.

The good news is that the risk surface for a small business is smaller and more definable than the discourse suggests. You are not training models or deploying software to millions. You are putting text into tools and getting text back. That is a contained, understandable set of risks, and each one has a practice that handles it.

## Rule One: Your Customers' Information Is Not Yours to Paste

Start here because it is the violation most likely to happen by accident, on day one, by someone acting in good faith.

When you paste a customer's details into a consumer AI tool, you are sending that information to a third party's servers, where — depending on which tool, which tier, and which settings — it may be logged, reviewed, or used to train future models. Name and email are a nuisance if leaked. Home address and gate code are worse. Anything health-related, financial, or relating to a vulnerability crosses from hygiene into liability, and in plenty of jurisdictions you are the one legally holding that data, not the tool you forwarded it to.

The practical handling, in decreasing order of preference:

**Anonymize first.** For most drafting work, the model does not need the real details — it needs the shape. Replace the customer's name with "the customer," the address with "the property," account numbers with "the account," and draft against the anonymized version. For the enquiry-reply workflow of Chapter 4, this costs you nothing: you need the substance of what they asked, not their file. Make this a habit before you have a policy, because the habit is what survives busy days.

**Check your tier.** The consumer free tiers of the major tools generally do not offer no-training commitments; the paid business tiers generally do — meaning inputs are not used to train models and are handled under a business agreement. If your work regularly involves real customer data, thirty-odd dollars a month per user for the business tier is not an expense, it is the price of being allowed to do this at all. Read the actual data-handling terms once; they are shorter than you fear and clearer than the marketing.

**Keep an exclusion list.** Some categories should never go into any chat window, tier or not: payment card details, government ID numbers, medical information, passwords or access codes, and anything you would not be comfortable explaining to the customer whose it is, read out loud, in a deposition. When a task needs those facts, the task needs to be done the old way, or inside software that already holds the data under its own obligations — your accounting system, your CRM — not exported through a chat box for convenience.

Write your exclusion list somewhere your team can see it. This is the one boundary that gets crossed by well-meaning staff, because "it was just a quick question" is exactly how it always starts.

## Rule Two: A Human Sees What the Customer Sees

Recurring theme, stated here as policy: no AI-drafted output reaches a customer, a supplier, an employee, or the public without a person reading it first. This applies to replies, quotes, reviews, posts, price changes — everything discussed in Chapters 4 through 7 — and it is not really a concession to AI's imperfection. It is just good practice for anything a customer will read as coming from you; you would not have an untrained hire send without review either, and the model is an extremely well-read hire on its first day who does not know which of your customers is currently angry.

Three failure types make the case better than any principle.

**The invented fact.** The model states something that is not true — a feature, a policy, a number — with the same confidence it states the weather. Hallucination is not rare enough to ignore and not malicious enough to detect by feel; it simply happens, most often in exactly the domains where confidence matters, because those are the ones where plausible-sounding text is abundant in the training data. Your Chapter 3 fact-check pass exists for this, and the pass only happens if a person reads.

**The tone miss.** The words are all correct and the message is wrong for the moment — breezy in a complaint thread, legalistic in a reply to a long-standing customer, efficient where warmth was the whole point. Customers forgive errors faster than they forgive tone, because tone tells them what you think of them. A read-through catches what a word-check cannot.

**The unfired foot.** The draft that answers a different question than the one asked, includes a line about a service they did not mention, or — the classic — pastes the residue of a previous conversation or an instruction that was meant for you. Rare, startling when it happens, and caught by literally any human reading before send.

If you take one habit from this chapter: drafts are drafts. The speed you gained was never in skipping review; it was in skipping composition. Keep the fifteen seconds of review and you keep the benefit entirely.

## Rule Three: Verify Anything Factual Before You Rely On It

Chapter 1 covered the capability gap; this is the operating procedure.

Model output falls into three buckets, and each gets different handling. **Things you supplied** — your prices, your terms, your facts — are trustworthy to the extent your fact sheet is current; keep it current, because a stale fact sheet automates staleness. **Reasonable-sounding claims you did not supply** — industry conventions, typical timeframes, general statements about how things are done — treat as a hypothesis: often right, occasionally confidently wrong, cheap to check when it matters and fine to leave unchecked when it does not. **Specific verifiable facts** — numbers, dates, names, regulations, anything you would stake money or reputation on — verify against a primary source every time, no exceptions, because this is precisely the category models fabricate in.

The asymmetry worth internalizing: the claims most likely to be wrong are the ones you are least likely to check, because they arrive dressed as background knowledge — the kind of thing you assumed you already knew, so it does not trigger scrutiny. It does not matter that you "knew" it; the model said it, and the model does not know. Check anyway.

For anything load-bearing — a contract point, a tax position, a safety standard, a claim in a customer-facing document — the model's role ends at preparing your question for the professional. It can summarize the contract so you know what to ask; it does not tell you what to sign. That line has no exceptions in this book.

## Rule Four: Watch the Skills You Are Quietly Handing Over

The subtle risk, and the one experienced owners raise themselves: dependency.

Drafting everything with a tool you do not fully understand is fine while the tool is available and behaving. The problems are specific. If the tool changes its behavior — different model, new restrictions, a price rise you will not pay — your ability to do the work by hand should still exist, because it is the fallback for every other failure in this chapter. More quietly: if nobody on your team can write a clear brief, a firm but warm reply, or a proposal that maps to what the client actually said, then the business has outsourced a core competence to something it rents by the month.

The defense is small and deliberately old-fashioned: keep writing some things yourself. The most important message of the week, the proposal you are nervous about, the reply where the relationship is delicate — draft those by hand, at least the first pass. Not because AI would do badly — often it does fine — but because the skill needs reps to exist, and it is easier to maintain a skill than to rebuild one after a gap. A useful test: if your tool vanished tomorrow, how long until you were answering customers at your current standard without it? If the answer embarrasses you, send one important thing a week the long way.

Related and more measurable: your customers chose you, not a category. The specific voice in your best messages — the one your message library is collecting — is the reason a reply from you lands differently than a reply from the alternative, and generic-ness is the failure mode AI drifts toward when you stop supplying specifics. The fact sheet, the example library, the habit of anchoring every draft to one concrete detail: those are not prompt tricks, they are how your business keeps sounding like itself while a machine does the typing.

## Rule Five: Decide the Policy Before the Incident

Every business using these tools eventually has an incident: something went out that should not have, or a draft was built on a wrong assumption, or two people's work looked suspiciously identical. The businesses that handle it well had already decided how they would; the ones that do not, improvise under stress and usually improvise secrecy.

Have these four answers written down, in whatever document your team already reads:

**What never gets sent without a named human approving it.** For most small businesses: anything with money in it, anything to do with a dispute, anything published publicly, anything automated from Chapter 8 — plus whatever is specific to your trade.

**What to do when a mistake gets out.** The boring sequence — spot it, tell the customer before they find out, correct it plainly, fix whatever let it happen — works for AI errors exactly as it always worked for human ones. The instinct to hide the involvement of a tool is usually what turns a small mistake into a trust problem: customers care about the error and the fix, and mostly do not care which part a machine typed.

**Where the records live.** Your fact sheet, your message library, your prompt file, your automations' locations and what they do. Ten minutes of documentation now is the difference between a system your business owns and a setup only one person understands, which — ask anyone who has inherited a small business — is a liability of exactly the same shape whether the thing you inherited was software or a filing cabinet.

**Who to call when it is outside your competence.** Accountant, insurer, lawyer, hosting or software support — identify them before you need them, and know that some contracts and regulated fields have clauses about automated communications specifically. Five minutes of checking your own industry's rules now is cheaper than any amount of checking afterward.

## The Boundary, in One Paragraph

Let a machine read everything and draft most things. Let it summarize your contracts so you ask better questions, prepare your numbers so your accountant works from something legible, and assemble your week while you sleep. Never let it be the thing that verified a fact, made a promise, allocated a risk, or decided how a human being should be spoken to in a difficult moment. Keep the customer's data off consumer servers, keep your eye on the drafts, keep one hand on the skills — and the whole arrangement stays inside the boundary comfortably, for years, without a single dramatic day.

## This Week

Twenty minutes, once, and it never needs doing again: write your one-page AI policy. Your exclusion list (the categories that never go in a chat window), your named approver for the four never-send-without-review categories, your tier decision (are you on a business tier or anonymizing everything — pick one deliberately), and where your fact sheet and message library live. Put it somewhere the people who answer messages for you will actually find it. This is the least exciting page you will produce from this book and the one most likely to save you real money — not theoretically, not someday — the week something would otherwise have gone wrong.
