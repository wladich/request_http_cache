#!/usr/bin/env python3
from __future__ import annotations

import sys
import argparse
import time
import functools
from multiprocessing.pool import ThreadPool
import requests
import requests.adapters


def connection_pool(size):
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=size, pool_maxsize=size)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def parse_user_input_headers(headers: list[str]):
    if headers is None:
        return {}
    headers_dict = {}
    for header in headers:
        name, _, value = header.partition(":")
        headers_dict[name.strip().lower()] = value.strip()
    return headers_dict


def request_url(
    url,
    session: requests.Session,
    headers,
    check_headers,
    retry_count,
    retry_delay,
    timeout,
) -> tuple[str, str | None]:
    while retry_count + 1 > 0:
        try:
            response = session.get(
                url,
                timeout=timeout,
                allow_redirects=False,
                headers=headers,
                stream=False,
            )
        except (requests.Timeout, requests.ConnectionError) as err:
            if retry_count > 0:
                time.sleep(retry_delay)
                retry_count -= 1
                continue
            return url, str(err)
        except Exception as err:
            return url, str(err)
        if str(response.status_code)[0] == "5":
            if retry_count > 0:
                time.sleep(retry_delay)
                retry_count -= 1
                continue
            return url, "response status code %d" % response.status_code

        if response.status_code != 200:
            return url, "response status code %d" % response.status_code
        if len(response.content) == 0:
            return url, "response empty"
        for name, value in check_headers.items():
            if response.headers.get(name) != value:
                return url, "response headers check failed (%s: %s)" % (name, value)
        return url, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        metavar="FILE",
        type=argparse.FileType("r", encoding="utf-8"),
        required=True,
        help="Input file",
    )
    parser.add_argument("--base", metavar="URL", required=False, help="URL base")
    parser.add_argument(
        "--threads",
        type=int,
        required=False,
        default=1,
        help="Number of concurrent requests",
    )
    parser.add_argument("--headers", required=False, nargs="+", help="Request headers")
    parser.add_argument(
        "--check-headers", required=False, nargs="*", help="Check response headers"
    )
    parser.add_argument(
        "--retry-count",
        default=0,
        type=int,
        help="Number of retries for timeouts, connection errors and HTTP 5XX error",
    )
    parser.add_argument(
        "--retry-delay",
        default=1,
        type=int,
        help="Delay between retries for --retry-count",
    )
    parser.add_argument(
        "--max-errors", type=int, help="Stop program after this many errors", default=1
    )
    parser.add_argument("--no-progress", action="store_true", default=False)
    parser.add_argument("--timeout", default=60, type=int, help="Connect/read timeout")
    conf = parser.parse_args()
    urls = [url.strip() for url in conf.input.readlines()]
    urls = list(filter(None, urls))
    base = conf.base.rstrip("/")
    if conf.base:
        urls = [base + "/" + url.lstrip("/") for url in urls]

    session = connection_pool(conf.threads)
    errors_count = 0
    try:
        with ThreadPool(conf.threads) as pool:
            processor = functools.partial(
                request_url,
                session=session,
                headers=parse_user_input_headers(conf.headers),
                check_headers=parse_user_input_headers(conf.check_headers),
                retry_count=conf.retry_count,
                retry_delay=conf.retry_delay,
                timeout=conf.timeout,
            )
            for i, (url, error) in enumerate(pool.imap_unordered(processor, urls), 1):
                if error:
                    errors_count += 1
                    if not conf.no_progress:
                        print("\r", end="")
                    print(url, error)
                    if errors_count > conf.max_errors:
                        print("Too many errors, exiting")
                        break
                if not conf.no_progress:
                    print("\r%.2f%%" % (100 * i / len(urls)), flush=True, end="")
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        if not conf.no_progress:
            print()
    if errors_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
