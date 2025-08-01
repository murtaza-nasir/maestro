import logging
import os
from typing import Dict, Any

def setup_logging(log_level: str = "WARNING") -> None:
    """
    Configure logging to reduce verbosity and focus on important messages.
    
    Args:
        log_level: The minimum log level to display (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    
    # Get log level from environment or use provided default
    log_level = os.getenv("LOG_LEVEL", log_level).upper()
    
    # Convert string to logging level
    numeric_level = getattr(logging, log_level, logging.WARNING)
    
    # Configure root logger. This sets the default level for all loggers.
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # If the global log level is higher than DEBUG, we can selectively silence
    # noisy third-party libraries to focus on application-specific logs.
    # If the level is DEBUG, we let everything through for detailed debugging.
    if numeric_level > logging.DEBUG:
        # A list of loggers known for high verbosity
        noisy_libraries = [
            'httpx', 'httpcore', 'urllib3', 'requests', 'chromadb',
            'sentence_transformers', 'transformers', 'torch', 'numpy',
            'PIL', 'matplotlib', 'uvicorn', 'uvicorn.access', 'fastapi'
        ]
        for logger_name in noisy_libraries:
            logging.getLogger(logger_name).setLevel(logging.WARNING)

        # The model_dispatcher is exceptionally noisy with token counts.
        # We'll set it to ERROR to hide these messages unless in DEBUG mode.
        logging.getLogger('ai_researcher.agentic_layer.model_dispatcher').setLevel(logging.ERROR)
    
    # Create a custom filter to reduce repetitive messages
    class DuplicateFilter:
        def __init__(self):
            self.msgs = set()
        
        def filter(self, record):
            # Allow ERROR and CRITICAL messages through always
            if record.levelno >= logging.ERROR:
                return True
            
            # For other levels, filter duplicates
            msg = record.getMessage()
            if msg in self.msgs:
                return False
            self.msgs.add(msg)
            
            # Clear the set periodically to avoid memory issues
            if len(self.msgs) > 1000:
                self.msgs.clear()
            
            return True
    
    # Apply duplicate filter to root logger
    duplicate_filter = DuplicateFilter()
    logging.getLogger().addFilter(duplicate_filter)
    
    print(f"Logging configured with level: {log_level}")

def get_production_logging_config() -> Dict[str, Any]:
    """
    Get a production-ready logging configuration that minimizes noise.
    """
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
            'minimal': {
                'format': '%(levelname)s: %(message)s'
            }
        },
        'handlers': {
            'default': {
                'level': 'WARNING',
                'formatter': 'standard',
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stdout'
            }
        },
        'loggers': {
            '': {  # root logger
                'handlers': ['default'],
                'level': 'WARNING',
                'propagate': False
            },
            'uvicorn': {
                'handlers': ['default'],
                'level': 'WARNING',
                'propagate': False
            },
            'fastapi': {
                'handlers': ['default'],
                'level': 'WARNING',
                'propagate': False
            }
        }
    }
