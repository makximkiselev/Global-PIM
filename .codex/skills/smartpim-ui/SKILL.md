---
name: smartpim-ui
description: Use for frontend and UX work in Global PIM when the screen should follow the SmartPim visual language: warm light base, orange accents, restrained gradients, editorial hierarchy, compact form cards, dense but clean data screens, and desktop-first viewport-fit layouts without decorative clutter.
---

# SmartPim UI

Use this skill for new screens and meaningful UI refactors in this repo.

## Design intent

- Product feel: operational PIM, not generic SaaS marketing.
- Base look: light surfaces, warm neutrals, orange accents, soft gradients.
- Tone: sharp, structured, dense, calm.
- Layout: desktop-first, broad working canvas, clear left-to-right hierarchy.

## Visual rules

- Prefer a warm light background over dark mode by default.
- Use orange as the active accent, not as constant fill everywhere.
- Gradients should be soft and atmospheric, not glossy or loud.
- Keep one dominant visual idea per screen. Do not scatter many decorative cards.
- Typography should carry the hierarchy. Use large, confident headings and restrained supporting copy.
- Avoid purple bias, default-looking UI kits, and interchangeable startup visuals.

## Composition rules

- Favor strong asymmetry: content mass on one side, focused action area on the other.
- Forms should be compact, readable cards. Do not let auth or admin forms dominate the whole viewport.
- Working screens should maximize horizontal space for the real task.
- Reduce empty decorative space unless it improves hierarchy.
- On desktop, important first-view content should fit without unnecessary vertical scrolling.

## Interaction rules

- Prefer progressive disclosure over visible clutter.
- Hide secondary actions until they are needed.
- Keep controls near the work they affect.
- Avoid too many tabs, pills, badges, and competing buttons in one area.

## Data-heavy screens

- Dense is acceptable; chaotic is not.
- Use stable alignment, consistent column rhythm, and obvious grouping.
- Keep primary identifiers sticky or persistently visible when horizontal scrolling exists.
- Side panels should support the main task, not compete with it.
- Marketplace, competitor, and source data should feel like one workflow, not separate mini-products.

## Auth screens

- Login and registration should share one structural language.
- Differences between auth screens should come from copy, color mode, and CTA, not unrelated layouts.
- Avoid decorative top chips or labels that do not add meaning.
- Keep auth screens visually premium but operational, not “landing page” styled.

## Avoid

- Generic card grids as the default answer.
- Oversized empty hero areas.
- Random dark sections mixed into light product flows without reason.
- UI noise: repeated pills, redundant helper text, duplicate actions.
- Motion for its own sake.

## Delivery checklist

- Preserve SmartPim visual language.
- Check desktop viewport-fit.
- Check that the primary task is obvious in under a few seconds.
- Remove any control or text block that does not materially help the workflow.
- For major UI changes, build the frontend and visually verify the affected screen.

## Project note

When the user asks for frontend changes in this repo, prefer applying this skill together with the general web/frontend skill rather than inventing a new style each time.
