# Radio completeness sweep — agent brief

_Working brief for the parallel sourcing agents. Not player-facing. The goal
is a full roster per market, so the in-cab dial reflects the whole city, not
just one flagship._

**Scope change, 2026-07-30 (owner):** commercial stations are no longer
excluded. The earlier sweeps deliberately built a non-commercial dial, and
they succeeded — but the result skews hard to news and classical (271 "news",
126 "classical", 7 "rock", no country and no sports), which is not what a
driver actually rides. Commercial country, classic rock, sports, and
news/talk are now in scope.

## What you are producing

For every city in your shard, enumerate **all real radio stations** and
return a structured record for each one that has a real, station-owned,
playable internet stream. You do research and hand back data. **You never
edit the catalog, never touch `src/`, never run the game.** You write exactly
one output file (path given in your task) and nothing else.

## Include / exclude

INCLUDE:
- **Commercial stations** — country, classic rock, top 40, sports, news/talk,
  Spanish-language, oldies. These are the formats the dial is thinnest on.
- NPR member / public-radio stations (news-talk, and separate classical,
  jazz, or news-only sisters — a market often has 2-3).
- Community radio (LPFM `-LP`, listener-run, e.g. WEVL Memphis, KEXP-style).
- College / university stations (student or NPR-affiliated campus stations).
- **HD subchannels (HD2 / HD3).** US FM stations broadcast digital
  subchannels carrying distinct formats — classical, jazz, AAA, and notably
  **BBC World Service on many HD3s** (e.g. WKNO Memphis HD2 classical, HD3
  BBC World Service). Each subchannel is its **own record**, same
  transmitter, different `stream_url` mount and `format`.

EXCLUDE:
- Any station with no real, station-owned playable stream.
- **Stored aggregator proxy URLs: no TuneIn, no Streema/Radio-Garden, no
  `radio.garden` listen links.** Find the station's OWN mount.
- **TuneIn entirely**, as a source as well as a URL. They have filed real
  DMCA takedowns asserting their API is partner-only. Do not query it.

## Discovery vs. storage — the rule that replaced the commercial ban

The aggregator rule above is about **what you store**, not what you consult.
The distinction matters now that commercial stations are in scope:

- **Fine:** consulting a directory at build time to find out that a station
  exists and where its stream lives.
- **Not fine:** storing that directory's proxy URL, or making the shipped
  game depend on the directory at runtime.

iHeart's API is usable under this rule *because it returns the broadcaster's
own mount* — Cumulus stations resolve to `playerservices.streamtheworld.com`,
Audacy to `live.amperwave.net/direct/...`, and so on. Harvest the metadata,
store the broadcaster's URL, and the shipped game never contacts iHeart.

**Audacy: reach their stations through iHeart's catalog, never through
`api.audacy.com`.** Their terms flatly prohibit accessing the service through
any other interface; iHeart's catalog already carries 262 Audacy stations
(at 128 kbps, better than iHeart's own 48 kbps), via a distribution deal
Audacy itself signed.

**Honor refusals.** A mount that answers with a "listen in our app"
announcement, a 403, or a User-Agent block is `supported: false` with an
honest note — the same treatment as the geo-blocked AFN mounts. Never spoof
a User-Agent or Referer to get past one. Send a descriptive agent
(`FreightFate/1.9`); Triton explicitly asks third-party players to identify
themselves.

## The stream URL — the hard part

- **Prefer the station's own "Listen Live" page.** Open the station website,
  find the Listen Live / Stream page, and pull the direct mount it plays
  (Icecast, StreamGuys, StreamTheWorld-resolved, or HLS `.m3u8`). The
  station-hosted URL beats an aggregator every time.
- **Owner tip:** when a StreamTheWorld mount is flaky or won't resolve, go to
  the station's own home/listen page and take the direct Icecast/StreamGuys/
  HLS mount from there instead. StreamTheWorld `playerservices...` redirect
  URLs rate-limit and give false deaths — prefer a direct SC/HLS mount.
- Acceptable hosts seen in this catalog: `*.streamguys1.com`,
  `*.streamguys.com`, `*.streamtheworld.com` (direct `:PORT/MOUNT_SC` form,
  not the `playerservices` redirect), `*.ice.infomaniak.ch`, Akamai HLS,
  generic Icecast `host:port/mount`, `.m3u8` HLS.
- **HTTP 200 ≠ playable.** You may `curl -sI` (or GET a couple seconds) to
  sanity-check the URL resolves and returns audio, but do not trust HTTP
  alone — I run the authoritative BASS playback gate on every URL you return.
  So: **never invent a URL. If you can't find a real one, omit the station.**
  It is far better to return 3 solid stations than 8 with guessed mounts.
- Record where you got the URL in the `evidence` field (the listen-live page
  or directory URL). No evidence → don't submit it.

## Call-sign rigor (FCC)

- Verify each call sign against the **FCC FM Query / LPFM Query**, not just
  Wikipedia. Wikipedia misses LPFM and translators.
- Suffix matters: a bare 4-letter call is often the AM/TV sister — the FM is
  `-FM`. LPFMs are `-LP`. Get the suffix right.
- **Translators** use the K/W + channel-number + two-letter form (e.g.
  `W234AB`, `K247AG`) — a 4-letter vanity call is NEVER a translator. If a
  network reaches a town only via a translator, use the translator's real
  call and a short range.

## Transmitter coordinates & honest range

- `lat`/`lon` = the real **FM transmitter** site (from FCC / Wikipedia), not
  the city hall. Round to 4 decimals.
- `range_miles` — this catalog's ranges are generous "catch it while you pass
  through the metro" values, not strict FM contour. Use:
  - Full-power NPR flagship (Class C / C0 / C1): **100-130**
  - Mid-power regional (Class C2 / C3 / B1): **60-90**
  - Small Class A: **35-55**
  - LPFM (`-LP`) / community: **20-30**
  - FM translator (`K/W###XX`): **15-22**
  - HD subchannel: same as its parent full-power station's range.
  Be honest — do not inflate a 100-watt LPFM to metro range.

## Output record schema (one object per station)

```json
{
  "id": "wkno-memphis",
  "call_sign": "WKNO",
  "name": "WKNO 91.1",
  "format": "news and classical",
  "city_slug": "memphis",
  "state": "TN",
  "stream_url": "https://<station-owned mount>",
  "stream_format": "mp3|aac|hls|icecast",
  "codec": "mp3|aac",
  "lat": 35.1174,
  "lon": -89.7462,
  "range_miles": 110,
  "kind": "npr|community|college|hd2|hd3",
  "evidence": "https://www.wkno.org/listen-live",
  "notes": "optional — HD3 = BBC World Service; geo-block risk; etc."
}
```

- `id`: kebab-case, unique, stable, `callsign-city` (HD subs:
  `wkno-hd2-memphis`). It becomes a player-save key forever — pick well.
  **Must not collide with any id in `existing.json`.**
- Omit `market`/`region` — the merge step fills those from `city_slug`.
- `supported` is decided by my BASS gate; you don't set it. Just flag
  `notes` with "geo-block risk" if the stream is a foreign CDN likely to
  403 US IPs (I'll verify).

## Dedup

- `existing.json` (path in your task) lists every id and call sign already in
  the catalog. **Do not resubmit a station already there.** If an existing
  entry is wrong (bad call sign, dead-looking stream), note it in the
  `existing_issues` list of your output rather than duplicating it.

## Honest darkness

If a city genuinely has **no** station with a real stream, say so — add its
slug to the `dark` list with a one-line reason. **Never invent a station to
un-dark a market.** Honest absence is required (a test even enforces
interior-Nevada staying dark).

Tag every record with its `station_type` as usual. Commercial records get
`station_type: "commercial"`, which is what the in-game filter keys on — a
player who turns commercial stations off must be left with exactly the
public/community/college dial the earlier sweeps built.

## Your output file

Write **only** this JSON (to the path in your task), nothing else:

```json
{
  "shard": <n>,
  "stations": [ <records...> ],
  "dark": [ {"city_slug": "...", "reason": "..."} ],
  "existing_issues": [ {"id": "...", "issue": "..."} ]
}
```

Then your final text reply is a one-line summary: `shard N: X stations, Y
dark, Z issues`. Do not paste the JSON in the reply — it's in the file.
