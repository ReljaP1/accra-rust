import tomllib
from pathlib import Path
from typing import Any, override

from accra_language import AccraError, Config, Dependency, Manifest, ManifestSpec

# A project that pins no toolchain builds with either.
DEFAULT_VERSIONS = frozenset({"stable", "nightly"})

_DEPENDENCY_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")
_SKIPPED_DIRS = {"target", ".git", "node_modules"}


MAX_FILE_BYTES = 2 * 1024 * 1024


def read_text(path: Path) -> str | None:
    """The text of a regular file of at most 2 MiB (after following symlinks).
    None for a missing file, a device, a directory, a larger or an unreadable
    one, or one that is not UTF-8; never raises."""
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        with open(path, "rb") as f:
            data = f.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            return None
        return data.decode("utf-8")
    except (OSError, ValueError, MemoryError):
        return None


def parse_toml(text: str, path: Path) -> dict[str, Any] | None:
    """The table `text` holds; None when it is not valid TOML."""
    try:
        return tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError, RecursionError):
        return None


def read_toml(path: Path) -> dict[str, Any] | None:
    """The TOML file at `path` read with `read_text`; None when unreadable or
    invalid; never raises."""
    text = read_text(path)
    return None if text is None else parse_toml(text, path)


def pinned_toolchain(cwd: Path) -> str | None:
    """The channel `rust-toolchain.toml` or `rust-toolchain` pins, if any."""
    for name in ("rust-toolchain.toml", "rust-toolchain"):
        path = cwd / name
        text = read_text(path)
        if text is None:
            continue
        stripped = text.strip()
        if not stripped:
            continue
        if name.endswith(".toml") or stripped.startswith("["):
            table = parse_toml(text, path)
            toolchain = table.get("toolchain") if table else None
            channel = toolchain.get("channel") if isinstance(toolchain, dict) else None
        else:
            channel = stripped.splitlines()[0].strip()
        if isinstance(channel, str) and channel.strip():
            return channel.strip()
    return None


def _expand(root: Path, pattern: object) -> list[Path]:
    """The directories a `members` or `exclude` entry names: a plain path, or a
    glob such as `crates/*`."""
    text = str(pattern)
    if not any(c in text for c in "*?["):
        return [root / text]
    try:
        return sorted(root.glob(text))
    except (ValueError, IndexError, NotImplementedError):
        return []


def _member_dirs(root: Path, workspace: dict[str, Any]) -> list[Path]:
    """The directories of the workspace's member crates that hold a manifest."""
    excluded = {
        p.resolve()
        for pattern in workspace.get("exclude", [])
        for p in _expand(root, pattern)
    }
    members: list[Path] = []
    for pattern in workspace.get("members", []):
        for candidate in _expand(root, pattern):
            if (
                (candidate / "Cargo.toml").is_file()
                and candidate.resolve() not in excluded
                and candidate.resolve() != root.resolve()
                and not _SKIPPED_DIRS & set(candidate.relative_to(root).parts)
            ):
                members.append(candidate)
    return members


def manifest_files(root: Path) -> list[Path]:
    """The root `Cargo.toml` and the manifests of its workspace members."""
    top = root / "Cargo.toml"
    cargo = read_toml(top)
    if cargo is None:
        return []
    files = [top]
    for member in _member_dirs(root, cargo.get("workspace", {})):
        path = member / "Cargo.toml"
        if path not in files:
            files.append(path)
    return files


def _dependency_tables(cargo: dict[str, Any]):
    """Every table of dependencies of one manifest: the ordinary ones, those of
    each `[target.<cfg>]` and the workspace's `[workspace.dependencies]`."""
    for key in _DEPENDENCY_TABLES:
        table = cargo.get(key)
        if isinstance(table, dict):
            yield table
    for target in cargo.get("target", {}).values():
        if isinstance(target, dict):
            for key in _DEPENDENCY_TABLES:
                table = target.get(key)
                if isinstance(table, dict):
                    yield table
    shared = cargo.get("workspace", {}).get("dependencies")
    if isinstance(shared, dict):
        yield shared


def _dependency(key: str, value: Any) -> Dependency | None:
    """A crate dependency from one entry of a dependency table; None for a path
    dependency (the project's own crate)."""
    if isinstance(value, str):
        return Dependency(name=key, version=value.strip())
    if not isinstance(value, dict):
        return None
    if "path" in value and "git" not in value and "version" not in value:
        return None
    name = str(value.get("package") or key)
    version = value.get("version")
    return Dependency(name=name, version=str(version).strip() if version else "")


class Cargo_toml(Manifest):
    def __init__(self, config: Config):
        spec = ManifestSpec(name="Cargo.toml", version="", config=config)
        super().__init__(spec)

    def _root(self) -> Path:
        return Path(self.spec.config.cwd or ".")

    @override
    def detect(self) -> bool:
        return read_toml(self._root() / self.spec.name) is not None

    def crate_names(self) -> set[str]:
        """The names of the project's crates: the root package's and every
        workspace member's."""
        names: set[str] = set()
        for path in manifest_files(self._root()):
            cargo = read_toml(path)
            if cargo is None:
                continue
            name = cargo.get("package", {}).get("name")
            if isinstance(name, str) and name:
                names.add(name)
            lib = cargo.get("lib", {}).get("name")
            if isinstance(lib, str) and lib:
                names.add(lib)
        return names

    @override
    def extract_dependencies(self) -> set[Dependency] | None:
        """The crates every manifest of the workspace depends on, without the
        workspace's own crates. A dependency a member takes from the workspace
        (`workspace = true`) is the one `[workspace.dependencies]` names."""
        own = self.crate_names()
        found: dict[str, Dependency] = {}
        for path in manifest_files(self._root()):
            cargo = read_toml(path)
            if cargo is None:
                continue
            for table in _dependency_tables(cargo):
                for key, value in table.items():
                    if isinstance(value, dict) and value.get("workspace") is True:
                        continue
                    dependency = _dependency(str(key), value)
                    if dependency is None or dependency.name in own:
                        continue
                    kept = found.get(dependency.name)
                    if kept is None or (not kept.version and dependency.version):
                        found[dependency.name] = dependency
        return set(found.values()) or None

    @override
    def get_supported_language_versions(self) -> set[str] | AccraError:
        """The toolchain the project pins, else stable and nightly."""
        pinned = pinned_toolchain(self._root())
        return {pinned} if pinned else set(DEFAULT_VERSIONS)
