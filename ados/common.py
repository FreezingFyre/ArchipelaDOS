# Thrown to send a particular error message to the user through Discord.
class ADOSError(Exception):
    pass


class Color:
    RESET = "\u001b[0m"
    GRAY = "\u001b[0;30m"
    RED = "\u001b[0;31m"
    GREEN = "\u001b[0;32m"
    YELLOW = "\u001b[0;33m"
    BLUE = "\u001b[0;34m"
    PINK = "\u001b[0;35m"
    CYAN = "\u001b[0;36m"
    WHITE = "\u001b[0;37m"
