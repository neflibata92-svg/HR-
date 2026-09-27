from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_makefile_exposes_layered_test_and_typecheck_targets() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "test-domain:" in makefile
    assert "python -m pytest -q tests/domain" in makefile
    assert "test-api:" in makefile
    assert "python -m pytest -q tests/api" in makefile
    assert "test-agent:" in makefile
    assert "python -m pytest -q tests/agent" in makefile
    assert "typecheck-web:" in makefile
    assert "npm run typecheck" in makefile
    assert "test-all: test-domain test-api test-agent test-web typecheck-web build-web" in makefile


def test_web_package_exposes_typecheck_script() -> None:
    package_json = (ROOT / "apps" / "web" / "package.json").read_text(encoding="utf-8")

    assert '"typecheck": "vue-tsc --noEmit"' in package_json
