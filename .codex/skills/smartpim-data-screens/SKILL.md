---
name: smartpim-data-screens
description: Use for admin, mapping, catalog, source, and other data-heavy SmartPim screens where the interface must stay dense, fast, and operational: stable columns, reduced button noise, persistent context, balanced side panels, and desktop-first workflows over decorative UI.
---

# SmartPim Data Screens

Use this skill for working screens in Global PIM:

- mappings
- admin panels
- category tools
- source/import screens
- product/content workspaces
- organization and membership management

This skill is about operational UI, not marketing presentation.

## Primary goal

Make the screen fast to read and fast to operate.

The user should be able to:

- see context immediately
- find the active object quickly
- edit without losing orientation
- compare related entities side by side
- avoid scrolling chaos and button overload

## Structural rules

- Keep one primary work area. Supporting panels must support it, not fight it.
- Use 3-column layouts only when each column has a clear role.
- If a side panel is optional, allow collapse or narrowing.
- Preserve context when scrolling:
  - sticky first column where needed
  - sticky headers where needed
  - persistent selected entity context
- Prefer horizontal productivity over stacked mobile-like cards on desktop.

## Table and grid rules

- Tables are allowed to be dense, but spacing must stay consistent.
- Primary identifiers should stay visible during horizontal scroll.
- Group rows, section headers, and pinned columns are preferred over repeated labels.
- Avoid excessive borders, shadows, and nested card wrappers inside cells.
- Use whitespace to separate groups, not a forest of containers.

## Controls

- Every visible button must justify itself.
- Default action count per area should be minimal.
- Move destructive or secondary actions away from the main rhythm.
- Prefer inline toggles, disclosure, and segmented filters over long action bars.
- Repeated row-level actions should be visually quiet.

## Side panels

- Side panels should contain:
  - source context
  - reference data
  - supporting filters
  - auxiliary details
- Side panels should not duplicate the central table.
- If the user needs more workspace, panels should be collapsible.

## Mapping screens

- Marketplace, competitor, and source entities should feel like one mapping workflow.
- Do not split conceptually related data across disconnected UI modes unless necessary.
- Mapping success and completeness should be visible from the current category/model context.
- Reduce text noise in source pools. Show what matters for matching.
- Use expand/collapse to hide already-understood blocks.

## Admin screens

- Admin screens should feel controlled and procedural.
- Prefer lists, filters, status chips, and detail panes over dashboard theater.
- Organization, member, and invite flows should be obvious in one scan.
- Status, role, and current organization context must be visible without drilling in.

## Product/content workspaces

- Keep the active product/category/model visible.
- Show only the controls needed for the current operation.
- Derived readiness, source coverage, and export state should read as operational signals, not decorative metrics.

## Visual rules

- Use the SmartPim base language from [`smartpim-ui`](/Users/maksimkiselev/Desktop/Global%20PIM/.codex/skills/smartpim-ui/SKILL.md).
- For dense work areas, reduce decorative gradients and increase structural clarity.
- Keep accent color for state and action, not for flooding the interface.
- Prefer flat or lightly elevated surfaces over stacks of cards.

## Avoid

- Overloaded top toolbars
- Card-inside-card-inside-card layouts
- Too many pills, counters, and badges competing at once
- Huge helper paragraphs on operational screens
- Splitting one workflow into multiple disconnected tabs when a single workspace would do
- Making desktop tools look like mobile settings pages

## Delivery checklist

- Can the user identify the current object and next action immediately?
- Are the main columns or entities aligned and comparable?
- Is button noise lower than before?
- Is important context still visible during scroll?
- Can optional panels be collapsed if they consume too much space?
- Did the screen become more operational, not more decorative?

## Project note

Use this skill together with [`smartpim-ui`](/Users/maksimkiselev/Desktop/Global%20PIM/.codex/skills/smartpim-ui/SKILL.md) for data-heavy frontend work in this repo.
