# Word Activity Simulator

Simulates a person writing in Microsoft Word: continuous typing with natural
rhythm, typos and corrections, rereading, scrolling, and curved mouse
movement. It acts **only while a Word window is the active foreground
window**. When anything else is in front, it idles.

## Run

Double-click `dist\word_activity.exe`, or from a terminal:

```
word_activity.exe                 # typing speed picked at random (55-80 wpm)
word_activity.exe --wpm 55        # fixed typing speed
word_activity.exe --breaks 2      # longer and more frequent thinking pauses
word_activity.exe --breaks 0.5    # fewer pauses, more continuous typing
word_activity.exe --mouse-only    # never types: mouse, scroll and clicks only
word_activity.exe --autosave      # Ctrl+S every 3-8 min (doc must already be saved to a file)
```

Then click into your Word document. It settles in for a second or two, clicks
into the page, jumps to the end of the text, and starts writing.

## What it does

- **Writes prose** in paragraphs of 2 to 5 business-style sentences, with an
  occasional short heading line, drawn from eight sentence patterns and a
  vocabulary of about 450 words. It avoids reusing recent phrases. Typing runs at a
  realistic words-per-minute. Speed drifts slightly over time. It slows after
  commas and full stops and sometimes stops mid-sentence to think.
- **Makes typos** on adjacent keys about 3% of the time, then backspaces and
  fixes them. Sometimes it notices immediately, sometimes a few characters later.
- **Rephrases**: occasionally deletes the last word or two with Ctrl+Backspace
  and retypes them. Occasionally goes back a few words, selects one, swaps it for
  a synonym, and returns to the end.
- **Reading breaks**: scrolls up a few notches, reads for 6 to 25 seconds while
  the mouse drifts, scrolls back, clicks back into the page.
- **Mouse**: moves along curved paths with easing and slight overshoot. It parks
  the mouse to the side while typing, like a person does, and occasionally hovers
  around the window without clicking.
- **Clicks** only land on the page body. The ribbon, status bar and scrollbar
  are avoided so nothing can be toggled or closed.

Use a scratch document. It writes wherever the end of the text is.

## Stopping it

- **Hold ESC for about one second.**
- **Fling the mouse into the top-left corner** of the primary screen (emergency stop).
- Close the console window.

If you move the mouse yourself it pauses for 10 seconds, then clicks back into
the page and carries on.

## Rebuild the .exe from source

```
python -m pip install pyautogui pywin32 pyinstaller
python -m PyInstaller --onefile --console --name word_activity word_activity.py
```

Output lands in `dist\word_activity.exe`.
