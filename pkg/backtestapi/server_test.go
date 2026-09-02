package backtestapi

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func projectRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "tasks", "chanlun_backtest.py")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("project root not found")
		}
		dir = parent
	}
}

func TestBacktestAPIFlow(t *testing.T) {
	root := projectRoot(t)

	storeDir := t.TempDir()
	store, err := NewStore(storeDir)
	if err != nil {
		t.Fatal(err)
	}
	queue := NewQueue(store, &Runner{ProjectRoot: root}, 1)
	srv := NewServer(queue)
	mux := http.NewServeMux()
	srv.Register(mux)

	body := `{"symbol":"BTCUSDT","interval":"5m","start_date":"2024-01-01","end_date":"2024-01-02"}`
	req := httptest.NewRequest(http.MethodPost, "/api/backtest", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("submit status=%d body=%s", rec.Code, rec.Body.String())
	}
	var sub SubmitResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &sub); err != nil {
		t.Fatal(err)
	}
	if sub.TaskID == "" {
		t.Fatal("empty task_id")
	}

	deadline := time.Now().Add(30 * time.Second)
	for {
		if time.Now().After(deadline) {
			t.Fatal("timeout waiting for task completion")
		}
		stReq := httptest.NewRequest(http.MethodGet, "/api/backtest/"+sub.TaskID, nil)
		stRec := httptest.NewRecorder()
		mux.ServeHTTP(stRec, stReq)
		var st TaskStatus
		_ = json.Unmarshal(stRec.Body.Bytes(), &st)
		if st.Status == StatusCompleted || st.Status == StatusFailed {
			if st.Status == StatusFailed {
				t.Fatalf("task failed: %s", st.Error)
			}
			break
		}
		time.Sleep(200 * time.Millisecond)
	}

	repReq := httptest.NewRequest(http.MethodGet, "/api/report/"+sub.TaskID, nil)
	repRec := httptest.NewRecorder()
	mux.ServeHTTP(repRec, repReq)
	if repRec.Code != http.StatusOK {
		t.Fatalf("report status=%d body=%s", repRec.Code, repRec.Body.String())
	}
	var rep ReportResponse
	if err := json.Unmarshal(repRec.Body.Bytes(), &rep); err != nil {
		t.Fatal(err)
	}
	if rep.BiCount <= 0 {
		t.Fatalf("expected bi_count > 0, got %+v", rep)
	}
	if rep.RawReport == "" {
		t.Fatal("expected raw_report content")
	}
}

func TestValidateSubmit(t *testing.T) {
	if err := validateSubmit(SubmitRequest{}); err == nil {
		t.Fatal("expected error for empty request")
	}
}

func TestResolveMarketPathFallback(t *testing.T) {
	root := projectRoot(t)
	p, err := ResolveMarketPath(root, SubmitRequest{
		Symbol: "BTCUSDT", Interval: "5m",
		StartDate: "2024-01-01", EndDate: "2024-01-02",
	})
	if err != nil {
		t.Fatal(err)
	}
	if p == "" {
		t.Fatal("empty path")
	}
}
