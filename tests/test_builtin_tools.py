from __future__ import annotations

import pytest

from aegis_zero.tools import default_registry


@pytest.fixture
def reg():
    return default_registry(enable_http=False)


async def test_calculate(reg):
    assert (await reg.execute("calculate", {"expression": "2**10 + 4"})).output == "1028"


async def test_calculate_supports_math(reg):
    assert (await reg.execute("calculate", {"expression": "sqrt(16)"})).output == "4.0"


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('ls')",
        "open('/etc/passwd').read()",
        "eval('1+1')",
    ],
)
async def test_calculate_blocks_escapes(reg, expr):
    res = await reg.execute("calculate", {"expression": expr})
    assert not res.ok


async def test_read_and_write_file(reg, tmp_path):
    target = tmp_path / "sub" / "f.txt"
    w = await reg.execute("write_file", {"path": str(target), "content": "hello"})
    assert w.ok and target.read_text() == "hello"
    r = await reg.execute("read_file", {"path": str(target)})
    assert r.output == "hello"


async def test_read_file_truncates(reg, tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 5000)
    res = await reg.execute("read_file", {"path": str(p), "max_bytes": 100})
    assert len(res.output) == 100


async def test_read_missing_file_is_soft_failure(reg, tmp_path):
    res = await reg.execute("read_file", {"path": str(tmp_path / "nope")})
    assert not res.ok and "FileNotFound" in res.error


async def test_list_dir(reg, tmp_path):
    (tmp_path / "a.txt").write_text("1")
    (tmp_path / "d").mkdir()
    out = (await reg.execute("list_dir", {"path": str(tmp_path)})).output
    assert "a.txt" in out and "d/" in out


async def test_format_json(reg):
    assert '"a": 1' in (await reg.execute("format_json", {"text": '{"a":1}'})).output


async def test_format_json_rejects_invalid(reg):
    assert not (await reg.execute("format_json", {"text": "{nope"})).ok


def test_http_tool_can_be_disabled():
    assert "http_fetch" not in default_registry(enable_http=False).names()
    assert "http_fetch" in default_registry(enable_http=True).names()
