"""Production against port captures (tools/look.md).

Modules:
  states   states files: load, normalise per side, write from an area map section
  pixels   difference images, regions and crops (needs Pillow and numpy)
  page     the compare page of one panel and the index of every panel
  control  for drivers: launch a craft app with its control channel, send requests, take a screenshot
  display  for drivers: a private headless display on Linux
"""
