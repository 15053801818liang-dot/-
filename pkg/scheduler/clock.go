package scheduler

import "time"

// Clock 时间源，便于测试注入。
type Clock interface {
	Now() time.Time
}

// RealClock 使用系统时钟。
type RealClock struct{}

func (RealClock) Now() time.Time { return time.Now() }

// MockClock 固定时间，测试用。
type MockClock struct {
	Current time.Time
}

func (c MockClock) Now() time.Time {
	if c.Current.IsZero() {
		return time.Unix(0, 0).UTC()
	}
	return c.Current
}
