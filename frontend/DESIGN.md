# Cortex Frontend Design Direction

## Product thesis

Cortex is a personal command center for the life already in motion. The
interface should make the next meaningful action obvious without turning
private life into an operations dashboard. It should feel calm, dense, and
deliberate: useful information close at hand, visual noise kept low.

The initial page is only a foundation proof point. Future task, knowledge, and
finance surfaces should inherit this direction without becoming decorative
dashboard tiles.

## Visual language

### Palette

Use semantic tokens rather than raw colors in components.

- Rose: #F4AFAB — primary action, selected state, active rail, and brand mark.
- Rose strong: #9E5662 — readable light-theme links, labels, and icons.
- Canvas: #FBF7F5 — warm rose application background.
- Surface: #FFFCFA — cards, panels, and raised reading surfaces.
- Ink: #2B252B — primary text and strong labels.
- Sea glass: #3A756D — completed and low-priority status.
- Amber: #94672F — in-progress and medium-priority status.
- Slate: #4B719B — to-do status and navigation signal.
- Destructive: #B64D5A — canceled, overdue, and blocking errors.
- Border: #E6D9DD — quiet separation between adjacent surfaces.

Dark mode keeps the exact Rose brand color while shifting surfaces to plum-black
and lifting the supporting status colors for contrast. The system preference
controls the mode; there is no user toggle yet. Rose is reserved for filled
controls and decorative emphasis in the light theme; Rose strong is used when
the brand color must appear as readable text.

Task state mapping remains explicit: backlog uses muted text, to-do uses Slate,
in progress uses Amber, done uses Sea glass, canceled uses Destructive, and
high priority uses Rose strong. Labels and icons must never rely on color alone.

### Typography

- Geist Sans: body copy, labels, headings, and controls.
- Geist Mono: timestamps, system metadata, IDs, and compact status readouts.
- Use sentence case and specific copy. Avoid unexplained acronyms and generic
  productivity language.

Type should establish hierarchy before color or decoration does. Use short
eyebrow labels, clear titles, compact supporting text, and generous line height
for longer notes.

### Layout

The future workspace should organize around a primary focus column and a
secondary context rail:

    [brand + navigation] [today / current focus        ] [context]
                         [task or note sequence         ] [signals ]
                         [next action                    ] [memory  ]

Prefer a stable max-width, quiet dividers, shallow cards, and one strong
accent rail for priority or time. Avoid gradients, glass effects, excessive
rounded containers, and equal-weight card grids.

### Signature interaction

Priority is expressed as a narrow rust rail paired with explicit time or
context labeling. The rail is a reinforcement, never the only status cue.
Completed, blocked, and overdue states must also use text or iconography.

## Interaction states

- Loading: preserve layout geometry with restrained skeletons or reserved
  blocks; do not flash unrelated content.
- Empty: explain what belongs here and offer one clear next action.
- Error: state what failed, preserve useful surrounding context, and provide a
  retry or recovery path without exposing backend details.
- Hover: use small surface or border changes, never large motion.
- Focus: use a high-contrast visible ring and keep keyboard order logical.
- Reduced motion: disable non-essential transitions and animated emphasis.

## Responsive behavior

Design mobile-first. Collapse secondary context below the primary focus rather
than shrinking dense panels until text becomes unreadable. Keep touch targets
comfortable, prevent horizontal scrolling, and preserve the order of the
user's next action, supporting context, and navigation.

## Accessibility baseline

Use semantic landmarks, heading hierarchy, native controls, explicit labels,
descriptive link text, and status announcements for asynchronous changes.
Contrast must remain readable in both themes and at increased text scale.

## Component governance

Use shadcn/ui as the frontend's reusable component library. The configured
`base-nova` style and the semantic Cortex tokens above remain the source of
truth for appearance; shadcn components provide the interaction primitives and
their in-repository implementation.

- Feature and route code imports reusable UI from `@/components/ui/*`.
- Direct `@base-ui/react` imports are implementation details of generated
  shadcn components and must not be added to `src/app` or `src/features`.
- Add new primitives with the configured shadcn CLI so generated components,
  dependencies, and aliases stay aligned with `components.json`.
- Compose product-specific patterns, such as task rows and workspace rails,
  in their feature folders from shadcn primitives. Do not turn every layout
  wrapper or semantic navigation link into a generic component.
- Preserve native semantics where shadcn has no direct replacement, such as
  `date` and `datetime-local` input types, by rendering them through the
  shadcn `Input` component.
