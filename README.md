# Simple-Info

An information board for a spare screen, a TV or a Raspberry Pi. Switch
between full-screen **boards** of live information. Each board has its own
background, so you can tell at a glance what it's showing.

Boards so far:

1. **Weather.** A big clock, today's conditions, the next 12 hours and the
   week ahead, over a sky that matches the real weather and time of day.
   You'll see the sun, drifting clouds, rain, snow, fog, lightning, and
   stars and the moon at night.

Planned: sport results and tables, train departures and arrivals, currency
exchange rates, TV listings…

## Keys

| Key | What it does |
| --- | --- |
| ◀ ▶, Page Up / Down, Space / Tab | Previous / next board |
| 1–9 | Go to a board |
| C | Move through the boards by itself (on / off) |
| F / F11, double-click | Full screen (Esc to leave) |
| R | Refresh this board's information now |
| P | Preview each kind of weather (cycles back to live) |
| T | Preview dawn / day / dusk / night (cycles back to live) |
| S | Settings: location, units, board timing, display |
| Right-click | All of the above as a menu |

The bar of board names along the bottom shows up for a few seconds after
each switch or mouse move. You can click a name to go to that board.

To open straight into full screen, tick **Start in full screen** in
Settings → Display, or run `simple-info --fullscreen`.

## TV remote (HDMI-CEC)

On Linux (for example a Raspberry Pi behind the TV) the app registers with
the TV over HDMI, so the TV's own remote works:

| Button | Does |
| --- | --- |
| ◀ ▶ | Previous / next board |
| OK, Channel + | Next board |
| Back / Exit, Channel − | Previous board |
| 1–9 | Go to a board |
| Red | Move through the boards by itself (on / off) |
| Green, Info | Refresh now |
| Yellow / Blue | Weather / time-of-day previews |

This needs `cec-ctl` (package `v4l-utils`, which the .deb recommends) and a TV
with HDMI-CEC switched on. TV makers give it their own names: Samsung
"Anynet+", LG "SimpLink", Sony "Bravia Sync", Panasonic "VIERA Link" and so
on.

## Raspberry Pi

The release includes an arm64 `.deb` for 64-bit Raspberry Pi OS. On a Pi,
**Graphics: Automatic** chooses *Light*. In Light mode the moving background
is drawn at half resolution and 20 frames a second, and the words stay at
full sharpness. While the app is open it keeps the screen from blanking.

## Running from source

```bash
python3 -m venv venv
venv/bin/pip install -e . pytest
venv/bin/simple-info
venv/bin/pytest
```

## Data

Weather by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Your rough
location comes from [ipwho.is](https://ipwho.is/), unless you choose a
place in Settings.
