"""Generate English and Korean PNG figures for the commodity scenario."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - exercised only without Pillow
    raise SystemExit(
        "Pillow is required only for figures: "
        "python3 -m pip install -r requirements-visualization.txt"
    ) from exc

from rwa_market_gap.commodity_simulation.visualization import (
    GoldDiscountChartData,
    LeverageBandChartData,
    LineSeries,
    WTIFundingChartData,
    build_gold_discount_chart_data,
    build_leverage_band_chart_data,
    build_wti_funding_chart_data,
)


WIDTH = 1600
HEIGHT = 1000
BACKGROUND = "#FFFFFF"
FOREGROUND = "#172033"
MUTED = "#5A6578"
GRID = "#D8DEE9"
ZERO = "#8A94A6"
BLUE = "#246BFD"
ORANGE = "#F28E2B"
GREEN = "#2A9D67"
PURPLE = "#7A5AF8"
RED = "#D64550"
PALE_BLUE = "#EAF1FF"


def _font(size: int, *, bold: bool = False):
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _korean_font(size: int):
    candidates = (
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    raise RuntimeError(
        "A Korean font is required to generate the _ko figures. "
        "Install Noto Sans KR or add a supported font path."
    )


TITLE_FONT = _font(42, bold=True)
SUBTITLE_FONT = _font(24)
LABEL_FONT = _font(24)
SMALL_FONT = _font(20)
LEGEND_FONT = _font(22)
KOREAN_TITLE_FONT = _korean_font(42)
KOREAN_SUBTITLE_FONT = _korean_font(24)
KOREAN_LABEL_FONT = _korean_font(24)
KOREAN_SMALL_FONT = _korean_font(20)
KOREAN_LEGEND_FONT = _korean_font(22)


class PlotCanvas:
    def __init__(
        self,
        *,
        title: str,
        subtitle: str,
        x_label: str,
        y_label: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        korean: bool = False,
    ) -> None:
        self.image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
        self.draw = ImageDraw.Draw(self.image)
        self.left = 170
        self.right = WIDTH - 85
        self.top = 230
        self.bottom = HEIGHT - 145
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        if korean:
            self.title_font = KOREAN_TITLE_FONT
            self.subtitle_font = KOREAN_SUBTITLE_FONT
            self.label_font = KOREAN_LABEL_FONT
            self.small_font = KOREAN_SMALL_FONT
            self.legend_font = KOREAN_LEGEND_FONT
        else:
            self.title_font = TITLE_FONT
            self.subtitle_font = SUBTITLE_FONT
            self.label_font = LABEL_FONT
            self.small_font = SMALL_FONT
            self.legend_font = LEGEND_FONT
        self.draw.text((70, 50), title, fill=FOREGROUND, font=self.title_font)
        self.draw.text(
            (72, 110), subtitle, fill=MUTED, font=self.subtitle_font
        )
        self.draw.text(
            ((self.left + self.right) / 2, HEIGHT - 72),
            x_label,
            fill=FOREGROUND,
            font=self.label_font,
            anchor="mm",
        )
        self._rotated_y_label(y_label)

    def _rotated_y_label(self, label: str) -> None:
        bounds = self.draw.textbbox((0, 0), label, font=self.label_font)
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        layer = Image.new("RGBA", (width + 24, height + 24), (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer)
        layer_draw.text(
            (12, 12), label, fill=FOREGROUND, font=self.label_font
        )
        rotated = layer.rotate(90, expand=True)
        self.image.paste(
            rotated,
            (
                24,
                int((self.top + self.bottom - rotated.height) / 2),
            ),
            rotated,
        )

    def x(self, value: float) -> float:
        return self.left + (value - self.x_min) / (
            self.x_max - self.x_min
        ) * (self.right - self.left)

    def y(self, value: float) -> float:
        return self.bottom - (value - self.y_min) / (
            self.y_max - self.y_min
        ) * (self.bottom - self.top)

    def axes(
        self,
        *,
        x_ticks: tuple[float, ...],
        y_ticks: tuple[float, ...],
        x_format,
        y_format,
    ) -> None:
        for value in y_ticks:
            pixel = self.y(value)
            self.draw.line(
                (self.left, pixel, self.right, pixel), fill=GRID, width=2
            )
            self.draw.text(
                (self.left - 20, pixel),
                y_format(value),
                fill=MUTED,
                font=self.small_font,
                anchor="rm",
            )
        for value in x_ticks:
            pixel = self.x(value)
            self.draw.line(
                (pixel, self.bottom, pixel, self.bottom + 9),
                fill=FOREGROUND,
                width=2,
            )
            self.draw.text(
                (pixel, self.bottom + 20),
                x_format(value),
                fill=MUTED,
                font=self.small_font,
                anchor="ma",
            )
        self.draw.line(
            (self.left, self.top, self.left, self.bottom),
            fill=FOREGROUND,
            width=3,
        )
        self.draw.line(
            (self.left, self.bottom, self.right, self.bottom),
            fill=FOREGROUND,
            width=3,
        )

    def horizontal(self, value: float, *, color: str, width: int = 3) -> None:
        pixel = self.y(value)
        self.draw.line((self.left, pixel, self.right, pixel), fill=color, width=width)

    def dashed_vertical(
        self,
        value: float,
        *,
        color: str,
        dash: int = 14,
        gap: int = 10,
        width: int = 4,
    ) -> None:
        pixel = self.x(value)
        y = self.top
        while y < self.bottom:
            self.draw.line(
                (pixel, y, pixel, min(y + dash, self.bottom)),
                fill=color,
                width=width,
            )
            y += dash + gap

    def line_series(self, series: LineSeries, *, color: str) -> None:
        points = [(self.x(point.x), self.y(point.y)) for point in series.points]
        self.draw.line(points, fill=color, width=6, joint="curve")

    def legend(self, entries: tuple[tuple[str, str], ...]) -> None:
        x = self.left
        y = 167
        for label, color in entries:
            width = self.draw.textlength(label, font=self.legend_font)
            self.draw.line((x, y + 14, x + 38, y + 14), fill=color, width=6)
            self.draw.text(
                (x + 48, y), label, fill=FOREGROUND, font=self.legend_font
            )
            x += width + 92

    def save(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(destination, format="PNG", optimize=True)


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{sign}${absolute / 1_000:.0f}k"
    return f"{sign}${absolute:.0f}"


def _percentage(value: float) -> str:
    return f"{value:.1%}"


def _ticks(start: float, stop: float, count: int) -> tuple[float, ...]:
    return tuple(start + (stop - start) * index / (count - 1) for index in range(count))


def _padded_domain(values: list[float], *, zero: bool = False) -> tuple[float, float]:
    low = min(values)
    high = max(values)
    if zero:
        low = min(low, 0.0)
        high = max(high, 0.0)
    span = max(high - low, 1.0)
    return low - span * 0.10, high + span * 0.10


def draw_wti_funding(
    data: WTIFundingChartData,
    destination: Path,
    *,
    korean: bool = False,
) -> None:
    y_values = [point.y for series in data.series for point in series.points]
    y_min, y_max = _padded_domain(y_values, zero=True)
    title = (
        "WTI: 펀딩비에 따른 순이익"
        if korean
        else "WTI: Net Profit vs 49h Funding"
    )
    subtitle = (
        "관측된 두 주말 사례를 같은 가정으로 계산한 결과 · 성공확률 아님"
        if korean
        else (
            "Post-event conditional strategy; diagnostic range beyond the "
            "declared funding sensitivity"
        )
    )
    canvas = PlotCanvas(
        title=title,
        subtitle=subtitle,
        x_label=(
            "49시간 누적 펀딩비"
            if korean
            else "49-hour cumulative funding paid"
        ),
        y_label="순이익(달러)" if korean else "Net profit (USD)",
        x_min=data.x_min,
        x_max=data.x_max,
        y_min=y_min,
        y_max=y_max,
        korean=korean,
    )
    sensitivity_left = canvas.x(data.declared_sensitivity_low)
    sensitivity_right = canvas.x(data.declared_sensitivity_high)
    canvas.draw.rectangle(
        (sensitivity_left, canvas.top, sensitivity_right, canvas.bottom),
        fill=PALE_BLUE,
    )
    canvas.axes(
        x_ticks=_ticks(data.x_min, data.x_max, 8),
        y_ticks=_ticks(y_min, y_max, 7),
        x_format=_percentage,
        y_format=_money,
    )
    canvas.horizontal(0.0, color=ZERO, width=4)
    canvas.line_series(data.series[0], color=BLUE)
    canvas.line_series(data.series[1], color=ORANGE)
    canvas.dashed_vertical(data.assumed_funding_rate, color=GREEN)
    for index, (series, break_even) in enumerate(
        zip(data.series, data.break_even_rates)
    ):
        color = (BLUE, ORANGE)[index]
        pixel = (canvas.x(break_even), canvas.y(0.0))
        canvas.draw.ellipse(
            (pixel[0] - 8, pixel[1] - 8, pixel[0] + 8, pixel[1] + 8),
            fill=color,
        )
        canvas.draw.text(
            (pixel[0], pixel[1] - 22 - index * 32),
            (
                f"손익분기 {break_even:.3%}"
                if korean
                else f"BE {break_even:.3%}"
            ),
            fill=FOREGROUND,
            font=canvas.small_font,
            anchor="ms",
        )
    canvas.legend(
        (
            ("1차 주말" if korean else data.series[0].label, BLUE),
            ("2차 주말" if korean else data.series[1].label, ORANGE),
            (
                "기본 펀딩비 0.050%"
                if korean
                else "Assumed funding 0.050%",
                GREEN,
            ),
        )
    )
    canvas.draw.text(
        (canvas.left + 12, canvas.top + 12),
        (
            "기본 민감도 범위: -0.5%~0.5%"
            if korean
            else "Declared sensitivity: -0.5% to 0.5%"
        ),
        fill=MUTED,
        font=canvas.small_font,
    )
    canvas.save(destination)


def draw_gold_discount(
    data: GoldDiscountChartData,
    destination: Path,
    *,
    korean: bool = False,
) -> None:
    y_values = [point.y for series in data.series for point in series.points]
    y_min, y_max = _padded_domain(y_values, zero=True)
    title = (
        "토큰화 금: 매입 할인 가정에 따른 순이익"
        if korean
        else "Tokenized Gold: Net Profit vs Assumed Acquisition Discount"
    )
    subtitle = (
        "4.5%는 실제 할인이 아니라 관측된 최대 가격 차이를 할인으로 가정한 값"
        if korean
        else (
            "4.5% is the maximum observed token-metal divergence, applied as "
            "an attacker-favorable discount assumption"
        )
    )
    canvas = PlotCanvas(
        title=title,
        subtitle=subtitle,
        x_label=(
            "가정한 매입 할인율"
            if korean
            else "Assumed acquisition discount"
        ),
        y_label="순이익(달러)" if korean else "Net profit (USD)",
        x_min=data.x_min,
        x_max=data.x_max,
        y_min=y_min,
        y_max=y_max,
        korean=korean,
    )
    canvas.axes(
        x_ticks=_ticks(data.x_min, data.x_max, 8),
        y_ticks=_ticks(y_min, y_max, 7),
        x_format=_percentage,
        y_format=_money,
    )
    canvas.horizontal(0.0, color=ZERO, width=4)
    colors = (BLUE, ORANGE, PURPLE)
    for series, color in zip(data.series, colors):
        canvas.line_series(series, color=color)
    canvas.dashed_vertical(data.tested_divergence_as_discount, color=RED)
    canvas.draw.text(
        (
            canvas.x(data.tested_divergence_as_discount) + 12,
            canvas.top + 12,
        ),
        (
            "가격 차이 4.5%를 할인으로 가정"
            if korean
            else "4.5% divergence used as discount"
        ),
        fill=FOREGROUND,
        font=canvas.small_font,
    )
    for index, break_even in enumerate(data.break_even_discounts):
        pixel = (canvas.x(break_even), canvas.y(0.0))
        canvas.draw.ellipse(
            (pixel[0] - 8, pixel[1] - 8, pixel[0] + 8, pixel[1] + 8),
            fill=colors[index],
        )
        canvas.draw.text(
            (pixel[0], pixel[1] - 18 - index * 30),
            (
                f"손익분기 {break_even:.2%}"
                if korean
                else f"BE {break_even:.2%}"
            ),
            fill=FOREGROUND,
            font=canvas.small_font,
            anchor="ms",
        )
    if korean:
        legend_labels = ("가격 영향 완만", "가격 영향 기본", "가격 영향 가파름")
        canvas.legend(tuple(zip(legend_labels, colors)))
    else:
        canvas.legend(
            tuple(
                (series.label, color)
                for series, color in zip(data.series, colors)
            )
        )
    canvas.save(destination)


def draw_leverage_bands(
    data: LeverageBandChartData,
    destination: Path,
    *,
    korean: bool = False,
) -> None:
    y_max = max(
        max(bar.liquidation_adverse_move for bar in data.bars),
        data.counterfactual_reanchor_cap_rate,
    ) * 1.16
    canvas = PlotCanvas(
        title=(
            "WTI: 레버리지별 청산 가격 변화폭"
            if korean
            else "WTI: Liquidation Move vs Price-Discovery Bounds"
        ),
        subtitle=(
            "공개되지 않은 대형 포지션 구간은 제외하고 기본 구간만 계산"
            if korean
            else "Simplified base tier only; unpublished margin tiers are not modelled"
        ),
        x_label="선택 레버리지" if korean else "Selected leverage",
        y_label="청산까지 필요한 가격 변화폭" if korean else "Adverse price move",
        x_min=0.0,
        x_max=float(len(data.bars)),
        y_min=0.0,
        y_max=y_max,
        korean=korean,
    )
    x_centers = tuple(index + 0.5 for index in range(len(data.bars)))
    canvas.axes(
        x_ticks=x_centers,
        y_ticks=_ticks(0.0, y_max, 6),
        x_format=lambda value: f"{data.bars[int(value - 0.5)].leverage:g}x",
        y_format=_percentage,
    )
    bar_half_width = 0.24
    for center, bar in zip(x_centers, data.bars):
        left = canvas.x(center - bar_half_width)
        right = canvas.x(center + bar_half_width)
        top = canvas.y(bar.liquidation_adverse_move)
        canvas.draw.rounded_rectangle(
            (left, top, right, canvas.bottom),
            radius=12,
            fill=BLUE,
        )
        canvas.draw.text(
            ((left + right) / 2, top - 16),
            f"{bar.liquidation_adverse_move:.1%}",
            fill=FOREGROUND,
            font=canvas.label_font,
            anchor="ms",
        )
    canvas.horizontal(data.static_band_rate, color=ORANGE, width=5)
    canvas.horizontal(data.counterfactual_reanchor_cap_rate, color=PURPLE, width=5)
    canvas.draw.text(
        (canvas.right - 8, canvas.y(data.static_band_rate) - 10),
        (
            f"기존 가격 제한 {data.static_band_rate:.1%}"
            if korean
            else f"Static band {data.static_band_rate:.1%}"
        ),
        fill=FOREGROUND,
        font=canvas.small_font,
        anchor="rs",
    )
    canvas.draw.text(
        (canvas.right - 8, canvas.y(data.counterfactual_reanchor_cap_rate) - 10),
        (
            f"가격 기준 재설정 상한 {data.counterfactual_reanchor_cap_rate:.2%} (당시 미적용)"
            if korean
            else (
                "Counterfactual reanchor cap "
                f"{data.counterfactual_reanchor_cap_rate:.2%}"
            )
        ),
        fill=FOREGROUND,
        font=canvas.small_font,
        anchor="rs",
    )
    canvas.legend(
        (
            ("청산까지 필요한 변화폭" if korean else "Liquidation move", BLUE),
            ("기존 가격 제한" if korean else "Static band", ORANGE),
            (
                "가격 기준 재설정 상한(당시 미적용)"
                if korean
                else "Counterfactual reanchor cap",
                PURPLE,
            ),
        )
    )
    canvas.save(destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("figures/commodity_simulation"),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    english_destinations = (
        args.output_dir / "wti_funding_break_even.png",
        args.output_dir / "gold_discount_break_even.png",
        args.output_dir / "wti_leverage_bounds.png",
    )
    korean_destinations = (
        args.output_dir / "wti_funding_break_even_ko.png",
        args.output_dir / "gold_discount_break_even_ko.png",
        args.output_dir / "wti_leverage_bounds_ko.png",
    )
    funding_data = build_wti_funding_chart_data()
    gold_data = build_gold_discount_chart_data()
    leverage_data = build_leverage_band_chart_data()
    draw_wti_funding(funding_data, english_destinations[0])
    draw_gold_discount(gold_data, english_destinations[1])
    draw_leverage_bands(leverage_data, english_destinations[2])
    draw_wti_funding(funding_data, korean_destinations[0], korean=True)
    draw_gold_discount(gold_data, korean_destinations[1], korean=True)
    draw_leverage_bands(leverage_data, korean_destinations[2], korean=True)
    destinations = english_destinations + korean_destinations
    for destination in destinations:
        print(destination)


if __name__ == "__main__":
    main()
