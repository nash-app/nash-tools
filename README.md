# Tools Development Guide

## Getting started

```sh
# Install dependencies
poetry install

# Activate the tools environment
eval $(poetry env activate)
```

## Running Tools Locally

Run the tool:

```sh
PYTHONPATH=$PWD python app/tools/scripts/run_tool.py
```

## Creating New Tools

See [`template.py`](./template.py) for a reference implementation.

Follow the best practices defined in [`.cursor/rules`](./.cursor/rules).
