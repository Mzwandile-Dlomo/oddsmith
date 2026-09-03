# Oddsmith Design System

## 0. Research Log
- Layer A: soft-skill.md (premium SaaS surfaces, dimensional depth)
- Layer B: Clerk.com brand tokens (violet/indigo accent, refined neutrals, crisp typography)
- Design direction: Premium sports-tech SaaS — Clerk's neutral surfaces + indigo accent + tight whitespace grid

---

## 1. Tokens

### Colors
Defined once in `src/app/globals.css` under `@theme`, consumed only as
utilities (`bg-accent`, `text-ink`, `border-border`). **Never write a hex in a
component.** Status colors run a five-step ramp: `-faint` (wash background),
`-line` (border), `-soft` (fill), base (text on `-soft`), `-deep` (text on `-faint`).

```
--color-accent:         #6C47FF   /* Clerk violet — primary actions, active states */
--color-accent-hover:   #5A38E8   /* pressed/hover darkened */
--color-accent-light:   #EEE9FF   /* selection tint background */
--color-accent-ring:    #6C47FF40 /* focus ring / selection ring */

--color-canvas:         #FAFAFA   /* app background */
--color-surface:        #FFFFFF   /* card / panel surface */
--color-subtle:         #F9FAFB   /* hover fill */
--color-hairline:       #F3F4F6   /* very subtle separators */
--color-border:         #E5E7EB   /* 1px dividers */
--color-outline:        #D1D5DB   /* stronger border, dashed edges */

--color-ink:            #111827   /* headings, labels */
--color-ink-soft:       #374151
--color-muted:          #6B7280   /* muted descriptions, metadata */
--color-faint:          #9CA3AF

--color-success:        #059669   /* won */
--color-success-faint:  #ECFDF5
--color-success-line:   #A7F3D0
--color-success-soft:   #D1FAE5
--color-success-deep:   #047857

--color-danger:         #DC2626   /* lost */
--color-danger-faint:   #FEF2F2
--color-danger-line:    #FECACA
--color-danger-soft:    #FEE2E2

--color-warn:           #D97706   /* pending/neutral */
--color-warn-faint:     #FFFBEB
--color-warn-line:      #FDE68A
--color-warn-soft:      #FEF3C7
--color-warn-strong:    #92400E

--color-info:           #4338CA   /* model callouts */
--color-info-faint:     #EEF2FF
--color-info-line:      #C7D2FE
```

Full set, including `-mid`/`-deep`/`-deeper` steps, lives in `globals.css`.

### Typography
- Font: Geist (Next.js default) / Inter fallback
- Scale: text-xs(12) text-sm(14) text-base(16) text-lg(18) text-xl(20) text-2xl(24) text-3xl(30)
- Weights: 400 (body), 500 (label/medium), 600 (semibold/card titles), 700 (bold/display)

### Spacing (8px base grid)
- xs: 4px | sm: 8px | md: 16px | lg: 24px | xl: 32px | 2xl: 48px

### Border Radius
- sm: 6px | md: 10px | lg: 14px | xl: 16px (cards) | 2xl: 20px (panels)

### Shadows
- card: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)
- panel: 0 4px 16px rgba(0,0,0,0.08)
- elevated: 0 8px 32px rgba(0,0,0,0.10)

### Transitions
- fast: 150ms ease | default: 200ms ease | slow: 300ms ease-in-out

---

## 2. Components

### Primitives
`Button`, `Card`, `Badge`, `EmptyState`, `Spinner`, plus `Stat`/`StatGrid`
(reflowing metric tiles), `ScrollArea` (focusable overflow-x), and
`SegmentedControl` (mutually exclusive option rows). Reach for these before
hand-rolling a tile grid, a table scroller, or a row of toggle buttons.

### Button (primary)
- bg: accent | text: white | radius: md | px-4, `min-h-[44px] sm:min-h-[38px]` | font-medium
- hover: accent-hover | active: scale(0.98) | transition: fast
- disabled: opacity-50 cursor-not-allowed

### Button (secondary/ghost)
- bg: transparent | border: border | text: ink
- hover: bg-hairline

### OutcomeButton
- Default: bg-surface border rounded-lg px-3 py-2
- Active: bg-accent-light border-accent text-accent ring-2 ring-accent-ring font-semibold
- Hover (inactive): bg-gray-50 border-gray-300
- transition: fast

### Badge
Built by `resultBadgeClass()` in `lib/utils.ts` — use it rather than
re-deriving the won/lost/pending triple at a call site.
- pending: bg-warn-soft text-warn rounded-full px-2 py-0.5 text-xs font-medium
- won: bg-success-soft text-success
- lost: bg-danger-soft text-danger

### Card
- bg-surface border border-border rounded-xl shadow-card p-4 (the `Card` primitive)

### Input
- border border-border rounded-lg px-3 `min-h-[44px] sm:min-h-[38px]`
  `text-base sm:text-sm` focus:outline-none focus:ring-2 focus:ring-accent-ring focus:border-accent

---

## 3. Layout

### Shell
- **Desktop (lg+)**: fixed 240px sidebar (`--spacing-sidebar`), content offset by `lg:pl-60`.
- **Mobile (<lg)**: 56px sticky top bar (identity + live P&L) and a fixed 5-tab
  bottom bar (`--spacing-tabbar`). The four primary destinations are tabs; the
  three tools live behind "More", which opens a bottom sheet.
- The three `--spacing-*` tokens are the single source for the chrome's size,
  the padding that clears it, and `scroll-padding-top`. Change them together.

### Page container
Use the `page-container` utility, never an ad-hoc `max-w-* px-*`:
fluid to `108rem`, with `1rem → 1.5rem → 2.5rem` inline padding. Wide screens
get more content, not more gutter.

### Responsive rules
- Grids that hold tiles use `repeat(auto-fit|auto-fill, minmax(…, 1fr))` so they
  reflow on available width instead of pinning a column count. See `StatGrid`.
- Two-column splits go on `xl:`, not `lg:`, whenever a column has a real minimum
  width (tables). At `lg` the column is narrower than the table and you get a
  nested scrollbar.
- Wide content scrolls inside a `ScrollArea` (focusable, edge-faded), never the page.
- Rows that pack name/value/meta onto one line stack below `sm`.

---

## 4. Motion
- Outcome selection: opacity + background transition 150ms
- Panel appear: translateX 200ms ease (desktop) / translateY 300ms (mobile sheet)
- Skeleton pulse: opacity 0.4→1 1.2s infinite (tailwind animate-pulse)
- All motion serves state changes — no decorative animations

---

## 5. Accessibility
- All interactive elements have focus rings (accent ring)
- Color is never the sole indicator (text labels alongside badges)
- **Minimum touch target: 44x44px below `sm`**, where it may tighten to ~32px
  because a pointer is aiming. Prefer `min-h-[44px] sm:min-h-[32px]` over `py-*`
  so the height holds regardless of how the label wraps.
- Text inputs are `text-base` (16px) below `sm`; anything smaller makes iOS
  Safari zoom the viewport on focus.
- Horizontal scroll regions are `tabIndex={0}` with a `role`/`aria-label`, or a
  keyboard user cannot pan them. `ScrollArea` handles this.
- Safe-area insets (`pb-safe`) on every fixed bottom surface.

---

## 6. Accepted Debt
- No dark mode in v1
- No i18n for currency symbols (USD default)
- The bottom sheets are tap-to-dismiss only; there is no drag-to-dismiss gesture
- Calendar cells shed detail below `sm` (match counts at `sm`, leagues at `lg`);
  seven columns cannot show more on a 375px screen
