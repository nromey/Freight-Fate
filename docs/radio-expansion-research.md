# Radio expansion research — 2026-07-30

Commissioned: can we add TuneIn / iHeart / Audacy and more to the dial, and
can we reuse Mason Armstrong's FastPlay to do it?

Five research agents plus hands-on probing on this machine. Everything marked
**measured** was tested here, not read about. Nothing was written into the
repo; all working data is in the session scratchpad.

---

## The short version

**FastPlay can't be reused — but you don't need it.** It has no LICENSE file
at all, which is *more* restrictive than GPL, not less: default copyright,
all rights reserved. We may read it and reimplement the technique (endpoints
and protocol behaviour are facts, not expression), but we may not vendor a
line. Everything useful in it was independently re-verified against the live
services anyway, and permissively-licensed equivalents exist.

**The three services are all technically wide open — the constraint is
contractual, not technical.** No keys, no logins, no tokens. An account
unlocks *nothing*: storing credentials is off the table as unnecessary, not
as blocked. That disposes of the "salt logons" idea — there's nothing to log
into.

**But the best answer isn't any of the three.** The highest-value finding is
NOAA Weather Radio: 1,036 transmitters, public domain, and it fixes our dark
corridors better than iHeart does.

---

## 1. The recommendation, in priority order

### First: NOAA Weather Radio — do this one regardless of every other decision

**Measured.** `https://www.weather.gov/source/nwr/JS/ccl-data.js`, 754,496
bytes, no key. 1,036 transmitters, **1,035 with coordinates**, 1,015 NORMAL.
Each record carries callsign, site name, state, frequency, power, lat/lon,
and the full county list with FIPS/SAME codes.

Tested against our own route points:

| | dark points (0 stations) | thin points (<3) |
|---|---|---|
| today | 39 | 660 |
| **reachable by NWR** | **26 (67%)** | **551 (83%)** |
| reachable by iHeart | 10 (26%) | — |

**NOAA fixes our dark corridors two and a half times better than iHeart, and
it is unambiguously public domain.**

It gets better: `api.weather.gov` is keyless and public domain too, so the
broadcast can be **synthesized with our own TTS** from our baked weather
model — *"This is NOAA Weather Radio All Hazards station WXL69, Ely, Nevada,
broadcasting on 162 point 4 0 0 megahertz."* Every fact public domain. No
stream to health-check, no third-party bandwidth, works offline, never rots.

For a trucking sim this is thematically perfect — weather is the thing a
driver actually needs — and it's the lowest-effort, highest-payoff item in
the entire survey. It also sits exactly inside the standing rule about
amplifying real cues rather than inventing them: every word traces to a real
transmitter on a real frequency.

### Second: FCC as the catalog spine — and it upgrades what we already ship

**Measured.** Python's urllib gets 403; `curl` with an ordinary UA gets 200.
That was *our client*, not the FCC — worth remembering as a general trap.

```
https://transition.fcc.gov/fcc-bin/fmq?state=MT&list=4&size=9   # FM
https://transition.fcc.gov/fcc-bin/amq?state=MT&list=4&size=9   # AM
```

Full US harvest run here: **22,015 licensed FM call signs** (including
**8,384 FM translators**) and **4,217 AM**. Pipe-delimited, public domain,
deterministic, offline-bakeable — fits our data rules exactly. The FM Query
page confirms it's current LMS data, NAD83, not stale CDBS.

Three things this unlocks:

**(a) Honest range.** Every record carries **ERP and HAAT** — the two inputs
the real FM propagation curves need. `range_miles` is hand-assigned today
(median 60). We could compute each station's actual licensed contour instead
of guessing, **for the existing 741 stations too**, not just new ones.

**(b) The translator hunt, already done.** 8,384 translators are sitting in
the scratchpad now. The open roadmap item — query FCC for translators along
dark corridors, resolve to parent network, seat at the translator's dial
position — is the same harvest. One tool, two roadmap items. The named leads
(KQEI Sacramento, the Winnemucca/KUNR translator) are resolvable from data
already downloaded.

**(c) AM day/night propagation — free realism.** AM records carry *separate
day and night rows with different power*: **492 daytime-only stations** that
must sign off at sunset, and **72 Class A clear-channel stations** — KDKA
1020, KFI 640, KFAB 1110, KEX 1190, KFBK 1530 — the legendary night-drive
signals audible 700+ miles after dark. That is a real night-driving feature
straight out of public-domain data, and it is exactly the kind of physics
the dial currently fakes.

### Third: Wikidata — identity and websites, CC0

15,859 US stations, **14,474 with coordinates (91.3%)**, **94.4% with FCC
facility ID**, 12,455 with an official website. P1400 joins to FCC *exactly*
— no call-sign regex, no ambiguity — at 93.1%.

Use Wikidata, **not** Wikipedia: the "List of radio stations in X" articles
are CC BY-SA, with share-alike attaching. Wikidata is CC0.

### Fourth: Radio Browser — the stream layer, public domain

7,610 US stations, and the **only** general directory that can legally be
baked into a shipped game. Verbatim from the project: *"Data license: public
domain."* It's also what the entire blind-community toolchain runs on —
freeRadio, RadioDroid, Home Assistant, Kodi.

Three operational warnings, all measured:

- **`state` is unusable as a key** — 768 distinct free-text values for 50
  states (`"Los Angeles CA"`, `"Abilene KY"`, `"US"`). Use `iso_3166_2`,
  which is populated 3% of the time, or derive state from coordinates.
- **`lastcheckok` is nearly worthless** — 95% of US records were last checked
  over 60 days ago, and byte-gating 60 "OK" streams found only 34 playable.
  **~40% of "OK" stations are dead.** Our BASS gate isn't optional, it's
  load-bearing.
- **The mirror network has collapsed to one server** (`de1`; the others are
  NXDOMAIN). Bake, don't query live.

---

## 2. The three services you asked about

### iHeartRadio — technically wide open

**Measured.** `https://us.api.iheart.com/api/v2/content/liveStations?limit=1000&offset=N`
— no key, no token, no login, no device id. **3,650 stations**, 3,547 US.

It is a *distribution platform*, not just iHeart's own stations: Clear
Channel 937, Cumulus 365, **Audacy 246**, Alpha 170, Salem 76, Beasley 59.
And the `streams` field returns **the broadcaster's own direct URL**, not an
iHeart proxy:

| Provider | Stream host |
|---|---|
| Clear Channel | `stream.revma.ihrhls.com/zc####` |
| Audacy, Alpha | `live.amperwave.net/direct/<mount>` |
| Cumulus, Salem, Beasley | `playerservices.streamtheworld.com/api/livestream-redirect/<MOUNT>.aac` |
| Other (e.g. NHPR) | the station's own StreamGuys / Zeno mount |

**It plays: 16/16 through our own BASS backend.** First pass was 13/16; all
three failures were fixable and one was the false-death the roadmap already
predicted:

| Failure | Cause | Fix |
|---|---|---|
| `/pls/KRWKFMAAC.pls` | BASS can't open a `.pls`; contents are expiring numbered-edge URLs — the exact rot from commit 3a81da73 | rewrite to canonical `/api/livestream-redirect/<MOUNT>.aac` |
| `/playlist/audacy-…m3u` | `.m3u` wrapper; contents are session-bound ephemeral hosts | rewrite to `/direct/<mount>` |
| `WWKXFMAAC` | rate-limit false death | retry spaced |

Coverage: 2,536 terrestrial AM/FM, 97% playable, only 100 overlapping our
741 — **+2,436 net new**, landing hardest where we're thinnest (WV 3→24,
DC 3→28, NE 5→26, SD 5→37, AR 5→37).

### Audacy — the "locked" note was wrong, but it's the one to leave alone

Audacy has its **own public API** — `api.audacy.com/experience/v1/stations`,
2,279 stations, unauthenticated, **with latitude/longitude and
`phonetic_name`**. Their *app* is locked; their *stations* are not. The old
note came from their retired StreamTheWorld mounts, which now 404 — they
migrated to AmperWave.

**But Audacy has the clearest prohibition of the three**, one flat sentence:
*"Access the Services using any interface other than ours."* There is no
equivalent sentence in iHeart's terms. **Recommendation: leave Audacy
parked.** The conclusion in our notes holds; only the stated reason needs
correcting. And 262 Audacy stations arrive inside iHeart's catalog anyway,
at 128 kbps — better than iHeart's own 48 kbps revma.

### TuneIn — the one genuine "don't", with a real door instead

TuneIn **filed actual DMCA takedowns** in 2018 against a Kodi radio plugin
and 31 forks, asserting verbatim: *"The content shared on GitHub is TuneIn
API documentation only available to contracted partners."* The takedown was
about the *discovery layer*, not playback — which is precisely the line in
question. `developer.tunein.com` is login-gated; there is no self-serve path.

**The door that is open:** in November 2023 TuneIn built an official
accessibility integration with **HumanWare's Victor Reader Stream 3** — the
flagship blind-community player. They actively want accessibility
partnerships and have done this exact deal, in this exact community,
recently. An audio-first trucking sim for blind players is the same pitch.
**That's an email, not a scraper.** Worst case is no reply.

One thing to know and then set aside: a firmware repo commits a live TuneIn
OAuth partner ID and secret in the clear. **Do not reuse it.** It's someone
else's certified credential; using it would be credential misuse stacked on
top of the ToS problem.

---

## 3. FastPlay — what we can and can't take

**No LICENSE file exists.** Verified four ways (GitHub license API 404, all
five conventional filenames 404, full 73-blob tree, `"license": null`). The
README's "License" heading lists only *its own dependencies*.

That means **default copyright, all rights reserved — we may not vendor,
copy, or line-for-line translate any of it.** This is more restrictive than
GPL, which would at least grant a copy-and-modify right we could evaluate.

What we *can* do: read it and reimplement the technique. Endpoints, header
names, and "resolve a `.pls` before handing it to BASS" are facts.

Its architecture, for reference — three services, all anonymous, all inline
in one 288 KB `ui.cpp`: **RadioBrowser** (hardcoded `de1`, no geo params),
**TuneIn** (`opml.radiotime.com/Search.ashx`, no partnerId), **iHeart**
(v2 + v3 fallback; their v2 search `q` is silently ignored, so every search
falls through to v3). It uses **BASS, same as us**, with `basshls` and
`bass_aac`. **It bundles no station catalog** — nothing to seed from.

If Norm wants the code, the path is a polite issue asking Mason for an
explicit MIT/BSD grant. He licenses other repos (FastGH is MIT), so the
omission looks like oversight. Scope any request to the radio files only —
FastPlay links Rubber Band, which is GPL and would encumber a blanket grant.

**Take code from these instead**, all permissive:
- `mopidy-tunein` (Apache-2.0) — the best `.pls`/`.m3u`/`.asx` parsers found
  anywhere, ~80 lines. Its trick of using `stream=True` and only reading the
  body when `content-type != audio/mpeg` is worth stealing outright for our
  health check.
- `TigreGotico/tunein` (Apache-2.0, actively maintained — the repo moved
  from OpenJarbas, last push 2026-07-25)
- `m3u8` (MIT, zero deps on 3.12)

**Reject** `pyradios` (raises on geo params, and does blocking reverse-DNS in
its constructor — it can't even be constructed offline) and `streamscrobbler`
(Python 2 only).

---

## 4. What I found in our own code and catalog

### A real gap in the health check — decoys pass as live

Providers signal refusal by serving a **recorded voice announcement inside an
HTTP 200**. TuneIn has three with known byte sizes; other broadcasters serve
"listen in our app" messages the same way.

Our gate calls a stream alive if `stream.position` advances after 2 seconds.
**Measured: a decoy advances position too.** Our check cannot tell them
apart, and would bake a 35 KB voice clip into the catalog as a working
station.

**The discriminator is provider-agnostic and clean:**

| | Content-Length | ICY headers |
|---|---|---|
| live stream | absent | `icy-name`, `icy-metaint` present |
| decoy / finite file | set | absent |

This does double duty: it hardens the health check *and* implements the
"drop stations that refuse third-party players" policy that the legal review
recommends — automatically, without ever spoofing a User-Agent to get past a
refusal.

**Audit result: our catalog is clean.** All 713 real supported streams
probed — **zero decoys**, 664 live, 11 playlist wrappers (fine, BASSHLS
handles them).

### Two more false-death traps to encode

My own header probe produced 34 false deaths, which is itself the lesson:

- **31× TLS handshake failures** on Icecast servers that BASS plays fine.
- **3× `BadStatusLine: ICY 200 OK`** — SHOUTcast v1 servers reply `ICY 200 OK`
  instead of `HTTP/1.1 200 OK`, and Python's `http.client` chokes. BASS
  handles it natively.

So the header check is a **decoy detector, not a liveness gate**. Liveness
stays with BASS. Also flagged by the survey: never `HEAD`-probe Icecast (some
mounts 405 on HEAD and 200 on GET), and never Range-probe a live stream.

### Three genuinely dead stations

BASS-verified, then independently re-gated after a pause to rule out the
false-death trap:

- `kglt-bozeman` — `https://live.kgltradio.com/256` (connection refused)
- `wesu-middletown` — `http://radio.wesleyan.edu:8000/stream` (timeout)
- `knds-fargo` — `http://ice.romanport.com/knds` (404)

(`kera-dallas` looked dead to my probe but is **alive** — a TLS quirk in my
tool, not the station.)

### A compliance rule we already satisfy

Triton requires that live streams not be paused, and that mute behave as
stop. **We're already compliant by construction:** `play_radio_stream` never
pauses, and stop slides volume to `-1.0`, which makes BASS stop and autofree
the channel (`audio.py:963`). The socket genuinely closes. No work needed.

### Free pronunciation data

Both iHeart (`pronouncements`, 1,136 stations) and Audacy (`phonetic_name`)
ship **broadcaster-supplied spoken pronunciation** — e.g. WLTW = *"one oh six
point seven lite f. m."* For a screen-reader-first game that's hand-authored
TTS work for 700+ existing stations, free. Worth harvesting regardless of how
the commercial-station question is decided.

---

## 5. The decision that's actually yours

Everything above runs into one line in `docs/radio-completeness-sweep-brief.md`:

> **EXCLUDE:** Any commercial station (iHeart/Cumulus/Audacy pop, country,
> sports, etc.)

Two separate rules live in that brief, and **only one is in tension**:

- The *aggregator* rule ("no TuneIn/iHeartRadio proxy URLs — find the
  station's OWN mount") is **satisfied, not violated**. iHeart's API returns
  the broadcaster's own mount. Using it once, offline, as a finding aid and
  storing the station's own URL is what that rule asks for.
- The *commercial-station* exclusion is a **genuine scope decision, and it's
  the owner's.** Nothing here has decided it.

### Why it might be worth revisiting

Measured against our own world, adding iHeart barely moves darkness (39 → 29
dark points, and I'd distrust even that — checkpoints cluster near towns, so
the sample under-measures empty stretches). What it moves is **density**
(median 4 → 7 stations in range) and, above all, **format**.

Our dial's format words today:

> news 271, community 160, classical 126, college 96, variety 94, talk 87,
> public 79, freeform 75, alternative 49, jazz 46 … **rock 7**

Zero country. Zero top 40. Zero sports. The sweeps solved coverage honestly;
they left the dial sounding like a pledge drive. iHeart brings Country 398,
News & Talk 416, Sports 234, Oldies 234, Classic Rock 175 — for a *trucking*
sim, that's the formats a driver actually rides.

### The risk, stated straight

Zero enforcement history: a full clone of the `github/dmca` corpus (21,593
notices) returns **zero** hits for iheart, audacy, streamtheworld, triton, or
radio-browser. The TuneIn takedowns were about partner-confidential *docs*,
not stream access.

But both broadcasters have a clause this would breach, and the closest
analogue — hiQ v. LinkedIn — shows those clauses are enforceable when someone
bothers: scraping survived CFAA twice, then LinkedIn won on **breach of
contract**. The risk shape is contract, not copyright.

**iHeart and Audacy are not equivalent.** iHeart's restriction takes a
paragraph of construction to reach; Audacy's is one unambiguous sentence.

### A middle path

The 2,436 net-new iHeart stations are **not uniformly commercial** — the
catalog carries 47 NPR plus college, tribal, and community stations whose
rights-holders are the stations themselves, exactly like our current 741.
Using these directories purely as a **discovery layer for non-commercial
stations** stays inside existing policy and would still meaningfully fill
WV, NE, AR, SD and the other thin states.

### One thing to add regardless

**Publish a takedown path.** One line in the README plus a contact address:
any station operator who asks to be removed is removed in the next build, no
questions. It costs nothing, and it converts the question from "are we
allowed" into "we're a good-faith listener who honors the operator's wishes."
It's also the best mitigation if the game ships to UK/EU players, where the
*Warner v. TuneIn* precedent is closest to being on point.

---

## 6. Things to not spend time on

Dead, empty, paywalled, or forbidding our exact use in writing: Shoutcast
(docs gone, key by partnership only), `dir.xiph.org` (directory returns 23
bytes — empty), Live365 (401), Streema, myTuner (robots.txt blocks crawlers
by name), vTuner (B2B only), Onlineradiobox (`Disallow: /json/*`), radio.net
(no geo at all), PRX/PRSS (dead ends), RadioReference (every end user needs
their own paid subscription).

**Broadcastify is categorically out**, and this matters for the
trucker-scanner idea: their feed API is **$2,500/month, reviewed**, and the
docs say verbatim *"We are not licensing any new 'police scanner' style
applications, free or paid, hobby or commercial."* There's also a documented
AppleVis advisory about them ignoring accessibility reports from this very
community. WebSDR and KiwiSDR can't help either — their audio is a custom
binary WebSocket protocol BASS cannot open.

If we want scanner flavour, synthesized CB chatter from our own content,
geolocated by our world data, ships clean.

---

## 7. Caveats

- The dark-corridor figures sample baked leg checkpoints, which cluster near
  towns. That **under-measures genuinely empty stretches** — it's the least
  trustworthy number here, and it understates both NOAA's and iHeart's value.
- FCC and NOAA endpoints are undocumented CGI/JS assets, not versioned APIs.
  Snapshot them and re-pull at map-pack build time.
- The legal material is engineering-level risk assessment, not counsel.
  Where it says gray area, it means gray area.
- Not independently re-verified by me: the Broadcastify pricing quotes, the
  NPR terms, and the curated-provider terms.
- One agent could not retrieve TuneIn's consumer ToS (JavaScript-rendered).
  The 2018 DMCA notices are stronger evidence of their posture anyway.
