import logging
import queue

# Shared queue for backward compatibility
log_queue = queue.Queue()

# Persistent log history for the current run
log_history = []

# List of active client queues
active_clients = []

def clear_log_history():
    global log_history
    log_history = []
    # Clear backward compatibility queue
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except Exception:
            break

def add_log(msg):
    log_history.append(msg)
    log_queue.put(msg)
    for q in list(active_clients):
        try:
            q.put_nowait(msg)
        except Exception:
            pass

class SSEHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            add_log(msg)
        except Exception:
            self.handleError(record)
