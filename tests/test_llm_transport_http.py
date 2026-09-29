"""HTTP transport of the LLM client.

* What goes on the wire: URL, bearer key, the body as given, the given timeout.
* Backpressure (429, 503/504 with Retry-After) goes up to the limiter unrepeated.
* Only a request the server never received whole is repeated.
* The body comes back as received, never parsed here.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
from email.message import Message

import pytest

from tools.llm.transport import http as transport_http
from tools.llm.transport.base import HTTP_ERROR, NETWORK, OK, RATE_LIMITED, TIMEOUT
from tools.llm.transport.http import HttpClient, parse_retry_after

#: The wall clock the fake reports; ``parse_retry_after`` measures dates from it.
NOW = 1792000000.0


class FakeClock:
    """Stands in for the ``time`` module inside the transport: nothing really sleeps."""

    def __init__(self, wall: float = NOW) -> None:
        self.now = 0.0
        self.wall = wall
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def time(self) -> float:
        return self.wall + self.now


class FixedRandom:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


class FakeResponse:
    def __init__(self, payload=None, status=200, headers=None, raw=None):
        if raw is not None:
            self._raw = raw
        else:
            self._raw = json.dumps(payload).encode() if payload is not None else b""
        self.status = status
        self.headers = headers or Message()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Recorder:
    """Replaces ``urlopen``: records each request and answers with the queued
    outcomes, repeating the last one."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def headers(**pairs) -> Message:
    message = Message()
    for key, value in pairs.items():
        message[key.replace("_", "-")] = str(value)
    return message


def http_error(code, hdrs=None, raw=b""):
    error = urllib.error.HTTPError(
        url="https://example/api",
        code=code,
        msg="nope",
        hdrs=hdrs or Message(),
        fp=None,
    )
    error.read = lambda: raw
    return error


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(transport_http, "time", fake)
    monkeypatch.setattr(transport_http, "random", FixedRandom(0.0))
    return fake


@pytest.fixture
def opener(monkeypatch, clock):
    """Install a ``Recorder`` answering with the given outcomes."""

    def install(*outcomes):
        recorder = Recorder(*outcomes)
        monkeypatch.setattr(transport_http, "urlopen", recorder)
        return recorder

    return install


def client(**kw) -> HttpClient:
    kw.setdefault("attempts", 2)
    return HttpClient(base_url="https://example/v1", api_key="secret", **kw)


# --- success --- #


def test_success_returns_the_raw_body_and_status(opener):
    payload = {"choices": [{"message": {"content": "text"}}]}
    opener(FakeResponse(payload))
    result = client().send("chat/completions", {"model": "m"}, timeout=45)
    assert result.status == OK
    assert result.http_status == 200
    assert json.loads(result.raw.decode("utf-8")) == payload


def test_request_carries_url_bearer_key_json_body_and_the_given_timeout(opener):
    recorder = opener(FakeResponse({}))
    client().send("chat/completions", {"model": "m", "Größe": "Straße"}, timeout=180)
    request = recorder.requests[0]
    assert request.full_url == "https://example/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer secret"
    assert json.loads(request.data.decode("utf-8"))["Größe"] == "Straße"
    assert recorder.timeouts[0] == 180


def test_the_body_is_sent_as_given_without_inspection(opener):
    recorder = opener(FakeResponse({}))
    payload = {"model": "m", "response_format": {"json_schema": {"schema": {"a": 1}}}}
    client().send("chat/completions", payload, timeout=45)
    assert json.loads(recorder.requests[0].data.decode("utf-8")) == payload


# --- backpressure goes up to the limiter --- #


def test_429_is_not_retried_here(opener):
    recorder = opener(http_error(429, headers(Retry_After="7")))
    result = client(attempts=3).send("chat", {}, timeout=45)
    assert result.status == RATE_LIMITED
    assert result.retry_after == 7.0
    assert len(recorder.requests) == 1


def test_429_without_retry_after_still_goes_up(opener):
    recorder = opener(http_error(429))
    result = client().send("chat", {}, timeout=45)
    assert result.status == RATE_LIMITED
    assert result.retry_after is None
    assert len(recorder.requests) == 1


def test_503_with_retry_after_is_backpressure_not_a_transport_failure(opener):
    recorder = opener(http_error(503, headers(Retry_After="3")))
    result = client(attempts=3).send("chat", {}, timeout=45)
    assert result.status == RATE_LIMITED
    assert result.retry_after == 3.0
    assert len(recorder.requests) == 1


@pytest.mark.parametrize(
    "spelling", ["Retry-After", "retry-after", "RETRY-AFTER", "ReTrY-aFtEr"]
)
def test_retry_after_is_read_case_insensitively_on_429(opener, spelling):
    message = Message()
    message[spelling] = "7"
    opener(http_error(429, message))
    assert client().send("chat", {}, timeout=45).retry_after == 7.0


def test_lowercase_retry_after_still_makes_503_backpressure(opener):
    message = Message()
    message["retry-after"] = "3"
    recorder = opener(http_error(503, message))
    result = client(attempts=3).send("chat", {}, timeout=45)
    assert result.status == RATE_LIMITED
    assert result.retry_after == 3.0
    assert len(recorder.requests) == 1


def test_503_without_retry_after_is_retried(opener):
    recorder = opener(http_error(503), FakeResponse({"ok": True}))
    result = client(attempts=2).send("chat", {}, timeout=45)
    assert result.status == OK
    assert len(recorder.requests) == 2


def test_exhausted_503_stays_an_http_error_and_is_not_renamed_to_network(opener):
    recorder = opener(http_error(503))
    result = client(attempts=2).send("chat", {}, timeout=45)
    assert result.status == HTTP_ERROR
    assert result.http_status == 503
    assert len(recorder.requests) == 2


def test_exhausted_504_stays_an_http_error(opener):
    opener(http_error(504))
    result = client(attempts=2).send("chat", {}, timeout=45)
    assert result.status == HTTP_ERROR
    assert result.http_status == 504


# --- failures before the send: free to repeat --- #
#
# Which side of the send a failure lands on decides whether it is repeated.
# urllib wraps connect/send errors in URLError - the request never reached the
# server whole. Everything raised bare happened while waiting for or reading the
# answer: the request was delivered, and a finished generation may be hiding
# behind the failure. Those are never repeated.


def test_connect_failure_is_retried_then_named_network_and_unsent(opener):
    recorder = opener(urllib.error.URLError(ConnectionRefusedError("refused")))
    result = client(attempts=2).send("chat", {}, timeout=45)
    assert result.status == NETWORK
    assert result.sent is False
    assert len(recorder.requests) == 2


def test_connect_timeout_is_retried_and_named_timeout(opener):
    recorder = opener(urllib.error.URLError(TimeoutError("connect")))
    result = client(attempts=2).send("chat", {}, timeout=45)
    assert result.status == TIMEOUT
    assert result.sent is False
    assert len(recorder.requests) == 2


def test_dns_failure_is_network_and_unsent(opener):
    opener(urllib.error.URLError("Name or service not known"))
    result = client(attempts=1).send("chat", {}, timeout=45)
    assert result.status == NETWORK
    assert result.sent is False


def test_a_connect_failure_recovers_on_the_second_attempt(opener):
    opener(
        urllib.error.URLError(ConnectionResetError("reset")), FakeResponse({"ok": True})
    )
    assert client().send("chat", {}, timeout=45).status == OK


def test_attempts_is_a_ceiling_on_repeats(opener):
    recorder = opener(urllib.error.URLError(ConnectionResetError("reset")))
    client(attempts=3).send("chat", {}, timeout=45)
    assert len(recorder.requests) == 3


def test_repeats_back_off_between_attempts(opener, clock):
    opener(urllib.error.URLError(ConnectionResetError("reset")))
    client(attempts=3, backoff=0.5, jitter=0.0).send("chat", {}, timeout=45)
    assert clock.slept == [0.5, 1.0]


# --- failures after the send: never repeated --- #


def test_read_timeout_is_named_and_not_retried(opener):
    recorder = opener(TimeoutError("read timed out"))
    result = client(attempts=2).send("chat", {}, timeout=45)
    assert result.status == TIMEOUT
    assert result.sent is True
    assert len(recorder.requests) == 1


def test_a_reset_while_waiting_for_the_answer_is_not_retried(opener):
    recorder = opener(ConnectionResetError("reset by peer"))
    result = client(attempts=2).send("chat", {}, timeout=45)
    assert result.status == NETWORK
    assert result.sent is True
    assert len(recorder.requests) == 1


@pytest.mark.parametrize(
    "error",
    [http.client.BadStatusLine("garbage"), http.client.RemoteDisconnected("closed")],
    ids=["BadStatusLine", "RemoteDisconnected"],
)
def test_a_garbled_or_closed_response_is_network_and_not_retried(opener, error):
    """BadStatusLine / RemoteDisconnected are HTTPException, not OSError: without
    their own branch they escape the port as a traceback. And bytes did arrive -
    or the server hung up after reading the request - so it may have been served."""
    recorder = opener(error)
    result = client(attempts=2).send("chat", {}, timeout=45)
    assert result.status == NETWORK
    assert type(error).__name__ in result.error
    assert result.sent is True
    assert len(recorder.requests) == 1


def test_a_body_cut_off_after_the_headers_is_network_and_not_retried(opener):
    """The headers arrived: the generation was served, only the body was lost.
    http.client.IncompleteRead is an HTTPException too."""

    class CutOff(FakeResponse):
        def read(self):
            raise http.client.IncompleteRead(b"partial")

    recorder = opener(CutOff())
    result = client(attempts=3).send("chat", {}, timeout=45)
    assert result.status == NETWORK
    assert "IncompleteRead" in result.error
    assert result.http_status == 200  # the server did answer
    assert result.sent is True
    assert len(recorder.requests) == 1


# --- hard HTTP errors --- #


def test_400_is_not_retried(opener):
    recorder = opener(http_error(400))
    result = client(attempts=3).send("chat", {}, timeout=45)
    assert result.status == HTTP_ERROR
    assert result.http_status == 400
    assert len(recorder.requests) == 1


def test_402_is_not_retried(opener):
    recorder = opener(http_error(402))
    assert client(attempts=3).send("chat", {}, timeout=45).status == HTTP_ERROR
    assert len(recorder.requests) == 1


def test_an_error_body_that_cannot_be_read_is_simply_absent(opener):
    error = http_error(400)

    def unreadable():
        raise OSError("socket closed")

    error.read = unreadable
    opener(error)
    result = client(attempts=1).send("chat", {}, timeout=45)
    assert result.status == HTTP_ERROR
    assert result.raw == b""


# --- Retry-After parsing --- #


def test_retry_after_in_seconds():
    assert parse_retry_after("12") == 12.0


def test_retry_after_as_an_http_date_is_measured_from_the_wall_clock(clock):
    assert parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") == 567680.0


def test_retry_after_date_in_the_past_is_zero_not_negative(clock):
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0


@pytest.mark.parametrize("value", [None, "", "someday"])
def test_retry_after_missing_or_garbage_is_none(value):
    assert parse_retry_after(value) is None


# --- the body comes back as received --- #


def test_a_non_json_body_survives_intact(opener):
    page = b"<html><body>502 Bad Gateway</body></html>"
    opener(FakeResponse(raw=page))
    result = client().send("chat", {}, timeout=45)
    assert result.status == OK
    assert result.raw == page


def test_truncated_json_survives_intact(opener):
    cut = '{"choices": [{"message": {"content": "Grö'.encode()
    opener(FakeResponse(raw=cut))
    assert client().send("chat", {}, timeout=45).raw == cut


def test_json_that_is_not_an_object_survives_intact(opener):
    opener(FakeResponse(raw=b"[1, 2, 3]"))
    assert client().send("chat", {}, timeout=45).raw == b"[1, 2, 3]"


def test_an_error_body_is_kept_too(opener):
    explanation = b'{"error": {"message": "no such model"}}'
    opener(http_error(400, raw=explanation))
    result = client(attempts=1).send("chat", {}, timeout=45)
    assert result.status == HTTP_ERROR
    assert result.raw == explanation


def test_charset_comes_from_the_content_type_header(opener):
    opener(
        FakeResponse(
            {}, headers=headers(Content_Type="application/json; charset=UTF-8")
        )
    )
    assert client().send("chat", {}, timeout=45).charset == "utf-8"


def test_charset_defaults_to_utf8_when_the_header_is_silent(opener):
    opener(FakeResponse({}))
    assert client().send("chat", {}, timeout=45).charset == "utf-8"


# --- construction --- #


def test_attempts_below_one_are_refused():
    with pytest.raises(ValueError, match="attempts"):
        HttpClient(base_url="https://example/v1", api_key="secret", attempts=0)
