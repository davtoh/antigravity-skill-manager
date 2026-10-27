param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)
python "C:\src\skill-manager\skill_manager.py" @ScriptArgs
