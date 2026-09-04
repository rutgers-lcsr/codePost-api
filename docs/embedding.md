# Embedding codePost in an iframe

codePost can be embedded in an iframe on trusted sites (e.g. departmental pages under
`*.cs.rutgers.edu`). The app never scrolls at the document level — every console clamps to
100% of its container and scrolls inside — so **the iframe must exactly fill the visible
area of the embedding page**. If the iframe is taller than what the visitor can see, the
bottom of codePost (navigation bars, pinned footers, fixed buttons) is unreachable.

## Prerequisites (already configured)

Two layers must allow the embedding origin — both already permit `'self'` and
`https://*.cs.rutgers.edu`:

- **API**: `core/middleware.py` (`csp_frame_ancestors_middleware`) sets
  `Content-Security-Policy: frame-ancestors …` on every response. Override the origin list
  with the `CSP_FRAME_ANCESTORS` env var (space-separated origins).
- **Frontend nginx**: `frame-ancestors` in `codePost-ui/nginx.conf` (or
  `CSP_FRAME_ANCESTORS` in `nginx.conf.template`).

No `X-Frame-Options` is sent; the CSP directive is the single source of truth.

## The embed snippet

The parent page must not scroll, and the iframe must be sized to the *visible* viewport
(`100dvh`), not to a fixed pixel height:

```html
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; }
  .codepost-frame {
    display: block;
    border: 0;
    width: 100%;
    height: 100dvh; /* below a site header: calc(100dvh - <header height>px) */
  }
</style>

<iframe
  class="codepost-frame"
  src="https://codepost.cs.rutgers.edu/…"
  allow="clipboard-read; clipboard-write; fullscreen"
  title="codePost"
></iframe>
```

If the embedding page keeps its own fixed header (say 64px tall), subtract it:
`height: calc(100dvh - 64px);`.

## Anti-patterns

- **Fixed pixel heights** (`height: 1200px`): on small screens the iframe overflows the
  viewport and codePost's bottom bars land below the fold with no way to scroll to them.
- **`height: 100%` on the iframe without sizing every ancestor**: percentage heights
  resolve to `auto` unless the whole chain (`html`, `body`, wrappers) has a height.
- **Placing the iframe in a page that scrolls**: produces double scrollbars, and
  bottom-anchored codePost UI tracks the iframe's box rather than what the visitor sees.
- **`100vh` instead of `100dvh`** on mobile: `100vh` ignores the browser's collapsing URL
  bar, cutting off the bottom by the bar's height until the user scrolls.
