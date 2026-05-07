# Broadcasting

[Back to README](../README.md)

The bot can broadcast messages from the Archipelago multiworld into one or more Discord channels in real time. Broadcasts are configured per-channel, allowing fine-grained control over which types of messages appear where. For example, you could have a "spoiler-free" channel that only shows join/leave and goal events, and a full-detail channel that shows all item sends.

## Configuration

Broadcast channels are configured via the `discord_broadcast_channels` field in `config.yaml`. Each entry maps a Discord channel name to a list of broadcast categories. If the list is empty, **all** message types will be broadcast to that channel. As an example:

```yaml
discord_broadcast_channels:
    archipelago-full: []
    archipelago-important: ["progression_items", "death_links", "goal_reached"]
```

## Broadcast categories

The following categories can be used to control what is broadcast to each channel:

| Category | Description |
|-|-|
| `progression_items` | Item sends classified as progression |
| `useful_items`      | Item sends classified as useful (includes progression) |
| `all_items`         | All item sends (includes useful and progression, excludes traps) |
| `trap_items`        | Trap item sends |
| `death_links`       | Death link messages |
| `join_leave`        | Player join and leave messages |
| `player_chat`       | Messages sent by players in the Archipelago chat |
| `server_chat`       | Messages sent by the Archipelago server |
| `goal_reached`      | Notifications when a player reaches their goal |

Only one of `progression_items`, `useful_items`, or `all_items` may be specified per channel. These are hierarchical filters; `useful_items` includes progression items, and `all_items` includes both.

## Message specifics

### Item sends

When an item is sent from one slot to another, the bot broadcasts a message indicating the sender, receiver, item name, and location. Users who have subscribed to the item (via `!subscribe`) will be @mentioned in the message. Regardless of whether item sends are broadcast, the full history of item sends is available for users to query with the `!replay` command.

### Death links

When a death link is triggered in the multiworld, the bot can broadcast a message featuring the slot/player who died. Custom death link messages can be configured via the `death_link_messages_path` option in `config.yaml`. This file should contain one message per line, each including a `{player}` token that will be replaced with the dying slot's name. For example:

```
{player} died of dysentery.
It's super effective! {player} fainted.
{player} took a calculated risk. Too bad they're bad at math.
```

If no custom messages file is provided, the default message `{player} has triggered a death link` is used.
