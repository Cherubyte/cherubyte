"""The page a person lands on to admit a machine.

Server-rendered rather than a route in the SPA. The link is printed on a
terminal and typed into a browser by somebody who may not have the panel open,
so it has to work as a plain page load with no client-side router involved. It
is also the one page in the panel whose whole job is to be visited from
somewhere else.

**Approving is a decision, so the page is built to support one.** It shows the
name the machine gave, where the request came from and when, and it says
plainly that none of that is verified — because none of it is, at the point
where the caller has no credential. What makes this safe is not the data on
the page; it is that the person reading it knows whether they just ran the
command.

The form posts to the API route with the session cookie the browser already
has, so the same role check guards it as everything else that changes state.
"""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models import iso_utc
from ..services import agents as agent_service
from .deps import current_account

router = APIRouter(tags=["agents"], include_in_schema=False)

_STYLE = """
:root { color-scheme: light dark; --fg: 23 23 23; --bg: 242 242 245;
        --card: 255 255 255; --muted: 101 101 106; --edge: 226 226 230; }
@media (prefers-color-scheme: dark) {
  :root { --fg: 237 237 240; --bg: 18 18 20; --card: 28 28 31;
          --muted: 150 150 158; --edge: 48 48 54; }
}
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center;
       background: rgb(var(--bg)); color: rgb(var(--fg));
       font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
.card { width: min(30rem, calc(100vw - 2rem)); background: rgb(var(--card));
        border-radius: 16px; padding: 28px 30px; margin: 2rem 0;
        box-shadow: 0 1px 2px rgb(0 0 0 / .06), 0 8px 30px rgb(0 0 0 / .06); }
h1 { font-size: 19px; margin: 0 0 6px; letter-spacing: -.01em; }
p { margin: 0 0 14px; color: rgb(var(--muted)); }
dl { display: grid; grid-template-columns: auto 1fr; gap: 8px 18px; margin: 20px 0;
     padding: 16px 0; border-top: 1px solid rgb(var(--edge));
     border-bottom: 1px solid rgb(var(--edge)); }
dt { color: rgb(var(--muted)); font-size: 13px; }
dd { margin: 0; font-size: 13px;
     font-family: ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; }
.code { font-size: 26px; letter-spacing: .12em; font-weight: 600;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
button { font: inherit; font-size: 14px; font-weight: 500; border: 0; cursor: pointer;
         border-radius: 10px; padding: 10px 18px; background: rgb(var(--fg));
         color: rgb(var(--bg)); }
button:hover { opacity: .88; }
.warn { font-size: 13px; color: rgb(var(--muted)); margin-top: 18px; }
.ok { font-size: 15px; }
"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} — Cherubyte</title><style>{_STYLE}</style></head>
<body><div class="card">{body}</div></body></html>"""
    )


@router.get("/a/{code}", response_class=HTMLResponse)
async def approval_page(
    code: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    account=Depends(current_account),
):
    row = await agent_service.find_device_code(session, code)
    if row is None:
        # One answer for expired, collected and never-existed. A page that
        # distinguished them would confirm which codes had been real.
        return _page(
            "Nothing to approve",
            "<h1>Nothing to approve</h1>"
            "<p>This code has expired, has already been used, or was never issued. "
            "Codes last ten minutes. Run the command again on the machine to get "
            "a new one.</p>",
        )

    if row.approved_at is not None:
        return _page(
            "Already approved",
            "<h1>Already approved</h1>"
            f"<p>{escape(row.name or 'The machine')} was approved. It should be "
            "reporting within a few seconds; you can close this page.</p>",
        )

    return _page(
        "Approve this machine",
        f"""<h1>Approve this machine?</h1>
<p>A machine is asking to join this panel and send it what it finds on the
network. Approve it only if you just started it yourself.</p>
<p class="code">{escape(row.code)}</p>
<dl>
  <dt>Calls itself</dt><dd>{escape(row.name or "unnamed")}</dd>
  <dt>Version</dt><dd>{escape(row.version or "unknown")}</dd>
  <dt>Asked from</dt><dd>{escape(row.source_ip or "unknown")}</dd>
  <dt>Asked at</dt><dd>{escape(iso_utc(row.created_at) or "")}</dd>
</dl>
<form method="post" action="/a/{escape(row.code)}/approve">
  <button type="submit">Approve and issue a key</button>
</form>
<p class="warn">The machine chose its own name and version, so neither is
proof of anything. What it gets is a key that can send reports to this panel
and read the configuration you set for it. It cannot read your devices, and
you can remove it at any time from Agents.</p>""",
    )


@router.post("/a/{code}/approve", response_class=HTMLResponse)
async def approve_from_page(
    code: str,
    session: AsyncSession = Depends(get_session),
    account=Depends(current_account),
):
    """Approve from the page.

    A form post rather than fetch, so the page needs no script and works on a
    browser that has just been handed a URL. The role check lives in the
    dependency, the same one the API route uses.
    """
    from ..models import AccountRole
    from .deps import _LEVEL

    if _LEVEL[account.role] < _LEVEL[AccountRole.editor]:
        return _page(
            "Not allowed",
            "<h1>Not allowed</h1><p>Admitting a machine needs an editor or admin "
            "account. Ask somebody with one to open this link.</p>",
        )

    row = await agent_service.approve_device_code(
        session, code, account_id=getattr(account, "id", 0)
    )
    if row is None:
        return RedirectResponse(f"/a/{code}", status_code=303)
    await session.commit()
    return _page(
        "Approved",
        f"<h1>Approved</h1><p class='ok'>{escape(row.name or 'The machine')} has been "
        "admitted and will pick up its key within a few seconds. You can close "
        "this page.</p>",
    )
