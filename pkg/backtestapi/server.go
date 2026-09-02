package backtestapi

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strings"
)

// Server HTTP handlers for backtest API.
type Server struct {
	queue *Queue
}

func NewServer(queue *Queue) *Server {
	return &Server{queue: queue}
}

func (s *Server) Register(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/backtest", s.handleSubmit)
	mux.HandleFunc("GET /api/backtest/{id}", s.handleStatus)
	mux.HandleFunc("GET /api/report/{id}", s.handleReport)
	mux.HandleFunc("GET /health", s.handleHealth)
}

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok"))
}

func (s *Server) handleSubmit(w http.ResponseWriter, r *http.Request) {
	var req SubmitRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}
	if err := validateSubmit(req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	taskID, err := newTaskID()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	task := &Task{
		ID:      taskID,
		Request: req,
	}
	if err := s.queue.Submit(task); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusAccepted, SubmitResponse{TaskID: taskID, Status: StatusSubmitted})
}

func (s *Server) handleStatus(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	task, ok := s.queue.store.Get(id)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "task not found"})
		return
	}
	writeJSON(w, http.StatusOK, s.queue.StatusView(task))
}

func (s *Server) handleReport(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	task, ok := s.queue.store.Get(id)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "task not found"})
		return
	}
	if task.Status != StatusCompleted || task.Report == nil {
		writeJSON(w, http.StatusConflict, map[string]string{
			"error":  "report not ready",
			"status": task.Status,
		})
		return
	}
	writeJSON(w, http.StatusOK, task.Report)
}

func validateSubmit(req SubmitRequest) error {
	req.Symbol = strings.TrimSpace(req.Symbol)
	req.Interval = strings.TrimSpace(req.Interval)
	if req.Symbol == "" {
		return errString("symbol is required")
	}
	if req.Interval == "" {
		return errString("interval is required")
	}
	if req.StartDate == "" || req.EndDate == "" {
		return errString("start_date and end_date are required")
	}
	return nil
}

type errString string

func (e errString) Error() string { return string(e) }

func writeJSON(w http.ResponseWriter, code int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func newTaskID() (string, error) {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}
