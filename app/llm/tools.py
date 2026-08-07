"""Tool calling definitions for the LLM — OpenAI function-calling format.

Available tools:
- save_activity_log: persist the generated activity
- get_user_stats: retrieve current user statistics
- apply_penalty: apply a penalty for an interrupted task
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_activity_log",
            "description": "Persist a generated activity. Call after suggesting a task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "UUID of the selected entity from the allowed list",
                    },
                    "entity_name": {
                        "type": "string",
                        "description": "Name of the selected entity",
                    },
                    "params": {
                        "type": "object",
                        "description": ("Parameters within the entity's params_schema ranges"),
                    },
                    "reasoning": {
                        "type": "string",
                        "description": ("Reasoning based on user history and preferences"),
                    },
                },
                "required": ["entity_id", "entity_name", "params", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_stats",
            "description": "Get current user statistics (XP, level, streaks, etc.)",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_penalty",
            "description": "Apply a penalty for an interrupted or skipped task",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity_log_id": {
                        "type": "string",
                        "description": "UUID of the activity log being penalized",
                    },
                    "penalty_type": {
                        "type": "string",
                        "enum": ["xp_deduction", "difficulty_increase", "extra_task"],
                        "description": "Type of penalty to apply",
                    },
                    "severity": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "description": "Penalty severity (1-5)",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for the penalty",
                    },
                },
                "required": ["activity_log_id", "penalty_type", "severity"],
            },
        },
    },
]
