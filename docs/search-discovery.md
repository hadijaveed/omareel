# Omareel: search and discovery plan

Prepared 2026-09-08 for `hadijaveed/omareel`. This is a launch plan, not a claim
of improved rankings. Studio copy remains on the 0.9.3 development branch until
[its release gates](0.9.3-testing.md) pass.

## What the audit found

- GitHub's public About still says “Loom-style screen recording”; its topics are
  empty, homepage is unset, and GitHub Pages is not enabled. Those are observed
  repository settings, not proof that search engines cannot index the repository.
- A small search sample found Hadi's [Mac-to-Omarchy article](https://www.hadijaveed.me/2026/09/06/leaving-mac-after-12-years/)
  discussing the plugin. It did not reliably surface our repository/listing.
  Search results vary; this is not a ranking report or proof of non-indexing.
- [omacom/omareel](https://github.com/omacom/omareel) also describes an Omarchy
  screen recorder. GitHub reports it as a separate repository, not a fork.
  Whether the projects have any relationship still needs Hadi's clarification.
  The name overlap can confuse users and search engines; this is an inference,
  not a trademark conclusion. Keep `hadijaveed/omareel`, Hadi Javeed, and plugin
  ID `hadijaveed.omareel` consistent. Resolve the public identity before choosing
  a domain or doing a broad launch. Don't rename the package or break old links
  as an incidental SEO change.
- No search analytics, keyword-volume data, verified product-site property, or
  installation conversion data was available in this audit. We have no basis
  for promising a position, volume, or traffic increase.

## The work prepared on this branch

- README title says what the product is, while the headline keeps the human
  promise: **Polished product demos, made on Omarchy.**
- Opening text identifies the author and exact project, platform and category.
- Visible questions answer Linux compatibility, click zoom, alternatives,
  self-hosting, price/account requirements, originals/audio, and installation.
- Existing screenshots have descriptive filenames, alt text and provenance.
- Launcher aliases include `studio`, `screencast`, `screen-recorder`, and `demo`.
  These help Omarchy's local discovery; they are not Google ranking metadata.
- [Search metadata](search-metadata.json) has exact draft titles, descriptions
  and GitHub topics, separated into current-release and Studio-release copy.

No Studio publishing, domain registration, repository metadata mutation,
Search Console verification, or public website deployment was performed here.

## Priorities in order

### 1. Establish one recognizable home

First confirm how the other Omareel project relates to this one. Then choose a
stable public product URL. A dedicated page on Hadi's existing site is a simple
starting option, because that site already has an indexed article mentioning
this plugin. A new domain is optional, not an SEO prerequisite.

The product page should show the app, platform, actual demo, install link,
release status, author/repository, and hosting choices. Put the essential text
in crawlable HTML. Link the homepage from the GitHub About field, marketplace
homepage field at the next approved update, and Hadi's existing article.
Use the same identity and URL in release notes. Avoid parallel landing pages
that all try to be the main product page.

### 2. Make the GitHub and marketplace listings useful

The draft current-release description in `search-metadata.json` is accurate for
0.9.2. The Studio description is for 0.9.3 after testing/approval. Add the relevant
GitHub topics once the identity is settled. GitHub documents topics as a way to
help people discover related repositories; they don't guarantee web rankings.
[GitHub topic guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics).

At the approved Studio launch, update the About description, manifest/listing,
README and website together. Use one genuine product screenshot for social
previews; don't let the fictional demo app's name be mistaken for Omareel.
Marketplace markup is controlled by its maintainer: request improvements there
only if inspection finds a concrete issue. Adding robots.txt to this GitHub
source repository will not configure github.com's crawling behavior.

### 3. Answer a few real searches well

These are qualitative intent hypotheses based on the product and sampled
searches, not measured keyword volumes. Start narrow and validate in Search
Console once the site is live.

| Priority | Search intent | Useful content to publish after the matching feature is ready |
| --- | --- | --- |
| First | Omareel by Hadi / Omarchy screen recorder | Product homepage, exact repository identity, quick install and a working demo |
| First | Record screen and webcam on Omarchy | A tested 30-second tutorial with camera setup and the actual Stop controls |
| First | Screen recorder with click zoom on Omarchy | Studio guide and a short before/after motion example, including limitations |
| Next | Self-host screen recordings / share videos from your own storage | Walkthrough of one tested S3-compatible setup and a working player link |
| Next | Screen Studio alternative for Omarchy | Dated, sourced comparison explaining the supported subset and platform limits |
| Later | Linux screen recorder with automatic zoom | Broader article that clearly states the Omarchy requirement; don't imply all Linux desktops work |

Keep one substantial page per distinct task. Expand existing guides before
creating overlapping pages for every spelling of a keyword. Explain the result,
show the steps, then disclose any limits relevant to the reader's choice.

### 4. Make the public site technically easy to understand

At website implementation, use the title and description drafts as a starting
point. Give each page a descriptive title, one clear main heading, visible
answer text, and links to installation, compatibility and relevant guides.
Google may rewrite title links or snippets; metadata is an input, not a display
guarantee. [Title guidance](https://developers.google.com/search/docs/appearance/title-link),
[snippet guidance](https://developers.google.com/search/docs/appearance/snippet).

Validate public pages return 200, are reachable without login, and have an
absolute canonical pointing at the final production URL. Keep canonical URLs,
internal links and sitemap entries consistent. Allow intended crawling through
hosting/CDN settings. Use a sitemap for actual published pages, without staging
URLs. Check mobile layout, image dimensions/compression, descriptive alt text,
keyboard use and loading speed. No placeholder domain or empty canonical should
be emitted while the domain is undecided.

Add Open Graph/social-card title, description and a clear Omareel image for link
previews. Those tags improve presentation, not a guaranteed search ranking boost.
If adding structured data, describe the software truthfully and match the
visible content; no invented ratings, reviews or unsupported features.

A short launch demo should have a descriptive title, thumbnail and transcript
on a useful public page. Add video metadata only for a real published video with
accurate URLs and dates; don't invent a VideoObject for screenshots.
[Google video guidance](https://developers.google.com/search/docs/appearance/video).

The generated recording player currently uses `noindex`. Keep that behavior:
this SEO work is for product documentation and deliberately public demos, not
for indexing everyone's recordings. `noindex` is not authentication; access
controls still belong to the storage owner.

### 5. Earn discovery through useful examples

After release, publish a working Omarchy tutorial and a short product demo with
captions/transcript. Add a relevant link from the existing Mac-to-Omarchy story.
Share where Omarchy users already ask about recording and zoom, following each
community's rules and explaining that you built the tool. A specific solution,
real sample and honest limitations are more useful than repeated launch pitches.

Prepare comparison pages only with dated official sources and actual checks.
The competitor research in [positioning.md](positioning.md) is an input, not
proof of hands-on parity. Avoid bought links, mass directory submissions,
fabricated testimonials, keyword stuffing and generic AI-generated articles.

## AI-assisted search

Google says the same SEO foundations apply to AI Overviews and AI Mode. No
special AI file or schema is required. Prioritize readable facts, accessible
pages, useful images/video, and markup that matches the visible text. Eligibility
does not guarantee inclusion. [Google's AI search guidance](https://developers.google.com/search/docs/appearance/ai-features).

Other answer engines have their own discovery and crawler policies; verify
those individually if they become a channel we measure. Don't claim that a
single file or FAQ guarantees recommendations by ChatGPT, Perplexity, or Google.

## Measurement and release order

1. **Before launch:** settle identity and product URL; retain the current public
   release claims. Finish 0.9.2 approval and the multiple-laptop Studio tests.
2. **At the approved 0.9.3 launch:** publish the product page, guide, real demo,
   release and listing updates. Verify the site in Search Console, submit its
   sitemap and inspect the product URL. This requires control of the chosen site
   or DNS; no credentials or verification tokens should be committed here.
3. **Weekly for the first month:** check indexing, branded versus unbranded
   impressions, clicks, CTR and relevant queries by page. Review whether people
   arrive through the intended plugin/repository rather than the other project.
4. **After enough data:** improve pages that receive relevant impressions but
   few clicks, and answer repeated installation questions. Compare equal date
   windows and account for the launch spike and small sample sizes.

Track repository/install-link clicks separately from successful installations.
Stars and link clicks aren't proof that recording worked. Use voluntarily
reported successful test takes for activation feedback; don't add product
telemetry as an incidental SEO task. Use GitHub traffic/referrers where available
and Search Console on the site we control. AI-feature traffic is included in
Google's overall Web reporting; don't invent a separate measured AI lift.
[Search Console setup](https://developers.google.com/search/docs/monitor-debug/search-console-start).

Owners: Hadi settles identity/domain and approves publishing; development prepares
and validates assets; marketplace maintainers approve the exact plugin update.
Search Console and actual usage determine what we improve next. Rankings and
indexing are outcomes to measure, not promises to put in the README.
