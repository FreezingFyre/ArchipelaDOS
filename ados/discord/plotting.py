import io

import discord
import matplotlib.pyplot as plt

from ados.common import FullSlotStatus, SlotInfo
from ados.discord.common import BotContext, send_table

COLOR_1 = "#2C3947"
COLOR_2 = "#547A95"
COLOR_3 = "#C2A56D"
COLOR_4 = "#E8EDF2"


async def _send_graph(ctx: BotContext) -> None:
    image_buffer = io.BytesIO()
    plt.savefig(image_buffer, dpi=250, format="png")
    plt.close()
    image_buffer.seek(0)
    await ctx.send(file=discord.File(fp=image_buffer, filename="stats.png"))


async def send_checks_table(ctx: BotContext, full_statuses: dict[SlotInfo, FullSlotStatus]) -> None:
    table: dict[str, list[str]] = {
        "Slot": [],
        "Total": [],
        "Found": [],
        " ": [],
        "Other Freed": [],
        "  ": [],
        "Self Freed": [],
        "   ": [],
    }
    for slot, status in full_statuses.items():
        slot_prefix = "+" if status.goal_completed else "-" if status.has_released else " "
        table["Slot"].append(f"{slot_prefix} {slot}")
        table["Total"].append(str(status.total_checks))
        table["Found"].append(str(status.found_checks))
        table[" "].append(f"{status.found_checks / status.total_checks * 100:.1f}%")
        table["Other Freed"].append(str(status.other_freed_checks))
        table["  "].append(f"{status.other_freed_checks / status.total_checks * 100:.1f}%")
        table["Self Freed"].append(str(status.self_freed_checks))
        table["   "].append(f"{status.self_freed_checks / status.total_checks * 100:.1f}%")

    if all(status.other_freed_checks == 0 for status in full_statuses.values()):
        table.pop("Other Freed")
        table.pop("  ")
    if all(status.self_freed_checks == 0 for status in full_statuses.values()):
        table.pop("Self Freed")
        table.pop("   ")

    await send_table(ctx, table, right_just=True)


async def send_checks_graph(ctx: BotContext, full_statuses: dict[SlotInfo, FullSlotStatus]) -> None:
    labels = [str(slot) for slot in full_statuses.keys()]
    full_found = [status.found_checks for status in full_statuses.values()]
    full_unfound = [status.total_checks - status.found_checks for status in full_statuses.values()]
    other_freed = [status.other_freed_checks for status in full_statuses.values()]
    self_freed = [status.self_freed_checks for status in full_statuses.values()]
    base_found = [
        status.found_checks - status.self_freed_checks - status.other_freed_checks for status in full_statuses.values()
    ]

    plt.figure(figsize=(max(8, len(labels) * 0.5), 6))
    plt.bar(labels, base_found, color=COLOR_1)
    plt.bar(labels, other_freed, bottom=base_found, color=COLOR_2)
    bars = plt.bar(labels, self_freed, bottom=[a + b for a, b in zip(base_found, other_freed)], color=COLOR_3)
    plt.bar_label(bars, labels=[str(status.found_checks) for status in full_statuses.values()], padding=2)
    plt.bar(labels, full_unfound, bottom=full_found, color=COLOR_4)

    plt.title("Check Completion", fontsize=16)
    plt.xlabel("Slot", fontsize=14)
    plt.xticks(rotation=45, ha="right")
    plt.gca().set_ylim(top=plt.gca().get_ylim()[1] * 1.05)
    plt.tight_layout()

    plot_labels = plt.gca().get_xticklabels()
    for slot, status in full_statuses.items():
        if not status.has_released:
            continue
        for plot_label in plot_labels:
            if plot_label.get_text() == str(slot):
                plot_label.set_fontweight("bold")
                break

    await _send_graph(ctx)


async def send_deaths_table(ctx: BotContext, death_counts: dict[SlotInfo, int]) -> None:
    table: dict[str, list[str]] = {"Slot": [], "Deaths": []}
    for slot, count in death_counts.items():
        table["Slot"].append(str(slot))
        table["Deaths"].append(str(count))
    await send_table(ctx, table, right_just=True)


async def send_deaths_graph(ctx: BotContext, death_counts: dict[SlotInfo, int]) -> None:
    plt.figure(figsize=(max(8, len(death_counts) * 0.5), 6))
    bars = plt.bar([str(slot) for slot in death_counts.keys()], list(death_counts.values()), color=COLOR_1)
    plt.bar_label(bars, padding=2)

    plt.title("Death Counts", fontsize=16)
    plt.xlabel("Slot", fontsize=14)
    plt.xticks(rotation=45, ha="right")
    plt.gca().set_ylim(top=plt.gca().get_ylim()[1] * 1.05)
    plt.tight_layout()

    await _send_graph(ctx)
