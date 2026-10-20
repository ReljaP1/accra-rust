from accra_language import Config, EnvironmentManager, Language, LanguageSpec

from .cargo import Cargo


class Rust(Language):
    def __init__(self, config: Config, env_manager: EnvironmentManager | None = None):
        spec = LanguageSpec(
            name="rust",
            version="nightly",
            config=config,
            supported_env_managers={Cargo(config)},
        )
        super().__init__(spec, env_manager=env_manager)
