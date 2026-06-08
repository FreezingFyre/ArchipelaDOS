# Discord Commands

[Back to README](../README.md)

All commands are available to all users, from whatever Discord channels are configured. Commands are also usable from threads within the configured channels, and in user DMs. For some commands with large output (such as `!help` and `!replay`), the bot will reply in a thread to keep the main channel decluttered. These threads are automatically archived after a period of inactivity.

For the below command specs, for those who are unfamiliar: `<angle_brackets>` denote required fields, while `[square_brackets]` denote optional fields. Fields do *not* need to be surrounded with quotes to work, and slot/item/group names are *not* case-sensitive. Some examples of valid commands (all specified in the tables below):

- `!help`
- `!help slot clear`
- `!slot add My Slot`
- `!replay full traps`
- `!replay full slot: My Slot`
- `!subscribe item My Item slot: My Slot`
- `!deaths graph`

## General commands

| | |
|-|-|
| `!help [command]` | Print general help info, or help for a specific command/subcommand |
| `!hello`          | Greet the bot (it might greet you back) |
| `!dmme`           | Trigger the bot to send you a direct message |
| `!threadme`       | Trigger the bot to send you a message in a new thread |

## Room management commands

The bot operates by connecting to one Archipelago room at a time.

| | |
|-|-|
| `!room connect <id_or_url> [slot: <slot>] [game: <game>] [password: <password>]`  | Connect to a new Archipelago room via room ID or socket URL, with `slot`, `game`, and `password` optionally specified |
| `!room finalize`                                                                  | Disconnect from the current Archipelago room, allowing a new connection |
| `!room info`                                                                      | Get information about the Archipelago room (port, list of slots, etc) |
| `!room refresh`                                                                   | Refresh the room on archipelago.gg, reconnecting the bot if it got disconnected |

## Slot management commands

Users can "register" themselves for particular slots. This affects which slots' items are replayed during `!replay` commands, as well as which slots are used by default when using `!hint` or `!subscribe`.

| | |
|-|-|
| `!slot add <slot>`                   | Registers you for the given `slot` |
| `!slot remove <slot>`                | Unregisters you from the given `slot` |
| `!slot list`                         | Lists all slots for which you are registered |
| `!slot clear`                        | Clears your registration for all slots |
| `!slot info [slot]`                  | Get information about your registered slots (game, item groups, etc); optionally filtered by `slot` |
| `!slot search <text> [slot: <slot>]` | Search for items/locations in your registered slots containing the given `text`; optionally filtered by `slot` |

## Item send replay commands

A particularly useful feature of the bot is the ability of users to replay the history of sent items. These replay commands will return a list of items received by a user's registered slots, though other slots can be optionally selected. Each replay command can also be filtered by item rarity: `all`, `useful`, `progression`, `traps`.

| | |
|-|-|
| `!replay new [filter] [slot: <slot>] [since: <delta>]`  | Replay items received since last call to `!replay new`; optionally filtered by rarity `filter`, `slot`, or relative time `delta` ("8h", "30m", etc) |
| `!replay full [filter] [slot: <slot>] [since: <delta>]` | Replay all items received since game start; optionally filtered by rarity `filter`, `slot`, or relative time `delta` ("8h", "30m", etc) |
| `!ketchmeup [filter] [slot: <slot>] [since: <delta>]`   | Alias of `!replay new` (credit to [bridgeipelago](https://github.com/Quasky/bridgeipelago) for the name) |

## Subscription commands

Another useful feature of the bot is the ability of users to subscribe to particular item notifications. If a user so chooses, they can subscribe so that the bot will @mention them when a specific item (or item from a specific group) is sent to their registered slot. This is useful if the user is stuck behind an item, or if they regard one group of items as particularly important for them to know about. When subscribing for an item or group using the below commands, the `slot` only needs to be specified if the item or group exists in multiple registered slots. The bot intelligently subscribes only for the slot containing the item or group. Note: item groups are discoverable with `!slot info`.

| | |
|-|-|
| `!subscribe item <item> [slot: <slot>]`   | Subscribes you for the given `item`; optionally filtered by `slot` |
| `!subscribe group <group> [slot: <slot>]` | Subscribes you for the given `group`; optionally filtered by `slot` |
| `!subscribe remove <text> [slot: <slot>]` | Unsubscribes you from items/groups matching the given `text`; optionally filtered by `slot` |
| `!subscribe list [slot: <slot>]`          | Lists your active item/group subscriptions; optionally filtered by `slot` |
| `!subscribe clear [slot: <slot>]`         | Clears all your item/group subscriptions; optionally filtered by `slot` |
| `!subscribe <item> [slot: <slot>]`        | Alias of `!subscribe item` |

## Hint commands

If a slot is password-less, the bot can be used to facilitate hint operations on it. These hints consume the required number of hint points, just as they would if executed through a normal text client. When hinting for an item or location using the below commands, the `slot` only needs to be specified if the item or location exists in multiple registered slots. The bot intelligently sends the hint request for the slot containing the item or location.

| | |
|-|-|
| `!hint item <item> [slot: <slot>]`         | Use a hint for the given `item`; optionally filtered by `slot` |
| `!hint location <location> [slot: <slot>]` | Use a hint to see what is at the given `location`; optionally filtered by `slot` |
| `!hint list [filter] [slot: <slot>]`       | List hints; optionally filtered by found `filter` or `slot` |
| `!hint points [slot: <slot>]`              | Show hint points held and needed; optionally filtered by `slot` |
| `!hint <item> [slot: <slot>]`              | Alias of `!hint item` |

## Statistics commands

Some fun and useful stats are aggregated by the bot during its run. These commands expose these statistics.

| | |
|-|-|
| `!checks <graph\|list\|table>` | Outputs data on completed/total checks per slot, in graph or table format |
| `!items <graph\|list\|table>`  | Outputs data on types of items sent/received per slot, in graph or table format |
| `!deaths <graph\|list\|table>` | Outputs data on death links triggered per slot, in graph or table format |
