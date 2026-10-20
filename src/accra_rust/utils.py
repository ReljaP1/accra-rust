from functools import cache

from accra_language import DockerfileInstruction


@cache
def docker_setup_workdir(repo: str) -> list[DockerfileInstruction]:
    return [
        DockerfileInstruction(f"RUN git clone {repo} /project"),
        DockerfileInstruction("WORKDIR /project"),
    ]


_DOCKER_CREATE_USER: list[DockerfileInstruction] = [
    DockerfileInstruction(
        'RUN adduser \
                --disabled-password \
                --gecos "" \
                --home "/home/appuser" \
                --shell "/bin/bash" \
                --uid "10001" \
                appuser'
    )
]


_DOCKER_SWITCH_USER: list[DockerfileInstruction] = [
    DockerfileInstruction("RUN chown -R appuser:appuser /project"),
    DockerfileInstruction("USER appuser"),
]
