import datetime
import logging
import os
import pprint
import traceback

logger = logging.getLogger("template.exception_manager")

def create_detailed_error_log(log_dir, command_name, exc_type, exc_value, tb):
    """
    Catches an exception and logs it to a unique file with
    a full traceback and variable state.
    """

    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(log_dir, f"error_{timestamp}.log")

    tb_lines = traceback.format_exception(exc_type, exc_value, tb)
    traceback_str = "".join(tb_lines)

    variable_state_str = f"Error at {timestamp} in command {command_name}, \n--- VARIABLE STATE (FULL STACK) ---\n"
    current_tb = tb
    while current_tb:
        frame = current_tb.tb_frame

        # Get frame details
        filename = frame.f_code.co_filename
        func_name = frame.f_code.co_name
        line_no = frame.f_lineno

        variable_state_str += (
            f"\n--- Frame: {func_name} in {filename} at line {line_no} ---\n"
        )

        # Function to format variables, expanding objects one level
        def format_vars(var_dict):
            formatted_vars = {}
            for var_name, var_value in var_dict.items():
                # Avoid logging sensitive data

                repr_str = repr(var_value)
                is_default_object = repr_str.startswith('<') and 'object at 0x' in repr_str

                if is_default_object and hasattr(var_value, '__dict__'):
                    formatted_vars[var_name] = {
                        '__type__': str(type(var_value)),
                        '__dict__': {k: (v if not any(keyword in k.lower() for keyword in ['token', 'password', 'secret']) else "********") for k, v in var_value.__dict__.items()}
                    }
                else:
                    formatted_vars[var_name] = var_value
            return formatted_vars

        # Pretty-print locals
        try:
            variable_state_str += "\n--- Locals ---\n"
            formatted_locals = format_vars(frame.f_locals)
            variable_state_str += pprint.pformat(formatted_locals, indent=2, width=120)
        except Exception as e:
            variable_state_str += f"  [Could not format locals: {e}]\n"

        # Pretty-print globals
        try:
            variable_state_str += "\n\n--- Globals ---\n"
            formatted_globals = format_vars(frame.f_globals)
            variable_state_str += pprint.pformat(formatted_globals, indent=2, width=120)
        except Exception as e:
            variable_state_str += f"  [Could not format globals: {e}]\n"

        variable_state_str += "\n"

        # Move to the next frame up the stack
        current_tb = current_tb.tb_next

    # Write everything to the log file
    try:
        with open(log_file, "w") as f:
            f.write("--- UNCAUGHT EXCEPTION LOG ---\n\n")
            f.write(traceback_str)
            f.write("\n")
            f.write(variable_state_str)

        logger.error(f"Uncaught exception. Detailed log saved to: {log_file}")
        return log_file

    except Exception as e:
        logger.warning(f"Error writing to log file: {e}")
        logger.warning(f"Original traceback:\n{traceback_str}")
        logger.warning(f"Variable state:\n{variable_state_str}")
        return None