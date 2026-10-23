# Simple-Info

An information board for a spare screen, a TV or a Raspberry Pi. Switch
between full-screen **boards** of live information. Each board has its own
background, so you can tell at a glance what it's showing.

Boards so far:

1. **Weather.** A big clock, today's conditions, the next 12 hours and the
   week ahead, over a sky that matches the real weather and time of day.
   You'll see the sun, drifting clouds, rain, snow, fog, lightning, and
   stars and the moon at night.

2. **Trains.** Live departures and arrivals for any station in Great
   Britain, shown on an amber dot-matrix board hanging in a Victorian train
   shed. As on a real platform, the next train gets a line that scrolls
   through its calling points, and its operator, length and any delay
   reason sit underneath. Late trains show in orange and cancellations in
   red. Station notices scroll along the bottom next to the clock. Choose
   the station in Settings: departures, arrivals, or both in turn
   (switching every 20 seconds). You can also show only the trains to or
   from another station. It refreshes every minute.

3. **Currency.** What one pound (or whichever currency you choose) buys
   abroad, on a banknote-green background with slowly turning guilloché
   rosettes. Each currency gets a card with its rate, the change on the day
   (green up, red down), a trend line for the last month, and the rate the
   other way round. Bitcoin and Ethereum can join in with their prices and
   their last week. In Settings you choose the base currency, which of
   about 30 currencies to show (up to 12), and their order.

4. **Sport.** Football, baseball, cricket and rugby. Each competition you
   follow gets a page, and the pages take turns every 20 seconds (▲ ▼ turn
   them by hand). Each page shows live games with the score and the minute
   or innings, the latest results and the next fixtures, next to the
   league table. Cricket shows scorecards instead, with the runs and
   wickets, overs and how the match stands. Each sport has its own
   floodlit stadium behind it: a football pitch, a rugby pitch with
   H-shaped posts, a cricket oval with the wicket, or a baseball diamond.
   While a game is on, its competition is checked every minute; the rest
   every 10 minutes. Choose the competitions in Settings → Sport: the
   Premier League, Championship, FA Cup, Scottish Premiership,
   Championship, League One and League Two, Champions and Europa League, La Liga, Bundesliga, Serie
   A, Ligue 1, MLS, the World Cup, Major League Baseball, international
   (or all) cricket, the Six Nations, Premiership Rugby, the URC,
   Champions Cup, Rugby Championship, Top 14, Super Rugby and rugby
   internationals. Pick a competition in that list to choose your
   favourite team in it: its matches and its row in the table are
   picked out in gold, and its games come first on each day.

5. **TV.** A TV guide grid for the next two and a half hours on your
   Freeview channels. A red line marks "now", and what's on now is lit up
   with a bar showing how far through it is. It sits on the glow of an old
   television set: soft colour bars, scanlines and the slow roll of the
   picture. Ten channels fit on a page; more go onto further pages, which
   take turns. Choose and order the channels in Settings → TV, from about
   200 (regional BBC One, ITV and STV included). It starts with the main
   channels as seen in the north of Scotland.

6. **News.** A page for each news feed you follow: the lead story with its
   picture and summary, and the next six headlines with theirs, each
   saying how long ago it was published. A red **LATEST** ticker along
   the bottom runs through the newest headlines from all your feeds. It
   sits in a newsroom, in front of a big wireframe globe that turns
   slowly. Choose and order the feeds in Settings → News: BBC News (top
   stories, UK, world, Scotland and its regions — including North East,
   Orkney & Shetland — England, Wales, Northern Ireland, politics,
   business, technology, science, health, entertainment), BBC Sport, Sky
   News and The Guardian. They're checked every 10 minutes.

## Keys

| Key | What it does |
| --- | --- |
| ◀ ▶, Page Up / Down, Space / Tab | Previous / next board |
| ▲ ▼ | Previous / next page (on boards with pages, like Sport) |
| 1–9 | Go to a board |
| C | Move through the boards by itself (on / off) |
| F / F11, double-click | Full screen (Esc to leave) |
| R | Refresh this board's information now |
| P | Preview each kind of weather (cycles back to live) |
| T | Preview dawn / day / dusk / night (cycles back to live) |
| S | Settings: units, display, weather location, train station, currencies, sport, TV channels, news |
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
| ▲ ▼ | Previous / next page |
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

Weather by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Train
times are National Rail Enquiries' live departure boards (Darwin), read
through the free [Huxley 2](https://huxley2.azurewebsites.net/) service, so
no sign-up is needed, and nothing but station codes is sent to it. With
your own free key from the [Rail Data Marketplace](https://raildata.org.uk/)
(the "Live Departure Board" product), put in Settings → Trains, departures
come straight from National Rail instead; the key is sent only to National
Rail, and Huxley 2 becomes the fallback. The train
board carries the "Powered by National Rail Enquiries" credit. Exchange rates are the European
Central Bank's daily reference rates, read through
[Frankfurter](https://frankfurter.dev/). Crypto prices come from
[CoinGecko](https://www.coingecko.com/). News comes from the BBC News, Sky News and Guardian RSS feeds. TV listings are the open-source
[Freeview EPG](https://github.com/dp247/Freeview-EPG), rebuilt twice a day and
downloaded at most every six hours. Sport comes from ESPN's public
scoreboards, except Scottish League One and Two (which ESPN no longer
keeps up to date): those come from BBC Sport. Your rough
location comes from [ipwho.is](https://ipwho.is/), unless you choose a
place in Settings.
