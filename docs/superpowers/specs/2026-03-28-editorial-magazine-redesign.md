# Editorial Magazine Redesign — spark.wedd.au

**Date**: 2026-03-28
**Status**: Approved
**Author**: Adrian + Claude
**Scope**: Full redesign of all pages — hero, nav, typography, feed, blog, thought permalink, dashboard, warm sections, charts, scroll animations, footer, chat widget.

---

## 1. Design Intent

spark.wedd.au serves two audiences: visitors meeting SPARK (a robot with an inner life) and technical visitors appreciating the craft behind it. The site should feel like a glossy editorial magazine about a thinking robot — not a developer dashboard, not a terminal.

**Warm = human** (Brain, FAQ sections). **Dark = machine** (everything else). This is an intentional design choice, not a leftover. The Racing section is removed from the public site (internal-only at picar.local:8420).

---

## 2. Design System Foundation

### 2.1 Typography

**Primary font**: Inter (Google Fonts) — `'Inter', system-ui, -apple-system, sans-serif`. Loaded at weights 300, 500, 600, 700, 800.

**Monospace font**: Courier Prime (Google Fonts) — `'Courier Prime', 'Courier New', monospace`. Used only for SPARK's voice (thought quotes, carousel text, blog post body) and technical elements (h3 labels, badges, code blocks).

**Playfair Display is removed entirely** from the site. One less font, one less voice.

**Type scale** (1.25 modular ratio):

| Token              | Value                           | Weight | Use                                |
|---------------------|---------------------------------|--------|------------------------------------|
| `--text-display`    | `clamp(2.5rem, 6vw, 3.5rem)`   | 800    | h1 only                           |
| `--text-title`      | `1.75rem`                       | 700    | h2 section headings               |
| `--text-subtitle`   | `1.25rem`                       | 600    | Lead text, card titles, featured quotes |
| `--text-body`       | `1rem` (16px)                   | 300    | Body copy                         |
| `--text-small`      | `0.875rem`                      | 500    | Metadata, nav links, captions     |
| `--text-xs`         | `0.75rem`                       | 500    | Badges, labels                    |

**Font assignments**:
- **Headings (h1, h2)**: Inter. h1: weight 800, `letter-spacing: -0.04em`, `line-height: 1.05`. h2: weight 700, `letter-spacing: -0.025em`.
- **Body copy**: Inter 300, `line-height: 1.7`. Light weight reads elegant on dark backgrounds.
- **Nav, metadata**: Inter 500, `letter-spacing: 0.01em`.
- **SPARK's voice** (thought quotes, carousel, blog body): Courier Prime italic.
- **Section labels (h3)**: Courier Prime regular, uppercase, `letter-spacing: 0.08em`.
- **Numeric displays**: `font-variant-numeric: tabular-nums` on timestamps, metrics, percentages.

### 2.2 Spacing

Remove `min-height: 100vh` from all sections. Sections use `padding: 4rem 2rem` on desktop, `padding: 2.5rem 1rem` on mobile. Let content determine height.

### 2.3 Containers

| Context         | Max-width |
|-----------------|-----------|
| Hero            | `1100px`  |
| Homepage body   | `900px`   |
| Feed/blog/thought | `680px` |

### 2.4 Border radii

- `--radius-sm`: `8px` (badges, inputs)
- `--radius`: `12px` (cards)
- `--radius-lg`: `16px` (hero image)

### 2.5 Motion

All entrance animations gated behind `@media (prefers-reduced-motion: no-preference)`.

- **Scroll entrance**: `IntersectionObserver` with `threshold: 0.1`, `rootMargin: '0px 0px -40px 0px'`. Animation: `opacity: 0 → 1`, `translateY(16px) → 0`, `0.4s cubic-bezier(0.25, 0.1, 0.25, 1)`. One-shot (no re-trigger on scroll back).
- **Card hover**: `translateY(-2px)`, `transition: all 0.25s cubic-bezier(0.25, 0.1, 0.25, 1)`.
- **Mood pulse**: Existing animation retained (slow/mid/fast by arousal).

### 2.6 Polish details

- Mood badges: `backdrop-filter: blur(8px)` on surface tints for frosted-glass effect.
- Hero photo: `filter: contrast(1.05) brightness(1.02)` to pop on dark background.
- Thought quotes: `text-indent: -0.4em` for hanging punctuation on opening quote marks.

---

## 3. Hero Section

### 3.1 Layout

Two-column on desktop (text 60% left, photo 40% right), stacked on mobile (text above, photo below). Hero container: `max-width: 1100px`.

### 3.2 Left column

- **h1**: "SPARK" — Inter 800, `--text-display`, copper (`--dark-accent`), subtle `text-shadow: 0 0 60px var(--dark-glow)`.
- **Live mood sentence**: Inter 600, `--text-subtitle`, off-white (`--dark-text`). Populated by JS from `/api/v1/public/status` — constructs sentence from `mood` field and `last_thought` snippet: *"Feeling contemplative about the afternoon quiet."* Offline fallback: *"A robot with an inner life."*
- **Credit line**: Inter 500, `--text-small`, muted (`--dark-muted`). "Built by Adrian and Obi together."
- **CTA row**: Two ghost buttons — "Explore the feed →" (`/feed/`) and "Live dashboard ↓" (`#live`). Copper border + text, hover fills copper background with dark text.

### 3.3 Right column

- **Photo**: `border-radius: var(--radius-lg)`, mood-colored `box-shadow: 0 0 60px var(--spark-glow)`. Glow shifts with SPARK's current mood via `--spark-accent`. Offline: copper glow.
- **Status line**: Below photo — status dot + "Online" / "Sleeping" in `--text-xs` muted.

### 3.4 Thought carousel (below two-column hero)

Moves below the hero columns, centered at `900px` container width. Pull-quote style: no card background, large Courier Prime italic text, mood badge, timestamp. Single thought at a time, crossfading every 8 seconds. No navigation dots.

### 3.5 Mobile (below 700px)

Single column. Photo shrinks to `max-width: 280px`, centered. CTA buttons stack vertically. Mood sentence stays above photo.

### 3.6 Offline degradation

If API unreachable: mood sentence shows static fallback, photo glow defaults to copper, carousel shows cached thoughts from localStorage.

---

## 4. Navigation

### 4.1 Structure

5 items: Home (`/`), Live (`/#live`), Feed (`/feed/`), Blog (`/blog/`), GitHub (external).

Logo: "SPARK" in Courier Prime + status dot. Height: `56px`.

### 4.2 Styling

Inter 500, `--text-small`. Active link: copper color. Hover: `--dark-text`. GitHub link: opacity treatment (existing pattern).

### 4.3 Mobile (below 700px)

Hamburger → slide-down panel with backdrop overlay (`rgba(0,0,0,0.5)`). 5 links, well-spaced. Focus-trapped while open.

---

## 5. Feed Page (`/feed/`)

### 5.1 Header

- **h1**: "Thought Feed" — Inter 700, `--text-title`, copper.
- **Summary line**: Mood distribution computed client-side from the fetched feed data (count moods across all posts in the current dataset) — *"42 thoughts this week — 12 curious, 9 contemplative, 8 peaceful, ..."* in Inter 500, `--text-small`, muted. Offline fallback: *"A stream of SPARK's inner life — thoughts that crossed the salience threshold."*

### 5.2 Card design — two tiers

**Standard card** (salience < 0.85):
- Background: `--dark-surface`. Border: `1px solid var(--dark-border)`. Radius: `var(--radius)`.
- Mood-colored top border: `border-top: 2px solid var(--mood-*)`.
- Padding: `1.75rem 2rem`.
- Quote: Courier Prime italic, `--text-body`, `--dark-text`.
- Spacer: `0.75rem`.
- Metadata row: mood badge (left), timestamp (right). Inter 500, `--text-small`.
- Hover: `translateY(-2px)`, faint glow.

**Featured card** (salience >= 0.85):
- `border-top: 3px solid var(--mood-*)`.
- Quote: Courier Prime italic, `--text-subtitle` (1.25rem).
- Padding: `2rem 2.25rem`.
- Otherwise identical structure.

### 5.3 Date headers

Full-width. Courier Prime regular, `--text-xs`, uppercase, `letter-spacing: 0.08em`. A thin copper rule stretches after the text via `::after` pseudo-element — `"25 March 2026 ————————"` effect.

### 5.4 Pagination

"Load more" ghost button (unchanged). Below: *"Showing 20 of 147 thoughts"* in `--text-xs` muted.

### 5.5 Scroll entrance

Cards fade in with staggered delay: `50ms * index` per batch, capped at `250ms`.

---

## 6. Blog Page (`/blog/`)

### 6.1 Header

- **h1**: "SPARK's Blog" — Inter 700, `--text-title`, copper.
- **Subtitle**: *"Reflections, essays, and the arc of a thinking life."* — Inter 500, `--text-small`, muted.

### 6.2 Card hierarchy — three tiers

**Essay cards** (type: essay, monthly, yearly):
- Title: Inter 600, `--text-subtitle`, copper.
- Excerpt: Courier Prime italic, `--text-body`, 2 lines max.
- `border-top: 3px solid var(--mood-*)`.
- Padding: `2.25rem`.
- Meta: type badge + mood badge + timestamp.

**Weekly cards** (type: weekly):
- Title: Inter 600, `--text-body`, off-white.
- Excerpt: Courier Prime italic, `--text-small`, 1 line.
- `border-top: 2px solid var(--mood-*)`.
- Standard padding.

**Daily cards** (type: daily):
- Title as link, no separate excerpt.
- Type badge + timestamp inline. No mood badge.
- `border-top: 1px solid var(--dark-border)` (muted, not mood-colored).
- Reduced padding: `1rem 1.5rem`.

### 6.3 Single post view

The article breaks OUT of the card. No card background, no border.

- **Back link**: "← Blog" — Inter 500, copper, `--text-small`.
- **Title**: Inter 700, `clamp(1.5rem, 4vw, 2.25rem)`, copper.
- **Meta row**: type badge + mood badge + timestamp.
- **Divider**: `1px solid var(--dark-border)`.
- **Body**: Courier Prime, `1rem`, `line-height: 1.8`, max-width `680px`. Paragraphs: `margin-bottom: 1.25rem`. This is SPARK's voice — monospace is intentional, with generous leading for readability.

### 6.4 Date grouping

Same as feed: uppercase Courier Prime date headers with copper rule.

---

## 7. Thought Permalink (`/thought/?ts=`)

### 7.1 Layout

No card container. The thought floats as a centrepiece.

- **Breadcrumb**: "SPARK / Feed / This thought" — Inter 500, `--text-small`, muted. Copper links.
- **Thought text**: Courier Prime italic, `clamp(1.25rem, 3vw, 1.75rem)`, centered, max-width `600px`. Vertical padding: `4rem 0`.
- **Mood rule**: `2px solid var(--mood-*)`, `max-width: 120px`, centered.
- **Meta**: Mood badge + timestamp, centered.
- **Prev/next**: "← Earlier thought" and "Later thought →" as copper ghost links, flex-spaced. Determined from the feed data array (the same data source used to render the thought) — no separate API call.

### 7.2 Mood wash

Subtle mood-colored radial gradient at top of page: `radial-gradient(ellipse at 50% 0%, var(--mood-*-surface) 0%, transparent 60%)`. A hint of mood color, not a full background change.

### 7.3 Share row

Below prev/next: "Share on Bluesky" link + "Copy link" button. Inter 500, `--text-xs`, muted.

### 7.4 Data source

Thought data resolves from the static snapshot on Cloudflare Pages first, enriched by the live Pi API when available. Thoughts are served from pages, not the Pi.

### 7.5 Not-found state

*"This thought has drifted off the feed."* + link to `/feed/`.

---

## 8. Dashboard (Live Section)

### 8.1 Presence band (always visible)

3-column grid:

- **Mood card** (left): Pulse circle (retained). Below: *"contemplative for 23 min"* — Inter 500, `--text-small`, muted. Sparklines move to World band.
- **State card** (center): Obi mode, presence, ambient, distance. Labels: Inter 500, `--text-xs`. Values: Inter 600, `--text-body`. Proximity bar: 10px height, mood-colored fill.
- **Speech card** (right): Last spoken, persona. Same typographic cleanup.

### 8.2 World band (collapsed)

Weather, sparklines, detection list. Sparkline canvases: 32px height (up from 20px).

### 8.3 Machine band (collapsed)

Grouped metric tiles:
- Row 1: CPU+Temp (one tile), RAM+Disk (one tile), Battery (one tile).
- Each tile: primary value large (`--text-subtitle`), secondary below (`--text-xs`). Inline sparkline accent.
- Row 2: Services strip (unchanged).

### 8.4 Race widget

Removed from public site. Stays on local dashboard (`picar.local:8420`).

---

## 9. Charts & Sparklines

### 9.1 Sparklines (mood, sonar, vitals)

- Height: 32px desktop, 28px mobile.
- Style: single 1.5px stroke in `--spark-accent`. No fill, no axes, no labels.
- Terminal dot: 4px circle at the line's end — anchors "now."
- Background: transparent.

### 9.2 Audio visualizer (speech card)

- Vertical bars: 3px width, 1px gap, `lineCap: 'round'`. Height: 32px.
- Color: `--spark-accent` at 60% opacity. Decays to 2px baseline when silent.

### 9.3 Dashboard metric bars

- Height: 8px, `border-radius: 4px`.
- Fill: `--spark-accent` (normal). Amber `#f59e0b` above 80%. Red `#ef4444` above 95%.
- Battery inverted: red below 20%, amber below 30%.

### 9.4 Services strip

Unchanged — colored dots are already effective.

---

## 10. Warm Sections (Brain, FAQ)

### 10.1 Transition

The dark→warm boundary gets a smooth `80px` gradient fade: `linear-gradient(to bottom, var(--dark-bg), var(--warm-bg) 80px)` on a pseudo-element. Intentional, not abrupt.

### 10.2 Warm card refresh

`.warm-card` retains white bg and soft shadow. Updates:
- Headings switch to Inter (matching the site-wide type system).
- `border-radius: var(--radius)` (12px).
- Hover lift preserved.

### 10.3 Warm headings

h2: Inter 700, `--warm-text`. No more Playfair Display.

### 10.4 Racing section

Removed from public homepage. Technical details live in the repo README.

---

## 11. Footer

### 11.1 Structure

Two-column link grid:

**Site**: Home, Live, How It Works, Brain, FAQ, Docs, Roadmap, Feed, Blog.
**External**: Bluesky, GitHub.

### 11.2 Styling

Inter 500, `--text-small`. Links in copper, hover underline. Thin `1px` top border. `padding-top: 4rem`. Generous link spacing.

Credit line: "SPARK — built by Adrian and Obi together." — Inter 300, `--text-small`, muted.

---

## 12. Chat Widget

Update `chat.css` fallback vars from `--warm-accent` to `--dark-accent`. Chat panel interior: `--dark-surface` background.

---

## 13. Offline Banner

`.feed-offline-banner` class (already implemented in feed.css). All three JS files (feed.js, blog.js, thought.js) use the class instead of inline styles.

---

## 14. Files Changed

### CSS
- `site/css/base.css` — type scale tokens, Inter font stack, remove `min-height: 100vh`, update body font
- `site/css/dark.css` — h1/h2 to Inter, carousel dark overrides, dashboard grouped metrics
- `site/css/warm.css` — replace Playfair with Inter, warm transition gradient, remove racing styles
- `site/css/feed.css` — two-tier feed cards, three-tier blog cards, date headers, thought permalink, article layout
- `site/css/colors.css` — unchanged (mood palette already correct)
- `site/css/chat.css` — swap warm fallbacks to dark

### HTML
- `site/index.html` — hero restructure, nav to 5 items, remove #racing section, footer link grid, add Inter font import
- `site/feed/index.html` — update font import (Inter replaces Playfair), add mood summary container
- `site/blog/index.html` — update font import
- `site/thought/index.html` — update font import, restructure for centrepiece layout, add prev/next + share

### JS
- `site/js/dashboard.js` — live mood sentence in hero, mood duration display, grouped metric rendering
- `site/js/live.js` — mood summary stats calculation for feed header
- `site/js/feed.js` — salience-based card tier selection, staggered scroll animation, mood distribution summary, count display
- `site/js/blog.js` — three-tier card rendering, article-style single post
- `site/js/thought.js` — prev/next navigation, share row, mood wash background
- `site/js/charts.js` — line sparklines, terminal dot, threshold-colored bars
- `site/js/nav.js` — focus trap on mobile, backdrop overlay
- New: `site/js/scroll-animate.js` — IntersectionObserver entrance animations

### Assets
- `site/img/spark-hero.jpg` — hero photo of SPARK (provided by Adrian)

### Removed
- Playfair Display font import (all HTML files)
- `#racing` section and nav link (index.html)
- Race widget from public dashboard (dashboard.js, live.js)
