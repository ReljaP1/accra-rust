import subprocess
from typing import override

from accra_language import (
    AccraBuildError,
    AccraError,
    AccraInstallError,
    AccraResult,
    Config,
    Dependency,
    DockerfileInstruction,
    EnvironmentManager,
    EnvironmentManagerSpec,
)

from .cargo_toml import Cargo_toml
from .utils import _DOCKER_CREATE_USER, _DOCKER_SWITCH_USER, docker_setup_workdir


class Cargo(EnvironmentManager):
    def __init__(self, config: Config):
        spec = EnvironmentManagerSpec(
            name="cargo",
            version="",
            supported_manifests={Cargo_toml(config)},
            config=config,
        )
        super().__init__(spec)

    @override
    def pre_dependencies_installation(self) -> AccraResult:
        result = AccraResult()

        language_version: str | AccraError = self.select_language_version()
        if isinstance(language_version, AccraError):
            return AccraResult(errors=[language_version], success=False)

        # install rustc
        rustup_result = subprocess.run(
            ["rustup", "toolchain", "install", language_version],
            check=False,
            capture_output=True,
            text=True,
            cwd=self.spec.config.cwd,
            env=self.spec.config.env,
            shell=self.spec.config.shell,
            timeout=self.spec.config.timeout,
        )

        if rustup_result.returncode != 0:
            return AccraResult(
                errors=[
                    AccraInstallError(
                        message=f"could not install rust version: {language_version}"
                    )
                ],
                success=False,
            )

        # set rust version
        rustup_result = subprocess.run(
            ["rustup", "override", "set", language_version],
            check=False,
            capture_output=True,
            text=True,
            cwd=self.spec.config.cwd,
            env=self.spec.config.env,
            shell=self.spec.config.shell,
            timeout=self.spec.config.timeout,
        )

        if rustup_result.returncode != 0:
            return AccraResult(
                errors=[
                    AccraInstallError(
                        message=f"could not set rust version: {language_version}"
                    )
                ],
                success=False,
            )

        result.dockerfile.pre_dependencies_installation.append(
            DockerfileInstruction(f"FROM rust:{language_version}-slim")
        )

        result.dockerfile.pre_dependencies_installation.extend(
            docker_setup_workdir(self.spec.config.repo) + _DOCKER_CREATE_USER
        )

        return result

    @override
    def _install_dependency(self, dependency: Dependency) -> AccraResult:
        # cargo downloads dependencies automatically during `cargo build`
        return AccraResult()

    @override
    def post_dependencies_installation(self) -> AccraResult:
        result = AccraResult()
        cargo_build_result = subprocess.run(
            ["cargo", "build", "--release"],
            check=False,
            capture_output=True,
            text=True,
            cwd=self.spec.config.cwd,
            env=self.spec.config.env,
            shell=self.spec.config.shell,
            timeout=self.spec.config.timeout,
        )
        if cargo_build_result.returncode != 0:
            return AccraResult(
                errors=[AccraBuildError(message="failed: cargo build --release")],
                success=False,
            )

        result.dockerfile.post_dependencies_installation.append(
            DockerfileInstruction("RUN cargo build --release")
        )

        result.dockerfile.post_dependencies_installation.extend(_DOCKER_SWITCH_USER)

        return result
