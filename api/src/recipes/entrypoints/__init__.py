"""Ways in to the app: the command line now, the FastAPI app later.

Entry points stay thin. They read input, call the core modules in `recipes`, and
report the result. Core modules never import from here.
"""
