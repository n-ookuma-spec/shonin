# DESIGN.md (Linear Style)

This document defines the visual language and design principles for the **Shift Auto-generation System**. It is optimized for AI agents to ensure consistent, high-quality UI generation that aligns with the **Linear.app** aesthetic: clean, high-performance, and focused on productivity.

## 1. Visual Theme & Atmosphere
- **Philosophy**: "Software should feel like a precise tool." High contrast where it matters, subtle where it doesn't.
- **Atmosphere**: Professional, focused, and "airy" but structured.
- **Key Characteristics**: Sub-pixel borders, subtle gradients, rounded corners, and a dark-mode first mentality (though this project uses a "Warm Parchment" light theme, we apply Linear's structural precision).

## 2. Color Palette (Warm Editorial x Linear Precision)
| Role | Hex | Usage |
|------|-----|-------|
| Background (Primary) | `#F7F4EE` | Main content area background |
| Background (Secondary)| `#F2EEE6` | Sidebar, headers, and grouping elements |
| Text (Primary) | `#231F1A` | Main headings and body text |
| Text (Secondary) | `#5C5650` | Labels, descriptions, and metadata |
| Accent (Primary) | `#BE4B20` | Primary actions, active states, and highlights |
| Success | `#059669` | Validated states and "OK" indicators |
| Warning | `#B45309` | Alerts and cautionary information |
| Danger | `#E11D48` | Errors and destructive actions |
| Border (Subtle) | `rgba(35,31,26,0.09)` | Default separators and containers |

## 3. Typography
- **Font Family**: `'Zen Kaku Gothic New'`, `'Noto Sans JP'`, sans-serif.
- **Monospace**: `'DM Mono'`, `'Courier New'`, monospace (used for times, codes, and IDs).
- **Scale**:
  - `Display`: 19px, 700 weight, -0.02em letter-spacing.
  - `Body`: 14px, 400 weight, 1.55 line-height.
  - `Label`: 12px, 600 weight, uppercase for small headers.
  - `Small`: 10px, 700 weight, 0.12em letter-spacing.

## 4. Component Stylings
### Buttons
- **Base**: `border-radius: 8px`, `padding: 7px 15px`, `font-weight: 600`.
- **Primary**: Background `#BE4B20`, Text `#FFFFFF`.
- **Interaction**: 
  - `Hover`: `translateY(-1px)`, subtle `box-shadow`.
  - `Active`: `translateY(0px)`, `scale(0.98)`.
- **Focus**: `2px` solid accent with `2px` offset.

### Sidebar
- **Width**: `240px`.
- **Active Item**: Left border `3px` solid accent, background `rgba(190,75,32,0.10)`, text accent.
- **Hover Item**: Subtle background shift, increased left padding.

### Cards & Panels
- **Container**: `border: 1px solid rgba(35,31,26,0.09)`, `border-radius: 12px`.
- **Elevation**: Use subtle borders instead of heavy shadows. For modals, use `box-shadow: 0 12px 40px rgba(35,31,26,0.18)`.

## 5. Layout Principles
- **Grid**: 8px based spacing system.
- **Structure**: Topbar (48px) + Layout (Sidebar + Main Content).
- **Density**: "Comfortable" density. Use whitespace to separate logical sections rather than heavy lines.

## 6. Depth & Elevation
- **Level 0**: Background (`#F7F4EE`).
- **Level 1**: Cards, sidebar, headers (`border-bottom`).
- **Level 2**: Modals, dropdowns, popovers (floating with shadow).

## 7. Do's and Don'ts
- **Do**: Use semantic colors for shift types (e.g., Night shift is purple).
- **Do**: Keep tables "sticky" for headers and name columns to maintain context.
- **Don't**: Use pure black (`#000000`) for text; use `#231F1A`.
- **Don't**: Use rounded corners larger than 12px for main containers.

## 8. Responsive Behavior
- **Mobile (< 860px)**: Sidebar collapses to 0px, layout switches to single column.
- **Tablet**: Sidebar can be toggled.

## 9. Agent Prompt Guide
When generating UI for this project:
- "Follow the Linear.app aesthetic: prioritize precision, subtle borders, and consistent 8px spacing."
- "Use the 'Warm Editorial' color scheme (Parchment & Terracotta) as defined in DESIGN.md."
- "Ensure all interactive elements (buttons, links) have the defined hover and active animations."
- "Keep data tables highly functional with sticky headers and sub-pixel borders."
