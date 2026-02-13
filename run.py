#!/usr/bin/env python3
"""
FORRASPY — Launcher
Execute: python run.py
"""
import sys
import os

# Adiciona o diretório do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot import main

if __name__ == "__main__":
    main()
