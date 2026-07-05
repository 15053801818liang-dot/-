package scheduler

import "time"

// Clock 时间源，便于测试注入。
type Clock interface {
	Now() time.Time
}

// RealClock 使用系统时钟。
type RealClock struct{}

func (RealClock) Now() time.Time { return time.Now() }
