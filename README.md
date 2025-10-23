# QuantumBagel's Discord.py Bot Template

A template for building modern Discord.py bots (v2.0+). 

  * Logs to both the console and timestamped files (`/logs/run_YYYY-MM-DD_HH-MM-SS.log`)
  * All settings—including bot token, cog lists, logging levels, and embed styles—are managed via external YAML config file.
  * Includes a comprehensive `Management` cog for controlling the bot:
      * Dynamic cog loading, unloading, and reloading.
      * Safely reloads cogs and *automatically rolls back* to the original state if the new code fails to load. (this literally took hours to implement)
      * Commands to sync, reset, and list slash commands (app commands) globally or for specific guilds.
      * Intelligent cog finding with fuzzy matching and suggestions.
      * Secure, owner-only `eval` command for live debugging.
  * Error handling
      * A global `on_command_error` handler that gracefully catches permissions errors, missing arguments, and command crashes so you don't have to 😎.
    Automatically generates a detailed, separate log file for *each* command crash, and also saves it to the logging folder.
  *  A standardized system (`embeds.py`) for creating consistent `Success`, `Error`, `Info`, `Warning`, and `Loading` embeds, while still exposing the underlying `discord.py` API.
  * Convenience functions
      * standardized `helpers.send` and `helpers.edit` function that intelligently handles responses for both `commands.Context` (prefix commands) and `discord.Interaction` (slash commands).
      * `ensure_requirements.py` script automatically installs/updates dependencies from `requirements.txt` on startup.

## Set up the template

### 1\. Prerequisites

  * Python 3.10 or newer

### 2\. Installation

1.  Clone the repository:

    ```bash
    git clone https://github.com/quantumbagel/discord.py-template.git
    cd "discord.py-template"
    ```

2.  Create a virtual environment (Highly recommended because the program will autoinstall dependencies when run):

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

### 3\. Configuration

This template is driven by a `config.yaml` file. You will need to create this file.

Here is an example `config.yaml`:

```yaml
# Bot authentication token
auth: "YOUR_BOT_TOKEN_HERE"

# Bot logging settings
logging:
  console_level: "info"     # Level for console output (debug, info, warning, error)
  output_level: "debug"     # Level for file output
  output_folder: "logs"     # Folder to store log files. If not set, NO LOGS will be saved

# List of cogs to load at startup
# The bot will iterate this list and load each cog.
cogs:
  - cogs.management:  # It is highly recommended not to disable the Management cog, but you can if you like.
      class: Management
      enabled: true
  - cogs.my_first_cog:
      class: MyFirstCog
      enabled: true
  - cogs.my_disabled_cog:
      class: MyDisabledCog
      enabled: false

# emoji configuration and embed function coming soon
```

### 4\. Run the Bot

Once your `config.yaml` is set up with your token, you can run the bot:

```bash
python main.py
```

## Project Structure

```
.
├── cogs/
│   ├── base.py           # Home of the `ImprovedCog` base class
│   └── management.py     # Built-in administrative cog
├── config/
│   └── config.yaml       # (You create this) Main configuration file
├── logs/
│   └── ...               # Log files are generated here
├── utilities/
│   ├── config.py         # Configuration loader
│   ├── embeds.py         # Class-based embed templates
│   ├── exception_manager.py # Creates detailed error logs
│   ├── formatter.py      # Custom log formatters (console & file)
│   ├── helpers.py        # `send()`, `edit()`, and `edit_or_send()`
│   └── ensure_requirements.py # Auto-installer for dependencies
├── main.py               # Main bot entry point (loads cogs, global error handler)
├── bot_requirements.txt  # Project dependencies that you set
├── template_requirements.txt # Dependencies the template needs to function (don't change this)
└── README.md             # This file
```

## The Management Cog

This template comes with a powerful management cog that is only usable by the owner(s) of the bot. It allows for hot-reloading of cogs and command tree syncing without stopping your bot from running.

**Default Prefix:** `!`
**Cog Alias:** `m` (e.g., `!m cog list`)

### Cog Commands

  * `!m cog list` (or `ls`): Lists all cogs from the config and their current load status.
  * `!m cog load <cog_name>`: Loads a cog.
  * `!m cog unload <cog_name>`: Unloads a cog.
  * `!m cog reload <cog_name>`: Reloads a cog. **If the reload fails, the bot will automatically roll back and restore the original, working cog.**

### Command Tree (Slash Commands)

  * `!m tree sync [guild_id]`: Syncs the command tree. No ID syncs globally (can take up to 1 hour). A guild ID syncs for one server (instant).
  * `!m tree reset [guild_id]`: Clears all commands and re-syncs.
  * `!m tree list`: Lists all registered slash commands, grouped by cog.

### Debugging

  * `!m help`: A built-in help command for the management cog.
