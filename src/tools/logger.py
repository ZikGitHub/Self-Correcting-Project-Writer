import logging
import sys
from src.tools.sse_handler import SSEHandler

def setup_logger(name: str = "project_writer"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # File handler
    fh = logging.FileHandler("app.log")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    # SSE Handler
    sse = SSEHandler()
    sse.setFormatter(formatter)
    logger.addHandler(sse)
    
    return logger

logger = setup_logger()
