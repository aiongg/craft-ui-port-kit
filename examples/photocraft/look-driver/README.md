# PhotoCraft look driver

A worked example of the driver interface in [tools/look.md](../../../tools/look.md). It was used to compare PhotoCraft's production build with the port, one panel at a time.

| File | What it shows |
|---|---|
| `driver.py` | `start`, `shoot` and `stop` for PhotoCraft, on the kit's `control` and `display` helpers. The module docstring lists what is specific to PhotoCraft. |
| `LayersPanel.json` | The Layers panel's states file: the panel crop, a named setup (`sample`, the sample document every state shares), the reset sent before every state, and two states. |

To use it as a starting point for another app:

1. Copy `driver.py` next to your workspace's port.toml and set `look.driver` to it.
2. Change the command line in `start` to your app's flags for the control port, the token file and the folders automation may write and read.
3. Replace `clear_startup` with whatever your app shows at launch on a headless display, or remove it.
4. Keep the order in `shoot`: setup when it changed, reset, window size, theme, the state's steps, a short settle, the screenshot. One states file then drives production and the port alike.

Production needs the same control methods as the port before it can be driven ([process/09-look-and-behaviour.md](../../../process/09-look-and-behaviour.md), step 1). For PhotoCraft that was a local branch from the production release with the missing hooks added, built once.
