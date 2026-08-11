import pandas as pd
import pytest
from icalendar import Calendar

import generate
from generate import add_announcement_events, add_holiday_events
from lib.jquants import jquants


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


@pytest.fixture
def jq(monkeypatch):
    monkeypatch.setenv("JQUANTS_API_KEY", "test-api-key")
    jquants._instance = None
    client = jquants()
    yield client
    jquants._instance = None


def test_get_fins_announcement_uses_v2_endpoint_and_normalizes_fields(
    jq, monkeypatch
):
    calls = []

    def fake_get(url, params, headers):
        calls.append((url, dict(params), dict(headers)))
        return FakeResponse(
            {
                "data": [
                    {
                        "PubDate": "2026-07-01",
                        "SchDate": "2026-08-12",
                        "FQName": "1Q",
                        "FYE": "0331",
                        "Code": "86970",
                        "CoName": "日本取引所グループ",
                        "CoNameEn": "Japan Exchange Group,Inc.",
                    }
                ]
            }
        )

    monkeypatch.setattr("lib.jquants.requests.get", fake_get)

    rows, df = jq.get_fins_announcement(scheduled_date="2026-08-12")

    assert calls == [
        (
            "https://api.jquants.com/v2/fins/earnings-date",
            {"scheduled_date": "2026-08-12"},
            {"x-api-key": "test-api-key"},
        )
    ]
    assert rows[0]["SchDate"] == "2026-08-12"
    assert rows[0]["Date"] == "2026-08-12"
    assert rows[0]["CompanyName"] == "日本取引所グループ"
    assert rows[0]["FiscalQuarter"] == "1Q"
    assert rows[0]["FiscalYearEnd"] == "0331"
    assert not df.empty


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"code": "86970", "date": "2026-07-01"},
        {"date": "2026-07-01", "scheduled_date": "2026-08-12"},
    ],
)
def test_get_fins_announcement_requires_exactly_one_filter(jq, kwargs):
    with pytest.raises(ValueError, match="いずれか1つ"):
        jq.get_fins_announcement(**kwargs)


def test_get_fins_announcement_follows_pagination(jq, monkeypatch):
    calls = []
    responses = iter(
        [
            FakeResponse(
                {
                    "data": [
                        {
                            "PubDate": "2026-07-01",
                            "SchDate": "2026-08-12",
                            "FQName": "1Q",
                            "FYE": "0331",
                            "Code": "11110",
                            "CoName": "会社A",
                            "CoNameEn": "Company A",
                        }
                    ],
                    "pagination_key": "next-page",
                }
            ),
            FakeResponse(
                {
                    "data": [
                        {
                            "PubDate": "2026-07-02",
                            "SchDate": "2026-08-12",
                            "FQName": "FY",
                            "FYE": "0630",
                            "Code": "22220",
                            "CoName": "会社B",
                            "CoNameEn": "Company B",
                        }
                    ]
                }
            ),
        ]
    )

    def fake_get(url, params, headers):
        calls.append(dict(params))
        return next(responses)

    monkeypatch.setattr("lib.jquants.requests.get", fake_get)

    rows, _ = jq.get_fins_announcement(date="2026-07-01")

    assert [row["Code"] for row in rows] == ["11110", "22220"]
    assert calls == [
        {"date": "2026-07-01"},
        {"date": "2026-07-01", "pagination_key": "next-page"},
    ]


def test_market_calendar_uses_v2_hol_div_parameter(jq, monkeypatch):
    calls = []

    def fake_get(url, params, headers):
        calls.append((url, dict(params)))
        return FakeResponse({"data": [{"Date": "2026-08-11", "HolDiv": "3"}]})

    monkeypatch.setattr("lib.jquants.requests.get", fake_get)

    rows, _ = jq.get_market_trading_calendar(
        holidaydivision="3", from_="2026-08-11", to="2026-08-11"
    )

    assert calls == [
        (
            "https://api.jquants.com/v2/markets/calendar",
            {"hol_div": "3", "from": "2026-08-11", "to": "2026-08-11"},
        )
    ]
    assert rows == [
        {"Date": "2026-08-11", "HolDiv": "3", "source": "j-quants"}
    ]


def test_add_holiday_events_understands_v2_hol_div():
    calendar = Calendar()

    add_holiday_events(
        calendar,
        [
            {"Date": "2026-08-10", "HolDiv": "1"},
            {"Date": "2026-08-11", "HolDiv": "3"},
            {"Date": "2026-08-12", "HolDiv": "2"},
        ],
    )

    event_dates = {event.get("dtstart").dt.isoformat() for event in calendar.walk("VEVENT")}
    assert event_dates == {"2026-08-11"}


def test_add_announcement_events_queries_v2_by_scheduled_date(monkeypatch):
    class FakeJQuants:
        isEnable = True

        def __init__(self):
            self.dates = []

        def get_fins_announcement(self, *, scheduled_date):
            self.dates.append(scheduled_date)
            frame = pd.DataFrame(
                [
                    {
                        "Code": "86970",
                        "Date": scheduled_date,
                        "CompanyName": "日本取引所グループ",
                        "FiscalQuarter": "1Q",
                        "FiscalYearEnd": "0331",
                        "source": "j-quants",
                    }
                ]
            )
            return frame.to_dict(orient="records"), frame

    class FakeJPX:
        def get_fins_announcement(self):
            return [], pd.DataFrame()

    monkeypatch.setattr(generate, "JPX", FakeJPX)
    client = FakeJQuants()
    calendar = Calendar()

    add_announcement_events(
        calendar, client, scheduled_dates=["2026-08-12"]
    )

    assert client.dates == ["2026-08-12"]
    events = list(calendar.walk("VEVENT"))
    assert len(events) == 1
    assert events[0].get("dtstart").dt.isoformat() == "2026-08-12"
    assert "日本取引所グループ" in str(events[0].get("summary"))


def test_add_announcement_events_respects_free_plan_request_limit(monkeypatch):
    class FakeJQuants:
        isEnable = True
        last_status_code = 200

        def __init__(self):
            self.dates = []

        def get_fins_announcement(self, *, scheduled_date):
            self.dates.append(scheduled_date)
            return [], pd.DataFrame()

    class FakeJPX:
        def get_fins_announcement(self):
            return [], pd.DataFrame()

    monkeypatch.setattr(generate, "JPX", FakeJPX)
    client = FakeJQuants()

    add_announcement_events(
        Calendar(),
        client,
        scheduled_dates=[f"2099-01-{day:02d}" for day in range(1, 8)],
    )

    assert client.dates == [
        "2099-01-01",
        "2099-01-02",
        "2099-01-03",
        "2099-01-04",
    ]


def test_add_announcement_events_stops_after_rate_limit(monkeypatch):
    class FakeJQuants:
        isEnable = True

        def __init__(self):
            self.dates = []
            self.last_status_code = None

        def get_fins_announcement(self, *, scheduled_date):
            self.dates.append(scheduled_date)
            self.last_status_code = 429
            return [], pd.DataFrame()

    class FakeJPX:
        def get_fins_announcement(self):
            return [], pd.DataFrame()

    monkeypatch.setattr(generate, "JPX", FakeJPX)
    client = FakeJQuants()

    add_announcement_events(
        Calendar(),
        client,
        scheduled_dates=["2099-01-01", "2099-01-02"],
    )

    assert client.dates == ["2099-01-01"]


def test_add_announcement_events_handles_nan_from_mixed_v2_and_jpx_frames(
    monkeypatch,
):
    class FakeJQuants:
        isEnable = True
        last_status_code = 200

        def get_fins_announcement(self, *, scheduled_date):
            frame = pd.DataFrame(
                [
                    {
                        "Code": "86970",
                        "Date": scheduled_date,
                        "CompanyName": "日本取引所グループ",
                        "FiscalQuarter": "1Q",
                        "FiscalYearEnd": "0331",
                        "source": "j-quants",
                    }
                ]
            )
            return frame.to_dict(orient="records"), frame

    class FakeJPX:
        def get_fins_announcement(self):
            frame = pd.DataFrame(
                [
                    {
                        "Code": "11110",
                        "Date": "2099-01-01",
                        "CompanyName": "会社A",
                        "FiscalQuarter": "FY",
                        "FiscalYear": "2098",
                        "source": "jpx-excel",
                    }
                ]
            )
            return frame.to_dict(orient="records"), frame

    monkeypatch.setattr(generate, "JPX", FakeJPX)
    calendar = Calendar()

    add_announcement_events(
        calendar,
        FakeJQuants(),
        scheduled_dates=["2099-01-01"],
    )

    summaries = [str(event.get("summary")) for event in calendar.walk("VEVENT")]
    assert len(summaries) == 2
    assert any("日本取引所グループ" in summary and "0331" in summary for summary in summaries)
