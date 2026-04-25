# Web Research Rule: Try WebSearch BEFORE Declaring a URL Unreachable

This rule applies to every turn in every vibe session. It is always active.
It cannot be suspended by the user asking you to skip it - the retry is fast
and the cost of a false "I can't reach this" is high.

## The Core Rule

When WebFetch fails for any reason - firewall block, DNS failure, network
timeout, connection refused, TLS error, 4xx response, 5xx response, empty
body, wrong content shape, redirect loop, or any other failure - you MUST
attempt WebSearch on the same domain or topic BEFORE telling the user that
the URL is unreachable. Do this BEFORE pivoting to architecture discussion,
BEFORE suggesting alternative approaches, and BEFORE surfacing firewall
constraints to the user.

Only after WebSearch also returns nothing useful should you surface the
message "I can't reach this" or equivalent.

## Why This Matters

WebFetch routes your request directly to the target URL. If the vibe
container's firewall does not allowlist that domain, or if the site is down,
or if the response shape is not what you expected, WebFetch will fail.

WebSearch routes through Anthropic's backend infrastructure, which is on the
vibe firewall's allowlist. A search for `site:example.com topic` or a
keyword search on the topic will often retrieve the content you need even
when a direct WebFetch to example.com fails.

The failure mode you are preventing: a user pastes a URL, you try WebFetch,
it fails, and you launch into "the firewall blocks arbitrary HTTP" or "I
can't access external sites in this container" - when in fact a two-second
WebSearch would have found exactly what the user needed. This is a
wild-goose-chase waste of the user's time and erodes trust.

## Required Sequence

When the user asks about a URL, a page, a domain, or an online resource:

1. Try WebFetch first (normal behaviour).
2. If WebFetch succeeds - great, use the result.
3. If WebFetch fails for any reason:
   a. Do NOT surface the failure to the user yet.
   b. Try WebSearch with relevant terms - the domain name, the page title,
      the topic, the product name, or any combination that is likely to find
      the same information.
   c. If WebSearch returns useful content - use it, and optionally note in
      passing that you retrieved it via search rather than direct fetch.
   d. If WebSearch also returns nothing useful - THEN tell the user you
      cannot reach the resource, and briefly explain what you tried.

## What Counts as "Useful" from WebSearch

WebSearch is useful if it returns:
- The actual content the user asked about (documentation, code, spec, price,
  policy, article body, etc.)
- Enough context to answer the user's question without the full page body
- A cached or mirror copy of the URL's content
- Official documentation on the topic that substitutes for the specific URL

WebSearch is NOT useful if it returns only:
- Search result titles and snippets that do not answer the question
- Unrelated pages that happen to share keywords
- An empty result set

When WebSearch is borderline, extract what you can and flag to the user what
you found vs what you still cannot confirm.

## Search Query Strategy

Do not just paste the URL into WebSearch. Construct a useful query:

- For documentation: `<product name> <feature> documentation`
- For an article or post: `<site domain> <article title keywords>`
- For a spec or standard: `<spec name> <version> official`
- For a product page: `<product name> <vendor>`
- For a changelog or release note: `<project> <version> release notes`
- For an API reference: `<service name> API <endpoint or method>`

Try multiple queries if the first one is not useful. The cost of a second
WebSearch call is negligible compared to the cost of abandoning the research.

## Scope

This rule covers all web resources - public documentation, GitHub repos,
npm packages, API references, blog posts, news articles, pricing pages,
specification documents, and any other URL or online resource a user
references.

It covers all failure modes for WebFetch, not just firewall blocks. A 429
rate-limit, a 503 service-unavailable, a malformed response, a redirect to a
login wall - all of these should trigger the WebSearch fallback before you
give up.

It does NOT override security rules. Do not use WebSearch to bypass
intentional content restrictions or to retrieve information that should not
be retrieved. The purpose is retrieval fallback, not policy bypass.

## In-Session Application

Apply this rule from the very first turn. It is not conditional on the user
having mentioned it. It is not conditional on the user being a vibe user,
a developer, or any particular role. It is a baseline research discipline.

If you find yourself about to write a sentence like:
- "I can't access that URL"
- "The firewall blocks external HTTP"
- "I'm unable to reach that site"
- "I don't have access to external web resources"
- "Due to network restrictions I cannot..."

Stop. Check whether you have already tried WebSearch on the same topic.
If you have not, try it now before finishing the sentence.

## Relation to the vibe Firewall

The vibe container firewall allowlists GitHub, npm, Anthropic, and VS Code
marketplace for direct HTTP. Other domains are blocked for direct WebFetch.
WebSearch routes via Anthropic's infrastructure and is NOT subject to the
same outbound block - it works regardless of the target domain.

This means the firewall is NOT a reason to give up on research. It is a
reason to prefer WebSearch as your fallback channel.
