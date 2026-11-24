"""Production against port captures (tools/look.md).

Modules:
  states   states files: load, normalise per side, write from an area map section
  pixels   difference images, regions and crops (needs Pillow and numpy)
  page     the compare page of one panel and the index of every panel
  differences  the differences file: the lead's rows, their class and outcome
  control  for drivers: launch a craft app with its control channel, send requests, take a screenshot
  procs    the Xvfb servers and apps of a run, recorded so the next run stops those of a killed one
  display  for drivers: a private headless display on Linux
  xinput   for drivers and hand-driven rows: real X input through XTEST (needs python-xlib)
"""
