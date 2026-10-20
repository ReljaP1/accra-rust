import re
import tomllib
from pathlib import Path
from typing import Any, override

from accra_language import AccraError, Config, Dependency, Manifest, ManifestSpec


class Cargo_toml(Manifest):
    def __init__(self, config: Config):
        spec = ManifestSpec(name="Cargo.toml", version="", config=config)
        super().__init__(spec)

        # TODO check the types
        self.package_section: dict[str, Any] | None = None
        self.dependencies_section: dict[str, Any] | None = None

    @override
    def detect(self) -> bool:
        cargo_path: Path = self.spec.config.cwd / Path(self.spec.name)

        try:
            if not Path.exists(cargo_path):
                return False

            with open(cargo_path, "rb") as f:
                cargo = tomllib.load(f)

                self.package_section = cargo.get("package", {})
                self.dependencies_section = cargo.get("dependencies", {})

        except tomllib.TOMLDecodeError:
            return False

        except Exception:  # noqa: BLE001
            return False

        return True

    @override
    def extract_dependencies(self) -> set[Dependency] | None:
        result: set[Dependency] = set()

        if not self.dependencies_section:
            return None

        deps = self.dependencies_section.get("dependencies", [])
        if not deps:
            return None

        for dep in deps:
            pkg = re.split(r"[<>=~!]", dep)

            pkg_name = pkg[0].strip()

            # TODO refine the version parsing
            pkg_ver = ""

            if pkg_name:
                result.add(Dependency(name=pkg_name, version=pkg_ver))

        return result

    @override
    def get_supported_language_versions(self) -> set[str] | AccraError:
        # cargo is backwards compatible; by specifying nightly we cover
        # the entire range of project versions
        return {"nightly"}
