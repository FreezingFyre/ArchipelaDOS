import sys

from ados.config import load_config
from ados.discord.bot import ADOSBot
from ados.logger import initialize_logging

DEFAULT_CONFIG_PATH = "config.yaml"


def main() -> None:

    if len(sys.argv) > 2:
        print("Usage: python server.py [config_path]")
        sys.exit(1)

    config_path = sys.argv[1] if len(sys.argv) == 2 else DEFAULT_CONFIG_PATH
    try:
        config = load_config(config_path)
        initialize_logging(config)
    except Exception as ex:
        print("\n".join(line for line in str(ex).splitlines() if "further information" not in line))
        sys.exit(1)

    bot = ADOSBot(config)
    bot.execute()


if __name__ == "__main__":
    main()
