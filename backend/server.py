#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility entrypoint for the backend web server."""

from app.service import app, main

__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
