#!/bin/sh

uv run uvicorn app.main:app --port 5000 --reload
