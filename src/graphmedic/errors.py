"""Error codes and exit statuses.

Exit codes:
0  lint completed and no finding met the fail threshold
1  lint completed and a finding met the fail threshold
2  invalid configuration or malformed input
3  the file's host format has no verified adapter
4  an internal exception escaped a rule or report writer
"""


class GraphMedicError(Exception):
    code = "GM-INTERNAL-001"
    exit_code = 4

    def __init__(self, message: str, *, code: str | None = None, exit_code: int | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code
        if exit_code is not None:
            self.exit_code = exit_code


class InputError(GraphMedicError):
    code = "GM-INPUT-001"
    exit_code = 2


class ConfigError(GraphMedicError):
    code = "GM-CONFIG-001"
    exit_code = 2


class UnsupportedFormatError(GraphMedicError):
    code = "GM-INPUT-003"
    exit_code = 3
