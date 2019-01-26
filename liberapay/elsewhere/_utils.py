from urllib.parse import urlsplit


def extract_domain_from_url(url):
    return urlsplit(url).hostname
