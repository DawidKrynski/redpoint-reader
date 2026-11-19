import json

from redpoint import config, ipc


def test_config_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "c" / "config.json"
    c = config.Config(path)
    assert c["wpm"] == 350 and c["hotkey"]
    c["wpm"] = 99999
    c.save()
    raw = json.loads(path.read_text())
    assert raw["wpm"] == 99999
    assert config.Config(path)["wpm"] == 1500  # clamped on load


def test_config_ignores_garbage(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"wpm": "fast", "unknown": 1}')
    c = config.Config(path)
    assert c["wpm"] == 350 and "unknown" not in c


def test_send_without_server(monkeypatch, tmp_path):
    monkeypatch.setenv("REDPOINT_SOCKET", str(tmp_path / "nothing.sock"))
    assert ipc.send({"cmd": "noop"}, timeout=0.2) is False


def test_cli_messages(tmp_path):
    from redpoint.cli import build_message, parse_args

    f = tmp_path / "t.txt"
    f.write_text("zażółć", encoding="utf-8")
    assert build_message(parse_args(["--read"])) == {"cmd": "read"}
    assert build_message(parse_args([])) == {"cmd": "settings"}
    assert build_message(parse_args(["--background"])) == {"cmd": "noop"}
    assert build_message(parse_args([str(f)])) == {"cmd": "text", "text": "zażółć"}
