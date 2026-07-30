class BuilderError(Exception):
   """A known, user-facing build failure.

   The command layer raises this (chained from the original exception) when a
   step fails, so cli.py can catch exactly this type once: print a one-line
   message and exit 1, or re-raise the full chain under --debug. Anything that
   is NOT a BuilderError is unexpected and always shows its full traceback.
   """
