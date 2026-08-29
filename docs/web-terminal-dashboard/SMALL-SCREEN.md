# Small-Screen Usage — Hermes Browser Terminal Dashboard

The dashboard is a fixed 6-pane (3×2) tmux grid. It does **not** reflow on small
screens: on a phone or a narrow browser window the panes shrink until the text is
unreadable (roughly 19×10 cells at 60×24, ~12×8 at 40×18). When that happens, use one
of these tmux keys. They work because the web terminal is launched writable (`ttyd -W`),
so your keypresses drive tmux directly.

Prefix is `Ctrl-b` (hold Ctrl, tap b, release, then the key).

| Key        | Action                                                        |
|------------|---------------------------------------------------------------|
| `Ctrl-b z` | **Zoom** the current (or hovered) pane to fill the screen.   |
|            |   Tap again to un-zoom and return to the 3×2 grid.           |
| `Ctrl-b w` | **Picker** — interactive tree of windows/panes; arrow + Enter|
|            |   to jump to any agent (agent-1 … agent-6) or window 0.      |
| `Ctrl-b q` | Briefly show **pane numbers** as an overlay; press the      |
|            |   number to focus that pane.                                 |
| `Ctrl-b o` | **Cycle** to the next pane.                                  |
| `Ctrl-b <arrows>` | Move focus between panes.                                |

Recommended phone/narrow flow:
  1. `Ctrl-b z` to blow the pane you care about up to full screen.
  2. Read/scroll it (mouse wheel works; `Ctrl-b [` enters copy/scroll mode, `q` exits).
  3. `Ctrl-b z` again to drop back into the grid.
  Or just `Ctrl-b w` to jump straight to the agent you need.

Note: there is no automatic small-screen layout switch by design — the single-pane zoom
above is the intended cramped-screen mode and costs nothing to use.
