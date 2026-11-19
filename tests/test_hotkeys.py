import pytest

from redpoint import hotkeys as H
from redpoint.hotkeys.portal import xdg_trigger


def test_parse_and_normalise():
    hk = H.parse("Ctrl + Alt + Space")
    assert str(hk) == "ctrl+alt+space"
    assert str(H.parse("win+ALT+c")) == "alt+super+c" or str(H.parse("win+ALT+c")) == "alt+super+c"
    assert H.parse("cmd+option+r").modifiers == {"super", "alt"}


@pytest.mark.parametrize("bad", ["", "space", "ctrl+", "hyper+a", "ctrl+ü", "ctrl+pageup"])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        H.parse(bad)


def test_xdg_trigger():
    assert xdg_trigger(H.parse("super+alt+c")) == "ALT+LOGO+c"
    assert xdg_trigger(H.parse("ctrl+alt+space")) == "CTRL+ALT+space"
    assert xdg_trigger(H.parse("ctrl+shift+f5")) == "CTRL+SHIFT+F5"


def test_label():
    assert "Space" in H.parse("ctrl+alt+space").label()
