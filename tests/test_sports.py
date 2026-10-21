from datetime import date

from simple_info.core import sports as sp


def event(id, start, state, home, away, hs="", as_="", detail="", winner=None):
    def side(name, code, ha, score):
        return {"homeAway": ha, "score": score, "winner": winner == ha,
                "team": {"displayName": name, "shortDisplayName": name, "abbreviation": code, "color": "0046ff"}}
    return {"id": id, "date": start, "status": {"type": {"state": state, "shortDetail": detail}},
            "competitions": [{"competitors": [side(home, home[:3].upper(), "home", hs), side(away, away[:3].upper(), "away", as_)]}]}


def board(events, calendar=None, whitelist=True, name="Scottish Premiership", start="", end=""):
    return {"leagues": [{"name": name, "calendar": calendar or [], "calendarIsWhitelist": whitelist,
                         "calendarStartDate": start, "calendarEndDate": end}], "events": events}


STANDINGS = {"children": [{"name": "2026-27 Scottish Premiership", "standings": {"entries": [
    {"team": {"displayName": "Rangers", "shortDisplayName": "Rangers", "abbreviation": "RAN"},
     "stats": [{"name": "rank", "displayValue": "2"}, {"name": "gamesPlayed", "displayValue": "9"}, {"name": "wins", "displayValue": "6"},
               {"name": "ties", "displayValue": "2"}, {"name": "losses", "displayValue": "1"},
               {"name": "pointDifferential", "displayValue": "+6"}, {"name": "points", "displayValue": "20"}]},
    {"team": {"displayName": "Celtic", "shortDisplayName": "Celtic", "abbreviation": "CEL"},
     "stats": [{"name": "rank", "displayValue": "1"}, {"name": "gamesPlayed", "displayValue": "9"}, {"name": "wins", "displayValue": "8"},
               {"name": "ties", "displayValue": "0"}, {"name": "losses", "displayValue": "1"},
               {"name": "pointDifferential", "displayValue": "+18"}, {"name": "points", "displayValue": "24"}]},
]}}]}


def test_parse_event_reads_teams_scores_and_state():
    m = sp.parse_event(event("1", "2026-10-18T14:00Z", "post", "Celtic", "Hearts", "7", "1", "FT", winner="home"))
    assert (m.home.name, m.home.score, m.home.winner, m.away.name, m.away.score) == ("Celtic", "7", True, "Hearts", "1")
    assert m.state == sp.DONE and m.detail == "FT" and m.home.colour == "0046ff"
    assert sp.parse_event({"competitions": [{"competitors": []}]}) is None


def test_match_days_from_a_list_of_match_days():
    league = {"calendarIsWhitelist": True, "calendar": [f"2026-10-{d:02d}T07:00Z" for d in (10, 11, 17, 18, 24, 25, 28)]}
    past, future = sp.match_days(league, date(2026, 10, 21))
    assert past == [date(2026, 10, 17), date(2026, 10, 18)] and future == [date(2026, 10, 24), date(2026, 10, 25)]


def test_match_days_from_baseballs_list_of_days_off():
    league = {"calendarIsWhitelist": False, "calendar": ["2026-10-20T07:00Z", "2026-10-22T07:00Z"],
              "calendarStartDate": "2026-02-19T08:00Z", "calendarEndDate": "2026-11-12T07:59Z"}
    past, future = sp.match_days(league, date(2026, 10, 21))
    assert past == [date(2026, 10, 19), date(2026, 10, 21)] and future == [date(2026, 10, 23), date(2026, 10, 24)]


def test_parse_standings_sorts_by_rank_and_picks_the_columns():
    (table,) = sp.parse_standings(STANDINGS, sp.FOOTBALL)
    assert table.columns == ["P", "W", "D", "L", "GD", "Pts"]
    assert [(pos, team.name, values[-1]) for pos, team, values in table.rows] == [(1, "Celtic", "24"), (2, "Rangers", "20")]
    assert sp.parse_standings(STANDINGS, sp.CRICKET) == []


def test_baseball_standings_by_win_percentage_with_games_behind():
    def team(code, w, l, pct):
        return {"team": {"displayName": code, "abbreviation": code},
                "stats": [{"name": "wins", "displayValue": str(w)}, {"name": "losses", "displayValue": str(l)},
                          {"name": "winPercent", "displayValue": pct}]}
    payload = {"children": [{"name": "American League", "standings": {"entries": [
        team("NYY", 93, 68, ".578"), team("TB", 98, 64, ".605"), team("BOS", 87, 75, ".537")]}}]}
    (table,) = sp.parse_standings(payload, sp.BASEBALL)
    assert [(t.short, v[3]) for _, t, v in table.rows] == [("TB", "–"), ("NYY", "4.5"), ("BOS", "11")]


def test_fetch_competition_gathers_days_table_and_colours_and_caches_finished_days():
    asked = []
    pages = {
        "scoreboard": board([event("3", "2026-10-24T14:00Z", "pre", "Rangers", "Dundee")],
                            ["2026-10-17T07:00Z", "2026-10-18T07:00Z", "2026-10-24T07:00Z"]),
        "dates=20261017": board([event("1", "2026-10-17T14:00Z", "post", "Dundee", "Rangers", "2", "2", "FT")]),
        "dates=20261018": board([event("2", "2026-10-18T14:00Z", "post", "Celtic", "Hearts", "7", "1", "FT", "home")]),
        "dates=20261024": board([event("3", "2026-10-24T14:00Z", "pre", "Rangers", "Dundee")]),
        "standings": STANDINGS,
        "teams": {"sports": [{"leagues": [{"teams": [{"team": {"abbreviation": "CEL", "color": "00843d"}}]}]}]},
    }

    def get(url):
        asked.append(url)
        for k, v in pages.items():
            if url.endswith(k):
                return v
        return None

    cache = {}
    data = sp.fetch_competition("soccer/sco.1", date(2026, 10, 21), cache, get)
    assert data.name == "Scottish Premiership"
    assert [m.id for m in data.results] == ["2", "1"] and [m.id for m in data.fixtures] == ["3"] and data.live == []
    assert data.tables[0].rows[0][1].colour == "00843d"
    first = len(asked)
    sp.fetch_competition("soccer/sco.1", date(2026, 10, 21), cache, get)
    again = asked[first:]
    assert not any("20261017" in u or "20261018" in u or "standings" in u or "teams" in u for u in again)
    assert sp.fetch_competition("soccer/sco.1", date(2026, 10, 21), {}, lambda url: None) is None
    assert sp.fetch_competition("nope/x") is None


CRICKET = {"scores": [
    {"leagues": [{"name": "Australia tour of South Africa"}], "events": [{
        "id": "9", "date": "2026-10-18T07:45Z", "status": {"type": {"state": "in", "description": "Live"}},
        "competitions": [{"class": {"generalClassCard": "Test"}, "status": {"summary": "Australia trail by 333 runs"},
                          "competitors": [
                              {"score": "425/9d", "team": {"displayName": "South Africa", "shortDisplayName": "SA", "abbreviation": "SA"}},
                              {"score": "92/7 (39.5 ov)", "team": {"displayName": "Australia", "shortDisplayName": "AUS", "abbreviation": "AUS"}}]}]}]},
    {"leagues": [{"name": "Sheffield Shield"}], "events": [{
        "id": "8", "date": "2026-10-18T23:30Z", "status": {"type": {"state": "post"}},
        "competitions": [{"class": {"generalClassCard": "First-class"}, "competitors": [
            {"team": {"displayName": "Tasmania"}}, {"team": {"displayName": "Victoria"}}]}]}]},
    {"leagues": [{"name": "Under-19s tour"}], "events": [{
        "id": "7", "date": "2026-10-18T23:30Z", "status": {"type": {"state": "post"}},
        "competitions": [{"class": {"generalClassCard": "Youth ODI"}, "competitors": [
            {"team": {"displayName": "Oman U19"}}, {"team": {"displayName": "Bangladesh U19"}}]}]}]},
]}


def test_cricket_uses_full_names_and_keeps_internationals():
    (m,) = sp.parse_cricket(CRICKET, international_only=True)
    assert (m.home.name, m.home.score, m.away.name, m.summary, m.kind, m.competition) == (
        "South Africa", "425/9d", "Australia", "Australia trail by 333 runs", "Test", "Australia tour of South Africa")
    assert m.state == sp.LIVE
    assert len(sp.parse_cricket(CRICKET, international_only=False)) == 3
    data = sp.fetch_cricket("cricket/all", lambda url: CRICKET)
    assert data.name == "Cricket worldwide" and len(data.matches) == 3 and data.tables == []


BBC_SCORES = {"eventGroups": [{"displayLabel": "Saturday 17th October", "secondaryGroups": [{"events": [
    {"id": "e1", "startDateTime": "2026-10-17T14:00:00Z", "status": "PostEvent", "winner": "away",
     "periodLabel": {"value": "FT"},
     "home": {"fullName": "East Fife", "shortName": "East Fife", "urn": "urn:team:east-fife", "score": "0"},
     "away": {"fullName": "Alloa Athletic", "shortName": "Alloa", "urn": "urn:team:alloa", "score": "3"}},
    {"id": "e2", "startDateTime": "2026-10-21T19:45:00Z", "status": "MidEvent", "periodLabel": {"value": "62'"},
     "home": {"fullName": "Cove Rangers", "urn": "urn:team:cove", "score": "1"},
     "away": {"fullName": "Kelty Hearts", "urn": "urn:team:kelty", "score": "1"}},
    {"id": "e3", "startDateTime": "2026-10-24T14:00:00Z", "status": "PreEvent", "periodLabel": {"value": "Scheduled"},
     "home": {"fullName": "Queen of the South", "shortName": "QOTS", "urn": "urn:team:qots"},
     "away": {"fullName": "Montrose", "urn": "urn:team:montrose"}},
]}]}]}
BBC_TABLE = {"tournaments": [{"name": "Scottish League One", "stages": [{"name": "Regular Season", "rounds": [{"participants": [
    {"rank": 2, "name": "Alloa Athletic", "shortName": "Alloa", "urn": "urn:team:alloa", "matchesPlayed": 10, "wins": 6,
     "draws": 2, "losses": 2, "goalDifference": 8, "points": 20},
    {"rank": 1, "name": "Ross County", "shortName": "Ross County", "urn": "urn:team:ross", "matchesPlayed": 10, "wins": 9,
     "draws": 1, "losses": 0, "goalDifference": 32, "points": 28},
]}]}]}]}


def test_bbc_scores_and_table():
    done, live, pre = sp.parse_bbc_scores(BBC_SCORES)
    assert (done.state, done.away.winner, done.away.score, done.detail) == (sp.DONE, True, "3", "FT")
    assert (live.state, live.detail, live.home.id) == (sp.LIVE, "62'", "urn:team:cove")
    assert pre.state == sp.PRE and pre.home.name == "Queen of the South"
    (table,) = sp.parse_bbc_table(BBC_TABLE)
    assert table.name == "Scottish League One" and table.columns == ["P", "W", "D", "L", "GD", "Pts"]
    assert [(pos, team.name, values) for pos, team, values in table.rows] == [
        (1, "Ross County", ["10", "9", "1", "0", "+32", "28"]), (2, "Alloa Athletic", ["10", "6", "2", "2", "+8", "20"])]


def test_bbc_ranges_stay_within_the_ones_bbc_answers():
    past, future = sp.bbc_ranges(date(2026, 10, 21))
    assert past == [(date(2026, 10, 1), date(2026, 10, 21)), (date(2026, 9, 1), date(2026, 9, 30))]
    assert future == [(date(2026, 10, 22), date(2026, 10, 31)), (date(2026, 11, 1), date(2026, 11, 30))]
    past, future = sp.bbc_ranges(date(2026, 12, 31))  # the last day of a month: fixtures are all next month
    assert future == [(date(2027, 1, 1), date(2027, 1, 31))]


def test_scottish_league_one_comes_from_the_bbc():
    asked = []

    def get(url):
        asked.append(url)
        if "football-table" in url:
            return BBC_TABLE
        if "scores-fixtures" in url:
            return BBC_SCORES
        if url.endswith("/teams"):
            return {"sports": [{"leagues": [{"teams": [{"team": {"displayName": "Alloa Athletic", "color": "F7AA25"}}]}]}]}
        return None

    data = sp.fetch_competition("soccer/sco.3", date(2026, 10, 21), {}, get)
    assert data.name == "Scottish League One"
    assert [m.id for m in data.results] == ["e1"] and [m.id for m in data.live] == ["e2"] and [m.id for m in data.fixtures] == ["e3"]
    assert data.results[0].away.colour == "f7aa25" and data.tables[0].rows[1][1].colour == "f7aa25"
    assert any("scottish-league-one" in u for u in asked) and not any("site.api.espn.com/apis/site/v2/sports/soccer/sco.3/scoreboard" in u for u in asked)
    assert sp.fetch_teams("soccer/sco.3", lambda url: BBC_TABLE) == [("urn:team:alloa", "Alloa Athletic"), ("urn:team:ross", "Ross County")]
    assert sp.fetch_competition("soccer/sco.4", date(2026, 10, 21), {}, lambda url: None) is None


def test_favourites_round_trip():
    favs = sp.parse_favourites("soccer/sco.1=256, cricket/international=England,nope=1,rugby/270557=")
    assert favs == {"soccer/sco.1": "256", "cricket/international": "England"}
    assert sp.parse_favourites(sp.format_favourites(favs)) == favs
    team = sp.Team("Celtic", "CEL", id="256")
    assert team.is_one_of({"256"}) and not team.is_one_of(set()) and sp.Team("England", "ENG").is_one_of({"England"})
