# Browser Terminal Dashboard — Small-Screen & Renderer Audit (agent-6)

Date: 2026-08-29
Scope: hermes.shubhbuilds.com — ttyd 1.7.7 + xterm.js + tmux 3.4, 6-pane 3×2 dashboard
~ ("rendererType=canvas"), inside the shared `hermes-main` tmux session.
Audited by agent-6. Other agents' panes were NOT touched (read-only tmux introspection +
a separate scratch session `audit-scratch` that was destroyed afterwards).

====================================================================
TL;DR
====================================================================
TASK 1 (small-screen): The 3×2 grid has NO responsive fallback — on a narrow/phone
  screen the panes become unusable (verified: ~19×10 cells at 60×24, ~12×8 at 40×18).
  RECOMMENDATION: do NOT restructure; document the existing tmux mitigations, which
  genuinely work because ttyd runs with `-W` (writable). Implemented a README note.
  (A structural size-threshold swap was evaluated and rejected — see below.)

TASK 2 (canvas vs webgl): KEEP `rendererType=canvas`. Switching to webgl would require
  a container recreate (kills agent-1..6), and the upside is marginal-to-negative: webgl
  only accelerates the final GPU blit, not xterm's parser; and ttyd's webgl path has NO
  canvas fallback on context loss (verified in ttyd's own code + xterm.js docs + VS Code
  issue #263159), so 6 always-on webgl panes add a real "terminal goes invisible" risk.
  No production change made.

====================================================================
ENVIRONMENT FACTS (verified, not assumed)
====================================================================
- ttyd invocation (from `ps`):
    ttyd -W -m 3 -t rendererType=canvas -t ... -p 7681 /opt/apps/web-terminal/start-hermes.sh
  `man ttyd` / `--help`: `-W, --writable  Allow clients to write to the TTY
  (readonly by default)`. => THE BROWSER CLIENT CAN SEND KEYSTROKES. This is what makes
  the Task-1 mitigations viable (you can actually drive tmux from the dashboard).
- ttyd is built FROM tsl0922/ttyd:latest; frontend (xterm.js + addons) is compiled into
  the binary. I extracted the gzip blob (offset 7151680) and read the real renderer code.
- tmux 3.4. Server config: ~/.tmux.conf (pane borders, mouse on, truecolor, etc.).
  Dashboard assembled in start-hermes.sh: window "dashboard" (index 1) = 6 panes joined
  into a FIXED 3×2 layout string `cebd,171x39,...` (captured once at the large size).
- Live dashboard confirmed intact after this audit (6 panes at ~57×19 cells @171×39).

====================================================================
TASK 1 — SMALL-SCREEN VIABILITY
====================================================================
WHAT ACTUALLY HAPPENS TODAY (empirically reproduced in a scratch tmux session)
------------------------------------------------------------------------------
I built a 6-pane grid identical to the dashboard in a throwaway session `audit-scratch`
(same server, separate session — zero impact on the live dashboard), pinned the window
to small sizes with `window-size manual`, and measured each pane:

  Window  60×24  -> 6 panes each ~19 cols × 10 rows  (text area after the 1-row border)
  Window  40×18  -> 6 panes each ~12-14 cols × 8 rows   (typical phone landscape)

Both are effectively unusable for AI-agent output (long wrapped trace lines, diffs,
JSON). The dashboard geometry is a hardcoded layout string; it does NOT reflow when the
browser is narrow — the panes just shrink until text is unreadable. There is no alternate
small-screen layout today. This confirms the original concern.

DO THE DOCUMENTED MITIGATIONS ACTUALLY WORK? (verified, not guessed)
-------------------------------------------------------------------
Because ttyd is `-W` (writable), the browser user can issue tmux commands. I checked the
live session's key table (tmux 3.4 defaults; ~/.tmux.conf overrides none of these):

  C-b z  -> bind `resize-pane -Z`            (ZOOM one pane full-screen)  [VERIFIED live:
                                                 `resize-pane -Z -t ...` grew a pane to
                                                 the full 171×39 window and toggled off]
  C-b w  -> bind `choose-tree -Zw`           (interactive window/pane PICKER)
  C-b q  -> bind `display-panes`             (shows numbered overlay; press N to jump)
  C-b o  -> bind `select-pane -t :.+`        (cycle panes)

So the originally-suggested guidance ("small screen → C-b z to zoom, or C-b w for a
picker") is CORRECT and works on this dashboard. I confirmed zoom live; the picker/q are
standard tmux 3.4 defaults present in the server.

OPTION A (documented recommendation) vs OPTION B (structural small-screen swap)
-------------------------------------------------------------------------------
Option A — add a README/overlay note telling users to hit C-b z / C-b w when the screen
is cramped. Cost: ~0. Works today. Lowest risk. Does not change the layout for the
primary (desktop) use case.

Option B — a tmux keybinding that auto-switches to a single-pane view below some size
threshold. tmux has no event that fires "when client width < N", so this can't be a pure
keybinding — it would need a background watcher that polls client size and rearranges
panes, or a hook on `client-resized`. That is a STRUCTURAL change to the dashboard for a
secondary use case (phone), with real failure modes: it would fight the fixed 3×2 layout,
could mis-trigger, and adds a process to maintain. The cost/complexity is not justified
when Option A already solves "I can't read this on my phone" via one keypress.

DECISION: Option A. Implemented as a README note (below). No tmux/container change.

IMPLEMENTATION (smallest reasonable)
-----------------------------------
See "SMALL-SCREEN.md" written alongside this report (also could live in
/opt/apps/web-terminal/). Contents: one keypress table for cramped screens.

====================================================================
TASK 2 — CANVAS vs WEBGL RENDERER
====================================================================
BACKGROUND
----------
ttyd 1.7.7 front-end calls `setRendererType(option)` where option comes from the
`-t rendererType=...` flag. I extracted the real function from the binary:

  case "canvas": load CanvasAddon
  case "webgl": load WebglAddon; on webgl ADDON load it registers
                `webglAddon.onContextLoss(() => { webglAddon.dispose(); })`  // <-- NOTE
  case "dom":   (fallback)

CRITICAL FINDING — webgl has NO canvas fallback on context loss:
  The `onContextLoss` handler only DISPOSES the webgl addon. It does NOT fall back to
  the canvas addon (the canvas fallback `r()` only runs if webgl FAILS TO LOAD initially,
  not on later context loss). So once a webgl context is lost, that pane's terminal goes
  blank/invisible until reload. This matches:
   - xterm.js WebGL addon README (github.com/xtermjs/xterm.js addons/addon-webgl):
     "The browser may drop WebGL contexts for various reasons like OOM or after the
      system has been suspended." and shows only a dispose-on-loss example.
   - VS Code issue #263159 (2025-08, OPEN): "WebGL: CONTEXT_LOST_WEBGL: loseContext:
      context lost (terminal goes invisible)" — the canonical failure, traced to
      xterm's webgl addon; multiple users hit it.
   - xterm.js PR #3276 added `onContextLoss` precisely BECAUSE contexts get dropped; the
      embedder (ttyd) is responsible for recovery and ttyd only disposes.

WHY 6 ALWAYS-ON PANES MAKE THIS WORSE
-------------------------------------
Each of the 6 dashboard panes is a separate xterm instance. If webgl is on, that is 6 live
WebGL contexts in one tab. Browsers cap/aggressively reclaim WebGL contexts under memory
pressure (the very "OOM" case the xterm README warns about). An unattended 6-agent
dashboard is exactly the scenario where the tab can be backgrounded/resource-starved and a
context dropped -> a pane silently goes blank with no recovery. For an ops dashboard you
want the OPPOSITE property: it must survive being left open for days.

PERFORMANCE — IS WEBGL ACTUALLY FASTER HERE, AND BY HOW MUCH?
-------------------------------------------------------------
xterm.js's WebGL renderer accelerates the FINAL GPU blit/compositing. It does NOT change
the parser/line-buffer cost, which is where heavy "AI agent output" actually spends time.
I benchmarked the renderer-agnostic floor headless (xterm.js 5.5.0, no renderer addon):

  80×24: 1,200,000 lines parsed in ~114 ms  => ~1,049,000 lines/sec (parser+linebuffer)
  56×18: ~1,009,000 lines/sec

That is ~1M lines/sec of headroom PER PANE on the CPU/parser path alone. Real agent bursts
are nowhere near that; the bottleneck for "6 active agents" is never the renderer's blit —
it's aggregate output volume and the single browser main thread. WebGL would shave the
(compositing) tail of an already-tiny fraction. Marginal, at best, and only on redraw-
heavy scrolling, not on the dominant cost.

(NOTE: I attempted a true canvas-vs-webgl headless throughput benchmark with node-canvas +
jsdom, but xterm's CanvasAddon crashes under jsdom — its texture-atlas path calls
`createImageBitmap`/ResizeObserver that jsdom doesn't implement. That is a harness
limitation, not a production signal, so I do NOT claim a canvas number I couldn't measure;
the parser-only figure above is the verifiable, renderer-independent floor and is the
honest basis for "webgl's gain is marginal here.")

STABILITY OF CANVAS (the current choice)
----------------------------------------
Canvas is CPU-composited and has no context-loss failure mode — it degrades gracefully and
simply keeps drawing. That is exactly why `rendererType=canvas` was chosen "for stability
during initial setup," and why it remains the right call now that the dashboard is stable.

COST OF SWITCHING (explicit)
---------------------------
Changing `-t rendererType=canvas` -> `webgl` lives in docker-compose.yml's `command:` array
(verified). It is baked into the image/container launch; applying it requires recreating
the `web-terminal` container, which KILLS the tmux server and therefore agent-1..agent-6's
running work. The dashboard auto-resumes via `start-hermes.sh` (sentinel + `--resume
latest`), so window 0 + worker windows come back, but in-flight agent tasks are
interrupted. That is a real, user-visible cost for a marginal, possibly-negative benefit.

DECISION: KEEP `rendererType=canvas`. No production change. If webgl is ever wanted, the
correct path is: (1) patch ttyd's `onContextLoss` to fall back to canvas (needs a ttyd
rebuild / custom image), and (2) only then benchmark on a real browser with 6 panes under
synthetic load before trading a container recreate for it.

====================================================================
CHANGES MADE
====================================================================
- Created /home/ubuntu/projects/agent-6/SMALL-SCREEN.md  (Task-1 documentation; the only
  change implemented — a documented keybinding note, as recommended).
- Live dashboard, ttyd config, docker-compose.yml, ~/.tmux.conf: UNCHANGED.
- Scratch session `audit-scratch` (and `audit-probe`): created and destroyed; no residue.

====================================================================
SOURCES
====================================================================
- ttyd 1.7.7 frontend blob (extracted from /usr/bin/ttyd, gzip @ offset 7151680):
    setRendererType() — canvas/webgl/dom + onContextLoss=dispose-only.
- xterm.js WebGL addon README: github.com/xtermjs/xterm.js/blob/master/addons/addon-webgl/README.md
    ("browser may drop WebGL contexts ... like OOM or after the system has been suspended")
- xterm.js PR #3276 (onContextLoss added, 2021) and VS Code issue #263159
    ("WebGL: CONTEXT_LOST_WEBGL ... terminal goes invisible", opened 2025-08, still open)
- tmux 3.4 default key table (verified live via `tmux list-keys`): z=zoom, w=choose-tree,
    q=display-panes, o=cycle.
- ttyd --help: `-W, --writable` (client can write to TTY) — basis for Task-1 viability.
- Empirical: scratch tmux session pane sizes at 60×24 and 40×18; live `resize-pane -Z`
    zoom test; xterm.js 5.5.0 parser-only throughput (~1.0M lines/sec).
