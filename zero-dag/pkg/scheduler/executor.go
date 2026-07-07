package scheduler

import "context"

type Executor interface {
	Execute(ctx context.Context, nodeID string, params map[string]interface{}, workspace string) (string, error)
}

type PythonExecutor struct {
	PythonPath string
	TaskDir    string
}

func NewPythonExecutor(pythonPath, taskDir string) *PythonExecutor {
	return &PythonExecutor{PythonPath: pythonPath, TaskDir: taskDir}
}

func (e *PythonExecutor) Execute(ctx context.Context, nodeID string, params map[string]interface{}, workspace string) (string, error) {
	// Execute Python task node
	// In production: spawn python subprocess with task script
	return "", nil
}
