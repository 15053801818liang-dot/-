package scheduler

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

// TaskInput 传给 Python 任务的 JSON 输入。
type TaskInput struct {
	Params       map[string]interface{} `json:"params"`
	WorkspaceDir string                 `json:"workspace_dir"`
	DagID        string                 `json:"dag_id"`
	Artifacts    map[string]interface{} `json:"artifacts"`
}

// TaskOutput Python 任务 stdout JSON。
type TaskOutput struct {
	Status  string                 `json:"status"`
	Message string                 `json:"message"`
	Payload map[string]interface{} `json:"payload"`
}

// JSONExecutor 通过 stdin/stdout JSON 驱动 Python 任务。
type JSONExecutor struct {
	PythonPath  string
	ProjectRoot string
	Env         []string
}

func NewJSONExecutor(projectRoot string) *JSONExecutor {
	py := os.Getenv("PYTHON_PATH")
	if py == "" {
		py = "python3"
	}
	env := os.Environ()
	env = append(env, "PYTHONPATH="+projectRoot)
	return &JSONExecutor{
		PythonPath:  py,
		ProjectRoot: projectRoot,
		Env:         env,
	}
}

func (e *JSONExecutor) RunTask(scriptRel string, input TaskInput) (*TaskOutput, error) {
	script := filepath.Join(e.ProjectRoot, scriptRel)
	if _, err := os.Stat(script); err != nil {
		return nil, fmt.Errorf("task script missing %s: %w", script, err)
	}

	body, err := json.Marshal(input)
	if err != nil {
		return nil, err
	}

	cmd := exec.Command(e.PythonPath, script)
	cmd.Dir = e.ProjectRoot
	cmd.Env = e.Env
	cmd.Stdin = bytes.NewReader(body)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("task failed: %w stderr=%s", err, stderr.String())
	}

	var out TaskOutput
	if err := json.Unmarshal(stdout.Bytes(), &out); err != nil {
		return nil, fmt.Errorf("invalid task json stdout=%s err=%w", stdout.String(), err)
	}
	if out.Status != "success" {
		return &out, fmt.Errorf("task status=%s message=%s", out.Status, out.Message)
	}
	return &out, nil
}

// Execute 实现 Executor 接口，调用节点 Script。
func (e *JSONExecutor) Execute(ctx context.Context, inst *DAGInstance, nodeID string) (string, error) {
	node, ok := inst.Spec.Nodes[nodeID]
	if !ok {
		return "", fmt.Errorf("node %s not found", nodeID)
	}
	if node.Script == "" {
		return "", fmt.Errorf("node %s has no script", nodeID)
	}
	input := TaskInput{
		Params: node.Params,
		DagID:  inst.ID,
	}
	out, err := e.RunTask(node.Script, input)
	if err != nil {
		return "", err
	}
	_ = ctx
	return out.Message, nil
}
