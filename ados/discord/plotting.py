import io
from typing import Optional, cast

import discord
import matplotlib.pyplot as plt
from matplotlib.container import BarContainer

from ados.common import ItemCategory, SlotFullStatus, SlotInfo, SlotItemCounts
from ados.discord.common import BotContext, send_table

BAR_COLORS = ["#2C3947", "#547A95", "#C2A56D", "#C16E6E"]
SHADOW_COLOR = "#E8EDF2"


class TablePlotter:

    @staticmethod
    async def send_checks(ctx: BotContext, full_statuses: dict[SlotInfo, SlotFullStatus]) -> None:
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

    @staticmethod
    async def send_items(ctx: BotContext, item_counts: dict[SlotInfo, SlotItemCounts]) -> None:
        for label, attr in (
            ("Sent", "sent_items"),
            ("Rcvd", "received_items"),
            ("Self", "self_items"),
        ):
            table: dict[str, list[str]] = {
                "Slot": [],
                f"{label} Total": [],
                f"{label} Progression": [],
                f"{label} Useful": [],
                f"{label} Filler": [],
                f"{label} Traps": [],
            }
            for slot, all_counts in item_counts.items():
                counts = cast(dict[ItemCategory, int], getattr(all_counts, attr))
                table["Slot"].append(str(slot))
                table[f"{label} Total"].append(str(sum(counts.values())))
                table[f"{label} Progression"].append(str(counts.get(ItemCategory.PROGRESSION, 0)))
                table[f"{label} Useful"].append(str(counts.get(ItemCategory.USEFUL, 0)))
                table[f"{label} Filler"].append(str(counts.get(ItemCategory.FILLER, 0)))
                table[f"{label} Traps"].append(str(counts.get(ItemCategory.TRAP, 0)))
            await send_table(ctx, table, right_just=True)

    @staticmethod
    async def send_deaths(ctx: BotContext, death_counts: dict[SlotInfo, int]) -> None:
        table: dict[str, list[str]] = {"Slot": [], "Deaths": []}
        for slot, count in death_counts.items():
            table["Slot"].append(str(slot))
            table["Deaths"].append(str(count))
        await send_table(ctx, table, right_just=True)


class GraphPlotter:

    @staticmethod
    async def send_checks(ctx: BotContext, full_statuses: dict[SlotInfo, SlotFullStatus]) -> None:
        slots = [str(slot) for slot in full_statuses.keys()]
        statuses = list(full_statuses.values())

        bold_columns = [s.has_released or s.goal_completed for s in statuses]
        actual_found = [s.found_checks - s.self_freed_checks - s.other_freed_checks for s in statuses]
        other_freed = [s.other_freed_checks for s in statuses]
        self_freed = [s.self_freed_checks for s in statuses]
        all_found = [s.found_checks for s in statuses]
        total_checks = [s.total_checks for s in statuses]

        legend = (
            ["Actual Found", "Other Freed", "Self Freed"]
            if any(s.other_freed_checks or s.self_freed_checks for s in statuses)
            else None
        )

        await GraphPlotter._send_graph(
            ctx,
            title="Check Completion",
            columns=slots,
            bold_columns=bold_columns,
            bar_values=[actual_found, other_freed, self_freed],
            bar_labels=[str(val) for val in all_found],
            bar_shadows=total_checks,
            legend=legend,
        )

        await GraphPlotter._send_graph(
            ctx,
            title="Check Completion Percentage",
            columns=slots,
            bold_columns=bold_columns,
            bar_values=[
                [a / b * 100 for a, b in zip(actual_found, total_checks)],
                [a / b * 100 for a, b in zip(other_freed, total_checks)],
                [a / b * 100 for a, b in zip(self_freed, total_checks)],
            ],
            bar_labels=[f"{a / b * 100:.1f}" for a, b in zip(all_found, total_checks)],
            legend=legend,
            max_value=100,
        )

    @staticmethod
    async def send_items(ctx: BotContext, item_counts: dict[SlotInfo, SlotItemCounts]) -> None:
        slots = [str(slot) for slot in item_counts.keys()]
        counts = list(item_counts.values())
        legend = ["Progression", "Useful", "Filler", "Trap"]

        for title, attr in (
            ("Sent Item Counts", "sent_items"),
            ("Received Item Counts", "received_items"),
            ("Self-Found Item Counts", "self_items"),
        ):
            progression = [getattr(c, attr).get(ItemCategory.PROGRESSION, 0) for c in counts]
            useful = [getattr(c, attr).get(ItemCategory.USEFUL, 0) for c in counts]
            filler = [getattr(c, attr).get(ItemCategory.FILLER, 0) for c in counts]
            trap = [getattr(c, attr).get(ItemCategory.TRAP, 0) for c in counts]
            full = [sum(vals) for vals in zip(progression, useful, filler, trap)]

            await GraphPlotter._send_graph(
                ctx,
                title=title,
                columns=slots,
                bar_values=[progression, useful, filler, trap],
                bar_labels=[str(val) for val in full],
                legend=legend,
            )

    @staticmethod
    async def send_deaths(ctx: BotContext, death_counts: dict[SlotInfo, int]) -> None:
        await GraphPlotter._send_graph(
            ctx,
            title="Death Counts",
            columns=[str(slot) for slot in death_counts.keys()],
            bar_values=[list(death_counts.values())],
            bar_labels=[str(val) for val in death_counts.values()],
        )

    @staticmethod
    async def _send_graph(
        ctx: BotContext,
        *,
        title: str,
        columns: list[str],
        bold_columns: Optional[list[bool]] = None,
        bar_values: list[list[int] | list[float]],
        bar_labels: Optional[list[str]] = None,
        bar_shadows: Optional[list[int] | list[float]] = None,
        legend: Optional[list[str]] = None,
        max_value: Optional[float] = None,
    ) -> None:
        plt.figure(figsize=(max(8, len(columns) * 0.5), 6))

        top: Optional[BarContainer] = None
        for idx, values in enumerate(bar_values):
            current = (
                [sum(vals) for vals in zip(*(other_values for other_values in bar_values[:idx]))] if idx > 0 else None
            )
            top = plt.bar(columns, values, bottom=current, color=BAR_COLORS[idx])
        if bar_shadows is not None:
            current = [sum(vals) for vals in zip(*bar_values)]
            values = [shadow - curr for shadow, curr in zip(bar_shadows, current)]
            plt.bar(columns, values, bottom=current, color=SHADOW_COLOR)

        if bar_labels is not None:
            assert top is not None
            plt.bar_label(top, labels=bar_labels, padding=2)

        if max_value is not None:
            plt.ylim(bottom=0, top=max_value)

        if bold_columns is not None:
            for column_label, should_bold in zip(plt.gca().get_xticklabels(), bold_columns):
                if should_bold:
                    column_label.set_fontweight("bold")

        if legend is not None:
            plt.legend(legend, reverse=True, fontsize="small", loc="upper right")

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
