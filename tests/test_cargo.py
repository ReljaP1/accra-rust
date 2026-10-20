import shutil
from pathlib import Path

from accra_language import AccraResult, Config, Dockerfile, DockerfileInstruction

from accra_rust import (
    _DOCKER_CREATE_USER,
    _DOCKER_SWITCH_USER,
    Rust,
    docker_setup_workdir,
)


def test_uv():
    correct = AccraResult(
        dockerfile=Dockerfile(
            pre_dependencies_installation=[
                "FROM rust:nightly-slim",
                *docker_setup_workdir("https://fake_repo"),
                *_DOCKER_CREATE_USER,
            ],
            dependencies_installation=[],
            post_dependencies_installation=[
                DockerfileInstruction("RUN cargo build --release"),
                *_DOCKER_SWITCH_USER,
            ],
        )
    )

    rust_sample_project_dir = Path(__file__).resolve().parent / Path(
        "fixtures/rust-sample-project"
    )
    tmp_dir = Path("/tmp/rust-sample-project")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    shutil.copytree(rust_sample_project_dir, tmp_dir)

    try:
        config = Config(cwd=tmp_dir, repo="https://fake_repo")
        rust = Rust(config)

        assert rust.detect()

        result: AccraResult = rust.build()
        assert result.success

        assert result == correct

    finally:
        shutil.rmtree(tmp_dir)
