import sys

from simple_info import __version__


def self_test() -> int:
    """`Simple-Info --self-test`: checks a built app has everything it
    needs bundled (the release workflow runs this on each OS). Exit code
    0 if so."""
    checks = {}
    try:
        from simple_info.core import weather

        checks["weather parsing"] = weather.condition_for(63) == weather.RAIN
    except Exception:
        checks["weather parsing"] = False
    try:
        from simple_info.core import sky

        checks["sky"] = 0 <= sky.moon_phase() < 1
    except Exception:
        checks["sky"] = False
    try:
        from simple_info.core import trains

        board = trains.parse_board({"locationName": "York", "crs": "YRK", "trainServices": [
            {"std": "10:00", "etd": "10:05", "destination": [{"locationName": "Leeds"}]}]}, trains.DEPARTURES)
        checks["train parsing"] = board.services[0].expected_text == "Exp 10:05"
    except Exception:
        checks["train parsing"] = False
    try:
        from simple_info.core import currency

        _, rates = currency.parse_series({"rates": {"2026-10-20": {"EUR": 1.19}}}, ["EUR"])
        checks["currency parsing"] = currency.format_rate(rates[0].rate) == "1.1900"
    except Exception:
        checks["currency parsing"] = False
    try:
        from simple_info.core import sports

        match = sports.parse_event({"id": "1", "status": {"type": {"state": "post"}}, "competitions": [{"competitors": [
            {"homeAway": "home", "score": "2", "team": {"displayName": "Celtic"}},
            {"homeAway": "away", "score": "1", "team": {"displayName": "Hearts"}}]}]})
        checks["sport parsing"] = match.home.name == "Celtic" and match.away.score == "1"
    except Exception:
        checks["sport parsing"] = False
    try:
        from simple_info.core import tv

        checks["tv guide parsing"] = tv.parse_time("20261020224000 +0100") is not None
    except Exception:
        checks["tv guide parsing"] = False
    if sys.platform.startswith("linux"):
        try:
            import jeepney.io.blocking  # noqa: F401  (keeping the screen awake)

            checks["keep awake"] = True
        except Exception:
            checks["keep awake"] = False
    try:
        import certifi  # noqa: F401

        checks["certificates"] = True
    except Exception:
        checks["certificates"] = False
    report = ", ".join(f"{name}: {'ok' if ok else 'MISSING'}" for name, ok in checks.items())
    try:
        print(f"Simple-Info {__version__} self-test — {report}", flush=True)
    except (AttributeError, OSError):  # no console (Windows GUI build)
        pass
    return 0 if all(checks.values()) else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    # Qt is imported only now, so --self-test runs even where there's no
    # display or graphics libraries (the release workflow's build machines).
    from PySide6.QtWidgets import QApplication

    from simple_info.core.diagnostics import enable_app_log, enable_crash_log, log_event
    from simple_info.gui.main_window import MainWindow

    enable_app_log(__version__)
    enable_crash_log()
    app = QApplication(sys.argv)
    app.setApplicationName("Simple-Info")
    app.setDesktopFileName("simple-info")
    window = MainWindow()
    window.show_at_start(fullscreen="--fullscreen" in sys.argv)
    code = app.exec()
    log_event(f"event loop finished (code {code})")
    return code


if __name__ == "__main__":
    sys.exit(main())
