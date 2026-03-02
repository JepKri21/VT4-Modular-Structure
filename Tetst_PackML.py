import time
import threading
from enum import Enum

#It does not run in threads or anything like that, so sending a stop command while executing does nothing

# -----------------------------
# PackML States
# -----------------------------
class State(Enum):
    IDLE = "Idle"
    STARTING = "Starting"
    EXECUTE = "Execute"
    STOPPING = "Stopping"
    STOPPED = "Stopped"
    ABORTED = "Aborted"
    CLEARING = "Clearing"
    COMPLETING = "Completing"


# -----------------------------
# Drilling Station
# -----------------------------
class DrillingStation:
    def __init__(self, drill_depth_mm: float):
        self.state = State.IDLE
        self.depth = drill_depth_mm
        self.mm_per_second = 5.0
        self.running = True
        self.lock = threading.Lock()

        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()

    def set_state(self, new_state):
        with self.lock:
            self.state = new_state
            print(f"[STATE] -> {self.state.value}")

    def _loop(self):
        while self.running:
            state = self.state

            if state == State.STARTING:
                print("[ACTION] Spindle starting...")
                time.sleep(1)
                self.set_state(State.EXECUTE)

            elif state == State.EXECUTE:
                duration = self.depth / self.mm_per_second
                print(f"[ACTION] Drilling {self.depth} mm ({duration:.1f}s)")
                time.sleep(duration)
                self.set_state(State.COMPLETING)

            elif state == State.COMPLETING:
                print("[ACTION] Retracting drill...")
                time.sleep(1)
                self.set_state(State.IDLE)

            elif state == State.STOPPING:
                print("[ACTION] Controlled stop")
                time.sleep(1)
                self.set_state(State.STOPPED)

            elif state == State.CLEARING:
                print("[ACTION] Clearing fault...")
                time.sleep(1)
                self.set_state(State.IDLE)

            time.sleep(0.1)

    # -------------------------
    # PackML Commands
    # -------------------------
    def start(self):
        if self.state == State.IDLE:
            self.set_state(State.STARTING)

    def stop(self):
        if self.state in (State.STARTING, State.EXECUTE):
            self.set_state(State.STOPPING)

    def abort(self):
        self.set_state(State.ABORTED)

    def clear(self):
        if self.state == State.ABORTED:
            self.set_state(State.CLEARING)

    def reset(self):
        if self.state in (State.STOPPED, State.COMPLETING):
            self.set_state(State.IDLE)

    def shutdown(self):
        self.running = False


# -----------------------------
# Terminal UI
# -----------------------------
def main():
    depth = float(input("Enter drill depth (mm): "))
    station = DrillingStation(depth)

    print("\nCommands:")
    print(" start | stop | abort | clear | reset | exit\n")

    while True:
        cmd = input("> ").strip().lower()

        if cmd == "exit":
            station.shutdown()
            break

        {
            "start": station.start,
            "stop": station.stop,
            "abort": station.abort,
            "clear": station.clear,
            "reset": station.reset,
        }.get(cmd, lambda: print("Unknown command"))()


if __name__ == "__main__":
    main()