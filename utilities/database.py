import logging
from typing import List
from tortoise import Tortoise
from utilities.config import get_config

logger = logging.getLogger("template.database")


async def init_database(modules: List[str] = None):
    """
    Initializes the Tortoise ORM connection.

    Args:
        modules: A list of python modules (paths) that contain your Tortoise Models.
                 Example: ["cogs.economy.models", "cogs.leveling.models"]
    """
    config = get_config()

    # Default to an SQLite file in the root directory if not configured
    # You could add a 'database' section to your config.yaml for more control
    db_url = "sqlite://db.sqlite3"

    logger.info(f"Initializing database connection to {db_url}...")

    # If no modules are provided, we default to an empty list.
    # Users should pass the paths to their model files here.
    if modules is None:
        modules = []

    try:
        await Tortoise.init(
            db_url=db_url,
            modules={'models': modules}
        )
        # Generate the schema (create tables) if they don't exist
        await Tortoise.generate_schemas()
        logger.info("Database initialized and schemas generated successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        raise


async def close_database():
    """Closes the Tortoise ORM connection."""
    try:
        await Tortoise.close_connections()
        logger.info("Database connections closed.")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")