"""Parity tests against the .NET SearchEndpoints sort/filter behavior."""

from datetime import UTC, datetime, timedelta

from carsties.modules.search.application.queries import build_search, clamp_paging

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def search(**overrides):
    params = dict(
        search_term=None, order_by=None, filter_by=None, seller=None, winner=None, now=NOW
    )
    params.update(overrides)
    return build_search(**params)


def test_default_sorts_by_auction_end_and_filters_live():
    query_filter, sort = search()
    assert sort == [("auction_end", 1)]
    assert query_filter == {"auction_end": {"$gt": NOW}}


def test_search_term_uses_text_search_sorted_by_score():
    query_filter, sort = search(search_term="ford")
    assert query_filter["$text"] == {"$search": "ford"}
    assert sort[0] == ("score", {"$meta": "textScore"})


def test_order_by_make_sorts_by_make_then_model():
    _, sort = search(order_by="make")
    assert sort == [("make", 1), ("model", 1)]


def test_order_by_new_sorts_by_created_at_desc():
    _, sort = search(order_by="new")
    assert sort == [("created_at", -1)]


def test_filter_finished():
    query_filter, _ = search(filter_by="finished")
    assert query_filter["auction_end"] == {"$lt": NOW}


def test_filter_ending_soon():
    query_filter, _ = search(filter_by="endingSoon")
    assert query_filter["auction_end"] == {"$lt": NOW + timedelta(hours=6), "$gt": NOW}


def test_seller_and_winner_filters():
    query_filter, _ = search(seller="bob", winner="alice")
    assert query_filter["seller"] == "bob"
    assert query_filter["winner"] == "alice"


def test_paging_defaults_and_cap():
    assert clamp_paging(None, None) == (1, 4)
    assert clamp_paging(3, 10) == (3, 10)
    assert clamp_paging(1, 500) == (1, 50)
