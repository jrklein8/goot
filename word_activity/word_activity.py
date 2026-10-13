"""
word_activity.py - Simulates a person writing in Microsoft Word.

It only acts while a Word window is the active foreground window. Anything
else in front and it idles.

Behaviour model (what a real person does):
  * Types continuous prose, sentence after sentence, paragraph after
    paragraph, at a realistic words-per-minute with natural rhythm: faster on
    easy runs, pauses after commas and full stops, longer pauses to think.
  * Makes occasional adjacent-key typos and backspaces to fix them, sometimes
    only noticing a few characters later. Sometimes deletes the last word or
    two and rephrases.
  * Occasionally goes back a few words with the keyboard, swaps a word for a
    synonym, then returns to the end and carries on.
  * Takes reading breaks: scrolls up, reads for a while, drifts the mouse,
    scrolls back, resumes.
  * Moves the mouse along curved paths with slight overshoot, not straight
    lines, and mostly leaves it alone while typing.

Controls
--------
  * Hold ESC for about a second                    -> quit
  * Fling the mouse to the top-left screen corner  -> emergency stop
  * Moving the mouse yourself pauses it for 10 s.

Usage
-----
  word_activity.exe                  # defaults (typing speed picked 55-80 wpm)
  word_activity.exe --wpm 55         # fixed typing speed
  word_activity.exe --breaks 2       # twice as long / frequent thinking pauses
  word_activity.exe --mouse-only     # never types (mouse, scroll, clicks only)
  word_activity.exe --autosave       # press Ctrl+S every few minutes
                                     # (document must already be saved to a file)
"""

import argparse
import math
import random
import sys
import time
from datetime import datetime

import pyautogui  # import first: it makes the process DPI-aware
import win32api
import win32gui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0

VK_ESCAPE = 0x1B

# --------------------------------------------------------------------------- #
# Text generation
# --------------------------------------------------------------------------- #
from collections import deque

OPENERS = [
    "As discussed,", "Going forward,", "At this stage,", "For context,",
    "In addition,", "Based on the latest review,", "To keep things on track,",
    "As a next step,", "In the meantime,", "Overall,", "Looking ahead,",
    "From what we have seen so far,", "On balance,", "In practice,",
    "Following the call yesterday,", "With that in mind,", "Separately,",
    "As things stand,", "After some discussion,", "For the time being,",
    "Given the current timeline,", "In light of the feedback,",
]
SUBJECTS = [
    "the team", "the project", "our current timeline", "the proposal",
    "the client", "the working group", "this draft", "the budget",
    "this phase of the work", "the vendor", "the review process",
    "the updated plan", "each workstream", "the steering committee",
    "the finance team", "the design lead", "the onboarding process",
    "the reporting cadence", "the pilot group", "our main supplier",
    "the migration", "the rollout", "the support team", "the new process",
    "the leadership team", "the analysis", "the second phase", "procurement",
    "the training material", "the handover", "the testing schedule",
]
VERBS = [
    "needs to", "should", "will", "is expected to", "may need to",
    "plans to", "continues to", "has agreed to", "is likely to",
    "is on track to", "has started to", "intends to", "still has to",
    "was asked to", "is well placed to", "ought to", "is unlikely to",
]
OBJECTS = [
    "review the outstanding items", "finalize the scope",
    "confirm the delivery dates", "update the risk register",
    "align on priorities", "circulate the revised document",
    "address the open questions", "track progress against the plan",
    "prepare a short summary", "evaluate the remaining options",
    "capture the key decisions", "clarify ownership of each task",
    "revisit the assumptions", "document the agreed approach",
    "consolidate the feedback", "reduce the number of handoffs",
    "simplify the approval steps", "validate the numbers",
    "set up a recurring check-in", "close out the remaining actions",
    "share an updated forecast", "walk through the findings",
    "test the new workflow", "agree on a fallback option",
    "confirm the resourcing", "pull together the supporting data",
    "flag any dependencies early", "refine the success criteria",
    "shortlist the candidate tools", "map out the transition period",
]
TAILS = [
    "before the end of the week", "ahead of the next checkpoint",
    "once feedback is received", "as part of the next iteration",
    "with input from stakeholders", "so that nothing is missed",
    "in line with the original brief", "and report back on any blockers",
    "by the end of the month", "before the next review", "over the coming days",
    "without adding to the overall cost", "while the details are still fresh",
    "as soon as the data is available", "to avoid any surprises later",
    "given how much has changed", "with minimal disruption",
    "early next week", "in the next few days", "before anything is committed",
]
CONNECTORS = [", and ", ", but ", " so that ", ", which means ", "; however, ",
              ", although ", ", provided that ", " because "]
FOLLOWUPS = [
    "this should not affect the overall schedule",
    "some of the details are still being confirmed",
    "we will need to revisit this once the numbers are in",
    "the impact on the budget is expected to be minimal",
    "it is worth flagging this early rather than later",
    "further discussion may be required",
    "there is still some flexibility in the timeline",
    "the remaining risks are being tracked separately",
    "the exact sequencing is still open",
    "nothing has been finalized yet",
    "we are not expecting any pushback",
    "the cost side is largely understood",
    "the earlier estimate looks optimistic",
    "most of the groundwork is already done",
    "this depends on availability over the next fortnight",
    "the underlying assumptions have not changed",
]
NOUNS = [
    "open questions", "action items", "dependencies", "risks", "assumptions",
    "outstanding approvals", "minor issues", "follow-ups", "edge cases",
    "unresolved comments", "requirements", "moving parts", "gaps in the data",
    "loose ends", "decisions still pending",
]
QUANT = ["a few", "several", "two or three", "a handful of", "a number of",
         "still some", "only a couple of", "quite a few", "a small number of"]
CLAUSES = [
    "that need to be worked through", "which we should be able to close quickly",
    "that came out of the last review", "that are worth calling out here",
    "that depend on the vendor", "that the team is already aware of",
    "which are covered in more detail below", "that were raised by the client",
    "that could shift the timeline", "that need an owner",
    "which we will pick up at the next meeting", "that are unlikely to cause problems",
]
CONDITIONS = [
    "If the approvals come through on time", "If the numbers hold up",
    "Assuming there are no further changes", "If the pilot goes well",
    "Provided the vendor delivers as planned", "If resourcing stays as it is",
    "Once the outstanding items are cleared", "If we can agree the scope this week",
    "Unless something unexpected comes up", "As long as the data is reliable",
]
OUTCOMES = [
    "we should be in a good position for the next phase",
    "the remaining work is fairly straightforward",
    "we can start the rollout as planned",
    "the timeline should hold",
    "there is room to bring some of the later work forward",
    "we can close this out without further escalation",
    "the rest should follow fairly quickly",
    "the original plan still looks achievable",
    "we should be able to keep the current dates",
    "the impact will be limited to the second phase",
]
LIST_ITEMS = [
    "the revised timeline", "the budget summary", "the risk register",
    "stakeholder feedback", "the resourcing plan", "the test results",
    "open vendor questions", "the communication plan", "the training schedule",
    "the handover checklist", "the updated requirements", "the draft agenda",
    "the pilot findings", "the cost breakdown", "the dependency map",
]
LIST_LEADS = [
    "Key items for this week include", "The main areas of focus are",
    "Topics for the next meeting include", "The pack will cover",
    "Items still to be reviewed include", "The main inputs at this point are",
    "Areas that need attention include", "For reference, the attachments include",
]
BANK = [
    "The main goal for this week is to close out the remaining action items.",
    "Feedback from the last round of reviews has been incorporated below.",
    "A few points still need clarification before we can move forward.",
    "The current estimate assumes no major changes to the requirements.",
    "We expect to have a clearer picture after the next status meeting.",
    "Please note that the dates below are provisional and subject to change.",
    "The following section summarises the key risks and how they are being managed.",
    "Most of the outstanding work is concentrated in the second phase.",
    "There are no significant blockers at the moment.",
    "This will be reviewed again once the remaining inputs are available.",
    "The approach outlined here is consistent with what was agreed previously.",
    "Any changes to scope should go through the usual approval process.",
    "It would be useful to get a view from the wider team before committing.",
    "The earlier draft has been shortened to keep the focus on decisions.",
    "Nothing in the latest figures changes the overall picture.",
    "The next step is to agree owners and dates for each item.",
    "Some of this is still a work in progress and will be updated as we go.",
    "The comparison with last quarter is included for reference.",
    "This section is intended as a starting point for discussion.",
    "We have kept the structure the same as the previous version for consistency.",
    "The feedback so far has been broadly positive.",
    "A more detailed breakdown can be provided on request.",
    "The remaining effort is mostly coordination rather than new work.",
    "It is worth noting that the scope has grown slightly since the kickoff.",
    "The team has done a good job of keeping things moving.",
    "No decision is needed on this yet, but it is worth being aware of.",
    "This is a summary of where things stand as of today.",
    "The plan below reflects the latest thinking and is open to comment.",
]
HEADINGS = [
    "Summary", "Next steps", "Current status", "Open items", "Key risks",
    "Background", "Progress this week", "Decisions needed", "Timeline",
    "Notes from the meeting", "Outstanding actions", "Recommendations",
    "Scope", "Dependencies", "Points for discussion",
]
REMARKS = [
    "More on this below.", "Details to follow.", "This is still being worked through.",
    "No change since last time.", "Happy to discuss.", "This remains a priority.",
    "To be confirmed.", "Timing is still open.", "Nothing further on this for now.",
    "Worth keeping an eye on.", "This is covered in the next section.",
]
SYNONYMS = {
    "review": "revisit", "update": "revise", "confirm": "verify",
    "short": "brief", "latest": "recent", "finalize": "complete",
    "address": "resolve", "prepare": "draft", "track": "monitor",
    "evaluate": "assess", "team": "group", "project": "initiative",
    "client": "customer", "timeline": "schedule", "summary": "overview",
    "progress": "status", "plan": "roadmap", "key": "main",
    "current": "existing", "remaining": "outstanding", "items": "points",
    "options": "alternatives", "approach": "method", "questions": "issues",
    "quickly": "promptly", "minor": "small", "main": "primary",
    "useful": "helpful", "agreed": "confirmed", "start": "begin",
}

ADJACENT = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh",
    "u": "yij", "i": "uok", "o": "ipl", "p": "ol", "a": "qsz", "s": "awdz",
    "d": "sefc", "f": "drgv", "g": "fthb", "h": "gyjn", "j": "hukm",
    "k": "jil", "l": "kop", "z": "asx", "x": "zsdc", "c": "xdfv",
    "v": "cfgb", "b": "vghn", "n": "bhjm", "m": "njk",
}

_recent_parts: deque = deque(maxlen=60)
_recent_sentences: deque = deque(maxlen=80)


def pick(pool):
    """Random choice that avoids anything used recently."""
    c = random.choice(pool)
    for _ in range(8):
        if c not in _recent_parts:
            break
        c = random.choice(pool)
    _recent_parts.append(c)
    return c


def _cap(s: str) -> str:
    return s[0].upper() + s[1:]


def _build() -> str:
    r = random.random()
    if r < 0.16:
        return pick(BANK)
    if r < 0.46:       # [opener] subject verb object [tail] [, connector followup]
        parts = [pick(SUBJECTS), pick(VERBS), pick(OBJECTS)]
        if random.random() < 0.55:
            parts.append(pick(TAILS))
        if random.random() < 0.45:
            parts.insert(0, pick(OPENERS))
        s = " ".join(parts)
        if random.random() < 0.3:
            s += pick(CONNECTORS) + pick(FOLLOWUPS)
        return _cap(s) + "."
    if r < 0.60:       # first person
        we = random.choice(["We", "We", "I", "The team and I", "We still", "We also"])
        verb = random.choice(["need to", "should", "plan to", "will", "expect to",
                              "would like to", "may have to", "have started to", "want to"])
        s = f"{we} {verb} {pick(OBJECTS)}"
        if random.random() < 0.6:
            s += " " + pick(TAILS)
        return s + "."
    if r < 0.72:       # there are N things that ...
        return _cap(f"there are {pick(QUANT)} {pick(NOUNS)} {pick(CLAUSES)}.")
    if r < 0.84:       # conditional
        return f"{pick(CONDITIONS)}, {pick(OUTCOMES)}."
    if r < 0.93:       # list sentence
        items = random.sample(LIST_ITEMS, random.randint(2, 4))
        joiner = ", and " if len(items) > 2 else " and "
        body = ", ".join(items[:-1]) + joiner + items[-1]
        return f"{pick(LIST_LEADS)} {body}."
    return pick(REMARKS)


def make_sentence() -> str:
    s = _build()
    for _ in range(6):
        if s not in _recent_sentences:
            break
        s = _build()
    _recent_sentences.append(s)
    return s


def make_heading() -> str:
    return pick(HEADINGS)


# --------------------------------------------------------------------------- #
# Logging / Word detection
# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def is_word_window(hwnd: int) -> bool:
    if not hwnd or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        return False
    cls = win32gui.GetClassName(hwnd)
    title = win32gui.GetWindowText(hwnd)
    return cls == "OpusApp" or title.endswith(" - Word") or title.endswith(" - Microsoft Word")


def word_rect():
    """Rect of the Word window if it is the foreground window, else None."""
    hwnd = win32gui.GetForegroundWindow()
    if not is_word_window(hwnd):
        return None
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    if r - l < 400 or b - t < 300:
        return None
    return l, t, r, b


def page_zone(rect):
    """Part of the window where clicking is harmless: the page body."""
    l, t, r, b = rect
    w, h = r - l, b - t
    return int(l + w * 0.22), int(t + h * 0.38), int(r - w * 0.22), int(b - h * 0.12)


def rand_in(zone):
    l, t, r, b = zone
    return random.randint(l, r), random.randint(t, b)


# --------------------------------------------------------------------------- #
# Quit / pause plumbing
# --------------------------------------------------------------------------- #
class Quit(Exception):
    pass


class FocusLost(Exception):
    pass


def esc_down() -> bool:
    return bool(win32api.GetAsyncKeyState(VK_ESCAPE) & 0x8000)


def check_quit() -> None:
    """Raise Quit if ESC is held for ~0.8 s."""
    if not esc_down():
        return
    start = time.time()
    while time.time() - start < 0.8:
        if not esc_down():
            return
        time.sleep(0.05)
    raise Quit


def check_focus() -> None:
    if word_rect() is None:
        raise FocusLost


def nap(seconds: float, need_focus: bool = True) -> None:
    """Sleep while polling ESC (and Word focus if asked)."""
    end = time.time() + seconds
    while time.time() < end:
        check_quit()
        if need_focus:
            check_focus()
        time.sleep(min(0.1, max(0.0, end - time.time())))


# --------------------------------------------------------------------------- #
# Mouse
# --------------------------------------------------------------------------- #
def human_move(x2: int, y2: int) -> None:
    """Move along a curved path with variable speed and a little overshoot."""
    x1, y1 = pyautogui.position()
    dist = math.hypot(x2 - x1, y2 - y1)
    if dist < 2:
        return
    # Two control points offset sideways from the straight line
    nx, ny = -(y2 - y1) / dist, (x2 - x1) / dist            # unit normal
    bend1 = random.uniform(-0.25, 0.25) * dist
    bend2 = random.uniform(-0.15, 0.15) * dist
    c1 = (x1 + (x2 - x1) * 0.3 + nx * bend1, y1 + (y2 - y1) * 0.3 + ny * bend1)
    c2 = (x1 + (x2 - x1) * 0.7 + nx * bend2, y1 + (y2 - y1) * 0.7 + ny * bend2)
    steps = max(10, int(dist / 6))
    duration = random.uniform(0.25, 0.6) + dist / 2200
    for i in range(1, steps + 1):
        t = i / steps
        t = t * t * (3 - 2 * t)                              # ease in-out
        u = 1 - t
        x = u**3 * x1 + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * x2
        y = u**3 * y1 + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * y2
        pyautogui.moveTo(int(x), int(y), _pause=False)
        time.sleep(duration / steps * random.uniform(0.6, 1.4))
    if random.random() < 0.3:                                # overshoot + settle
        ox, oy = x2 + random.randint(-6, 6), y2 + random.randint(-4, 4)
        pyautogui.moveTo(ox, oy, _pause=False)
        time.sleep(random.uniform(0.05, 0.15))
        pyautogui.moveTo(x2, y2, _pause=False)


def mouse_drift() -> None:
    """Tiny unconscious hand movement."""
    x, y = pyautogui.position()
    human_move(x + random.randint(-25, 25), y + random.randint(-15, 15))


def move_off_text(rect) -> None:
    """People park the mouse to the side of what they are typing."""
    l, t, r, b = rect
    w, h = r - l, b - t
    side = random.choice([(l + w * 0.05, l + w * 0.18), (r - w * 0.18, r - w * 0.05)])
    human_move(random.randint(int(side[0]), int(side[1])),
               random.randint(int(t + h * 0.35), int(b - h * 0.15)))


# --------------------------------------------------------------------------- #
# Typing
# --------------------------------------------------------------------------- #
class Typist:
    def __init__(self, wpm: float, breaks: float):
        self.base = 60.0 / (wpm * 5)          # seconds per character
        self.breaks = breaks
        self.fatigue = 1.0

    def delay(self, ch: str, prev: str) -> float:
        d = random.lognormvariate(math.log(self.base * self.fatigue), 0.35)
        if ch == " ":
            d += random.uniform(0.02, 0.10)
        if prev in ".!?":
            d += random.uniform(0.35, 1.3) * self.breaks
        elif prev in ",;:":
            d += random.uniform(0.12, 0.45) * self.breaks
        if ch.isupper():
            d += 0.05
        return d

    def key(self, ch: str) -> None:
        pyautogui.write(ch, _pause=False)

    def type_word_boundary_events(self, words_done: list) -> None:
        """Things that happen between words."""
        r = random.random()
        if r < 0.05 * self.breaks:                    # think
            nap(random.uniform(0.7, 2.8) * self.breaks)
        elif r < 0.07 and len(words_done) >= 2 and all(w.isalpha() for w in words_done[-2:]):
            n = random.randint(1, 2)                  # delete last 1-2 words, rephrase
            nap(random.uniform(0.4, 1.2))
            for _ in range(n):
                pyautogui.hotkey("ctrl", "backspace", _pause=False)
                time.sleep(random.uniform(0.12, 0.3))
            redo = words_done[-n:]
            del words_done[-n:]
            nap(random.uniform(0.3, 1.0))
            for w in redo:
                self.type_word(w, words_done)
                self.key(" ")
                time.sleep(self.delay(" ", w[-1]))
        elif r < 0.085 and len(words_done) >= 4 and all(w.isalpha() for w in words_done):
            # go back a few words, swap one for a synonym (or retype it), return
            k = random.randint(2, min(len(words_done) - 1, 8))
            target = words_done[-k]
            repl = SYNONYMS.get(target.lower(), target)
            if target[0].isupper():
                repl = repl.capitalize()
            nap(random.uniform(0.5, 1.5))
            for _ in range(k):
                pyautogui.hotkey("ctrl", "left", _pause=False)
                time.sleep(random.uniform(0.06, 0.16))
            pyautogui.hotkey("ctrl", "shift", "right", _pause=False)
            nap(random.uniform(0.3, 0.9))
            for ch in repl + " ":
                self.key(ch)
                time.sleep(self.delay(ch, "a"))
            words_done[-k] = repl
            nap(random.uniform(0.2, 0.6))
            pyautogui.hotkey("ctrl", "end", _pause=False)
            time.sleep(random.uniform(0.15, 0.4))

    def type_word(self, word: str, words_done: list) -> None:
        prev = " "
        pending_fix = 0          # characters typed after a typo before noticing
        i = 0
        while i < len(word):
            check_quit()
            check_focus()
            ch = word[i]
            # typo?
            if ch.lower() in ADJACENT and random.random() < 0.03:
                wrong = random.choice(ADJACENT[ch.lower()])
                if ch.isupper():
                    wrong = wrong.upper()
                self.key(wrong)
                time.sleep(self.delay(wrong, prev))
                # notice now, or after 1-3 more characters
                room = len(word) - i - 1
                extra = 0 if (room == 0 or random.random() < 0.6) else random.randint(1, min(3, room))
                for j in range(extra):
                    self.key(word[i + 1 + j])
                    time.sleep(self.delay(word[i + 1 + j], prev))
                time.sleep(random.uniform(0.25, 0.7))           # "oops"
                for _ in range(extra + 1):
                    pyautogui.press("backspace", _pause=False)
                    time.sleep(random.uniform(0.07, 0.15))
                time.sleep(random.uniform(0.1, 0.3))
                continue                                         # retype from ch
            self.key(ch)
            time.sleep(self.delay(ch, prev))
            prev = ch
            i += 1

    def type_sentence(self, sentence: str) -> None:
        words = sentence.split(" ")
        done: list = []
        for idx, w in enumerate(words):
            self.type_word(w, done)
            done.append(w)
            last = idx == len(words) - 1
            if not last:
                self.key(" ")
                time.sleep(self.delay(" ", w[-1]))
                self.type_word_boundary_events(done)
        # slow drift in speed over time, like a real person
        self.fatigue = min(1.25, max(0.85, self.fatigue + random.uniform(-0.03, 0.03)))


# --------------------------------------------------------------------------- #
# Session behaviours
# --------------------------------------------------------------------------- #
def click_into_page(rect) -> None:
    """Focus the document and jump the caret to the end of the text."""
    human_move(*rand_in(page_zone(rect)))
    time.sleep(random.uniform(0.08, 0.2))
    pyautogui.click(_pause=False)
    time.sleep(random.uniform(0.2, 0.5))
    pyautogui.hotkey("ctrl", "end", _pause=False)
    time.sleep(random.uniform(0.2, 0.5))


def reading_break(rect, breaks: float) -> None:
    """Scroll up, read for a while, fidget with the mouse, scroll back."""
    secs = random.uniform(6, 25) * breaks
    log(f"reading break ({secs:.0f}s)")
    human_move(*rand_in(page_zone(rect)))
    up = 0
    if random.random() < 0.7:
        up = random.randint(2, 7)
        for _ in range(up):
            pyautogui.scroll(random.choice([1, 1, 2]), _pause=False)
            time.sleep(random.uniform(0.08, 0.3))
    end = time.time() + secs
    while time.time() < end:
        nap(random.uniform(0.6, 2.5))
        r = random.random()
        if r < 0.25:
            mouse_drift()
        elif r < 0.32 and up:
            pyautogui.scroll(random.choice([-1, 1]), _pause=False)
    if up:
        for _ in range(up):
            pyautogui.scroll(-random.choice([1, 1, 2]), _pause=False)
            time.sleep(random.uniform(0.06, 0.2))
        time.sleep(random.uniform(0.3, 0.8))
    if random.random() < 0.5:
        click_into_page(rect)          # click back where they were
    else:
        pyautogui.hotkey("ctrl", "end", _pause=False)
        time.sleep(0.2)


def think(rect, breaks: float) -> None:
    secs = random.uniform(2.5, 9) * breaks
    log(f"thinking ({secs:.0f}s)")
    end = time.time() + secs
    while time.time() < end:
        nap(random.uniform(0.5, 1.8))
        if random.random() < 0.3:
            mouse_drift()


def wander_mouse(rect) -> None:
    """Idle hovering around the window (ribbon, margins), no clicking."""
    l, t, r, b = rect
    for _ in range(random.randint(1, 3)):
        human_move(random.randint(l + 20, r - 20), random.randint(t + 20, b - 20))
        nap(random.uniform(0.3, 1.5))
    move_off_text(rect)


def paragraph(rect, typist: Typist, breaks: float) -> None:
    if random.random() < 0.12:                 # occasional short heading line
        h = make_heading()
        typist.type_sentence(h)
        log(f"typed heading: {h}")
        pyautogui.press("enter", _pause=False)
        nap(random.uniform(0.5, 1.5))
    n = random.randint(2, 5)
    for i in range(n):
        s = make_sentence()
        typist.type_sentence(s)
        log(f"typed: {s}")
        if i < n - 1:
            typist.key(" ")
            time.sleep(typist.delay(" ", "."))
            r = random.random()
            if r < 0.14 * breaks:
                think(rect, breaks)
            elif r < 0.19:
                wander_mouse(rect)
    pyautogui.press("enter", _pause=False)
    time.sleep(random.uniform(0.3, 0.9))
    if random.random() < 0.5:
        pyautogui.press("enter", _pause=False)
        time.sleep(random.uniform(0.3, 0.9))


def mouse_only_round(rect, breaks: float) -> None:
    r = random.random()
    if r < 0.45:
        wander_mouse(rect)
    elif r < 0.75:
        reading_break(rect, breaks)
    elif r < 0.9:
        click_into_page(rect)
    else:
        think(rect, breaks)
    nap(random.uniform(1.5, 6) * breaks)


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Simulate a person writing in Word.")
    ap.add_argument("--wpm", type=float, default=None, help="typing speed (default: random 55-80)")
    ap.add_argument("--breaks", type=float, default=1.0,
                    help="multiplier for pause length/frequency (default 1.0)")
    ap.add_argument("--mouse-only", action="store_true", help="never type")
    ap.add_argument("--autosave", action="store_true",
                    help="press Ctrl+S every 3-8 minutes (document must already be saved)")
    args = ap.parse_args()

    wpm = args.wpm or random.uniform(55, 80)
    breaks = max(0.2, args.breaks)
    typist = Typist(wpm, breaks)

    log(f"Word activity simulator started. typing speed ~{wpm:.0f} wpm, breaks x{breaks:g}"
        + (", mouse only" if args.mouse_only else ""))
    log("Hold ESC ~1s to quit, or fling the mouse to the top-left corner.")
    log("Waiting for a Microsoft Word window to be in the foreground...")

    focused = False
    last_pos = pyautogui.position()
    next_save = time.time() + random.uniform(180, 480)
    paragraphs_since_break = 0

    try:
        while True:
            check_quit()
            rect = word_rect()
            if rect is None:
                if focused:
                    log("Word is not the active window - idle.")
                    focused = False
                nap(1.0, need_focus=False)
                last_pos = pyautogui.position()
                continue

            try:
                if not focused:
                    log("Word is active - settling in.")
                    nap(random.uniform(1.0, 3.0))
                    click_into_page(rect)
                    move_off_text(rect)
                    focused = True
                    last_pos = pyautogui.position()

                # Back off if the human is using the mouse
                cur = pyautogui.position()
                if abs(cur.x - last_pos.x) > 3 or abs(cur.y - last_pos.y) > 3:
                    log("Detected your mouse activity - pausing 10s.")
                    nap(10, need_focus=False)
                    focused = False       # re-click into page before continuing
                    continue

                if args.mouse_only:
                    mouse_only_round(rect, breaks)
                else:
                    paragraph(rect, typist, breaks)
                    paragraphs_since_break += 1
                    nap(random.uniform(0.8, 3.0) * breaks)
                    r = random.random()
                    if r < 0.35 * breaks or paragraphs_since_break >= 4:
                        reading_break(rect, breaks)
                        paragraphs_since_break = 0
                        move_off_text(rect)
                    elif r < 0.5:
                        think(rect, breaks)

                if args.autosave and time.time() >= next_save:
                    pyautogui.hotkey("ctrl", "s", _pause=False)
                    log("saved (Ctrl+S)")
                    next_save = time.time() + random.uniform(180, 480)
                    nap(random.uniform(1.0, 2.5))

                last_pos = pyautogui.position()

            except FocusLost:
                log("Word lost focus - idle.")
                focused = False
                last_pos = pyautogui.position()
            except pyautogui.FailSafeException:
                log("Fail-safe triggered (mouse in corner). Exiting.")
                return 0
    except (Quit, KeyboardInterrupt):
        pass

    log("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
