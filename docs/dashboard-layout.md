# Dashboard Layout Specification

## Layout Grid
- 12-column responsive grid, detachable widgets.
- Persistent user-specific layouts with profile presets.

## Core Widgets
1. **Scanner Widget**
   - Tabs: Indices, F&O universe, Top gainers/losers.
   - Filters: OI surge, IV spike, volume anomaly, momentum threshold.

2. **Signal Panel Widget**
   - Columns: symbol, strike, CE/PE, entry, stop loss, target, probability score, confidence.
   - Actions: one-click paper/live execution (plan-gated).

3. **Option Chain Widget**
   - Bid/ask, OI, OI delta, IV, Greeks heatmap.

4. **Execution Widget**
   - Order ticket with bracket/OCO support.
   - Mode banner: LIVE or PAPER (global lock protected).

5. **Portfolio Widget**
   - Net PnL, realized/unrealized, margin, Greeks aggregate, drawdown.

6. **AI Insights Widget**
   - Model version, feature contribution summary, confidence drift alert.

## Theming and UX
- Dark mode default.
- Accessibility-compliant contrast palette.
- Keyboard shortcuts for power users.
- Latency indicators per panel.
