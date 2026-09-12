import type { BacktestJobSubmitPayload } from "../../api/client";
import type { VerificationMode } from "./VerificationModeControl";

type Inputs = {
  mode: VerificationMode;
  symbol: string;
  market: string;
  start: string;
  end: string;
  dataTimeframe: string;
  strategy: string;
  strategyContext: Record<string, unknown>;
  tradeCapital: number;
  modelAllocation: number;
  dataVersionId: string;
  currency: string;
  verifiedQuantity: number;
  adjustedSeries: boolean;
  executionProfile: {
    commission_bps: number;
    slippage_model: string;
    slippage_bps: number;
    spread_bps: number;
    market_impact_bps: number;
    volume_cap_pct: number;
  };
};

const finite = (value: unknown, fallback = 0): number => Number.isFinite(Number(value)) ? Number(value) : fallback;

export function buildBacktestSubmitPayload(inputs: Inputs): BacktestJobSubmitPayload {
  const common = {
    symbol: inputs.symbol,
    asset: inputs.symbol,
    market: inputs.market,
    start: inputs.start,
    end: inputs.end,
    strategy: inputs.strategy,
  };
  if (inputs.mode === "VERIFIED") {
    return {
      ...common,
      timeframe: "1d",
      verification_level: "VERIFIED",
      data_version_id: inputs.dataVersionId,
      currency: inputs.currency,
      context: { ...inputs.strategyContext, quantity: finite(inputs.verifiedQuantity, 1) },
      config: {
        initial_cash: finite(inputs.tradeCapital, 100000),
        fee_bps: finite(inputs.executionProfile.commission_bps, 0),
        slippage_bps: finite(inputs.executionProfile.slippage_bps, 0),
      },
    };
  }
  return {
    ...common,
    timeframe: inputs.dataTimeframe,
    verification_level: "RESEARCH",
    context: inputs.strategyContext,
    config: {
      initial_cash: finite(inputs.tradeCapital, 100000),
      position_fraction: inputs.modelAllocation,
      data_version_id: inputs.dataVersionId || undefined,
      adjusted: inputs.adjustedSeries,
      execution_profile: {
        commission_bps: finite(inputs.executionProfile.commission_bps, 0),
        slippage_model: inputs.executionProfile.slippage_model,
        slippage_bps: finite(inputs.executionProfile.slippage_bps, 0),
        spread_bps: finite(inputs.executionProfile.spread_bps, 0),
        market_impact_bps: finite(inputs.executionProfile.market_impact_bps, 0),
        volume_cap_pct: finite(inputs.executionProfile.volume_cap_pct, 10),
      },
    },
  };
}

const VERIFIED_ERRORS: Record<string, string> = {
  DATA_VERSION_REQUIRED: "Select a persisted data version before running a verified backtest.",
  DATA_VERSION_NOT_FOUND: "The selected data version no longer exists.",
  INSTRUMENT_DATA_NOT_FOUND: "No persisted history matches this instrument and data version.",
  VERIFIED_DATA_MISSING: "Required persisted observations are missing for this verified range.",
  UNSUPPORTED_VERIFIED_TIMEFRAME: "Verified execution currently supports daily bars only.",
  UNSUPPORTED_VERIFIED_CONFIG: "One or more execution settings are not supported in verified mode.",
  UNSUPPORTED_VERIFIED_VENUE: "The selected venue is not supported for verified execution.",
};

export function explainVerifiedError(message: string): string {
  const code = Object.keys(VERIFIED_ERRORS).find((candidate) => message.includes(candidate));
  return code ? `${code}: ${VERIFIED_ERRORS[code]}` : message;
}
