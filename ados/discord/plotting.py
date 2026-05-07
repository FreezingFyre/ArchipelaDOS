import io
from typing import Optional

import discord
import matplotlib.pyplot as plt

from ados.common import FullSlotStatus, SlotInfo
from ados.discord.common import BotContext, send_table

COLOR_1 = "#2C3947"
COLOR_2 = "#547A95"
COLOR_3 = "#C2A56D"
COLOR_4 = "#E8EDF2"


async def _finalize_graph(ctx: BotContext, title: str) -> None:
    plt.title(title, fontsize=16)
    plt.xlabel("Slot", fontsize=14)
    plt.xticks(rotation=45, ha="right")
    plt.gca().set_ylim(top=plt.gca().get_ylim()[1] * 1.08)
    plt.tight_layout()

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
    statuses = list(full_statuses.values())

    bold_bars = [s.has_released or s.goal_completed for s in statuses]
    base_found = [s.found_checks - s.self_freed_checks - s.other_freed_checks for s in statuses]
    other_freed = [s.other_freed_checks for s in statuses]
    self_freed = [s.self_freed_checks for s in statuses]
    all_found = [s.found_checks for s in statuses]
    all_unfound = [s.total_checks - s.found_checks for s in statuses]
    total_checks = [s.total_checks for s in statuses]

    async def _send_stacked_graph(
        title: str,
        *,
        base: list[int] | list[float],
        mid: list[int] | list[float],
        top: list[int] | list[float],
        cap: Optional[list[int] | list[float]] = None,
        bar_labels: list[str],
    ) -> None:
        plt.figure(figsize=(max(8, len(labels) * 0.5), 6))

        plt.bar(labels, base, color=COLOR_1)
        plt.bar(labels, mid, bottom=base, color=COLOR_2)
        bars = plt.bar(labels, top, bottom=[sum(vals) for vals in zip(base, mid)], color=COLOR_3)
        plt.bar_label(bars, labels=bar_labels, padding=2)
        if cap is not None:
            plt.bar(labels, cap, bottom=[sum(vals) for vals in zip(base, mid, top)], color=COLOR_4)

        for label, should_bold in zip(plt.gca().get_xticklabels(), bold_bars):
            if should_bold:
                label.set_fontweight("bold")
        await _finalize_graph(ctx, title)

    await _send_stacked_graph(
        "Check Completion",
        base=base_found,
        mid=other_freed,
        top=self_freed,
        cap=all_unfound,
        bar_labels=[str(val) for val in all_found],
    )

    await _send_stacked_graph(
        "Completion Percentage",
        base=[a / b for a, b in zip(base_found, total_checks)],
        mid=[a / b for a, b in zip(other_freed, total_checks)],
        top=[a / b for a, b in zip(self_freed, total_checks)],
        bar_labels=[f"{a / b * 100:.1f}" for a, b in zip(all_found, total_checks)],
    )


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
    await _finalize_graph(ctx, "Death Counts")
