# Avoid AI Writing

Audit and rewrite content to eliminate AI-generated patterns ("AI-isms"). This is a writing-quality tool — not proof of AI authorship; humans under deadline or writing in a second language produce similar patterns.

## Modes

**Rewrite** (default): Identify AI-isms and return cleaned text with a diff summary and second-pass verification.

**Detect**: Flag patterns only; assess which are genuine problems vs. intentional or effective in context.

**Edit**: Modify a named file in place with minimal, targeted fixes; preserve already-human passages and re-verify after changes.

## Invocation

Natural language or power-user flags:

- `[--mode rewrite|detect|edit]`
- `[--voice casual|professional|technical|warm|blunt]`
- `[--context linkedin|blog|technical-blog|investor-email|docs|casual]`
- `[--file PATH]`
- `[--iterate N]` (max 2 — repeats audit→rewrite until clean or N passes reached)

Auto-detect context from signals: short + hashtags = `linkedin`; code blocks = `technical-blog`; salutation = `investor-email`; step-by-step = `docs`; default = `blog`.

---

## AI-ism Categories

### Formatting Issues

- **Em dashes** (— and --): Replace with commas, periods, or two sentences; target zero; hard max one per 1,000 words
- **Bold overuse**: One per major section max; restructure instead
- **Emoji in headers**: Remove entirely; social posts allow 1–2 at line end
- **Excessive bullets**: Convert to prose unless genuinely list-shaped
- **Curly quotes**: Weak signal; meaningful mainly in plain-text contexts

### Sentence Structure Problems

- "It's not X — it's Y" patterns → rewrite as direct statements
- Hollow intensifiers: Remove "genuine," "real," "truly," "quite frankly," "to be honest," "let's be clear," "it's worth noting"
- Vague endorsement: Cut "worth reading," "worth paying attention to," "worth exploring," "worth checking out"
- Hedging: Eliminate "perhaps," "could potentially," "it's important to note that," "to be clear"
- Missing connective tissue between paragraphs
- Compulsive rule of three: Vary groupings; use two or four items instead

---

## Vocabulary

### Tier 1 — Always Replace

| Term | Replace With |
|------|--------------|
| delve / delve into | explore, dig into, look at |
| landscape (metaphor) | field, space, industry, world |
| tapestry | describe actual complexity |
| realm | area, field, domain |
| paradigm | model, approach, framework |
| embark | start, begin |
| beacon | rewrite entirely |
| testament to | shows, proves, demonstrates |
| robust | strong, reliable, solid |
| comprehensive | thorough, complete, full |
| cutting-edge | latest, newest, advanced |
| leverage (verb) | use |
| pivotal | important, key, critical |
| underscores | highlights, shows |
| meticulous / meticulously | careful, detailed, precise |
| seamless / seamlessly | smooth, easy, without friction |
| game-changer / game-changing | describe specific change and impact |
| hit differently / hits different | specify what changed or cut |
| utilize | use |
| watershed moment | turning point, shift |
| marking a pivotal moment | state what happened |
| the future looks bright | say something specific or cut |
| only time will tell | cut or state specific claim |
| nestled | is located, sits, is in |
| vibrant | describe specifics or cut |
| thriving | growing, active, or cite numbers |
| despite challenges… continues to thrive | name challenge and response |
| showcasing | showing, demonstrating |
| deep dive / dive into | look at, examine, explore |
| unpack / unpacking | explain, break down, walk through |
| bustling | busy, active, or specify |
| intricate / intricacies | complex, detailed |
| complexities | name actual problems or details |
| ever-evolving | changing, growing |
| enduring | lasting, long-running |
| daunting | hard, difficult, challenging |
| holistic / holistically | complete, full, whole |
| actionable | practical, useful, concrete |
| impactful | effective, significant |
| learnings | lessons, findings, takeaways |
| thought leader / thought leadership | expert, authority |
| best practices | what works, proven methods |
| at its core | cut — state the thing directly |
| synergy / synergies | describe actual combined effect |
| interplay | relationship, connection, interaction |
| in order to | to |
| due to the fact that | because |
| serves as | is |
| features (verb) | has, includes |
| boasts | has |
| presents (inflated) | is, shows, gives |
| commence | start, begin |
| ascertain | find out, determine, learn |
| endeavor | effort, attempt, try |
| keen (intensifier) | interested, eager, or cut |
| genuinely / genuine (intensifier) | cut — state the fact |
| symphony (metaphor) | describe actual coordination |
| embrace (metaphor) | adopt, accept, use, switch to |

### Tier 2 — Flag When 2+ Appear Together

Legitimate individually; suspicious in clusters:

harness, navigate / navigating, foster, elevate, unleash, streamline, empower, bolster, spearhead, resonate / resonates with, revolutionize, facilitate / facilitates, underpin, nuanced, crucial, multifaceted, ecosystem (metaphor), myriad, plethora, encompass, catalyze, reimagine, galvanize, augment, cultivate, illuminate, elucidate, juxtapose, paradigm-shifting, transformative / transformation, cornerstone, paramount, poised (to), burgeoning, nascent, quintessential, overarching, underpinning / underpinnings

### Tier 3 — Flag at High Density (≈3%+ of text)

- significant / significantly → specifics: numbers, comparisons, examples
- innovative / innovation → describe what's actually new
- effective / effectively → say how or cite metrics
- dynamic / dynamics → name actual forces or changes
- scalable / scalability → describe what scales and to what extent
- compelling → explain why
- unprecedented → name precedent broken or cut
- exceptional / exceptionally → cite what makes it exceptional
- remarkable / remarkably → specify what's worth remarking on
- sophisticated → describe sophistication
- instrumental → state what role it played
- world-class / state-of-the-art / best-in-class → cite benchmark or comparison

#### Tier 3 Phrases — Flag at Density or in Clusters (2+ same phrase OR 3+ distinct phrases)

- emerging sector / emerging space / emerging category → name actual sector
- the integration of (X with Y) → describe what changes for user
- the intersection of (X and Y) → specify overlap that matters or cut
- community-driven → name what community does
- long-term sustainability → cite time horizon and constraint
- user engagement → name the action (clicks, comments, retention)
- decentralized compute → specify architecture or cut
- tokenized incentive structures → describe mechanism (vesting, gauge, bonded LP, etc.)
- designed for long-term [X] → cut "designed for" — state the property directly

---

## Patterns and Structures to Remove

### Template Phrases

- "a [adjective] step towards [adjective] AI infrastructure" → describe specific capability, benchmark, outcome
- "a [adjective] step forward for [noun]" → say what changed
- "Whether you're [X] or [Y]" → pick actual audience or cut
- "I recently had the pleasure of [verb]ing" → just say what happened

### Transition Phrases

- "Moreover," "Furthermore," "Additionally" → restructure or use "and," "also," "on top of that"
- "In today's [X]," "In an era where" → cut or state specific context
- "It's worth noting that," "Notably" → state the fact directly
- "Here's what's interesting," "Here's what caught my eye," "Here's what stood out" → let content signal importance
- "In conclusion," "In summary," "To summarize" → conclusion should be obvious
- "When it comes to" → talk about thing directly
- "At the end of the day" → cut
- "That said," "That being said" → use "but," "yet," "however" or cut

### Generic Future-Narrative Closers

Pattern: modal (may/could/will/is poised to) + "become" + "one of the most [adjective]" + narrative/story/trend/theme/chapter/movement/force

These contain no testable content. Pick a falsifiable version instead.

### Hedge-Stacked Predictions

"Could potentially create," "may eventually unlock," "might ultimately transform" — each hedge cancels the next. Pick one.

### "Real/Actual" Adjective Inflation

"Real on-chain tokenomics," "actual reward sustainability," "genuine utility" — implies rest of field is fake without naming what makes this instance real.

**Exception**: Named contrast is fine ("real on-chain settlement, not bridged IOUs").

### Hashtag Stuffing

6+ hashtags on short post is near-universal in LLM output. Fix: 2–3 specific tags max or none. Flag at 2+ phrase repetition or 3+ distinct phrases clustering.

### Bullet Lists of Bare Noun Phrases

5+ consecutive short (≤6 word) adjective-plus-noun items with no verbs. Fix: convert to prose or rewrite as full claims.

### Copula Avoidance

AI substitutes "serves as," "features," "boasts," "presents," "represents" for "is" / "has." Default to plain copulatives unless specific verb adds meaning.

### Synonym Cycling

AI rotates synonyms to avoid repetition ("developers… engineers… practitioners… builders"); human writers repeat the clearest word.

### Vague Attributions

"Experts believe," "Studies show," "Research suggests," "Industry leaders agree" — without naming source. Either cite specifically or drop attribution.

### Filler Phrases

- "It is important to note that" → state it
- "In terms of" → rewrite
- "The reality is that" → cut or state claim
- "In order to" → "to"
- "Due to the fact that" → "because"
- "At the end of the day" → cut

### Generic Conclusions

"The future looks bright," "Only time will tell," "One thing is certain," "As we move forward" — filler disguised as conclusions. Cut entirely.

### Chatbot Artifacts

"I hope this helps!", "Certainly!", "Absolutely!", "Great question!", "Feel free to reach out," "Let me know if you need anything else"

Also: "In this article, we will explore…," "Let's dive in!" — meta-narration. Cut or rewrite.

### "Let's" Constructions

"Let's explore," "Let's take a look," "Let's break this down," "Let's examine" — false-collaborative filler. Start with the point.

### Notability Name-Dropping

"Cited in NYT, BBC, FT, Hindu" piles citations for credibility without context. One specific reference beats four name-drops.

### Superficial -ing Analyses

Strings of present participles without substance: "symbolizing the region's commitment, reflecting investment, showcasing a new era." Replace with specific facts or cut.

### Promotional Language

"Nestled within breathtaking foothills," "vibrant hub of innovation," "thriving ecosystem." Replace with plain description.

### Formulaic Challenges

"Despite challenges, [subject] continues to thrive" — non-statement. Name actual challenge and response, or cut.

### False Ranges

"From Big Bang to dark matter," "from ancient civilizations to modern startups" — sweep without substance. List actual topics or pick one.

### Inline-Header Lists

Bullet lists where each item starts with bold header that repeats itself. Strip bold; write point directly.

### List-Label Periods

LLM-generated: `- **Intros.** Years of conferences and operator network.`
Human-generated: `- **Intros:** years of conferences and operator network.`

Fix: change period to colon, lowercase what follows.

### Title Case Headings

AI over-capitalizes: "Strategic Negotiations And Key Partnerships." Use sentence case for subheadings.

### Hyphenated-Pair Overuse

Strings of compound modifiers piled on one noun: "high-quality, well-architected, future-proof solution." Cut to modifier that matters; fix predicate hyphenation ("report is high quality," no hyphen).

### Cutoff Disclaimers

"While specific details are limited," "As of my last update," "I don't have access to real-time data." Either find info or remove. Never publish admissions of incomplete research.

### Speculative Gap-Filling

"Maintains relatively low profile," "is believed to have," "likely began career in," "appears to have studied" — guesses formatted as statements. Cut speculation or replace with sourced fact.

### Unfilled Placeholders

`[Your Name]`, `[INSERT SOURCE URL]`, `[Describe specific section]`, `2025-XX-XX`, `<!-- Add citation if available -->`

Treat as publishing bug: fill with real content or delete.

### Chatbot Citation Markup Leaks

`citeturn0search0`, `contentReference[oaicite:0]`, `oai_citation`, `[attached_file:1]`, `grok_card` — fingerprints of specific chat tools. Strip entirely.

### AI-Tool URL Parameters

`utm_source=chatgpt.com`, `utm_source=copilot.com`, `utm_source=openai`, `utm_source=claude.ai`, `utm_source=perplexity.ai`, `referrer=grok.com`

Fix: strip parameter; keep URL if meaningful.

### Novelty Inflation

AI treats established concepts as newly invented: "He introduced a term," "She coined the phrase," "a concept nobody's naming."

Fix: describe what person *did with* concept, not that they discovered it.

### Infomercial Engagement Hooks

"The catch?", "The kicker?", "Here's the thing.", "But here's the kicker:", "The best part?", "Plot twist:", "The result?" — mid-flow teasers. Delete hook and state the thing.

### Social Endorsement Closers

"This one is worth your time:", "This one's a must-read:", "I highly recommend giving this a read.", "Do yourself a favor and read this.", "You won't want to miss this one.", "Save this for later.", "Bookmark this.", "Don't sleep on this one.", "Trust me, you'll want to read this.", "Thank me later."

Fix: name *what* the thing is and *who* it's for; drop generic CTA.

### Emotional Flatline

"What surprised me most," "I was fascinated to discover," "What struck me was," "I was excited to learn," "The most interesting part," "Interesting part of project:" / "Interesting thing here:" / "Interesting aspect:"

Pre-announcing significance the writing hasn't earned. If emotion is genuine, content should earn it; otherwise cut.

### False Concession Structure

"While X is impressive, Y remains a challenge" — both halves vague. Either make specific or pick a side.

### Rhetorical Question Openers

"But what does this mean for developers?", "So why should you care?", "What's next?" — stalls before point. If you know answer, just say it.

### Parenthetical Hedging

"(and, increasingly, Z)," "(or, more precisely, Y)," "(and perhaps more importantly, W)" — asides without commitment. If it matters, give own sentence; if not, cut.

### Numbered List Inflation

"Three key takeaways," "Five things to know," "Here are top seven" — AI defaults to numbered lists for safety. Only use when content genuinely has that many parallel, discrete items.

### Reasoning Chain Artifacts

"Let me think step by step," "Breaking this down," "To approach this systematically," "Step 1:," "Here's my thought process," "First, let's consider," "Working through this logically" — chain-of-thought scaffolding leaking into prose. State conclusion, then evidence.

### Sycophantic Tone

"Great question!", "Excellent point!", "You're absolutely right!", "That's really insightful observation" — remove entirely.

### Acknowledgment Loops

"You're asking about," "The question of whether," "To answer your question," "That's great question. The..." — restates prompt before answering. Just answer.

### Confidence Calibration Phrases

"It's worth noting that," "Interestingly," "Surprisingly," "Importantly," "Significantly," "Notably," "Certainly," "Undoubtedly," "Without a doubt"

"Here's what's interesting," "Here's the interesting part," "Here are the parts I found interesting"

Related authority tropes: "the real question is," "at its core," "fundamentally," "make no mistake," "the truth is." Cut trope; lead with substance.

### Self-Labeling Significance

After listing items, pointing back at one as "contrarian"/"clever"/"surprising"/"counterintuitive"/"key": "That last move is the contrarian one," "This is the interesting part," "That third bullet is the real story."

Label does work content should do. Fix: cut labeling sentence; restructure so the right item carries its own weight.

### Excessive Structure

More than 3 headings in under 300 words; 8+ bullet points in under 200 words; formulaic headers ("Overview," "Key Points," "Summary," "Conclusion," "Introduction").

Fix: merge sections, use prose transitions, or write headers that tell reader something specific.

### Rhythm and Uniformity

- **Sentence length uniformity**: Most sentences 15–25 words → robotic. Mix short (3–8 words) with long (20+ words); fragments OK.
- **Paragraph length uniformity**: Every paragraph 3–5 sentences and roughly same size → vary deliberately. Include 1-sentence paragraphs.
- **Synonym cycling**: AI cycles conspicuously; human writers repeat when the word is right, vary when natural.
- **Read-aloud test**: If text sounds like text-to-speech, probably too uniform.
- **Missing first-person perspective**: Where appropriate, writer should have opinions, preferences, reactions. AI is relentlessly neutral.
- **Over-polishing**: Aggressively editing out irregularities pushes human writing toward AI profiles. Natural disfluency, idiosyncratic choices, uneven pacing keep text human.

### Vocabulary Diversity (Stylometric)

Type-token ratio (TTR) — distinct word types ÷ total tokens — signals prose quality. Human English prose: ~0.50–0.65. AI: often under 0.40.

Low TTR on general prose (200+ words) worth a second look, but context matters: narrow topics, technical material, second-language writing legitimately compress vocabulary.

Fix: broaden *what* — name specific things, cite cases, replace reused abstract noun with concrete instance.

### Paragraph-Reshuffle Immunity (Structure Test)

Can you swap two body paragraphs without breaking the piece? If order doesn't matter → you've written a list of points, not building an argument. AI prose often fails this test.

Fix: establish through-line where each paragraph depends on the previous.

### Treadmill Effect / Low Information Density (Content Test)

For each paragraph: "What's actually new here?" AI prose restates premise in fresh words instead of advancing it. Often 40–60% could be cut with no information loss.

Fix: for each paragraph, name the one fact, claim, or turn it contributes. If there isn't one → cut it. Lead with it and drop throat-clearing.

### When to Rewrite from Scratch vs. Patch

If text has 5+ flagged vocabulary hits across multiple categories, 3+ distinct pattern categories triggered, and uniform sentence/paragraph length → patching won't fix it. Advise full rewrite.

---

## Severity Tiers

### P0 — Credibility Killers (Fix Immediately)

- Cutoff disclaimers ("As of my last update")
- Chatbot artifacts ("I hope this helps!", "Great question!")
- Vague attributions without sources
- Significance inflation on routine events
- Hashtag stuffing on `linkedin` and `investor-email` posts

### P1 — Obvious AI Smell (Fix Before Publishing)

- Word-list violations (delve, leverage, harness, robust, etc.)
- Template phrases and slot-fill constructions
- "Let's" transition openers
- Synonym cycling within paragraph
- Formulaic openings
- Bold overuse
- Em dash frequency (above 1 per 1,000 words)
- Generic future-narrative closers
- Social endorsement closers
- Hedge-stacked predictions
- Real/actual adjective inflation
- Bullet lists of bare noun phrases
- Tier 3 phrase clustering

### P2 — Stylistic Polish (Fix When Time Allows)

- Generic conclusions
- Compulsive rule of three
- Uniform paragraph length
- Copula avoidance
- Transition phrases
- Hashtag stuffing (`blog` / `technical-blog` profiles)
- Tier 3 phrase repetition (single phrase 2+ times)

---

## Context Profiles

### Profile Definitions

- **`linkedin`** — Short-form social. Punchy fragments, visual formatting.
- **`blog`** — Default long-form prose. All rules at full strength.
- **`technical-blog`** — Long-form with code, architecture, APIs. Technical terms get a pass.
- **`investor-email`** — High-trust audience. Tighten everything; promotional language is biggest risk.
- **`docs`** — Documentation, READMEs, guides. Clarity over voice.
- **`casual`** — Slack, internal notes, quick replies. Only catch worst offenders.

### Context Tolerance Adjustments

**Relaxed on LinkedIn:** Em dashes (2/post OK), bold hooks, 1–2 end-of-line emoji, lists, numbered list inflation, rhetorical question hook (1 OK)

**Strict on Investor-Email:** Extra strict on promotional language, significance inflation, generic conclusions, hashtag stuffing, Tier 3 phrase clustering, future-narrative closers, hedge-stacked predictions, real/actual inflation

**Technical-Blog word exceptions:** `robust`, `comprehensive`, `seamless`, `ecosystem`, `leverage` (platform APIs), `facilitate`, `underpin`, `streamline` are legitimate technical terms — don't flag. Still flag: `delve`, `tapestry`, `beacon`, `embark`, `testament to`, `game-changer`, `harness`.

---

## Voice Profiles

Optional. Sets *how prose should sound*, independent of audience strictness.

- **`casual`**: Contractions throughout; short sentences (≤14 words avg); fragments allowed; at least one first-person or anecdote touch; near-zero jargon; cut corporate hedges but keep warm ones ("honestly").
- **`professional`**: Active voice mostly; varied sentence length; one concrete claim per paragraph (number, name, date); never "experts say"; explicit ask; low hedging tolerance.
- **`technical`**: Plain copulatives ("X is Y") over inflated substitutes; one idea per sentence; imperative for instructions; jargon fine if defined on first use; tables/lists only when genuinely list-shaped.
- **`warm`**: Address reader directly ("you"); acknowledge them at least once; cut intensifiers ("very," "truly," "incredibly"); no performative empathy openers; medium sentences (15–20 words) for unhurried cadence.
- **`blunt`**: Lead with claim; cut windups ("It's important to note that"); near-zero em-dashes; no rule-of-three padding; near-zero hedging ("may/could/potentially" stacks flagged); short declaratives with occasional long sentence for contrast.

**Calibrate to sample:** If writer gives own writing sample, analyze sentence-length pattern, contraction rate, paragraph openings, recurring word choices; match instead of named profile. Don't upgrade vocabulary if they write "stuff" and "things."

**Voice composes with context:** Where both govern same rule and agree, they reinforce. Where they conflict → stricter of two wins.

---

## Output Format

### Rewrite Mode

1. **Issues found** — Bulleted list of every AI-ism with offending text quoted
2. **Rewritten version** — Full rewritten content; preserve structure, intent, technical details; only change what guidelines require
3. **What changed** — Brief summary of major edits, not every word
4. **Second-pass audit** — Re-read rewrite for surviving AI tells. Fix inline; note changes. If clean, say so.

### Detect Mode

1. **Issues found** — Bulleted list by severity (P0, P1, P2)
2. **Assessment** — For each flag, note if clear problem or judgment call; what writer should definitely fix vs. worth a second look; if clean, say so.

### Edit Mode

1. **Edits made** — Bulleted list of changes with file location and before → after (only touched spans)
2. **Verification** — Confirm re-read and patterns resolved; note anything deliberately left alone.

---

## Self-Reference Escape Hatch

When writing *about* AI patterns (blog posts, tutorials, skill documentation), quoted examples are exempt from flagging. Only flag patterns in author's own prose, not cited examples of bad writing.

---

## Key Principles for Human-Sounding Rewrites

1. **Vary sentence length** — mix short (3–8 words) with long (20+ words); fragments OK
2. **Be concrete** — replace vague claims with numbers, names, dates, examples
3. **Have a voice** — use first person, state preferences, show reactions where appropriate
4. **Cut neutrality** — humans have opinions; if piece takes position, take it
5. **Earn emphasis** — don't tell reader something's interesting; make it interesting

If original writing is already strong, preserve it; make only necessary cuts.
