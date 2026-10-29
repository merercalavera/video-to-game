# Match-3 grids

Read this when the video, or the request, has a tile grid that the player solves: "match-3", "swap tiles",
"line up 3", or a puzzle-ad clip where tiles clear to open a path (water, lava, sand, a hero falling through).
It is the rule set and the implementation that worked in a shipped build: a 13x6 swap grid under a water channel,
where matched tiles leave open cells that the water flows through to a drain.

## Pick the variant first

| Variant | Input | After a clear | Use when |
|---|---|---|---|
| **Swap, no gravity** | swap two neighbours | cells stay open | the grid is a maze for something else (water, a hero, light) to flow through |
| **Swap, gravity + refill** | swap two neighbours | tiles fall, new ones drop in, cascades | the grid itself is the goal (score, targets, collect N) |
| **Tap to blast** | click a linked group of 2+ | cells stay open, or fall | the video shows single taps clearing clusters (common in puzzle ads) |

If the user says "match-3", they mean swapping. Puzzle-ad videos often show tap-to-blast, so check which one
was asked for before building. Write the variant into the spec.

## Rules (swap variants)

- **Swap:** the player selects a tile, then an orthogonal neighbour (click-click), or drags one onto the other.
  Diagonal or distant clicks move the selection instead.
- **Legal swap:** only if the swapped board has a run of 3+ of one color in a row or column, through either tile.
  An illegal swap animates there and back, then both tiles wiggle. It costs nothing.
- **Clear:** every cell in a run of 3+ clears. Overlapping runs (L, T, +) merge into one clear. Runs are found on
  the whole board after the swap, not only through the two swapped cells.
- **No standing matches:** a new board never starts with a run of 3. Reroll the run's cells until clean.
- **Always a move:** after every clear, check that a legal swap exists. If none does, reshuffle the remaining
  tiles' colors in place (same cells, new colors), then clean and re-check.
- **Empty cells:** tiles only swap with tiles. Open cells are not part of any run and can't be swapped into
  (allowing it makes the puzzle trivial).
- **Gravity variant only:** after a clear, tiles above fall into the holes, new tiles spawn at the top, and the
  board is re-scanned for cascades until no run remains. Lock input until the cascade settles.
- 3 colors on a big board (13x6) gives plenty of moves. 4 to 6 colors on 8x8 is the classic density. Fewer
  colors make more accidental cascades.

## Data model

```js
// tiles[r][c] = color index 0..K-1, or -1 for an open cell; row 0 is the top
const S = { tiles: [], sel: null /* [c, r] */, swap: null /* { a, b, t, back, ok } */, down: null, moves: 0 };
const inGrid = (c, r) => c >= 0 && r >= 0 && c < COLS && r < ROWS;
```

Keep one mesh (or sprite) per cell and re-skin it from `tiles` after each change, rather than moving meshes between
cells. Only the two swapping meshes are offset while the swap animates.

## Core functions

```js
function matchesIn(t) {                       // every cell in a run of 3+, as r * COLS + c
  const out = new Set();
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS;) {
    let e = c + 1; while (e < COLS && t[r][e] === t[r][c]) e++;
    if (t[r][c] >= 0 && e - c >= 3) for (let x = c; x < e; x++) out.add(r * COLS + x);
    c = e;
  }
  for (let c = 0; c < COLS; c++) for (let r = 0; r < ROWS;) {
    let e = r + 1; while (e < ROWS && t[e][c] === t[r][c]) e++;
    if (t[r][c] >= 0 && e - r >= 3) for (let y = r; y < e; y++) out.add(y * COLS + c);
    r = e;
  }
  return out;
}
function swapped(a, b) {                      // a copy of the board with a and b exchanged
  const t = S.tiles.map(row => row.slice());
  [t[a[1]][a[0]], t[b[1]][b[0]]] = [t[b[1]][b[0]], t[a[1]][a[0]]];
  return t;
}
function validSwaps() {                       // right and down neighbours cover every pair once
  const out = [];
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) for (const [dx, dy] of [[1, 0], [0, 1]]) {
    const nx = c + dx, ny = r + dy;
    if (!inGrid(nx, ny) || S.tiles[r][c] < 0 || S.tiles[ny][nx] < 0 || S.tiles[r][c] === S.tiles[ny][nx]) continue;
    if (matchesIn(swapped([c, r], [nx, ny])).size) out.push([[c, r], [nx, ny]]);
  }
  return out;
}
function settle() {                           // no run on the board, and at least one legal swap
  for (let i = 0; i < 200; i++) {
    const m = matchesIn(S.tiles);
    for (const k of m) S.tiles[Math.floor(k / COLS)][k % COLS] = Math.floor(rand() * K);
    if (!m.size && validSwaps().length) return;
    if (!m.size) for (const row of S.tiles) row.forEach((v, c) => { if (v >= 0) row[c] = Math.floor(rand() * K); });
  }
}
```

Use the game's seeded `rand()` (`?seed=N`), so a playtest sees the same board twice.

## Input and the swap state machine

```js
function tap(c, r) {                          // click, Space or gamepad A on a cell
  if (S.phase !== 'play' || S.swap) return;
  if (!inGrid(c, r) || S.tiles[r][c] < 0) { S.sel = null; return; }
  const s = S.sel;
  if (!s) { S.sel = [c, r]; return; }
  if (s[0] === c && s[1] === r) { S.sel = null; return; }
  if (Math.abs(s[0] - c) + Math.abs(s[1] - r) === 1) { trySwap(s, [c, r]); return; }
  S.sel = [c, r];                             // not a neighbour: move the selection
}
function trySwap(a, b) {
  S.sel = S.down = null;
  if (S.swap || S.tiles[b[1]][b[0]] < 0) return;
  S.swap = { a, b, t: 0, back: false, ok: matchesIn(swapped(a, b)).size > 0 };
}
function finishSwap() {                       // called when S.swap.t reaches SWAPT (about 0.16 s)
  const { a, b, ok, back } = S.swap;
  if (!ok) {                                  // illegal: slide back, then wiggle both
    if (!back) { S.swap.back = true; S.swap.t = 0; }
    else { S.swap = null; wiggle(a); wiggle(b); }
    return;
  }
  S.tiles = swapped(a, b); S.swap = null; syncTiles();
  for (const k of matchesIn(S.tiles)) { popTile(k); S.tiles[Math.floor(k / COLS)][k % COLS] = -1; }
  S.moves++; onBoardChanged();                // e.g. recompute what the water can reach
  // gravity variant: collapse(), refill(), then loop matchesIn() until it is empty before unlocking input
  if (!validSwaps().length) { reshuffleColors(); settle(); syncTiles(); }
}
```

- **Drag:** on pointerdown, call `tap()` and remember `S.down = [c, r]` if it selected. On pointermove with a
  button held, if the pointer enters an orthogonal neighbour tile, call `trySwap(S.down, thatCell)`.
- **Keyboard and gamepad:** arrows or the d-pad move a cursor ring. Space, Enter or A call `tap(cursor)`. The ring
  shows the cursor, or the selected tile when playing with the mouse.
- **Hover:** scale the tile under the pointer by about 1.05. Pulse the selected tile at about 1.12.

## Feel and timing

| Moment | Value |
|---|---|
| Swap slide (smoothstep ease) | 0.14 to 0.18 s each way |
| Illegal swap | slide there and back, then a 0.3 s wiggle (rotation) on both tiles |
| Pop | scale 1 to 1.5 and fade over 0.2 s, plus 6 to 8 particles in the tile's color, and one pop sound per move |
| Fall (gravity variant) | 0.08 s per cell with a small bounce, and a cascade sound pitched up per chain step |
| Input lock | while a swap or cascade runs; selection clears on every swap attempt |

Render the moving tile above its neighbour (a higher `renderOrder`) so the two never z-fight mid-slide.

## When the grid opens a path (water, sand, a falling hero)

- Recompute reachability after each clear, as a BFS over open cells from the source cells (for example, the
  channel's mouth above row 0, columns 0 to 2). Use the BFS parent links to rebuild the shortest path to the goal
  (for example, a drain under the bottom row).
- Before the goal is reached, the flow fills the lowest reachable open cells first, and each cell's volume is
  taken from the source.
- Once a path reaches the goal, drain the source at **one constant rate** until it's empty. Don't fill pockets
  first and then drain, or the pace stutters. Run a visual stream front down the path at a few cells per second,
  fill side pockets slowly and only for show, and emit droplets at the exit every frame.
- Put the danger (creeping gravel, rising lava, a timer) outside the grid, so the grid stays a calm puzzle and
  the tension lives in the world above it.

## State for the playtest

Expose the board the way a player reads it, plus enough geometry to click:

```js
window.__game = { get state() { return {
  phase: S.phase, moves: S.moves, selected: S.sel, swapping: !!S.swap,
  tiles: S.tiles.map((row, r) => row.map((k, c) => k >= 0 ? 'RGY'[k] : wet(c, r) ? '~' : '.').join('')),
  grid: { x0: view.ox + GX * view.scale, y0: view.oy + GY * view.scale, cell: CS * view.scale },
}; } };
```

In `play.mjs`, copy `matchesIn()` over the strings. Try every right and down neighbour, keep the swaps that match,
and score them by what the game rewards (touches the flow, depth toward the goal, run length). Then click the
first tile, wait about 180 ms, and click the second. Wait while `swapping` is true. Keep making moves at a calmer
pace after the goal opens, so the take has no dead seconds.

## A pointer hand (optional, common in puzzle ads)

Generate it on fal (a pointing hand seen from the back, so the fingernail and knuckles face the viewer, isolated
on white), then cut it out with `fal-ai/birefnet/v2`. Use an `<img>` with `pointer-events: none` that follows the
pointer, and set `cursor: none` on the canvas. Size it from the video (about 2.5 cells tall). Put its hotspot at
the fingertip: measure the topmost opaque row of the cutout, and use its mean x. Dip it on press (scale 0.88,
rotate a few degrees). With the keyboard, move it to the cursor cell. A DOM pointer shows up in `record_play.mjs`
takes.

## Pitfalls

- Scanning only the two swapped cells misses runs that the swap completes elsewhere in the same line. Scan the
  whole board.
- A board with a standing run at the start, or with no legal move, reads as broken. Always `settle()`.
- Re-creating meshes on every change leaks GPU memory and flickers. Re-skin per-cell meshes instead.
- In the no-gravity variant the board thins out, so check `validSwaps()` after every clear, not only at the start.
- Tap-to-blast and swap rules feel very different. Don't mix them unless the design asks for it.
