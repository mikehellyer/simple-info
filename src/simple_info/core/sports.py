"""Sport: results, fixtures, live scores and league tables.

Everything comes from ESPN's public scoreboard feeds (no sign-up), which
cover football (soccer), baseball, rugby union and cricket. Each
competition has a scoreboard and a calendar of the days it plays on (or,
for baseball, of the days it doesn't), so we fetch the latest couple of
match days for results and the next couple for fixtures, plus the table.
Cricket comes from ESPN's cricket score panel instead: what's on now and
just finished, worldwide, which we narrow to internationals by default.

Everything that touches the network returns None on failure rather than
raising: the board keeps showing the last scores it had.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from simple_info.core.http import SSL_CONTEXT

TIMEOUT_SECONDS = 10
SITE_URL = "https://site.api.espn.com/apis/site/v2/sports"
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports"
CRICKET_URL = "https://site.web.api.espn.com/apis/site/v2/sports/cricket/scorepanel"
PAST_DAYS = 2  # match days of results
NEXT_DAYS = 2  # match days of fixtures

FOOTBALL, BASEBALL, CRICKET, RUGBY = "soccer", "baseball", "cricket", "rugby"
SPORT_NAMES = {FOOTBALL: "Football", BASEBALL: "Baseball", CRICKET: "Cricket", RUGBY: "Rugby"}
PRE, LIVE, DONE = "pre", "in", "post"


@dataclass(frozen=True)
class Competition:
    key: str  # "soccer/eng.1": the sport and ESPN's league id
    name: str

    @property
    def sport(self) -> str:
        return self.key.split("/", 1)[0]

    @property
    def league(self) -> str:
        return self.key.split("/", 1)[1]


COMPETITIONS = [
    Competition("soccer/eng.1", "Premier League"),
    Competition("soccer/eng.2", "EFL Championship"),
    Competition("soccer/eng.fa", "FA Cup"),
    Competition("soccer/sco.1", "Scottish Premiership"),
    Competition("soccer/sco.2", "Scottish Championship"),
    Competition("soccer/uefa.champions", "Champions League"),
    Competition("soccer/uefa.europa", "Europa League"),
    Competition("soccer/esp.1", "La Liga"),
    Competition("soccer/ger.1", "Bundesliga"),
    Competition("soccer/ita.1", "Serie A"),
    Competition("soccer/fra.1", "Ligue 1"),
    Competition("soccer/usa.1", "MLS"),
    Competition("soccer/fifa.world", "World Cup"),
    Competition("baseball/mlb", "Major League Baseball"),
    Competition("cricket/international", "International cricket"),
    Competition("cricket/all", "Cricket worldwide"),
    Competition("rugby/180659", "Six Nations"),
    Competition("rugby/267979", "Premiership Rugby"),
    Competition("rugby/270557", "United Rugby Championship"),
    Competition("rugby/271937", "Champions Cup"),
    Competition("rugby/244293", "The Rugby Championship"),
    Competition("rugby/289234", "Rugby internationals"),
    Competition("rugby/270559", "Top 14"),
    Competition("rugby/242041", "Super Rugby Pacific"),
    Competition("rugby/164205", "Rugby World Cup"),
]
BY_KEY = {c.key: c for c in COMPETITIONS}
DEFAULT_KEYS = ["soccer/eng.1", "soccer/sco.1", "baseball/mlb", "cricket/international", "rugby/180659",
                "rugby/267979", "rugby/270557"]


@dataclass
class Team:
    name: str
    short: str  # "CEL"
    colour: str = ""  # hex, "0046ff", or "" if ESPN hasn't one
    score: str = ""  # "2", or for cricket "241 & 98/5 (36 ov)"
    winner: bool = False


@dataclass
class Match:
    id: str
    start: str  # ISO time, UTC
    state: str  # PRE, LIVE or DONE
    detail: str  # "FT", "62'", "Top 7th", "Stumps"…
    home: Team
    away: Team
    summary: str = ""  # cricket: "Victoria require 173 runs"
    competition: str = ""  # cricket: the series or tournament
    kind: str = ""  # cricket: "Test", "ODI", "T20I"…

    def local_start(self) -> datetime:
        return datetime.fromisoformat(self.start.replace("Z", "+00:00")).astimezone()


@dataclass
class Table:
    name: str
    columns: list[str]  # headings after the team, e.g. ["P", "W", "D", "L", "GD", "Pts"]
    rows: list[tuple[int, Team, list[str]]]  # (position, team, values)


@dataclass
class CompetitionData:
    key: str
    name: str
    matches: list[Match]
    tables: list[Table] = field(default_factory=list)
    fetched_at: float = 0.0

    @property
    def sport(self) -> str:
        return self.key.split("/", 1)[0]

    @property
    def live(self) -> list[Match]:
        return [m for m in self.matches if m.state == LIVE]

    @property
    def results(self) -> list[Match]:
        """Finished matches, the latest first."""
        return sorted((m for m in self.matches if m.state == DONE), key=lambda m: m.start, reverse=True)

    @property
    def fixtures(self) -> list[Match]:
        """Matches still to come, the soonest first."""
        return sorted((m for m in self.matches if m.state == PRE), key=lambda m: m.start)


def _get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Info/1", "Accept": "application/json",
                                                   "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
            data = response.read()
    except OSError:
        return None
    try:
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        return json.loads(data.decode("utf-8"))
    except (OSError, ValueError, EOFError):
        return None


def _text(value) -> str:
    return "" if value is None else str(value).strip()


# --- scoreboards

def parse_team(c: dict) -> Team:
    team = c.get("team") or {}
    short = _text(team.get("shortDisplayName"))
    if not short or short == _text(team.get("abbreviation")):  # (cricket's "short" names are just the codes)
        short = _text(team.get("displayName") or team.get("name"))
    return Team(
        name=short or "?",
        short=_text(team.get("abbreviation"))[:5],
        colour=_text(team.get("color")).lstrip("#").lower(),
        score=_text(c.get("score")),
        winner=bool(c.get("winner")),
    )


def parse_event(e: dict) -> Optional[Match]:
    try:
        comp = (e.get("competitions") or [{}])[0]
        status = (e.get("status") or comp.get("status") or {})
        kind = status.get("type") or {}
        teams = comp.get("competitors") or []
        if len(teams) < 2:
            return None
        home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
        away = next((t for t in teams if t is not home), teams[1])
        state = kind.get("state") if kind.get("state") in (PRE, LIVE, DONE) else PRE
        summary = ""
        comp_status = comp.get("status")
        if isinstance(comp_status, dict):
            summary = _text(comp_status.get("summary"))
        klass = comp.get("class") if isinstance(comp.get("class"), dict) else {}
        return Match(
            id=_text(e.get("id")),
            start=_text(e.get("date") or comp.get("date")),
            state=state,
            detail=_text(kind.get("shortDetail") or kind.get("detail") or kind.get("description")),
            home=parse_team(home),
            away=parse_team(away),
            summary=summary,
            kind=_text(klass.get("generalClassCard")),
        )
    except (AttributeError, TypeError, IndexError):
        return None


def parse_scoreboard(payload: dict) -> list[Match]:
    return [m for m in (parse_event(e) for e in payload.get("events") or [] if isinstance(e, dict)) if m]


def _day(text: str) -> Optional[date]:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (AttributeError, ValueError):
        return None


def match_days(league: dict, today: date) -> tuple[list[date], list[date]]:
    """(the latest days with results, the next days with fixtures) from a
    league's calendar. Most leagues list the days they play on; baseball
    lists the days it doesn't (a "blacklist"), between its start and end."""
    calendar = [d for d in (_day(c) if isinstance(c, str) else None for c in league.get("calendar") or []) if d]
    if league.get("calendarIsWhitelist", True):
        days = sorted(set(calendar))
    else:
        start, end = _day(_text(league.get("calendarStartDate"))), _day(_text(league.get("calendarEndDate")))
        if not start or not end:
            return [], []
        skip = set(calendar)
        lo, hi = max(start, today - timedelta(days=30)), min(end, today + timedelta(days=30))
        days = [lo + timedelta(days=i) for i in range((hi - lo).days + 1) if lo + timedelta(days=i) not in skip]
    past = [d for d in days if d <= today][-PAST_DAYS:]
    future = [d for d in days if d > today][:NEXT_DAYS]
    return past, future


# --- league tables

_COLUMNS = {
    FOOTBALL: [("P", "gamesPlayed"), ("W", "wins"), ("D", "ties"), ("L", "losses"), ("GD", "pointDifferential"), ("Pts", "points")],
    RUGBY: [("P", "gamesPlayed"), ("W", "gamesWon"), ("D", "gamesDrawn"), ("L", "gamesLost"), ("PD", "pointsDifference"),
            ("BP", "bonusPoints"), ("Pts", "points")],
    BASEBALL: [("W", "wins"), ("L", "losses"), ("PCT", "winPercent"), ("GB", None)],
}


def _num(text: str) -> float:
    try:
        return float(text.replace("+", ""))
    except (AttributeError, ValueError):
        return 0.0


def parse_standings(payload: dict, sport: str) -> list[Table]:
    columns = _COLUMNS.get(sport)
    if not columns:
        return []
    groups = payload.get("children") or ([payload] if payload.get("standings") else [])
    tables = []
    for g in groups:
        entries = ((g.get("standings") or {}).get("entries")) or []
        rows = []
        for e in entries:
            stats = {s.get("name"): _text(s.get("displayValue")) for s in e.get("stats") or [] if isinstance(s, dict)}
            rows.append((stats, parse_team(e)))
        if not rows:
            continue
        if sport == BASEBALL:
            rows.sort(key=lambda r: (-_num(r[0].get("winPercent", "0")), -_num(r[0].get("wins", "0"))))
            lw, ll = _num(rows[0][0].get("wins", "0")), _num(rows[0][0].get("losses", "0"))
        else:
            rows.sort(key=lambda r: _num(r[0].get("rank", "0")) or 999)
        out = []
        for i, (stats, team) in enumerate(rows):
            values = []
            for _, name in columns:
                if name is None:  # games behind the leader
                    gb = ((lw - _num(stats.get("wins", "0"))) + (_num(stats.get("losses", "0")) - ll)) / 2
                    values.append("–" if gb <= 0 else f"{gb:g}")
                else:
                    values.append(stats.get(name, "") or "0")
            out.append((i + 1, team, values))
        tables.append(Table(_text(g.get("name")), [c for c, _ in columns], out))
    return tables


# --- fetching a competition

def fetch_competition(key: str, today: Optional[date] = None, cache: Optional[dict] = None,
                      get: Callable = _get_json) -> Optional[CompetitionData]:
    """One competition's recent results, fixtures and table. `cache` (a
    dict the caller keeps) saves fetching finished days and tables again."""
    comp = BY_KEY.get(key)
    if comp is None:
        return None
    if comp.sport == CRICKET:
        return fetch_cricket(key, get)
    cache = cache if cache is not None else {}
    today = today or datetime.now(timezone.utc).date()
    base = f"{SITE_URL}/{comp.sport}/{comp.league}/scoreboard"
    current = get(base)
    if not isinstance(current, dict):
        return None
    league = (current.get("leagues") or [{}])[0]
    matches = {m.id: m for m in parse_scoreboard(current)}
    past, future = match_days(league, today)
    for day in past + future:
        stamp = day.strftime("%Y%m%d")
        cached = cache.get((key, stamp))
        if cached is not None:
            day_matches = cached
        else:
            payload = get(f"{base}?dates={stamp}")
            if not isinstance(payload, dict):
                continue
            day_matches = parse_scoreboard(payload)
            if day < today and day_matches and all(m.state == DONE for m in day_matches):
                cache[(key, stamp)] = day_matches  # finished: it won't change
        for m in day_matches:
            matches.setdefault(m.id, m)
    tables = cache.get((key, "table"))
    if tables is None or time.time() - tables[0] > 30 * 60 or any(m.state == LIVE for m in matches.values()):
        payload = get(f"{STANDINGS_URL}/{comp.sport}/{comp.league}/standings")
        if isinstance(payload, dict):
            tables = (time.time(), parse_standings(payload, comp.sport))
            cache[(key, "table")] = tables
    # the tables don't give the teams' colours, so learn them once from the team list
    colours = cache.get((key, "colours"))
    if colours is None and tables and tables[1]:
        payload = get(f"{SITE_URL}/{comp.sport}/{comp.league}/teams")
        if isinstance(payload, dict):
            colours = parse_team_colours(payload)
            cache[(key, "colours")] = colours
    if colours:
        for t in tables[1]:
            for _, team, _ in t.rows:
                team.colour = team.colour or colours.get(team.short, "")
    return CompetitionData(key, _text(league.get("name")) or comp.name, list(matches.values()),
                           tables[1] if tables else [], time.time())


def parse_team_colours(payload: dict) -> dict[str, str]:
    """{abbreviation: colour} from a league's team list."""
    colours = {}
    for sport in payload.get("sports") or []:
        for league in sport.get("leagues") or []:
            for entry in league.get("teams") or []:
                team = entry.get("team") or {} if isinstance(entry, dict) else {}
                code, colour = _text(team.get("abbreviation")), _text(team.get("color")).lstrip("#").lower()
                if code and colour:
                    colours[code[:5]] = colour
    return colours


INTERNATIONAL_KINDS = ("Test", "ODI", "T20I")


def is_international(match: Match) -> bool:
    return any(match.kind.endswith(k) for k in INTERNATIONAL_KINDS) and "youth" not in match.kind.lower()


def parse_cricket(payload: dict, international_only: bool) -> list[Match]:
    matches = []
    for block in payload.get("scores") or []:
        if not isinstance(block, dict):
            continue
        league = (block.get("leagues") or [{}])[0]
        for m in parse_scoreboard(block):
            m.competition = _text(league.get("name"))
            if not international_only or is_international(m):
                matches.append(m)
    return matches


def fetch_cricket(key: str, get: Callable = _get_json) -> Optional[CompetitionData]:
    payload = get(CRICKET_URL)
    if not isinstance(payload, dict):
        return None
    comp = BY_KEY[key]
    return CompetitionData(key, comp.name, parse_cricket(payload, key.endswith("international")), [], time.time())
