"""Task base class — stdin/stdout JSON protocol"""
import sys
import json
import traceback


class TaskBase:
    def run(self, workspace: dict, spec: dict) -> dict:
        raise NotImplementedError

    def execute(self):
        try:
            raw = sys.stdin.read()
            if not raw:
                raise ValueError("no input on stdin")
            input_data = json.loads(raw)
            workspace = input_data.get("workspace", {})
            spec = input_data.get("spec", {})
            payload = self.run(workspace, spec)
            output = {"status": "success", "message": "done", "payload": payload}
        except Exception as e:
            output = {"status": "failed", "message": str(e), "payload": {"traceback": traceback.format_exc()}}
        sys.stdout.write(json.dumps(output, ensure_ascii=False))
