# Omareel 0.9.3 positioning

Draft for the Studio release. Keep it on `feat/studio-mode` until the release
gates in [the test plan](0.9.3-testing.md) are met.
See the [search and discovery plan](search-discovery.md) for the name-overlap
finding, search-facing copy, distribution and measurement.

## The promise

**Record a walkthrough. Share a link. Add a little polish when you want it.**

Omareel is for people building and explaining things on Omarchy: a feature
walkthrough, a tutorial, a bug fix, or an update for a teammate. Start from the
bar, record your screen and voice, then give the video a finished look in Studio.
Share an MP4 or a link from storage you control.

Lead with the complete recording and sharing workflow: screen, camera, voice,
Stop, saved video and a link. Show the actual recorder and saved-video controls
first. Studio adds optional finishing for demos and tutorials. Local files and
independent hosting apply to both workflows. “Loom-style” is a useful familiar
reference, as long as the optional Studio capabilities are also clear.
Avoid letting a generic styled sample replace the product's own interface or
implying that every recording needs editing before it can be shared.

## Copy to reuse

**Short description**

Record your screen, camera and voice on Omarchy, then save the video or share a
link from your own storage. Optional Studio finishing adds click zooms,
backgrounds and frames when you want a more polished demo.

**A little more room**

Open Omareel from your bar, choose your screen, camera and microphone, and start
explaining. Stop to save the video, give it a title, and share a link from storage
you control. For a demo that needs a finished look, Studio adds click zooms,
backgrounds and frames. It keeps your original and copies your audio unchanged.
A quick update can go straight from recording to sharing.

**Hosting copy**

Your recordings don't need a new home just because you made a video. Keep them
locally, use your existing bucket, or host them on your own S3-compatible server.
Omareel can upload the video, thumbnail, and a simple player page. You choose
what to share and where it lives. No Omareel account is required.

Say “your own storage” for the broad option, and “self-hosted S3-compatible
storage” when someone actually runs the server. An R2 bucket is user-controlled
cloud storage, not a server the user hosts. A custom domain requires the user's
DNS/TLS/storage configuration. Provider costs still apply.

## Competitive context

Official homepages reviewed on 2026-09-08. These are advertised capabilities,
not hands-on product benchmarks.

| Product | What its site emphasizes | What that means for Omareel's message |
| --- | --- | --- |
| [Screen Studio](https://screen.studio/) | Polished macOS recordings, automatic/manual zoom and animation | Lead with the finished demo, then show actual Studio output. |
| [Tella](https://www.tella.com/) | Recording, editing and sharing, dynamic layouts and transcript editing | Keep our simple finishing flow clear; don't imply a full editing suite. |
| [Screenix](https://screenix.studio/) | Linux recording, click zoom, camera layout, local files and own-storage sharing | Linux and own storage alone aren't unique. Show the specific Omarchy bar integration and tested Quattro workflow. |

The useful distinction is the combination: an Omarchy plugin, a small Studio
finishing step, and files/sharing under the user's control. Hadi's Screenix
installation problem is an individual experience, not evidence that the product
fails generally. Don't use it as a public comparison claim.

## Keep the promise specific

We can show click-triggered zoom, three looks, frame/background/spacing choices,
canvas ratios, camera capture, voice cleanup, untouched original files, and
optional storage-backed sharing. Use screenshots from the actual UI and exports.

Don't promise feature parity with the competitors, every Arch desktop, automatic
support for every future Omarchy version, cursor smoothing, transcript editing,
captions, a multi-clip timeline, hosted team features, or a camera that stays
fixed during every zoom. They aren't established features of this build.

For compatibility, say “built for Omarchy Quattro (4.0) and later,” alongside
the tested versions and remaining device checks. For screenshots, disclose demo
content and keep customer recordings, personal paths, credentials, and fabricated
usage statistics out of the assets.
