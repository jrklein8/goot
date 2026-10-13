# Contractor Estimator (rough draft)

Dark-themed web app for a small contracting / construction business in
Wilmington, NC. Built as a capabilities demo: estimate jobs with local
pricing, keep everything organized by job, and run a schedule that links to
the owner's own calendar.

## Run it

```
cd contractor-app
python -m pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 and sign in with the demo account:

    demo@example.com / demo1234

The demo account comes pre-loaded with five sample jobs and a week of
scheduled events. Create your own account from the "Create account" tab.

## What's in it

**Login** - email + password, hashed with Werkzeug, cookie sessions.
Every record is scoped to the signed-in user.

**Jobs** - the organizing unit. Each job has a client, address, type, status
(lead → estimating → quoted → approved → in progress → complete / lost), notes,
an estimate made of line items, and its own schedule. Status can be changed
inline from the job list.

**Calculators** - real material takeoffs priced from the Wilmington price
book, focused on what he actually does: deck (joists, beams, posts,
footings, decking, hangers, ties, rail, stairs), wall framing (studs,
plates, headers, nails, sheathing), drywall (board, mud, screws, finish),
painting, trim & doors (base, casing, crown, prehung doors, hardware), and
trade labor by the hour. Results update live and can be pushed into any
open job as a named group of line items (or spin up a new job).

**Estimate** - line items grouped by where they came from, with inline qty
and unit-cost edits, custom lines, category subtotals, NC sales tax on
materials only, contingency, and overhead + profit markup. Per-job overrides
for the percentages. A printable client proposal hides unit costs and shows
grouped scope pricing.

**Price book** - lumber, hardware, drywall, trim, paint, labor rates,
permits and disposal in one place with per-user overrides and a reset.
An **Add material** button lets him put in anything the built-ins don't
cover (his own section, unit, cost), and a **From price book** picker on
every job drops any material, built-in or his own, onto the estimate with
a quantity. Flags the Wilmington specifics: 7% sales tax, 130 mph wind
zone, deck permits, Type X in garages.

**Schedule** - month calendar with typed events (site visit, work day,
inspection, delivery, meeting), linked to jobs. A private `.ics` feed URL
lets him subscribe from Google Calendar, iPhone or Outlook so the schedule
shows up on his phone, and each event has an "Add to Google Calendar" link.

**Dashboard** - pipeline value, booked work, job status breakdown, what's
coming up.

## Pricing disclaimer

All prices in `pricing.py` are planning figures for a draft. They are in
the right neighborhood for the Wilmington market in 2026 but must be
checked against real supplier quotes and his actual labor costs before
anything goes to a client. The price book page is where he'd tune them.

## Stack

Flask + SQLite backend (`app.py`, `pricing.py`), vanilla JS single-page
frontend (`static/`). No build step. The database and session secret are
created in `data/` on first run and are gitignored.

## Obvious next steps for a real build

- Two-way Google Calendar sync via OAuth (events made on his phone flow back).
- Client-facing proposal e-sign and PDF email.
- Photo uploads per job, change orders, invoicing and deposits (Stripe).
- Crew accounts with limited permissions; time tracking against jobs.
- Supplier price import (CSV) to keep the price book current.
- Host it (Fly.io / Render / a $6 VPS) behind HTTPS with a real domain.
