"""Cross-cutting HTTP helper with exponential backoff."""

import time

import requests

from app.config import RETRY_ATTEMPTS, RETRY_BACKOFF_S


def post_with_retry(url, *, headers=None, json=None, data=None, files=None,
                    timeout=30):
    """POST with exponential-backoff retries on transient failures.

    Retries on connection errors, timeouts, and 5xx. 4xx responses are
    surfaced immediately — they are caller errors, not transient ones.
    """
    last_err = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.post(
                url, headers=headers, json=json, data=data, files=files,
                timeout=timeout,
            )
            if 500 <= resp.status_code < 600:
                last_err = requests.HTTPError(
                    f"{resp.status_code}: {resp.text[:500]}"
                )
            else:
                try:
                    resp.raise_for_status()
                except requests.HTTPError as e:
                    print(f"[HTTP {resp.status_code}] {resp.text[:500]}")
                    raise
                return resp
        except requests.HTTPError:
            raise
        except requests.RequestException as e:
            last_err = e

        # Back off before the next try, but skip the sleep after the last one.
        if attempt < RETRY_ATTEMPTS - 1:
            sleep_for = RETRY_BACKOFF_S * (2 ** attempt)
            print(f"[retry {attempt + 1}/{RETRY_ATTEMPTS - 1}] "
                  f"{type(last_err).__name__}, sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)

    raise last_err
