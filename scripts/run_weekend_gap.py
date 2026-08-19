"""Run both weekend-gap reference models from the repository root."""

from rwa_market_gap.weekend_gap.baseline import main as run_baseline
from rwa_market_gap.weekend_gap.protocol import main as run_protocol_aware


if __name__ == "__main__":
    run_baseline()
    print("\n" + "=" * 72 + "\n")
    run_protocol_aware()
