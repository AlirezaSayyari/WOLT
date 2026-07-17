# WOLT Web — UI Design Specification

Status: Visual direction for review

## Design concept

**Network Control Plane**: calm, precise and operational. The interface should
feel like an infrastructure product, not a generic admin template. Dense data
is allowed, but hierarchy and whitespace must make failures immediately
understandable.

## Visual foundations

### Color

| Token | Light | Dark | Purpose |
|---|---:|---:|---|
| Canvas | `#F5F7FA` | `#0B1118` | Page background |
| Surface | `#FFFFFF` | `#121B25` | Cards and panels |
| Elevated | `#FFFFFF` | `#172330` | Dialogs and menus |
| Primary | `#0F8B8D` | `#39C6C8` | Main actions and active paths |
| Success | `#16875D` | `#42D39B` | Healthy and completed |
| Warning | `#B26A00` | `#F2B84B` | Attention and degraded |
| Danger | `#C33A45` | `#FF6B76` | Failure and destructive action |
| Text | `#17212B` | `#E8EEF4` | Primary text |
| Muted | `#627181` | `#91A0AF` | Secondary information |
| Border | `#DDE3E9` | `#263646` | Dividers and controls |

Status never relies on color alone; icons and text labels accompany it.

### Typography

- UI: Inter or a system sans-serif stack.
- Technical values, MACs, ports and event IDs: JetBrains Mono or system mono.
- Base size: 14–16 px; table density is adjustable.
- Persian future locale: Vazirmatn with mirrored layout and unchanged data
  alignment for MAC/IP values.

### Shape and elevation

- 10 px card radius; 8 px control radius.
- Subtle one-pixel borders; shadows reserved for overlays.
- 8 px spacing grid.
- Icons are simple outline icons, 18–20 px.

## Application shell

```text
┌──────────────┬──────────────────────────────────────────────────────┐
│ WOLT         │ Search…               Engine: Active   ◐   Admin ▾ │
│              ├──────────────────────────────────────────────────────┤
│ Overview     │                                                      │
│ Dashboard    │                  Active page                         │
│ Architecture│                                                      │
│              │                                                      │
│ Wake Engine  │                                                      │
│ Listeners    │                                                      │
│ Devices      │                                                      │
│              │                                                      │
│ Observe      │                                                      │
│ Events       │                                                      │
│ Audit        │                                                      │
│              │                                                      │
│ Settings     │                                                      │
└──────────────┴──────────────────────────────────────────────────────┘
```

Desktop sidebar is 248 px expanded and 72 px collapsed. Content has a maximum
comfortable width for forms, while tables and diagrams may use the full area.

## Dashboard

### Header

- Title: `Overview`
- Current engine state with last transition.
- Primary action: `Pause engine` or `Resume engine`.
- Secondary action: `Send test wake`.

### First row

Four cards:

1. Engine: Active/Paused/Error, uptime and heartbeat.
2. Active listeners: active/total and port range.
3. Wake success: percentage plus comparison with previous period.
4. Device health: healthy/degraded/offline counts.

### Main area

- Left, 2/3 width: requests over time stacked by success/failure/rate limited.
- Right, 1/3 width: architecture mini-map showing live flow state.
- Bottom: recent wake events table with outcome, MAC, mapping, device, latency
  and timestamp.

## Listener mappings

### Toolbar

- `Add listener` primary button.
- Search, device filter, state filter and density control.
- UDP range indicator: `40000–40099 · 3 used`.

### Table

Columns:

```text
Status | Name | UDP Port | Device | Interface | Gateway IP | Last event | Actions
```

- Port and MAC-like technical values use monospace.
- Row action menu contains Edit, Clone, Enable/Disable, Test and Delete.
- Inline editing is used only for Name and enabled state.
- Port, device and driver fields use a side panel because they require
  validation and explanatory context.

### Add/edit side panel

1. General: name, description and enabled toggle.
2. Routing: device and auto/manual UDP port.
3. Driver fields: interface and gateway IP for FortiGate.
4. Live validation summary.
5. Guacamole values preview.

## Device page

- Device cards show driver icon, address, health and listener count.
- Detail page has Overview, Connection, Credentials, Host key and Activity tabs.
- `Test connection` returns a safe structured result and measured latency.
- Secret fields say `Configured` and offer `Replace`; they never display a
  fake masked value that could accidentally be saved.

## Events page

- Server-side filtering and pagination.
- Saved filter presets for Failures, Rate limited and Authentication.
- Expandable row shows the safe request timeline and correlation ID.
- Event drawer links directly to the mapping and device.
- CSV export respects current filters and role permissions.

## Architecture guide

The page has an interactive horizontal flow:

```text
[PAM / Guacamole] → [UDP Listener] → [Parse + Map] → [Device Driver] → [Workstation]
```

Selecting a node reveals:

- What enters and leaves the stage.
- Security checks.
- Relevant configuration fields.
- A concrete example using port 40016 and VLAN 16.

Below the diagram, a `Why UDP ports map to interfaces` explainer contrasts the
original inter-VLAN broadcast problem with the WOLT native-device solution.

## Setup wizard

- Centered 760 px panel with a persistent step list on desktop.
- Each step has one concept and one primary action.
- Connection tests run explicitly, never automatically on each keystroke.
- Recovery code step cannot be skipped until the user confirms it was saved.
- Final review clearly distinguishes settings stored in DB from bootstrap
  secrets stored outside it.

## Dark and light behavior

- Theme options: System, Light, Dark.
- User preference is stored server-side and cached locally for pre-paint.
- Charts use tokenized colors tested in both themes.
- Dark mode uses borders rather than heavy shadows.
- Architecture flow glows subtly only on active paths; no decorative neon.

## Responsive behavior

- Desktop is primary at 1280 px and above.
- At 768–1279 px, sidebar collapses and dashboard cards become two columns.
- Below 768 px, tables become prioritized cards; configuration remains usable
  but architecture editing is not optimized for phones.
- All dialogs become full-height sheets on narrow screens.

## Accessibility

- Target WCAG 2.2 AA contrast.
- Complete keyboard navigation and visible focus rings.
- Icons include accessible names; status changes announce through live regions.
- Reduced-motion preference disables animated architecture paths.
- Charts have tabular summaries.

## Exact copy for the first visual mockup

The initial design board uses these labels verbatim:

```text
WOLT
Wake orchestration for segmented networks
Overview
Architecture
Listeners
Devices
Events
Audit trail
Settings
Engine active
Pause engine
Send test wake
Active listeners
Wake success
Device health
Requests over time
Recent wake events
Add listener
UDP range 40000–40099
demo-vlan-16
198.51.100.94
02:AA:BB:CC:DD:16
Guacamole / PAM
UDP Listener
Parse & Map
Edge Device
Target Workstation
```

## Visual decisions awaiting approval

1. Teal operational accent, or a blue/purple product accent?
2. Compact NOC-like density, or more spacious SaaS-style density?
3. Sidebar navigation, or a top navigation layout?
4. Side panel editing, or centered modal forms?
5. Should the Architecture mini-map remain on the Dashboard?
6. Should public v0.2 include Persian translation or only RTL-ready structure?
