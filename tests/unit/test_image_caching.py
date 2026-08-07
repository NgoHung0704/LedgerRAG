"""Serving an image whose URL never changes but whose content does."""

from tablerag.api.caching import etag_for, stored_image

CROP = b"\x89PNG the first reading"
RECUT = b"\x89PNG the same table, cut in two"


def test_a_stored_image_is_always_revalidated():
    """Splitting a table rewrites the first part's crop IN PLACE, and so do
    joining, undo and reprocessing. Without this a browser reuses the old
    picture heuristically, so a table cut in two goes on showing the uncut
    image — the parse changed and the evidence beside it did not."""
    response = stored_image(CROP, None)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["etag"] == etag_for(CROP)
    assert response.body == CROP


def test_an_unchanged_image_costs_a_round_trip_and_no_pixels():
    """no-cache is not "do not cache": it is "always ask". The ETag makes
    asking free, which matters on a page holding forty crops."""
    response = stored_image(CROP, etag_for(CROP))
    assert response.status_code == 304
    assert response.body == b""
    assert response.headers["etag"] == etag_for(CROP)


def test_a_replaced_image_is_sent_again():
    """The split case: same URL, new bytes. The browser's old ETag no longer
    matches, so it gets the new picture instead of its cached one."""
    response = stored_image(RECUT, etag_for(CROP))
    assert response.status_code == 200
    assert response.body == RECUT
    assert response.headers["etag"] == etag_for(RECUT)


def test_two_different_images_never_share_an_etag():
    assert etag_for(CROP) != etag_for(RECUT)
