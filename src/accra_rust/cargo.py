import subprocess
from pathlib import Path
from typing import override

from accra_language import (
    AccraBuildError,
    AccraError,
    AccraInstallError,
    AccraResult,
    Config,
    Dependency,
    Dockerfile,
    DockerfileInstruction,
    EnvironmentManager,
    EnvironmentManagerSpec,
)

from .cargo_toml import Cargo_toml, read_toml
from .utils import (
    DOCKER_CHOWN_CARGO,
    build_packages_line,
    rustup_install_lines,
    rustup_toolchain_line,
)

_RUN_FAILED = "failed: "


def version_order(versions: set[str]) -> list[str]:
    """The toolchain the project pins, else stable, else nightly, then the
    rest in alphabetical order."""
    first = [v for v in ("stable", "nightly") if v in versions]
    return first + sorted(versions - set(first))


class Cargo(EnvironmentManager):
    def __init__(self, config: Config):
        spec = EnvironmentManagerSpec(
            name="cargo",
            version="",
            supported_manifests={Cargo_toml(config)},
            config=config,
            version_order=version_order,
        )
        super().__init__(spec)

    def _run(
        self, command: list[str], error_class: type[AccraError], message: str
    ) -> subprocess.CompletedProcess[str] | AccraError:
        """Runs `command` in the project; the error for one that failed to run,
        timed out or exited non-zero."""
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                cwd=self.spec.config.cwd,
                env=self.spec.config.env,
                shell=self.spec.config.shell,
                timeout=self.subprocess_timeout(),
            )
        except Exception as exc:  # noqa: BLE001 never-raises contract
            return error_class.from_exception(exc, f"{_RUN_FAILED}{message}")
        if completed.returncode != 0:
            return error_class(
                message=f"{_RUN_FAILED}{message} (exit code {completed.returncode})",
                command=command,
                exit_code=completed.returncode,
                stderr=(completed.stderr or "")[-2000:] or None,
            )
        return completed

    @override
    def pre_dependencies_installation(self) -> AccraResult:
        version = self.select_language_version()
        if isinstance(version, AccraError):
            return AccraResult(errors=[version], success=False)

        installed = self._run(
            ["rustup", "toolchain", "install", version, "--profile", "minimal"],
            AccraInstallError,
            f"rustup toolchain install {version}",
        )
        if isinstance(installed, AccraError):
            return AccraResult(errors=[installed], success=False)

        # NOTE an override, not `rust-toolchain`: it also holds for a version the
        # caller chose and it adds no file to the analysed project
        selected = self._run(
            ["rustup", "override", "set", version],
            AccraInstallError,
            f"rustup override set {version}",
        )
        if isinstance(selected, AccraError):
            return AccraResult(errors=[selected], success=False)

        return AccraResult(
            dockerfile=Dockerfile(
                # NOTE ACCRa's base is a bare Debian image: everything cargo
                # needs is installed here, for every version
                pre_dependencies_installation=[
                    build_packages_line(),
                    *rustup_install_lines(),
                    rustup_toolchain_line(version),
                ]
            )
        )

    @override
    def dependencies_installation(self) -> AccraResult:
        """Downloads every crate the workspace depends on with `cargo fetch`:
        cargo resolves and fetches them together, not one by one."""
        if not self._get_dependencies():
            return AccraResult()

        fetched = self._run(
            ["cargo", "fetch"], AccraInstallError, "cargo fetch (dependencies)"
        )
        if isinstance(fetched, AccraError):
            return AccraResult(errors=[fetched], success=False)

        return AccraResult(
            dockerfile=Dockerfile(
                dependencies_installation=[DockerfileInstruction("RUN cargo fetch")]
            )
        )

    @override
    def _install_dependency(self, dependency: Dependency) -> AccraResult:
        # NOTE cargo fetches the dependencies together (`dependencies_installation`)
        return AccraResult()

    @override
    def post_dependencies_installation(self) -> AccraResult:
        # the image's steps run as root; the user that runs the project owns cargo
        return AccraResult(
            dockerfile=Dockerfile(post_dependencies_installation=[DOCKER_CHOWN_CARGO])
        )

    # -- the project ------------------------------------------------

    @override
    def has_project_install(self) -> bool:
        return bool(self.present_manifests)

    @override
    def install_project(self) -> AccraResult:
        """Compiles the project in release mode; a project that does not
        compile leaves the fetched dependencies as they are."""
        built = self._run(
            ["cargo", "build", "--release"],
            AccraBuildError,
            "cargo build --release",
        )
        if isinstance(built, AccraError):
            return AccraResult(errors=[built], success=False)

        return AccraResult(
            dockerfile=Dockerfile(
                post_dependencies_installation=[
                    DockerfileInstruction("RUN cargo build --release"),
                    DOCKER_CHOWN_CARGO,
                ]
            )
        )

    @override
    def project_names(self) -> set[str]:
        """The crates of the project, a workspace's members included."""
        names: set[str] = set()
        for manifest in self.present_manifests:
            if isinstance(manifest, Cargo_toml):
                names |= manifest.crate_names()
        return names

    @override
    def is_usable(self, dependency: Dependency) -> bool | AccraError:
        """Whether the project's build can use the crate: one of the project's
        own, or one `Cargo.lock` resolved and `cargo fetch` downloaded."""
        name = dependency.name.strip()
        if name in self.project_names():
            return True
        installed = self.installed_dependencies()
        if isinstance(installed, AccraError):
            return installed
        return name in {d.name for d in installed}

    @override
    def installed_dependencies(self) -> set[Dependency] | AccraError:
        """The crates `Cargo.lock` resolved from a registry or a repository, as
        exact versions (`=1.2.3`)."""
        lock = Path(self.spec.config.cwd or ".") / "Cargo.lock"
        if not lock.exists():
            return AccraInstallError(message="no Cargo.lock: dependencies not fetched")
        table = read_toml(lock)
        if table is None:
            return AccraInstallError(message="cannot read Cargo.lock")
        packages = table.get("package", [])
        if not isinstance(packages, list):
            return AccraInstallError(message="cannot read Cargo.lock")
        return {
            Dependency(name=p["name"], version=f"={p['version']}")
            for p in packages
            if isinstance(p, dict)
            and p.get("source")
            and p.get("name")
            and p.get("version")
        }
