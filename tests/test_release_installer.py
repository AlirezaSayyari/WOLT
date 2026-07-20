from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]


def test_public_installer_is_clone_free_and_verifies_signed_image() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "git clone" not in script
    assert "require_command git" not in script
    assert "cosign verify" in script
    assert "docker-manifest-digest" in script
    assert 'docker cp "${SOURCE_CONTAINER}:/opt/wolt-runtime/."' in script
    assert "--upgrade-existing" in script
    assert "f7622ed3cf22e55e1ae6377c080979ff77a22da9981c11df222a2e444991e7cf" in script
    assert "90e7ae0b5dfd60f20816b52c012addf7fc055ebcc7bea4ce81c428ca8518c302" in script


def test_release_shell_scripts_pass_bash_syntax_validation() -> None:
    scripts = [
        ROOT / "install.sh",
        ROOT / "scripts" / "init-web-env.sh",
        ROOT / "scripts" / "install-cosign.sh",
        ROOT / "scripts" / "install-host-agent.sh",
    ]

    subprocess.run(["bash", "-n", *map(str, scripts)], check=True)


def test_release_compose_requires_an_explicit_image() -> None:
    compose = (ROOT / "compose.web.yml").read_text(encoding="utf-8")

    assert "WOLT_IMAGE:?" in compose
    assert "wolt:dev" not in compose


def test_production_image_contains_the_minimal_runtime_contract() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "/opt/wolt-runtime/" in dockerfile
    assert "scripts/install-cosign.sh" in dockerfile
    assert "compose.host-agent.yml" in dockerfile


def test_host_operations_ui_uses_the_minimal_runtime_repair_path() -> None:
    bundle = "\n".join(
        asset.read_text(encoding="utf-8")
        for asset in (ROOT / "app" / "web" / "static" / "assets").glob("*.js")
    )

    assert "sudo /data/WOLT/runtime/scripts/install-host-agent.sh /data/WOLT" in bundle
    assert "sudo ./scripts/install-host-agent.sh /data/WOLT" not in bundle
