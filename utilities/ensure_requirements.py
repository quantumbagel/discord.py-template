import logging
import os
import subprocess
import sys

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("template.requirements")


def run_command(command: list) -> bool:
    """
    Executes a command using the current Python interpreter's pip.

    Args:
        command (list): The command to run as a list of strings.

    Returns:
        bool: True if the command was successful, False otherwise.
    """
    try:
        # Use sys.executable to ensure we're using the pip from the correct Python env
        result = subprocess.run(
            [sys.executable, "-m"] + command,
            check=True,  # Raises CalledProcessError if command returns a non-zero exit code
            capture_output=True,
            text=True,  # Captures output as a string
            encoding='utf-8'
        )
        if result.stdout:
            logger.info(result.stdout)
        if result.stderr:
            # pip often uses stderr for warnings or notices, so we'll print it
            logger.info(f"Notices/Warnings:\n{result.stderr}")
        return True
    except FileNotFoundError:
        logger.info(f"Command not found. Is '{sys.executable}' a valid Python interpreter?")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Error executing: {' '.join(command)}")
        logger.error(f"STDERR:\n{e.stderr}")
        return False


def update_pip() -> bool:
    """
    Updates pip to the latest version.
    :return:
    """
    logger.info("Updating pip...")
    command = ["pip", "install", "--upgrade", "pip"]
    return run_command(command)


def install_requirements(filename: str) -> bool:
    """
    Install packages from a template_requirements.txt file.
    :param filename: the filename of the template_requirements.txt file
    :return: Nothing
    """
    if not os.path.exists(filename):
        logger.warning(f"Could not find requirements file '{filename}'. Skipping package installation.")
        return False

    command = ["pip", "install", "-r", filename]
    return run_command(command)


def ensure_requirements():
    update_pip()
    requirement_files = ["template_requirements.txt", "bot_requirements.txt"]
    success = True
    for requirement_file in requirement_files:
        logger.info(f"Installing packages from {requirement_file}...")
        if not install_requirements(requirement_file):
            logger.warning(f"Could not install packages from {requirement_file}. We will still try to run the bot.")
            success = False
    if success:
        logger.info("Requirements are satisfied.")
    return success
