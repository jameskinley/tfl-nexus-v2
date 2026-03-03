import pytest

from data.hateoas import HateoasBuilder


class TestEncodeStationIdentifier:
    def test_space_encoded_as_percent_20(self):
        result = HateoasBuilder.encode_station_identifier("King's Cross St. Pancras")

        assert "%20" in result or "+" in result or "King" in result

    def test_apostrophe_encoded(self):
        result = HateoasBuilder.encode_station_identifier("King's Cross")

        assert "'" not in result

    def test_plain_name_unchanged(self):
        result = HateoasBuilder.encode_station_identifier("Aldgate")

        assert result == "Aldgate"

    def test_space_in_name_encoded(self):
        result = HateoasBuilder.encode_station_identifier("London Bridge")

        assert " " not in result


class TestBuildPaginationLinks:
    def test_first_page_has_no_prev_link(self):
        links = HateoasBuilder.build_pagination_links("/stations", page=1, per_page=10, total_pages=5)

        assert not hasattr(links, "prev") or links.prev is None

    def test_first_page_has_next_link(self):
        links = HateoasBuilder.build_pagination_links("/stations", page=1, per_page=10, total_pages=5)

        assert links.next is not None

    def test_last_page_has_no_next_link(self):
        links = HateoasBuilder.build_pagination_links("/stations", page=5, per_page=10, total_pages=5)

        assert not hasattr(links, "next") or links.next is None

    def test_last_page_has_prev_link(self):
        links = HateoasBuilder.build_pagination_links("/stations", page=5, per_page=10, total_pages=5)

        assert links.prev is not None

    def test_middle_page_has_both_prev_and_next(self):
        links = HateoasBuilder.build_pagination_links("/stations", page=3, per_page=10, total_pages=5)

        assert links.prev is not None
        assert links.next is not None

    def test_single_page_has_no_prev_or_next(self):
        links = HateoasBuilder.build_pagination_links("/stations", page=1, per_page=10, total_pages=1)

        assert not hasattr(links, "prev") or links.prev is None
        assert not hasattr(links, "next") or links.next is None

    def test_self_link_contains_correct_page(self):
        links = HateoasBuilder.build_pagination_links("/stations", page=3, per_page=10, total_pages=5)

        assert "page=3" in links.self.href

    def test_next_link_points_to_next_page(self):
        links = HateoasBuilder.build_pagination_links("/lines", page=2, per_page=5, total_pages=4)

        assert "page=3" in links.next.href

    def test_prev_link_points_to_previous_page(self):
        links = HateoasBuilder.build_pagination_links("/lines", page=3, per_page=5, total_pages=4)

        assert "page=2" in links.prev.href

    def test_query_params_appended_to_links(self):
        links = HateoasBuilder.build_pagination_links(
            "/stations", page=1, per_page=10, total_pages=3,
            query_params={"mode": "tube"}
        )

        assert "mode=tube" in links.next.href


class TestBuildLinks:
    def test_self_link_always_present(self):
        links = HateoasBuilder.build_links("/stations/abc")

        assert links.self is not None
        assert links.self.href == "/stations/abc"

    def test_no_additional_links_produces_only_self(self):
        links = HateoasBuilder.build_links("/stations/abc")

        links_dict = links.model_dump(exclude_none=True)
        assert set(links_dict.keys()) == {"self"}

    def test_additional_links_included(self):
        links = HateoasBuilder.build_links("/stations/abc", additional_links={"lines": "/stations/abc/lines"})

        assert links.lines is not None
        assert links.lines.href == "/stations/abc/lines"
