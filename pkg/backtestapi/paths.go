package backtestapi

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func monthKey(date string) string {
	date = strings.TrimSpace(date)
	if len(date) >= 7 {
		return date[:7]
	}
	return date
}

// ResolveMarketPath finds parquet/csv for symbol+interval+date range.
func ResolveMarketPath(projectRoot string, req SubmitRequest) (string, error) {
	start := monthKey(req.StartDate)
	end := monthKey(req.EndDate)
	candidates := []string{
		fmt.Sprintf("data/%s-%s-%s_to_%s.parquet", req.Symbol, req.Interval, start, end),
		fmt.Sprintf("data/%s_%s.csv", req.Symbol, req.Interval),
		fmt.Sprintf("data/%s-%s.csv", req.Symbol, req.Interval),
		"data/BTCUSDT_5m.csv",
	}
	for _, rel := range candidates {
		full := filepath.Join(projectRoot, rel)
		if _, err := os.Stat(full); err == nil {
			return rel, nil
		}
	}
	return "", fmt.Errorf("no market data found for %s %s (%s to %s)", req.Symbol, req.Interval, start, end)
}

// ResolveStrategyConfig picks chanlun JSON config for the request.
func ResolveStrategyConfig(projectRoot string, req SubmitRequest) string {
	sym := strings.ToLower(strings.TrimSuffix(req.Symbol, "USDT"))
	candidates := []string{
		fmt.Sprintf("configs/chanlun_%s_%s.json", sym, req.Interval),
		fmt.Sprintf("configs/chanlun_%susdt_%s.json", sym, req.Interval),
		"configs/chanlun_pepe_5m.json",
		"configs/chanlun_btc.json",
	}
	for _, rel := range candidates {
		if _, err := os.Stat(filepath.Join(projectRoot, rel)); err == nil {
			return rel
		}
	}
	return "configs/chanlun_btc.json"
}
