from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def add_query_to_url(url, query_dict) -> str:
    """Add the items in query_dict to the url, which may already have a query.

    Args:
        url (str): An url that may already have a query
        query_dict (QueryDict or dict): The query that should be added to the url

    Returns:
        str: The url with the added query items.
    """
    url_parse = urlparse(url)
    query_items = parse_qsl(url_parse.query, keep_blank_values=True)
    query_items += parse_qsl(urlencode(query_dict), keep_blank_values=True)
    url_new_query = urlencode(query_items)
    url_parse = url_parse._replace(query=url_new_query)
    new_url: str = urlunparse(url_parse)
    return new_url
