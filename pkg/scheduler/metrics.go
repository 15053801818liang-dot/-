package scheduler

import (
	"os"
	"strconv"
	"strings"
	"time"
)

// RunMetrics 调度执行性能指标。
type RunMetrics struct {
	ElapsedSec float64
	RSSMB      float64
}

func readRSSMB() float64 {
	data, err := os.ReadFile("/proc/self/status")
	if err != nil {
		return 0
	}
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "VmRSS:") {
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				kb, err := strconv.ParseFloat(fields[1], 64)
				if err == nil {
					return kb / 1024.0
				}
			}
		}
	}
	return 0
}

func StartRunMetrics() (func() RunMetrics, time.Time) {
	start := time.Now()
	return func() RunMetrics {
		return RunMetrics{
			ElapsedSec: time.Since(start).Seconds(),
			RSSMB:      readRSSMB(),
		}
	}, start
}
