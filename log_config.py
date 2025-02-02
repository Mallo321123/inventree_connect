import os
import logging
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
from queue import Queue
from pathlib import Path

LOG_DIR = "logs"
LOGGING_LEVEL = logging.DEBUG
LOG_FORMAT = "%(asctime)s - %(threadName)s - %(name)s - %(levelname)s - %(message)s"
MAX_BYTES = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 3

def setup_logging():
    """Configure and return a logger instance with queue-based handlers for thread-safety."""
    try:
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
        
        logger = logging.getLogger('Inventree_connect')
        logger.setLevel(LOGGING_LEVEL)
        
        if not logger.handlers:
            # Create handlers
            log_file = os.path.join(LOG_DIR, "inventree_connect.log")
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT,
                encoding='utf-8'
            )
            console_handler = logging.StreamHandler()
            
            # Set levels
            file_handler.setLevel(LOGGING_LEVEL)
            console_handler.setLevel(LOGGING_LEVEL)
            
            # Create formatter with thread information
            formatter = logging.Formatter(LOG_FORMAT)
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            # Setup queue
            log_queue = Queue()
            queue_handler = QueueHandler(log_queue)
            logger.addHandler(queue_handler)
            
            # Start queue listener
            listener = QueueListener(
                log_queue,
                file_handler,
                console_handler,
                respect_handler_level=True
            )
            listener.start()
            
        return logger
    
    except Exception as e:
        print(f"Failed to setup logging: {e}")
        raise

