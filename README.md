# Tools Development Guide

## Getting started

```sh
# Install dependencies
poetry install

# Activate the tools environment
eval $(poetry env activate)
```

## Running Tools Locally

To test the tool, run the file itself to use its main block.

```sh
python tools/<dirname>/<filename>.py
```

## Creating New Tools

See [`template.py`](./template.py) for a reference implementation.

Follow the best practices defined in [`.cursor/rules`](./.cursor/rules).
