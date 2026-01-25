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

Setting up the bot is also a one-time deal. After you've set it up once (for a particular version), you can re-run the same bot for a different Archipelago room with minor configuration tweaks.

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

## Bot configuration

All bot configuration is done through the `config.yaml` file in the ArchipelaDOS installation folder. The configuration is well-documented there, and should be relatively self-explanatory. Still, the important configurations are described here.

Note that, in order for ArchipelaDOS to communicate with your Archipelago multiworld, it needs to do so through a slot. If you generate your multiworld with the `ArchipelaDOS.yaml` provided in the realease, it will add its own slot that you do not need to configure. Otherwise, you will need to change the configuration to connect through a different slot (which must be password-less).

The following configurations are *essential* to set:

- `archipelago_room`: The room ID for your multiworld hosted on archipelago.gg
- `discord_token`: The token for your Discord bot, copied in step \#2 of [Discord setup](#discord-setup) above
- `discord_server`: The name of the server in which ArchipelaDOS should operate
- `discord_command_channels`: A list of channels in which ArchipelaDOS should listen for, and repond to, user commands
- `discord_broadcast_channels`: A dictionary of which message types to broadcast to which Discord channels; these channels can overlap with those in `discord_command_channels`
    - The simplest configuration here is to broadcast all messages to a single channel; an empty list indicates you want all messages to be broadcast:
        ```
        discord_broadcast_channels: { "my_channel": [] }
        ```
    - If you want to broadcast death link messages to one channel, and item/join/leave messages to another, you could do:
        ```
        discord_broadcast_channels: {
            "channel_1": ["death_links"]
            "channel_2": ["all_items", "join_leave"]
        }
        ```
    - Note that `progression_items`, `useful_items`, and `all_items` are different filter levels for item send messages, and are mutually exclusive. Traps will only be broadcast if `trap_items` are configured.

The following configurations may need to be set, depending on your setup:

- `archipelago_slot`: If you did not generate your multiworld with `ArchipelaDOS.yaml`, change this to a slot that ArchipelaDOS can use when connecting to the server
- `archipelago_game`: The game for the slot configured in `archipelago_slot`
- `death_link_messages_path`: A filename containing custom death link notifications

## Running the bot

Once your bot environment is set up, and you've configured it appropriately in `config.yaml`, you can actually run ArchipelaDOS.

1. Navigate to the `ArchipelaDOS-<version>` folder within a terminal (the one you set up in [Bot setup](#bot-setup))
    - On Windows, you can Shift/Right-Click in the folder in Windows Explorer and select `Open PowerShell window here`
    - On Windows, you may need to run `Set-ExecutionPolicy RemoteSigned –Scope Process` to allow scripts to run
2. Activate the virtual environment:
    - On Linux: `source adosenv/bin/activate`
    - On Windows: `.\adosenv\Scripts\Activate.ps1`
3. Run the bot:
    - `python server.py`
    - `python server.py <config_file>` if you want to use a config file besides `config.yaml`
