from pydantic import BaseModel, Field
from typing import Dict, Any # Import Dict and Any
import math
import operator

# Define the input schema
class CalculatorInput(BaseModel):
    expression: str = Field(..., description="The mathematical expression to evaluate (e.g., '5 * (3 + 2)^2'). Supports basic arithmetic (+, -, *, /, **) and common math functions (sqrt, pow, sin, cos, tan, log, log10).")

# Limited set of allowed operations and functions for safety
ALLOWED_NAMES = {
    "sqrt": math.sqrt,
    "pow": math.pow,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "pi": math.pi,
    "e": math.e,
    # Basic operators are handled by eval, but could be explicitly listed if using a safer parser
}

class CalculatorTool:
    """
    A tool for performing mathematical calculations. Uses a safer eval approach.
    """
    def __init__(self):
        self.name = "calculator"
        self.description = "Evaluates mathematical expressions. Supports basic arithmetic (+, -, *, /, **) and functions like sqrt, pow, sin, cos, tan, log, log10."
        self.parameters_schema = CalculatorInput
        print("CalculatorTool initialized.")

    def _safe_eval(self, expression: str):
        """Safely evaluates a mathematical expression."""
        # Compile the expression to check for disallowed syntax early
        try:
            code = compile(expression, "<string>", "eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid syntax in expression: {e}")

        # Validate names used in the expression
        for name in code.co_names:
            if name not in ALLOWED_NAMES:
                raise NameError(f"Use of disallowed name '{name}' in expression")

        # Evaluate using the allowed names only
        try:
            # Provide only allowed names in the globals/locals for eval
            result = eval(code, {"__builtins__": {}}, ALLOWED_NAMES)
            # Check result type - should be numeric
            if not isinstance(result, (int, float)):
                 raise TypeError(f"Calculation result is not a number: {type(result)}")
            return result
        except Exception as e:
            # Catch potential runtime errors during evaluation
            raise ValueError(f"Error during calculation: {e}")


    def execute(self, expression: str) -> Dict[str, Any]:
        """
        Executes the calculation.

        Args:
            expression: The mathematical expression string.

        Returns:
            A dictionary containing the result or an error message.
        """
        print(f"Executing Calculator Tool with expression: '{expression}'")
        try:
            result = self._safe_eval(expression)
            print(f"Calculation result: {result}")
            return {"result": result}
        except (ValueError, NameError, TypeError, Exception) as e:
            print(f"Calculation failed: {e}")
            return {"error": str(e)}
