# Discord Commands

[Back to README](../README.md)

All commands are available to all users, from whatever Discord channels are configured. Commands are also usable from threads within the configured channels, and in user DMs. For some commands with large output (such as `!help` and `!replay`), the bot will reply in a thread to keep the main channel decluttered. These threads are automatically archived by the bot after a period of inactivity.

For the below command specs, for those who are unfamiliar: `<angle_brackets>` denote required fields, while `[square_brackets]` denote optional fields. Fields do *not* need to be surrounded with quotes to work, and slot/item/group names are *not* case-sensitive. Some examples of valid commands (all specified in the tables below):

- `!help`
- `!help slot clear`
- `!slot add My Slot`
- `!replay all traps`
- `!replay all slot: My Slot`
- `!subscribe item My Item slot: My Slot`
- `!deaths graph`

## General commands

| | |
|-|-|
| `!help [command]` | Print general help info, or help for a specific command/subcommand |
| `!hello`          | Greet the bot (it might greet you back) |
| `!dmme`           | Trigger the bot to send you a direct message |
| `!threadme`       | Trigger the bot to send you a message in a new thread |
| `!refresh`        | Refresh the room on archipelago.gg, reconnecting the bot if it got disconnected |
| `!info`           | Get information about the Archipelago room (port, list of slots, etc) |

## Slot registration commands

Users can "register" themselves for particular slots. This affects which slots' items are replayed during `!replay` commands, among other things.

| | |
|-|-|
| `!slot add <slot>`    | Registers you for the given `slot` |
| `!slot remove <slot>` | Unregisters you from the given `slot` |
| `!slot list`          | Lists all slots for which you are registered |
| `!slot clear`         | Clears your registration for all slots |
| `!slot info <slot>`   | Get information about a specific slot (corresponding game, item groups, etc) |

## Item send replay commands

A particularly useful feature of the bot is the ability of users to replay the history of sent items. These replay commands will return a list of items received by a user's registered slots, though other slots can be optionally selected. Each replay command can also be filtered by item rarity: `all`, `useful`, `progression`, `traps`.

| | |
|-|-|
| `!replay new [filter] [slot: <slot>]`  | Replay items received since last call to `!replay new`; optionally filtered by rarity `filter` or `slot` |
| `!replay full [filter] [slot: <slot>]` | Replay all items recieved since game start; optionally filtered by rarity `filter` or `slot`|
| `!ketchmeup [filter] [slot: <slot>]`   | Alias of `!replay new` (credit to [bridgeipelago](https://github.com/Quasky/bridgeipelago) for the name) |

## Subscription commands

Another useful feature of the bot is the ability of users to subscribe to particular item notifications. If a user so chooses, they can subscribe so that the bot will @mention them when a specific item (or item from a specific group) is sent to their registered slot. This is useful if the user is stuck behind an item, or if they regard one group of items as particularly important for them to know about. Note: item groups are discoverable with `!slot info`.

| | |
|-|-|
| `!subscribe item <item> [slot: <slot>]`   | Subscribes you for the given `item`; *must* filter by `slot` if multi-registered |
| `!subscribe group <group> [slot: <slot>]` | Subscribes you for the given item `group`; *must* filter by `slot` if multi-registered |
| `!subscribe remove <text> [slot: <slot>]` | Unsubscribes you from items/groups containing the given `text`; optionally filtered by `slot` |
| `!subscribe list [slot: <slot>]`          | Lists your active item/group subscriptions; optionally filtered by `slot` |
| `!subscribe clear [slot: <slot>]`         | Clears all your item/group subscriptions; optionally filtered by `slot` |

## Statistics commands

Some fun and useful stats are aggregated by the bot during its run. These commands expose these statistics.

| | |
|-|-|
| `!checks <graph\|list\|table>` | Outputs data on completed/total checks per slot, in graph or table format |
| `!deaths <graph\|list\|table>` | Outputs data on death links triggered per slot, in graph or table format |
