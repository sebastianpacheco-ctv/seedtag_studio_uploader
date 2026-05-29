# Project: OD Portal (Outsourcer Designer Portal)

## Seedtag Brand Identity — Mandatory for all outputs

### Fonts
- **Primary:** `Instrument Sans` (all text: titles, body, captions, labels)
- **Accent:** `Instrument Serif Italic` (only for aspirational/emotional main headlines — never body text)
- Never use: Arial, Inter, Roboto, Helvetica, Times New Roman, system fonts
- Google Fonts import:
  ```html
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=Instrument+Serif:ital@1&display=swap" rel="stylesheet">
  ```

### Colors (use ONLY these exact values)
| Token    | HEX       | Use                                         |
|----------|-----------|---------------------------------------------|
| Coral    | `#FF6B7C` | Brand accent, CTAs, highlights, primary data |
| Black    | `#000000` | Dark backgrounds, body text on light bg      |
| White    | `#FFFFFF` | Text on dark/coral bg, clean backgrounds     |
| Cream    | `#EBE6E4` | Warm neutral bg, chart areas                 |
| Grey-1   | `#D4D0CE` | Subtle dividers, light panels                |
| Grey-2   | `#BCB8B6` | Secondary UI, disabled states                |
| Grey-3   | `#8D8A89` | Captions, secondary labels                   |
| Grey-4   | `#5E5C5B` | Supporting body text                         |
| Grey-5   | `#2F2E2E` | Near-black text on light bg                  |

### Color pairing rules
- Coral bg → White text only (never Black on Coral)
- Black bg → White text, Coral for accents
- Cream bg → Black or Grey-5 text, Coral for accents
- White bg → Black or Grey-5 text, Coral for accents
- Charts: primary = Coral, secondary = Black, chart bg = Cream

### CSS variables (use in all HTML/React)
```css
:root {
  --coral: #FF6B7C;
  --black: #000000;
  --white: #FFFFFF;
  --cream: #EBE6E4;
  --grey-1: #D4D0CE;
  --grey-2: #BCB8B6;
  --grey-3: #8D8A89;
  --grey-4: #5E5C5B;
  --grey-5: #2F2E2E;
  --font-sans: 'Instrument Sans', sans-serif;
  --font-serif: 'Instrument Serif', serif;
}
```

### Wordmark
- `SEEDTAG` in Instrument Sans, letter-spacing 0.25em, footer placement only
- White on dark/coral backgrounds, Black on light/cream backgrounds
- In body copy write "Seedtag" (capital S, lowercase rest) — never all-caps

### Lens elements (signature visual)
Translucent overlapping circles with radial gradient — always on brand slides/sections:
```css
.lens {
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,0.25) 0%, rgba(255,255,255,0) 70%);
  border: 1px solid rgba(255,255,255,0.2);
  position: absolute;
}
.lens-coral-glow {
  background: radial-gradient(circle, rgba(255,107,124,0.4) 0%, rgba(255,107,124,0) 70%);
}
```

### Voice & tone
- Confident, human, concise — no corporate jargon
- Headlines: short, punchy, verb-first
- Never use: "leverage", "synergy", "innovative", "cutting-edge", "seamless", "best-in-class", "unlock", "robust"
- Active voice, specific numbers, short sentences

---

## Project context

This is the Outsourcer Designer Portal — a web platform for managing CTV design tickets with freelance designers.

### Architecture
- Connected to Jira (project SDS) for ticket sync
- Two roles: Admin (@seedtag.com) and Freelancer (external email)
- Review Pro embedded as hybrid service for file review/feedback
- Cloud hosted with 4 storage buckets: assets/ticket, repositorio, deliveries, review-pro

### Tech decisions
- Admin detects role by email domain (@seedtag.com = admin, else = freelancer)
- Jira sync via webhook or polling (bidirectional: tickets + status)
- Review Pro runs as independent service, embedded via iframe/API
- Assets split: per-ticket assets + shared repository (templates, mockups, guides)
