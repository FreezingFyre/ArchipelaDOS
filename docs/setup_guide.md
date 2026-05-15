# Setup Guide

[Back to README](../README.md)

## Discord setup

The Discord portion of the setup should be a one-time deal. You will create a bot through the developer portal, then add that bot to your Discord server.

1. Create a new application (bot) through the [Discord Developer Portal](https://discord.com/developers/applications?new_application=true)
    -  Recommended name: `ArchipelaDOS`
    -  Recommended app icon: [ArchipelaDOS logo](../assets/bot_icon.png)
2. Navigate to the `Bot` tab
    - Use `Reset Token` to generate your bot's token, and **save it for later**
    - Enable `Message Content Intent` under `Privileged Gateway Intents`
3. Navigate to the `Installation` tab
    - Enable `Guild Install` and disable `User Install` under `Installation Contexts`
    - Add `bot` under `Scopes` in `Default Install Settings`
    - Add `Permissions`: `Create Public Threads`, `Send Messages`, `Send Messages in Threads`, and `View Channels`
    - Copy the `Discord Provided Link` under `Install Link`
4. Navigate to the copied link
    - Select the server in which to install the bot
    - Authorize the bot without modifying the permissions

## Bot setup

Setting up the bot is also a one-time deal. After you've set it up once (for a particular version), you can run it persistently while connecting/disconnecting from Archipelago rooms via Discord commands.

### Manual

**Prerequisite**: [Python 3.12](https://www.python.org/downloads/latest/python3.12/) (with `pip` package manager)

Note: Python 3.13 should work as well, but 3.14 will *not*, as ArchipelaDOS's dependencies do not yet support the latest version.

1. Download the .zip or .tar.gz of the [latest ArchipelaDOS release](https://github.com/FreezingFyre/ArchipelaDOS/releases/latest)
2. Extract all files from the archive
3. Navigate to the `ArchipelaDOS-<version>` folder within a terminal
    - On Windows, you can Shift/Right-Click in the folder in Windows Explorer and select `Open PowerShell window here`
    - On Windows, you may need to run `Set-ExecutionPolicy RemoteSigned –Scope Process` to allow scripts to run
4. Create a Python virtual environment to run the bot from:
    - `python -m venv adosenv`
5. Activate the virtual environment:
    - On Linux: `source adosenv/bin/activate`
    - On Windows: `.\adosenv\Scripts\Activate.ps1`
6. Install dependencies:
    - `pip install -r requirements.txt`

### Docker

If you're familiar with Docker, it may be an easier way to get started with the bot. The latest Docker image for the bot is available through `ghcr.io/freezingfyre/archipelados:latest`. Within the container, the server is started from within the `/ados` directory, and it expects an `/ados/config.yaml` to be linked externally. Depending on your configuration, you may need to link a death link file as well.

Example `docker run` command:

```
docker run -d \
    -v /path/to/local/config.yaml:/ados/config.yaml:ro \
    -v /path/to/local/deathlinks.txt:/ados/deathlinks.txt:ro \
    ghcr.io/freezingfyre/archipelados:latest
```

Or alternatively, as a `docker-compose.yaml` file:

```yaml
services:
    archipelados:
        image: ghcr.io/freezingfyre/archipelados:latest
        restart: unless-stopped
        volumes:
            - /path/to/local/config.yaml:/ados/config.yaml:ro
            - /path/to/local/deathlinks.txt:/ados/deathlinks.txt:ro
```

## Bot configuration

All bot configuration is done through the `config.yaml` file in the ArchipelaDOS installation folder. The configuration is well-documented there, and should be relatively self-explanatory. Still, the important configurations are described here.

The following configurations are *essential* to set:

- `discord_token`: The token for your Discord bot, copied in step \#2 of [Discord setup](#discord-setup) above
- `discord_server`: The name of the server in which ArchipelaDOS should operate
- `discord_command_channels`: A list of channels in which ArchipelaDOS should listen for, and repond to, user commands
- `discord_broadcast_channels`: A dictionary of which message types to broadcast to which Discord channels; these channels can overlap with those in `discord_command_channels`
    - The simplest configuration here is to broadcast all messages to a single channel; an empty list indicates you want all messages to be broadcast:
        ```yaml
        discord_broadcast_channels: { "my_channel": [] }
        ```
    - If you want to broadcast death link messages to one channel, and item/join/leave messages to another, you could do:
        ```yaml
        discord_broadcast_channels: {
            "channel_1": ["death_links"],
            "channel_2": ["all_items", "join_leave"]
        }
        ```
    - Note that `progression_items`, `useful_items`, and `all_items` are different filter levels for item send messages, and are mutually exclusive. Traps will only be broadcast if `trap_items` are configured.

A fun feature of the bot is the ability to set custom death link messages. If you'd like to enable this functionality, set the `death_link_messages_path` configuration.

## Running the bot

Note that, in order for ArchipelaDOS to communicate with your Archipelago multiworld, it needs to do so through a slot. If you generate your multiworld with the `ArchipelaDOS.yaml` provided in the realease, it will add its own slot that you do not need to configure. Otherwise, you will need to choose a different (password-less) slot to specify at time of connection.

Once your bot environment is set up, and you've configured it appropriately in `config.yaml`, you can actually run ArchipelaDOS. If using Docker, it's as simple as starting the Docker container as one would typically. If running manually, you can:

1. Navigate to the `ArchipelaDOS-<version>` folder within a terminal (the one you set up in [Bot setup](#bot-setup))
    - On Windows, you can Shift/Right-Click in the folder in Windows Explorer and select `Open PowerShell window here`
    - On Windows, you may need to run `Set-ExecutionPolicy RemoteSigned –Scope Process` to allow scripts to run
2. Activate the virtual environment:
    - On Linux: `source adosenv/bin/activate`
    - On Windows: `.\adosenv\Scripts\Activate.ps1`
3. Run the bot:
    - `python server.py`
    - `python server.py <config_file>` if you want to use a config file besides `config.yaml`

Once the bot is running, use the `!room connect` command in Discord to connect the bot to a room/multiworld. The bot supports connecting to rooms hosted on archipelago.gg as well as those that are self-hosted. Some examples of valid `!room connect` commands:

- `!room connect N1J-OYhZRO-FBFcY-bMdea`
- `!room connect https://archipelago.gg/room/N1J-OYhZRO-FBFcY-bMdea`
- `!room connect wss://myownserver.net:54545`
- `!room connect N1J-OYhZRO-FBFcY-bMdea slot: MySlot game: OtherGame`

Once the bot has been connected to a room, that active connection and data related to it will persist even if the bot is restarted. The active room is only disconnected after using the Discord command `!room finalize`, after which a new room can be connected.
