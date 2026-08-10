# Oddsmith Design System

## 0. Research Log
- Layer A: soft-skill.md (premium SaaS surfaces, dimensional depth)
- Layer B: Clerk.com brand tokens (violet/indigo accent, refined neutrals, crisp typography)
- Design direction: Premium sports-tech SaaS — Clerk's neutral surfaces + indigo accent + tight whitespace grid

---

## 1. Tokens

### Colors
```
--color-accent:         #6C47FF   /* Clerk violet — primary actions, active states */
--color-accent-hover:   #5A38E8   /* pressed/hover darkened */
--color-accent-light:   #EEE9FF   /* selection tint background */
--color-accent-ring:    #6C47FF40 /* focus ring / selection ring */

--color-bg:             #FAFAFA   /* app background */
--color-surface:        #FFFFFF   /* card / panel surface */
--color-border:         #E5E7EB   /* 1px dividers */
--color-border-light:   #F3F4F6   /* very subtle separators */

--color-text-primary:   #111827   /* headings, labels */
--color-text-secondary: #6B7280   /* muted descriptions, metadata */
--color-text-disabled:  #9CA3AF

--color-success:        #059669   /* won */
--color-success-bg:     #D1FAE5
--color-error:          #DC2626   /* lost */
--color-error-bg:       #FEE2E2
--color-warning:        #D97706   /* pending/neutral */
--color-warning-bg:     #FEF3C7
```

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

### Button (primary)
- bg: accent | text: white | radius: md | px-4 py-2 | font-medium
- hover: accent-hover | active: scale(0.98) | transition: fast
- disabled: opacity-50 cursor-not-allowed

### Button (secondary/ghost)
- bg: transparent | border: border | text: text-primary
- hover: bg-border-light

### OutcomeButton
- Default: bg-white border rounded-lg px-3 py-2
- Active: bg-accent-light border-accent text-accent ring-2 ring-accent-ring font-semibold
- Hover (inactive): bg-gray-50 border-gray-300
- transition: fast

### Badge
- pending: bg-warning-bg text-warning rounded-full px-2 py-0.5 text-xs font-medium
- won: bg-success-bg text-success
- lost: bg-error-bg text-error

### Card
- bg-surface border border-border rounded-xl shadow-card p-4

### Input
- border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-ring focus:border-accent

---

## 3. Layout
- App shell: fixed top nav (64px) + two-pane content (fixtures list left + slip panel right, fixed 320px)
- Content area: max-w-7xl mx-auto px-6
- Fixture grid: vertical stack (lg:grid-cols responsive optional)
- Slip panel: fixed right side on desktop, slide-up sheet on mobile

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
- Minimum touch target: 44x44px

---

## 6. Accepted Debt
- No dark mode in v1
- Mobile slip panel is a bottom drawer (not a native sheet)
- No i18n for currency symbols (USD default)
