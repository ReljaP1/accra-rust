import shlex

from accra_language import DockerfileInstruction

# The layout of the official `rust` images, which the toolchain steps reproduce
# on ACCRa's Debian base.
_RUSTUP_HOME = "/usr/local/rustup"
_CARGO_HOME = "/usr/local/cargo"

# What cargo builds need beyond the compiler: a C and C++ toolchain, pkg-config
# and OpenSSL's headers.
BUILD_PACKAGES = ("build-essential", "pkg-config", "libssl-dev", "ca-certificates")

DOCKER_CHOWN_CARGO = DockerfileInstruction(
    f"RUN chown -R appuser:appuser {_CARGO_HOME}"
)


def rustup_toolchain_line(version: str) -> DockerfileInstruction:
    """The step that installs `version` with rustup and makes it the default."""
    quoted = shlex.quote(version)
    return DockerfileInstruction(
        f"RUN rustup toolchain install {quoted} --profile minimal "
        f"&& rustup default {quoted}"
    )


def build_packages_line() -> DockerfileInstruction:
    """The step that installs what cargo builds need (a C and C++ toolchain,
    pkg-config, OpenSSL's headers)."""
    packages = " ".join(BUILD_PACKAGES)
    return DockerfileInstruction(
        "RUN apt-get update && apt-get install -y --no-install-recommends "
        f"{packages} && rm -rf /var/lib/apt/lists/*"
    )


def rustup_install_lines() -> list[DockerfileInstruction]:
    """The steps that install rustup, without a toolchain, on a Debian base."""
    return [
        DockerfileInstruction(
            f"ENV RUSTUP_HOME={_RUSTUP_HOME} CARGO_HOME={_CARGO_HOME}"
        ),
        DockerfileInstruction(f"ENV PATH={_CARGO_HOME}/bin:$PATH"),
        # NOTE curl and the CA certificates come from ACCRa's own apt line
        DockerfileInstruction(
            "RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs "
            "| sh -s -- -y --profile minimal --default-toolchain none --no-modify-path"
        ),
    ]
