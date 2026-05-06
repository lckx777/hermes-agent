"""Tests for hermes_constants module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

import hermes_constants
from hermes_constants import get_default_hermes_root, is_container


class TestGetDefaultHermesRoot:
    """Tests for get_default_hermes_root() — Docker/custom deployment awareness."""

    def test_no_hermes_home_returns_native(self, tmp_path, monkeypatch):
        """When HERMES_HOME is not set, returns ~/.hermes."""
        monkeypatch.delenv("HERMES_HOME", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert get_default_hermes_root() == tmp_path / ".hermes"

    def test_hermes_home_is_native(self, tmp_path, monkeypatch):
        """When HERMES_HOME = ~/.hermes, returns ~/.hermes."""
        native = tmp_path / ".hermes"
        native.mkdir()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("HERMES_HOME", str(native))
        assert get_default_hermes_root() == native

    def test_hermes_home_is_profile(self, tmp_path, monkeypatch):
        """When HERMES_HOME is a profile under ~/.hermes, returns ~/.hermes."""
        native = tmp_path / ".hermes"
        profile = native / "profiles" / "coder"
        profile.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("HERMES_HOME", str(profile))
        assert get_default_hermes_root() == native

    def test_hermes_home_is_docker(self, tmp_path, monkeypatch):
        """When HERMES_HOME points outside ~/.hermes (Docker), returns HERMES_HOME."""
        docker_home = tmp_path / "opt" / "data"
        docker_home.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("HERMES_HOME", str(docker_home))
        assert get_default_hermes_root() == docker_home

    def test_hermes_home_is_custom_path(self, tmp_path, monkeypatch):
        """Any HERMES_HOME outside ~/.hermes is treated as the root."""
        custom = tmp_path / "my-hermes-data"
        custom.mkdir()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("HERMES_HOME", str(custom))
        assert get_default_hermes_root() == custom

    def test_docker_profile_active(self, tmp_path, monkeypatch):
        """When a Docker profile is active (HERMES_HOME=<root>/profiles/<name>),
        returns the Docker root, not the profile dir."""
        docker_root = tmp_path / "opt" / "data"
        profile = docker_root / "profiles" / "coder"
        profile.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setenv("HERMES_HOME", str(profile))
        assert get_default_hermes_root() == docker_root


class TestIsContainer:
    """Tests for is_container() — Docker/Podman detection."""

    def _reset_cache(self, monkeypatch):
        """Reset the cached detection result before each test."""
        monkeypatch.setattr(hermes_constants, "_container_detected", None)

    def test_detects_dockerenv(self, monkeypatch, tmp_path):
        """/.dockerenv triggers container detection."""
        self._reset_cache(monkeypatch)
        monkeypatch.setattr(os.path, "exists", lambda p: p == "/.dockerenv")
        assert is_container() is True

    def test_detects_containerenv(self, monkeypatch, tmp_path):
        """/run/.containerenv triggers container detection (Podman)."""
        self._reset_cache(monkeypatch)
        monkeypatch.setattr(os.path, "exists", lambda p: p == "/run/.containerenv")
        assert is_container() is True

    def test_detects_cgroup_docker(self, monkeypatch, tmp_path):
        """/proc/1/cgroup containing 'docker' triggers detection."""
        import builtins
        self._reset_cache(monkeypatch)
        monkeypatch.setattr(os.path, "exists", lambda p: False)
        cgroup_file = tmp_path / "cgroup"
        cgroup_file.write_text("12:memory:/docker/abc123\n")
        _real_open = builtins.open
        monkeypatch.setattr("builtins.open", lambda p, *a, **kw: _real_open(str(cgroup_file), *a, **kw) if p == "/proc/1/cgroup" else _real_open(p, *a, **kw))
        assert is_container() is True

    def test_negative_case(self, monkeypatch, tmp_path):
        """Returns False on a regular Linux host."""
        import builtins
        self._reset_cache(monkeypatch)
        monkeypatch.setattr(os.path, "exists", lambda p: False)
        cgroup_file = tmp_path / "cgroup"
        cgroup_file.write_text("12:memory:/\n")
        _real_open = builtins.open
        monkeypatch.setattr("builtins.open", lambda p, *a, **kw: _real_open(str(cgroup_file), *a, **kw) if p == "/proc/1/cgroup" else _real_open(p, *a, **kw))
        assert is_container() is False

    def test_caches_result(self, monkeypatch):
        """Second call uses cached value without re-probing."""
        monkeypatch.setattr(hermes_constants, "_container_detected", True)
        assert is_container() is True
        # Even if we make os.path.exists return False, cached value wins
        monkeypatch.setattr(os.path, "exists", lambda p: False)
        assert is_container() is True


# ──────────────────────────────────────────────────────────────────
# parse_reasoning_effort — alias resilience
# ──────────────────────────────────────────────────────────────────
import pytest
from hermes_constants import parse_reasoning_effort, REASONING_EFFORT_ALIASES


class TestParseReasoningEffort:
    """Lock the contract: user-friendly aliases normalize to canonical levels."""

    @pytest.mark.parametrize("alias,canonical", [
        ("max", "xhigh"),
        ("MAX", "xhigh"),
        (" Max ", "xhigh"),
        ("maximum", "xhigh"),
        ("ultra", "xhigh"),
        ("extreme", "xhigh"),
        ("min", "minimal"),
    ])
    def test_aliases_map_to_canonical(self, alias, canonical):
        assert parse_reasoning_effort(alias) == {"enabled": True, "effort": canonical}

    @pytest.mark.parametrize("level", ["minimal", "low", "medium", "high", "xhigh"])
    def test_canonical_levels_pass_through(self, level):
        assert parse_reasoning_effort(level) == {"enabled": True, "effort": level}

    @pytest.mark.parametrize("disabling", ["none", "off", "disabled"])
    def test_disabling_aliases(self, disabling):
        assert parse_reasoning_effort(disabling) == {"enabled": False}

    @pytest.mark.parametrize("empty", ["", "   ", None])
    def test_empty_returns_none(self, empty):
        assert parse_reasoning_effort(empty) is None

    @pytest.mark.parametrize("bogus", ["garbage", "supreme", "999"])
    def test_unknown_returns_none(self, bogus):
        assert parse_reasoning_effort(bogus) is None

    def test_alias_table_is_consistent(self):
        """Every alias must resolve to a known canonical level or 'none'."""
        from hermes_constants import VALID_REASONING_EFFORTS
        for alias, target in REASONING_EFFORT_ALIASES.items():
            assert target in VALID_REASONING_EFFORTS or target == "none", (
                f"Alias {alias!r} → {target!r} is neither a canonical level nor 'none'"
            )


# ──────────────────────────────────────────────────────────────────
# parse_service_tier — canonical shared parser (cli + gateway)
# ──────────────────────────────────────────────────────────────────
from hermes_constants import (
    parse_service_tier,
    SERVICE_TIER_OFF_VALUES,
    SERVICE_TIER_PRIORITY_VALUES,
)


class TestParseServiceTier:
    """Lock the contract for the shared parser. Both cli.py and
    gateway/run.py delegate to this — drift between them caused warnings
    to keep firing after one surface was patched."""

    @pytest.mark.parametrize("raw", [
        "normal", "default", "standard", "off", "none", "auto",
        "AUTO", " auto ", "Off",
    ])
    def test_off_values_return_none_recognized(self, raw):
        assert parse_service_tier(raw) == (None, True)

    @pytest.mark.parametrize("raw", [
        "fast", "priority", "on", "max", "maximum", "ultra",
        "FAST", " Priority ", "MAX",
    ])
    def test_priority_values(self, raw):
        assert parse_service_tier(raw) == ("priority", True)

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_empty_returns_none_recognized(self, raw):
        assert parse_service_tier(raw) == (None, True)

    @pytest.mark.parametrize("raw", ["garbage", "supreme", "999", "fasten"])
    def test_unknown_returns_unrecognized(self, raw):
        assert parse_service_tier(raw) == (None, False)

    def test_off_and_priority_sets_disjoint(self):
        """A value cannot be both 'off' and 'priority' simultaneously."""
        assert SERVICE_TIER_OFF_VALUES.isdisjoint(SERVICE_TIER_PRIORITY_VALUES)
