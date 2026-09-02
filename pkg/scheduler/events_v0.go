package scheduler

// NodeEventEmitter 节点状态变更事件接口。
type NodeEventEmitter interface {
	EmitReady(dagID, nodeID string)
	EmitRunning(dagID, nodeID string)
	EmitCompleted(dagID, nodeID, output string)
	EmitFailed(dagID, nodeID, errMsg string)
	EmitBlocked(dagID, nodeID, reason string)
	EmitSkipped(dagID, nodeID, reason string)
	EmitCancelled(dagID, nodeID, reason string)
}

// NoopNodeEventEmitter 默认空实现。
type NoopNodeEventEmitter struct{}

func (NoopNodeEventEmitter) EmitReady(string, string)                   {}
func (NoopNodeEventEmitter) EmitRunning(string, string)                 {}
func (NoopNodeEventEmitter) EmitCompleted(string, string, string)         {}
func (NoopNodeEventEmitter) EmitFailed(string, string, string)            {}
func (NoopNodeEventEmitter) EmitBlocked(string, string, string)           {}
func (NoopNodeEventEmitter) EmitSkipped(string, string, string)           {}
func (NoopNodeEventEmitter) EmitCancelled(string, string, string)         {}
