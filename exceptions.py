from fastapi import HTTPException

class StrategyNotFoundException(HTTPException):
    def __init__(self, strategy_id: int):
        super().__init__(status_code=404, detail=f"Strategy with ID {strategy_id} not found.")

class StrategyAlreadyRunningException(HTTPException):
    def __init__(self, strategy_id: int, status: str):
        super().__init__(status_code=400, detail=f"Strategy with ID {strategy_id} is already {status}.")

class StrategyCodeMissingException(HTTPException):
    def __init__(self):
        super().__init__(status_code=400, detail="Strategy name and code are required.")

class StrategyNameExistsException(HTTPException):
    def __init__(self, strategy_name: str):
        super().__init__(status_code=409, detail=f"Strategy name '{strategy_name}' already exists. Please choose a different name.")

class DataNotFoundException(HTTPException):
    def __init__(self, detail: str = "No data found for the given parameters."):
        super().__init__(status_code=404, detail=detail)

class InvalidDateFormatException(HTTPException):
    def __init__(self, detail: str = "Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS."):
        super().__init__(status_code=400, detail=detail)

class BacktestFailedException(HTTPException):
    def __init__(self, detail: str = "Backtest failed due to an unknown error."):
        super().__init__(status_code=500, detail=detail)

class MissingSignalFunctionException(HTTPException):
    def __init__(self):
        super().__init__(status_code=400, detail="Strategy code must contain a 'generate_signal' function.")
