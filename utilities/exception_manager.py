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

        # Pretty-print all local variables, expanding objects one level
        try:
            expanded_locals = {}
            for var_name, var_value in frame.f_locals.items():

                # Check for a default, unhelpful repr string
                repr_str = repr(var_value)
                is_default_object = repr_str.startswith('<') and 'object at 0x' in repr_str

                # If it's an object and has a __dict__, expand it
                if is_default_object and hasattr(var_value, '__dict__'):
                    expanded_locals[var_name] = {
                        '__type__': str(type(var_value)),
                        '__dict__': var_value.__dict__
                    }
                else:
                    # It's a simple type (int, str) or has a good repr
                    expanded_locals[var_name] = var_value  # Use the original value

            # Now, pprint the *new* dictionary
            variable_state_str += pprint.pformat(expanded_locals, indent=2, width=120)

        except Exception as e:
            variable_state_str += f"  [Could not format locals: {e}]\n"
        variable_state_str += "\n"

        # Move to the next frame up the stack
        current_tb = current_tb.tb_next

    # 5. Write everything to the log file
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