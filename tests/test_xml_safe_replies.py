"""Control characters in replies must not make the XML-RPC response unparseable."""

import sys
import xmlrpc.client

import pytest

from test_rpc_concurrency import client, filtered_server_class, running_server


def xml_safe(value):
    return sys.modules[filtered_server_class().__module__].xml_safe(value)


class Noisy:
    def execute_code(self, code: str) -> dict:
        return {"success": True, "message": "Output: \x1b[31mred\x1b[0m nul\x00 tab\t"}

    def get_async_status(self) -> dict:
        return {"success": True, "jobs": [{"id": "job-1", "error": "ValueError: x\x01y"}]}

    def fail(self) -> None:
        raise ValueError("bad\x00msg")

    def fault(self) -> None:
        raise xmlrpc.client.Fault(1, "GUI_DISPATCH_STUCK: bad\x0bmsg")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("\x1b[0m", "\\x1b[0m"),
        ("a\x00b\x0bc", "a\\x00b\\x0bc"),
        ("lone \udcff", "lone \\udcff"),
        ("￾", "\\ufffe"),
        ("tab\tnewline\ncr\r ü 漢 🎉", "tab\tnewline\ncr\r ü 漢 🎉"),
        ({"k\x01": ["v\x02", ("w\x03",)]}, {"k\\x01": ["v\\x02", ["w\\x03"]]}),
        (None, None),
        (3.5, 3.5),
    ],
)
def test_xml_safe_escapes_only_characters_xml_cannot_carry(value, expected) -> None:
    assert xml_safe(value) == expected


def test_control_characters_reach_the_client_escaped() -> None:
    with running_server(Noisy()) as (host, port):
        proxy = client(host, port, 5)
        assert proxy.execute_code("print('\\x1b[31mred')") == {
            "success": True, "message": "Output: \\x1b[31mred\\x1b[0m nul\\x00 tab\t",
        }
        assert proxy.get_async_status()["jobs"][0]["error"] == "ValueError: x\\x01y"


@pytest.mark.parametrize(("method", "text"), [("fail", "bad\\x00msg"), ("fault", "bad\\x0bmsg")])
def test_fault_text_reaches_the_client_escaped(method: str, text: str) -> None:
    with running_server(Noisy()) as (host, port):
        with pytest.raises(xmlrpc.client.Fault) as raised:
            getattr(client(host, port, 5), method)()
        assert text in raised.value.faultString
