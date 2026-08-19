"""Evidence-driven WTI, natural-gas, and tokenized-gold scenarios."""

from __future__ import annotations

from dataclasses import dataclass

from .discovery_bound import DiscoveryBoundMachine, OracleUpdateClamp
from .evidence import VerifiedInputLedger
from .margin import (
    LimitedLiabilityResult,
    liquidation_adverse_move,
    limited_liability_loss,
    loss_path,
    maintenance_margin_rate,
)
from .models import MarketSpec


@dataclass(frozen=True)
class LeverageZone:
    symbol: str
    chosen_leverage: float
    maintenance_margin_rate: float
    liquidation_adverse_move: float
    v1_bound_rate: float
    v2_hard_cap_rate: float
    liquidates_during_v1_gap: bool
    liquidates_during_v2_gap: bool
    margin_tiers_modelled: bool = False


@dataclass(frozen=True)
class WTITimeGapResult:
    friday_cme_close_usd: float
    observed_onchain_mark_usd: float
    theoretical_v1_cap_usd: float
    cme_reopen_price_usd: float
    intraday_high_usd: float
    onchain_recognized_move: float
    actual_reopen_move: float
    unrecognized_gap_percentage_points: float
    counterfactual_v2_cap_usd: float
    counterfactual_v2_cap_rate: float
    reopen_move_beyond_v2_cap_percentage_points: float
    minimum_clamped_updates: int
    observed_short_liquidations_usd: float
    observed_long_liquidations_usd: float
    short_to_long_liquidation_ratio: float
    reanchor_was_active_during_event: bool
    adl_was_confirmed: bool


@dataclass(frozen=True)
class BenchmarkGapResult:
    target_benchmark: str
    onchain_proxy: str
    target_change: float
    proxy_change: float
    benchmark_gap_percentage_points: float
    exposure_notional_usd: float
    proxy_hedge_shortfall_usd: float
    moves_in_opposite_directions: bool
    loss_path: tuple[str, ...]


@dataclass(frozen=True)
class GoldHierarchyGapResult:
    max_ltv: float
    liquidation_threshold: float
    liquidation_bonus: float
    liquidation_start_gap: float
    protocol_insolvency_buffer: float
    token_discount: float
    liquidator_residual_margin: float
    liquidator_economically_incentivized: bool
    secondary_holder_can_redeem: bool
    debt_cap_usd: float
    supply_cap_usd_at_liquidity_snapshot: float
    current_marked_supply_cap_usd: float
    disposal_capacity_within_bonus_usd: float
    debt_cap_to_capacity: float
    supply_cap_to_capacity: float
    supply_above_capacity_usd: float
    borrowing_token_itself_enabled: bool


@dataclass(frozen=True)
class CommodityScenarioSummary:
    wti: WTITimeGapResult
    natural_gas: BenchmarkGapResult
    gold: GoldHierarchyGapResult


class CommodityOracleScenarioEngine:
    """Run the three distinct commodity gaps from one verified input ledger."""

    def __init__(self, ledger: VerifiedInputLedger | None = None) -> None:
        self.ledger = ledger or VerifiedInputLedger.load()
        self.ledger.assert_complete()

    def market(self, symbol: str) -> MarketSpec:
        return MarketSpec.from_ledger(self.ledger, symbol)

    def leverage_zone(self, symbol: str, chosen_leverage: float) -> LeverageZone:
        market = self.market(symbol)
        maintenance_fraction = float(
            self.ledger.value("mechanics.maintenance_margin_fraction")
        )
        adverse_move = liquidation_adverse_move(
            chosen_leverage=chosen_leverage,
            max_leverage=market.max_leverage,
            maintenance_margin_fraction=maintenance_fraction,
        )
        return LeverageZone(
            symbol=symbol,
            chosen_leverage=chosen_leverage,
            maintenance_margin_rate=maintenance_margin_rate(
                market.max_leverage, maintenance_fraction
            ),
            liquidation_adverse_move=adverse_move,
            v1_bound_rate=market.band_rate,
            v2_hard_cap_rate=market.upward_hard_cap_rate,
            liquidates_during_v1_gap=adverse_move <= market.band_rate,
            liquidates_during_v2_gap=adverse_move <= market.upward_hard_cap_rate,
        )

    def wti_time_gap(self) -> WTITimeGapResult:
        market = self.market("WTIOIL")
        prefix = "events.wti_second_weekend"
        close = float(self.ledger.value(f"{prefix}.friday_cme_close_usd"))
        observed_mark = float(
            self.ledger.value(f"{prefix}.observed_onchain_mark_usd")
        )
        reopen = float(self.ledger.value(f"{prefix}.cme_reopen_price_usd"))
        intraday = float(self.ledger.value(f"{prefix}.intraday_high_usd"))
        short_liquidations = float(
            self.ledger.value(f"{prefix}.short_liquidations_usd")
        )
        long_liquidations = float(
            self.ledger.value(f"{prefix}.long_liquidations_usd")
        )
        actual_reanchor = bool(
            self.ledger.value(f"{prefix}.reanchor_active_during_event")
        )
        adl_confirmed = bool(self.ledger.value(f"{prefix}.adl_confirmed"))

        static = DiscoveryBoundMachine(
            reference_price=close,
            band_rate=market.band_rate,
            reset_limit=0,
            trigger_fraction=float(
                self.ledger.value("mechanics.reanchor_trigger_fraction")
            ),
        )
        counterfactual = DiscoveryBoundMachine(
            reference_price=close,
            band_rate=market.band_rate,
            reset_limit=market.reset_limit,
            trigger_fraction=float(
                self.ledger.value("mechanics.reanchor_trigger_fraction")
            ),
        )
        update_clamp = OracleUpdateClamp(
            protocol_rate=float(
                self.ledger.value("mechanics.protocol_update_clamp_rate")
            ),
            relayer_rate=float(
                self.ledger.value("mechanics.relayer_update_clamp_rate")
            ),
        )
        recognized_move = observed_mark / close - 1.0
        actual_move = reopen / close - 1.0
        unrecognized = actual_move - recognized_move
        v2_cap = counterfactual.theoretical_hard_cap("up")
        v2_rate = v2_cap / close - 1.0
        return WTITimeGapResult(
            friday_cme_close_usd=close,
            observed_onchain_mark_usd=observed_mark,
            theoretical_v1_cap_usd=static.theoretical_hard_cap("up"),
            cme_reopen_price_usd=reopen,
            intraday_high_usd=intraday,
            onchain_recognized_move=recognized_move,
            actual_reopen_move=actual_move,
            unrecognized_gap_percentage_points=unrecognized,
            counterfactual_v2_cap_usd=v2_cap,
            counterfactual_v2_cap_rate=v2_rate,
            reopen_move_beyond_v2_cap_percentage_points=max(
                0.0, actual_move - v2_rate
            ),
            minimum_clamped_updates=update_clamp.minimum_updates_for_reference_gap(
                unrecognized
            ),
            observed_short_liquidations_usd=short_liquidations,
            observed_long_liquidations_usd=long_liquidations,
            short_to_long_liquidation_ratio=(
                short_liquidations / long_liquidations
                if long_liquidations > 0.0
                else float("inf")
            ),
            reanchor_was_active_during_event=actual_reanchor,
            adl_was_confirmed=adl_confirmed,
        )

    def wti_limited_liability_example(self) -> LimitedLiabilityResult:
        market = self.market("WTIOIL")
        notional = float(
            self.ledger.value("analysis.loss_transfer_notional_usd")
        )
        chosen_leverage = float(
            self.ledger.value("analysis.loss_transfer_chosen_leverage")
        )
        return limited_liability_loss(
            notional_usd=notional,
            chosen_leverage=chosen_leverage,
            adverse_move=self.wti_time_gap().actual_reopen_move,
        )

    def natural_gas_benchmark_gap(self) -> BenchmarkGapResult:
        market = self.market("NATGAS")
        prefix = "events.natural_gas_benchmark_gap"
        target_change = float(self.ledger.value(f"{prefix}.jkm_change"))
        proxy_change = float(self.ledger.value(f"{prefix}.henry_hub_change"))
        notional = float(
            self.ledger.value("analysis.benchmark_exposure_notional_usd")
        )
        gap = target_change - proxy_change
        return BenchmarkGapResult(
            target_benchmark="JKM",
            onchain_proxy="Henry Hub",
            target_change=target_change,
            proxy_change=proxy_change,
            benchmark_gap_percentage_points=gap,
            exposure_notional_usd=notional,
            proxy_hedge_shortfall_usd=notional * gap,
            moves_in_opposite_directions=(target_change * proxy_change < 0.0),
            loss_path=loss_path(market.margin_mode),
        )

    def gold_hierarchy_gap(
        self, *, token_discount: float | None = None
    ) -> GoldHierarchyGapResult:
        prefix = "gold_collateral"
        max_ltv = float(self.ledger.value(f"{prefix}.max_ltv"))
        threshold = float(
            self.ledger.value(f"{prefix}.liquidation_threshold")
        )
        bonus = float(self.ledger.value(f"{prefix}.liquidation_bonus"))
        observed_discount = float(
            self.ledger.value(f"{prefix}.observed_max_token_discount")
        )
        discount = observed_discount if token_discount is None else token_discount
        if not 0.0 <= discount <= 1.0:
            raise ValueError("token_discount must be in [0, 1]")
        debt_cap = float(self.ledger.value(f"{prefix}.debt_cap_usd"))
        supply_tokens = float(self.ledger.value(f"{prefix}.supply_cap_tokens"))
        reference_price = float(
            self.ledger.value(f"{prefix}.reference_token_price_usd")
        )
        disposal_capacity = float(
            self.ledger.value(f"{prefix}.disposal_capacity_within_bonus_usd")
        )
        disposal_capacity_tokens = float(
            self.ledger.value(f"{prefix}.disposal_capacity_within_bonus_tokens")
        )
        liquidity_snapshot_price = disposal_capacity / disposal_capacity_tokens
        snapshot_supply_cap_usd = supply_tokens * liquidity_snapshot_price
        current_marked_supply_cap_usd = supply_tokens * reference_price
        residual = bonus - discount
        return GoldHierarchyGapResult(
            max_ltv=max_ltv,
            liquidation_threshold=threshold,
            liquidation_bonus=bonus,
            liquidation_start_gap=1.0 - max_ltv / threshold,
            protocol_insolvency_buffer=1.0 - threshold * (1.0 + bonus),
            token_discount=discount,
            liquidator_residual_margin=residual,
            liquidator_economically_incentivized=residual > 0.0,
            secondary_holder_can_redeem=bool(
                self.ledger.value(f"{prefix}.secondary_holder_can_redeem")
            ),
            debt_cap_usd=debt_cap,
            supply_cap_usd_at_liquidity_snapshot=snapshot_supply_cap_usd,
            current_marked_supply_cap_usd=current_marked_supply_cap_usd,
            disposal_capacity_within_bonus_usd=disposal_capacity,
            debt_cap_to_capacity=debt_cap / disposal_capacity,
            supply_cap_to_capacity=supply_tokens / disposal_capacity_tokens,
            supply_above_capacity_usd=max(
                0.0, snapshot_supply_cap_usd - disposal_capacity
            ),
            borrowing_token_itself_enabled=bool(
                self.ledger.value(f"{prefix}.borrowing_token_itself_enabled")
            ),
        )

    def run_all(self) -> CommodityScenarioSummary:
        return CommodityScenarioSummary(
            wti=self.wti_time_gap(),
            natural_gas=self.natural_gas_benchmark_gap(),
            gold=self.gold_hierarchy_gap(),
        )
