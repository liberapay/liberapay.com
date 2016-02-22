
import aspen
from aspen.website import Website


aspen.logging.LOGGING_THRESHOLD = 2  # Hide Aspen's startup messages
website = Website()
aspen.logging.LOGGING_THRESHOLD = 0
