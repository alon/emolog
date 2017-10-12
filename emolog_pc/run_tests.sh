#!/bin/bash
export PYTHONPATH=.
py.test --ignore=venv --ignore=dwarf --ignore=experiments $@
