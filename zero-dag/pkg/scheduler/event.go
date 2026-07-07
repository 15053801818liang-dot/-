package scheduler

import "time"

type EventBus struct {
	nodeSubs []chan NodeEvent
	dagSubs  []chan DAGEvent
}

func NewEventBus() *EventBus {
	return &EventBus{
		nodeSubs: make([]chan NodeEvent, 0),
		dagSubs:  make([]chan DAGEvent, 0),
	}
}

func (e *EventBus) SubscribeNode() <-chan NodeEvent {
	ch := make(chan NodeEvent, 64)
	e.nodeSubs = append(e.nodeSubs, ch)
	return ch
}

func (e *EventBus) SubscribeDAG() <-chan DAGEvent {
	ch := make(chan DAGEvent, 64)
	e.dagSubs = append(e.dagSubs, ch)
	return ch
}

func (e *EventBus) EmitNode(ev NodeEvent) {
	for _, ch := range e.nodeSubs {
		select {
		case ch <- ev:
		default:
		}
	}
}

func (e *EventBus) EmitDAG(ev DAGEvent) {
	for _, ch := range e.dagSubs {
		select {
		case ch <- ev:
		default:
		}
	}
}

type NodeEventSource struct {
	bus *EventBus
}

func NewNodeEventSource(bus *EventBus) *NodeEventSource {
	return &NodeEventSource{bus: bus}
}

func (n *NodeEventSource) Emit(nodeID, dagID string, from, to NodeStatus) {
	n.bus.EmitNode(NodeEvent{
		NodeID:    nodeID,
		DAGID:     dagID,
		From:      from,
		To:        to,
		Timestamp: time.Now(),
	})
}

type DAGEventSource struct {
	bus *EventBus
}

func NewDAGEventSource(bus *EventBus) *DAGEventSource {
	return &DAGEventSource{bus: bus}
}

func (d *DAGEventSource) Emit(dagID string, from, to InstanceStatus) {
	d.bus.EmitDAG(DAGEvent{
		DAGID:     dagID,
		From:      from,
		To:        to,
		Timestamp: time.Now(),
	})
}
