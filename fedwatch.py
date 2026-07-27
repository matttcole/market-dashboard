"""
fedwatch.py — Meeting-by-meeting Fed rate probabilities from 30-Day Fed Funds
futures (ZQ), replicating the CME FedWatch methodology.

WHY THIS WORKS
--------------
A ZQ contract for month M settles to 100 minus the *arithmetic average of the
daily effective fed funds rate (EFFR) over every calendar day in M*. So the
price of a contract tells you the market's expected average EFFR for that month.

If month M contains an FOMC rate change effective on day D, that average is a
weighted blend of the old rate (days 1..D-1) and the new rate (days D..N):

    avg = [(D-1)*r_old + (N-D+1)*r_new] / N

Everything else is bookkeeping: solve for r_new, chain month to month, and
distribute the implied move across 25bp buckets.

THE THREE THINGS THAT MAKE THIS ACCURATE
----------------------------------------
1. CLEAN MONTHS. A month with no FOMC effective date reads the post-meeting
   rate *directly* with no interpolation and no dependence on the prior chain.
   These are exact. We anchor on them wherever possible and only fall back to
   the split-month equation when we have to. This is the single biggest
   accuracy lever, because split-month solves amplify upstream error: the
   1/(N-D+1) coefficient blows up when a meeting lands late in the month.

2. EFFR BASIS. Futures settle to EFFR, but FedWatch reports *target range*
   probabilities. EFFR does not sit at the midpoint of the range — it drifts
   with repo conditions and reserve scarcity. We measure the basis live rather
   than hardcoding it, because it moves.

3. EFFECTIVE DATE != MEETING DATE. The FOMC announces at 14:00 ET on day two of
   the meeting; the new target takes effect the *following business day*. Using
   the announcement date shifts every day-count by one and quietly biases every
   probability. We compute the effective date properly.

USAGE
-----
    from fedwatch import FedWatch, Meeting
    import datetime as dt

    fw = FedWatch(
        current_lower=3.50,
        current_upper=3.75,
        effr=3.63,
        meetings=FOMC_2026_2027,
    )
    fw.add_contract(2026, 8, 96.375)   # Aug 2026 ZQ
    fw.add_contract(2026, 9, 96.405)   # Sep 2026 ZQ
    ...
    for r in fw.solve():
        print(r)
"""

from __future__ import annotations

import calendar
import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Iterable

STEP = 0.25  # standard FOMC increment, in percentage points


# --------------------------------------------------------------------------
# FOMC calendar
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Meeting:
    """A scheduled FOMC decision.

    `announcement` is the date the statement drops (day 2 of the meeting).
    The rate change takes effect the next business day.
    """
    announcement: dt.date
    has_sep: bool = False  # Summary of Economic Projections / dot plot

    @property
    def effective(self) -> dt.date:
        """First day the new target range applies."""
        d = self.announcement + dt.timedelta(days=1)
        while d.weekday() >= 5:  # Sat=5, Sun=6
            d += dt.timedelta(days=1)
        return d

    def __str__(self) -> str:
        tag = " (SEP)" if self.has_sep else ""
        return f"{self.announcement:%Y-%m-%d}{tag}"


# Verified against federalreserve.gov/monetarypolicy/fomccalendars.htm.
# 2027 dates are tentative until confirmed at the preceding meeting.
# Re-scrape this annually rather than trusting the hardcode.
FOMC_2026_2027: list[Meeting] = [
    Meeting(dt.date(2026, 1, 28)),
    Meeting(dt.date(2026, 3, 18), has_sep=True),
    Meeting(dt.date(2026, 4, 29)),
    Meeting(dt.date(2026, 6, 17), has_sep=True),
    Meeting(dt.date(2026, 7, 29)),
    Meeting(dt.date(2026, 9, 16), has_sep=True),
    Meeting(dt.date(2026, 10, 28)),
    Meeting(dt.date(2026, 12, 9), has_sep=True),
]


# --------------------------------------------------------------------------
# Contract month codes (CME standard)
# --------------------------------------------------------------------------

MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}


def zq_symbol(year: int, month: int, style: str = "yahoo") -> str:
    """Build a ZQ contract ticker.

    style='yahoo'    -> 'ZQQ26.CBT'
    style='barchart' -> 'ZQQ26'

    NOTE: verify the exact suffix your data source expects before relying on
    this. Vendors are inconsistent about the exchange suffix and the 2- vs
    4-digit year.
    """
    code = MONTH_CODES[month]
    yy = year % 100
    base = f"ZQ{code}{yy:02d}"
    return f"{base}.CBT" if style == "yahoo" else base


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

@dataclass
class MeetingOutcome:
    meeting: Meeting
    rate_before: float          # implied target midpoint entering the meeting
    rate_after: float           # implied target midpoint after the meeting
    move_bp: float              # implied change, basis points
    probabilities: dict[str, float]  # e.g. {'-25bp': 0.72, 'hold': 0.28}
    ranges: dict[str, float]    # e.g. {'3.25-3.50': 0.72, '3.50-3.75': 0.28}
    anchor: str                 # 'clean' | 'split' | 'assumed'

    def __str__(self) -> str:
        top = max(self.probabilities.items(), key=lambda kv: kv[1])
        parts = ", ".join(
            f"{k} {v:.1%}" for k, v in sorted(
                self.probabilities.items(), key=lambda kv: -kv[1]
            ) if v >= 0.005
        )
        return (
            f"{self.meeting.announcement:%b %d, %Y}  "
            f"{self.rate_before:.3f}% -> {self.rate_after:.3f}% "
            f"({self.move_bp:+.1f}bp)  [{self.anchor}]\n"
            f"    {parts}   << {top[0]}"
        )


# --------------------------------------------------------------------------
# Core solver
# --------------------------------------------------------------------------

class FedWatch:
    def __init__(
        self,
        current_lower: float,
        current_upper: float,
        effr: float,
        meetings: Iterable[Meeting],
        step: float = STEP,
        asof: dt.date | None = None,
    ):
        """
        current_lower / current_upper: the live target range, e.g. 3.50 / 3.75
        effr: the live effective fed funds rate print
        meetings: upcoming FOMC meetings (unsorted ok)
        asof: valuation date; defaults to today
        """
        self.lower = current_lower
        self.upper = current_upper
        self.midpoint = (current_lower + current_upper) / 2
        self.effr = effr
        self.step = step
        self.asof = asof or dt.date.today()

        # EFFR settles somewhere inside the target band, not at its midpoint.
        # Measure the offset rather than assuming it.
        self.basis = effr - self.midpoint

        self.meetings = sorted(meetings, key=lambda m: m.announcement)
        self.contracts: dict[tuple[int, int], float] = {}

    # ---- inputs ----------------------------------------------------------

    def add_contract(self, year: int, month: int, price: float) -> None:
        """Register a ZQ settlement/last price for a contract month."""
        if not 90 <= price <= 100:
            raise ValueError(
                f"ZQ price {price} out of plausible range - did you pass a rate?"
            )
        self.contracts[(year, month)] = price

    def implied_avg_target(self, year: int, month: int) -> float | None:
        """Market-implied average *target midpoint* for a contract month.

        Converts the futures-implied average EFFR into target-midpoint space
        by backing out the live basis.
        """
        price = self.contracts.get((year, month))
        if price is None:
            return None
        implied_avg_effr = 100.0 - price
        return implied_avg_effr - self.basis

    # ---- helpers ---------------------------------------------------------

    def _meetings_in(self, year: int, month: int) -> list[Meeting]:
        """Meetings whose *effective date* falls in this contract month."""
        return [
            m for m in self.meetings
            if m.effective.year == year and m.effective.month == month
        ]

    def _relevant_months(self) -> list[tuple[int, int]]:
        """Contract months from the current one through the last meeting."""
        if not self.meetings:
            return []
        start = (self.asof.year, self.asof.month)
        last = self.meetings[-1].effective
        out, (y, m) = [], start
        while (y, m) <= (last.year, last.month):
            out.append((y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out

    def _bucket(self, rate_after: float, rate_before: float) -> dict[str, float]:
        """Distribute an implied move across adjacent 25bp buckets.

        The futures market prices a single expected value; FedWatch converts
        that point estimate into a two-point distribution over the bracketing
        outcomes. A move of exactly -12.5bp reads as a 50/50 between hold and
        a 25bp cut.
        """
        move = rate_after - rate_before
        n = move / self.step

        lo = math.floor(round(n, 9))
        hi = lo + 1
        p_hi = round(n, 9) - lo

        if abs(p_hi) < 1e-9:          # lands exactly on a step
            dist = {lo: 1.0}
        elif abs(p_hi - 1) < 1e-9:
            dist = {hi: 1.0}
        else:
            dist = {lo: 1.0 - p_hi, hi: p_hi}

        return {self._label(k): v for k, v in dist.items() if v > 1e-9}

    @staticmethod
    def _label(steps: int) -> str:
        if steps == 0:
            return "hold"
        bp = int(round(steps * 25))
        return f"{bp:+d}bp"

    def _range_labels(
        self, dist: dict[str, float], rate_before: float
    ) -> dict[str, float]:
        """Translate step-labels into explicit target ranges."""
        # Reconstruct the band around the pre-meeting midpoint.
        half = (self.upper - self.lower) / 2
        out = {}
        for label, p in dist.items():
            steps = 0 if label == "hold" else int(label.replace("bp", "")) / 25
            mid = rate_before + steps * self.step
            out[f"{mid - half:.2f}-{mid + half:.2f}%"] = p
        return out

    # ---- the solve -------------------------------------------------------

    def solve(self) -> list[MeetingOutcome]:
        """Walk the contract strip and back out each meeting's implied move.

        Strategy: prefer clean months (no meeting) because they pin the rate
        exactly. Only use the split-month equation when a clean month isn't
        available downstream.
        """
        months = self._relevant_months()
        if not months:
            return []

        results: list[MeetingOutcome] = []
        rate_entering = self.midpoint

        for i, (y, m) in enumerate(months):
            avg = self.implied_avg_target(y, m)
            in_month = self._meetings_in(y, m)

            if not in_month:
                # Clean month. The whole-month average IS the prevailing rate.
                # Use it to re-anchor the chain and shed accumulated drift.
                if avg is not None:
                    rate_entering = avg
                continue

            if avg is None:
                # No contract for this month; we can't solve it. Carry forward.
                for mtg in in_month:
                    results.append(MeetingOutcome(
                        meeting=mtg,
                        rate_before=rate_entering,
                        rate_after=rate_entering,
                        move_bp=0.0,
                        probabilities={"hold": 1.0},
                        ranges=self._range_labels({"hold": 1.0}, rate_entering),
                        anchor="assumed",
                    ))
                continue

            n_days = calendar.monthrange(y, m)[1]

            if len(in_month) == 1:
                mtg = in_month[0]
                d = mtg.effective.day

                # Prefer the next clean month if we have it: it gives the
                # post-meeting rate directly, with none of the split-month
                # error amplification.
                nxt = months[i + 1] if i + 1 < len(months) else None
                clean_next = (
                    nxt is not None
                    and not self._meetings_in(*nxt)
                    and self.implied_avg_target(*nxt) is not None
                )

                if clean_next:
                    rate_after = self.implied_avg_target(*nxt)
                    anchor = "clean"
                else:
                    # avg = [(d-1)*r_before + (n-d+1)*r_after] / n
                    days_after = n_days - d + 1
                    if days_after <= 0:
                        rate_after = rate_entering
                        anchor = "assumed"
                    else:
                        rate_after = (
                            n_days * avg - (d - 1) * rate_entering
                        ) / days_after
                        anchor = "split"

                dist = self._bucket(rate_after, rate_entering)
                results.append(MeetingOutcome(
                    meeting=mtg,
                    rate_before=rate_entering,
                    rate_after=rate_after,
                    move_bp=(rate_after - rate_entering) * 100,
                    probabilities=dist,
                    ranges=self._range_labels(dist, rate_entering),
                    anchor=anchor,
                ))
                rate_entering = rate_after

            else:
                # Two meetings in one contract month: one equation, two
                # unknowns. Underdetermined. Resolve off the next clean month
                # and split the total move evenly, flagging it as assumed.
                nxt = months[i + 1] if i + 1 < len(months) else None
                target = (
                    self.implied_avg_target(*nxt)
                    if nxt and not self._meetings_in(*nxt)
                    else avg
                )
                total = target - rate_entering
                per = total / len(in_month)
                for mtg in in_month:
                    rate_after = rate_entering + per
                    dist = self._bucket(rate_after, rate_entering)
                    results.append(MeetingOutcome(
                        meeting=mtg,
                        rate_before=rate_entering,
                        rate_after=rate_after,
                        move_bp=per * 100,
                        probabilities=dist,
                        ranges=self._range_labels(dist, rate_entering),
                        anchor="assumed",
                    ))
                    rate_entering = rate_after

        return results

    # ---- convenience -----------------------------------------------------

    def cumulative_path(self) -> list[tuple[dt.date, float]]:
        """Implied target midpoint after each meeting — for charting."""
        return [(r.meeting.announcement, r.rate_after) for r in self.solve()]

    def summary(self) -> str:
        lines = [
            f"As of {self.asof:%Y-%m-%d}",
            f"Target range {self.lower:.2f}-{self.upper:.2f}%  "
            f"(mid {self.midpoint:.3f}%)",
            f"EFFR {self.effr:.3f}%  ->  basis {self.basis * 100:+.1f}bp",
            "",
        ]
        for r in self.solve():
            lines.append(str(r))
            lines.append("")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Self-test with synthetic prices (no network required)
# --------------------------------------------------------------------------

if __name__ == "__main__":
    # Scenario: range 3.50-3.75 (mid 3.625), EFFR 3.63.
    # Construct prices that encode a known answer so we can verify the solver
    # recovers it: full 25bp cut priced for September, nothing for July.
    fw = FedWatch(
        current_lower=3.50,
        current_upper=3.75,
        effr=3.63,
        meetings=FOMC_2026_2027,
        asof=dt.date(2026, 7, 27),
    )

    basis = fw.basis
    mid = 3.625

    def price_for(avg_target: float) -> float:
        return round(100.0 - (avg_target + basis), 4)

    # Jul: meeting effective Jul 30 -> 29 days at 3.625, 2 days at 3.625 (hold)
    fw.add_contract(2026, 7, price_for(mid))
    # Aug: clean month, still 3.625 -> confirms the July hold
    fw.add_contract(2026, 8, price_for(mid))
    # Sep: meeting effective Sep 17 -> 16 days @3.625, 14 days @3.375
    sep_avg = (16 * 3.625 + 14 * 3.375) / 30
    fw.add_contract(2026, 9, price_for(sep_avg))
    # Oct: clean until the Oct 29 effective date... actually Oct 28 announce
    # -> effective Oct 29, so Oct is a split month. Price a hold.
    oct_avg = (28 * 3.375 + 3 * 3.375) / 31
    fw.add_contract(2026, 10, price_for(oct_avg))
    # Nov: clean month at 3.375
    fw.add_contract(2026, 11, price_for(3.375))
    # Dec: meeting effective Dec 10 -> 9 days @3.375, 22 days @3.125
    dec_avg = (9 * 3.375 + 22 * 3.125) / 31
    fw.add_contract(2026, 12, price_for(dec_avg))

    print(fw.summary())

    # Assertions: did we recover what we encoded?
    out = {r.meeting.announcement.month: r for r in fw.solve()}
    assert abs(out[7].move_bp) < 0.5, f"July should be a hold, got {out[7].move_bp}"
    assert abs(out[9].move_bp + 25) < 0.5, f"Sep should be -25bp, got {out[9].move_bp}"
    assert abs(out[12].move_bp + 25) < 1.0, f"Dec should be -25bp, got {out[12].move_bp}"
    print("OK - solver recovered the encoded scenario.")
